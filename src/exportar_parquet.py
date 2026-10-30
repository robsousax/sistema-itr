"""
Exportação para o Power BI (Etapa 11): modelo estrela em arquivos Parquet, em exportacao/.

O Power BI não recalcula a contabilidade. Ele lê o que o motor já calculou, trimestre a trimestre,
e só agrega. Por isso cada linha das demonstrações diz como deve ser agregada:

    soma      linhas de fluxo (DRE, DRA, DFC, DVA): 1T26 + 2T26 + 3T26 = 9M26
    ultimo    saldos (BP e saldo final de caixa): o 9M26 é o saldo do último trimestre
    primeiro  saldo inicial de caixa da DFC: o 9M26 é o saldo do primeiro trimestre

Essa regra é a medida "semiaditiva" do DAX (docs/11_power_bi.md).

Tabelas:
    dim_calendario, dim_conta, dim_evento, dim_linha, dim_indicador
    fato_lancamento     um registro por partida, com o saldo de abertura como movimento em 31/12/2024
    fato_demonstracao   valor de cada linha em cada trimestre (BP, DRE, DRA, DFC, DVA e EBITDA)
    fato_indicador      os 21 indicadores da Etapa 8 por trimestre
    fato_qualidade      as 20 verificações da Central que liberou a exportação

Uso:
    python src/exportar_parquet.py
"""
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from checar_config import carregar
from demonstracoes import BASE_PADRAO, RAIZ, balanco, linhas_da, resultado
from dfc_dmpl import dfc
from dra_dva import dra, dva
from indicadores import INDICADORES, TRIMESTRES, datas_do_trimestre, ebitda, serie
from qualidade import exigir_liberacao

EXPORTACAO = RAIZ / "exportacao"
ABERTURA = date(2024, 12, 31)
TRIMESTRE_ITR = TRIMESTRES[-1]

DEMONSTRACOES = {  # código: (nome, ordem)
    "BP": ("Balanço Patrimonial", 1), "DRE": ("Demonstração do Resultado", 2),
    "DRA": ("Resultado Abrangente", 3), "DFC": ("Fluxos de Caixa", 4),
    "DVA": ("Valor Adicionado", 5), "EBITDA": ("Reconciliação do EBITDA", 6),
}
LINHAS_EBITDA = [  # (código, descrição, chave em indicadores.ebitda)
    ("E.01", "Lucro líquido do período", "lucro_liquido"),
    ("E.02", "(+) IR e CSLL", "ir_csll"),
    ("E.03", "(+/−) Resultado financeiro líquido", "resultado_financeiro"),
    ("E.04", "(+) Depreciação e amortização", "depreciacao_amortizacao"),
    ("E.05", "EBITDA", "ebitda"),
]
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
NBSP = " "


def reais(centavos) -> float:
    return round(int(centavos) / 100, 2)


def rotulo_trimestre(d: date) -> str:
    return f"{(d.month - 1) // 3 + 1}T{d.year % 100:02d}"


# ---------------------------------------------------------------- dimensões

def dim_calendario() -> pd.DataFrame:
    """Anos completos (exigência da inteligência de tempo do DAX). periodo_itr marca 1T25 a 3T26."""
    datas = pd.date_range("2024-01-01", "2026-12-31", freq="D")
    df = pd.DataFrame({"data": datas.date})
    df["ano"] = datas.year
    df["mes"] = datas.month
    df["mes_nome"] = [MESES[m - 1] for m in datas.month]
    df["ano_mes"] = datas.strftime("%Y-%m")
    df["trimestre"] = [rotulo_trimestre(d) for d in df.data]
    df["trimestre_ordem"] = datas.year * 10 + (datas.month - 1) // 3 + 1
    df["periodo_itr"] = df.trimestre.isin(TRIMESTRES).map({True: "Sim", False: "Não"})
    df["fim_trimestre"] = datas.is_quarter_end
    return df


def dim_linha(cfg) -> pd.DataFrame:
    partes = []
    for demo, (nome, ordem_demo) in DEMONSTRACOES.items():
        if demo == "EBITDA":
            l = pd.DataFrame([{"codigo": c, "descricao": d, "nivel": "1",
                               "tipo_linha": "formula" if c == "E.05" else "dado",
                               "tipo_valor": "movimento", "ordem": str(10 * (i + 1))}
                              for i, (c, d, _) in enumerate(LINHAS_EBITDA)])
        else:
            l = linhas_da(demo, cfg)
            l = l[l.tipo_linha != "info"]  # lucro por ação não se agrega: fica fora
        l = l[["codigo", "descricao", "nivel", "tipo_linha", "tipo_valor", "ordem"]].copy()
        l.insert(0, "demonstracao", demo)
        l["demonstracao_nome"] = nome
        l["demonstracao_ordem"] = ordem_demo
        partes.append(l)
    df = pd.concat(partes, ignore_index=True)
    df["nivel"] = df.nivel.astype(int)
    df["ordem"] = df.demonstracao_ordem * 10_000 + df.ordem.astype(int)
    df["agregacao"] = "soma"
    df.loc[df.tipo_valor == "posicao", "agregacao"] = "ultimo"
    df.loc[df.codigo == "6.05.01", "agregacao"] = "primeiro"
    # Rótulo da matriz: recuo pelo nível + código (o código torna o rótulo único,
    # o que o "Classificar por coluna" do Power BI exige).
    df["rotulo"] = [NBSP * 3 * (n - 1) + f"{c}  {d}" for n, c, d in zip(df.nivel, df.codigo, df.descricao)]
    df["destaque"] = df.tipo_linha.isin(["grupo", "formula"])
    df["lado_bp"] = df.codigo.str[0].map({"1": "Ativo", "2": "Passivo e PL"}).where(df.demonstracao == "BP")
    return df.drop(columns="tipo_valor").rename(columns={"codigo": "chave"}).assign(codigo=lambda x: x.chave)


def dim_conta(con, cfg) -> pd.DataFrame:
    plano = pd.read_sql("SELECT codigo, descricao, tipo, natureza, nivel, codigo_pai, grupo, redutora "
                        "FROM plano_de_contas", con)
    nomes = plano.set_index("codigo").descricao.to_dict()
    pais = plano.set_index("codigo").codigo_pai.to_dict()

    def ancestral(codigo, nivel):
        while codigo and plano.loc[plano.codigo == codigo, "nivel"].iat[0] > nivel:
            codigo = pais.get(codigo)
        return nomes.get(codigo, "")

    plano["grupo_nivel_2"] = [ancestral(c, 2) for c in plano.codigo]
    plano["grupo_nivel_3"] = [ancestral(c, 3) if n >= 3 else "" for c, n in zip(plano.codigo, plano.nivel)]
    mapa = cfg["map_conta_df"][["codigo_conta", "linha_bp_dre"]].rename(columns={"codigo_conta": "codigo"})
    df = plano.merge(mapa, on="codigo", how="left")
    descr = cfg["dim_linha_df"].drop_duplicates("codigo").set_index("codigo").descricao
    df["linha_df_descricao"] = df.linha_bp_dre.map(descr)
    df["rotulo"] = df.codigo + "  " + df.descricao
    return df


def dim_evento(con) -> pd.DataFrame:
    df = pd.read_sql("SELECT codigo, nome, grupo, descricao FROM dim_evento", con)
    abertura = pd.DataFrame([{"codigo": "ABERTURA", "nome": "Saldo de abertura", "grupo": "Abertura",
                              "descricao": f"Balancete de abertura em {ABERTURA:%d/%m/%Y}"}])
    return pd.concat([abertura, df], ignore_index=True)


def dim_indicador() -> pd.DataFrame:
    return pd.DataFrame([{"codigo": i.codigo, "nome": i.nome, "grupo": i.grupo, "unidade": i.unidade,
                          "formula": i.formula, "ordem": n} for n, i in enumerate(INDICADORES, 1)])


# ---------------------------------------------------------------- fatos

def fato_lancamento(con) -> pd.DataFrame:
    lanc = pd.read_sql("SELECT data, id_lancamento, codigo_evento AS evento, codigo_conta AS conta, "
                       "debito_centavos, credito_centavos, historico FROM lancamento", con)
    abert = pd.read_sql("SELECT data, codigo_conta AS conta, debito_centavos, credito_centavos "
                        "FROM saldo_abertura", con)
    abert["id_lancamento"] = "ABERTURA"
    abert["evento"] = "ABERTURA"
    abert["historico"] = "Saldo de abertura"
    df = pd.concat([abert, lanc], ignore_index=True)
    df["data"] = pd.to_datetime(df.data).dt.date
    df["debito"] = df.debito_centavos / 100
    df["credito"] = df.credito_centavos / 100
    df["movimento"] = (df.debito_centavos - df.credito_centavos) / 100  # devedor +, credor −
    return df[["data", "id_lancamento", "evento", "conta", "historico", "debito", "credito", "movimento"]]


def fato_demonstracao(con, cfg) -> pd.DataFrame:
    linhas = []

    def gravar(demo, data_fim, valores: dict, validas: set):
        for codigo, centavos in valores.items():
            if codigo in validas:
                linhas.append({"data": data_fim, "trimestre": rotulo_trimestre(data_fim),
                               "demonstracao": demo, "chave_linha": codigo, "valor": reais(centavos)})

    validas = {d: set(linhas_da(d, cfg).query("tipo_linha != 'info'").codigo) for d in DEMONSTRACOES if d != "EBITDA"}
    gravar("BP", ABERTURA, balanco(con, ABERTURA, cfg), validas["BP"])  # saldo de abertura do 1T25
    for rotulo in TRIMESTRES:
        inicio, fim = datas_do_trimestre(rotulo)
        gravar("BP", fim, balanco(con, fim, cfg), validas["BP"])
        gravar("DRE", fim, resultado(con, inicio, fim, cfg), validas["DRE"])
        gravar("DRA", fim, dra(con, inicio, fim, cfg), validas["DRA"])
        gravar("DFC", fim, dfc(con, inicio, fim, cfg), validas["DFC"])
        gravar("DVA", fim, dva(con, inicio, fim, cfg), validas["DVA"])
        e = ebitda(con, inicio, fim, cfg)
        gravar("EBITDA", fim, {c: e[chave] for c, _, chave in LINHAS_EBITDA}, {c for c, _, _ in LINHAS_EBITDA})
    return pd.DataFrame(linhas)


def fato_indicador(con, cfg) -> pd.DataFrame:
    df = serie(con, cfg)
    df["valor"] = pd.to_numeric(df.valor, errors="coerce")  # None (n.d.) vira vazio no Power BI
    return df[["data", "trimestre", "codigo", "valor"]]


def fato_qualidade(execucao) -> pd.DataFrame:
    nomes = {1: "Integridade", 2: "Coerência", 3: "Conciliação"}
    return pd.DataFrame([{"run_id": execucao.run_id, "executado_em": execucao.executado_em,
                          "trimestre": execucao.trimestre, "ordem": n, "codigo": v.codigo,
                          "nivel": v.nivel, "nivel_nome": nomes[v.nivel], "descricao": v.descricao,
                          "status": v.status, "esperado": v.esperado, "encontrado": v.encontrado}
                         for n, v in enumerate(execucao.verificacoes, 1)])


# ---------------------------------------------------------------- exportação

def montar(con, cfg=None) -> dict[str, pd.DataFrame]:
    """Monta as tabelas. A Central roda antes: com erro, PermissionError e nada é montado."""
    cfg = cfg or carregar()
    execucao = exigir_liberacao(con, TRIMESTRE_ITR, cfg)
    return {
        "dim_calendario": dim_calendario(),
        "dim_conta": dim_conta(con, cfg),
        "dim_evento": dim_evento(con),
        "dim_linha": dim_linha(cfg),
        "dim_indicador": dim_indicador(),
        "fato_lancamento": fato_lancamento(con),
        "fato_demonstracao": fato_demonstracao(con, cfg),
        "fato_indicador": fato_indicador(con, cfg),
        "fato_qualidade": fato_qualidade(execucao),
    }


def gravar_parquet(df: pd.DataFrame, caminho: Path) -> None:
    """Texto como `string` simples: o pandas novo usa `large_string`, um tipo menos difundido."""
    tabela = pa.Table.from_pandas(df, preserve_index=False)
    esquema = pa.schema([pa.field(c.name, pa.string() if pa.types.is_large_string(c.type) else c.type)
                         for c in tabela.schema])
    pq.write_table(tabela.cast(esquema).replace_schema_metadata(None), caminho)


def exportar(con, pasta: Path = EXPORTACAO, cfg=None) -> dict[str, Path]:
    tabelas = montar(con, cfg)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivos = {}
    for nome, df in tabelas.items():
        arquivos[nome] = pasta / f"{nome}.parquet"
        gravar_parquet(df, arquivos[nome])
    return arquivos


def main() -> None:
    if not BASE_PADRAO.exists():
        raise SystemExit("Base não encontrada. Rode antes: python src/importar_entrada.py")
    con = sqlite3.connect(BASE_PADRAO)
    try:
        arquivos = exportar(con)
    except PermissionError as erro:
        raise SystemExit(f"\n{erro}\n\nNada foi exportado. Detalhes: python src/qualidade.py")
    finally:
        con.close()
    print(f"Exportação para o Power BI em {EXPORTACAO}")
    for nome, caminho in arquivos.items():
        print(f"  {nome:<18} {len(pd.read_parquet(caminho)):>6} linhas")


if __name__ == "__main__":
    main()
