"""
Dados do painel web (Etapa 12). Lê os mesmos arquivos Parquet do Power BI e aplica as mesmas regras
das medidas DAX (docs/11_power_bi.md). Não depende do Streamlit, para poder ser testado.

Origem dos dados, nesta ordem:
    exportacao/            gerada por `python src/exportar_parquet.py`
    exemplos/exportacao/   cópia que vai para o GitHub (o app publicado na web usa esta)
"""
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PASTAS = [RAIZ / "exportacao", RAIZ / "exemplos" / "exportacao"]
TABELAS = ["dim_calendario", "dim_conta", "dim_evento", "dim_linha", "dim_indicador",
           "fato_lancamento", "fato_demonstracao", "fato_indicador", "fato_qualidade"]
NBSP = " "


@dataclass
class Dados:
    pasta: Path
    t: dict[str, pd.DataFrame]

    @property
    def trimestres(self) -> list[str]:
        cal = self.t["dim_calendario"]
        return cal[cal.periodo_itr == "Sim"].sort_values("trimestre_ordem").trimestre.unique().tolist()

    @property
    def run_id(self) -> str:
        return self.t["fato_qualidade"].run_id.iat[0]


def carregar(pasta: Path | None = None) -> Dados:
    candidatas = [pasta] if pasta else PASTAS
    for p in candidatas:
        if all((p / f"{n}.parquet").exists() for n in TABELAS):
            return Dados(p, {n: pd.read_parquet(p / f"{n}.parquet") for n in TABELAS})
    raise FileNotFoundError("Nenhuma exportação encontrada. Rode: python src/exportar_parquet.py")


# ---------------------------------------------------------------- a regra das medidas DAX

def valor_df(d: Dados, codigo: str, trimestres: list[str]) -> float | None:
    """Mesma regra da medida [Valor DF]: soma, último ou primeiro trimestre do período."""
    fato = d.t["fato_demonstracao"]
    serie = fato[(fato.chave_linha == codigo) & fato.trimestre.isin(trimestres)].sort_values("data")
    if serie.empty:
        return None
    regra = d.t["dim_linha"].set_index("chave").agregacao[codigo]
    if regra == "soma":
        return round(float(serie.valor.sum()), 2)
    return float(serie.valor.iat[-1] if regra == "ultimo" else serie.valor.iat[0])


def v(d: Dados, codigo: str, trimestre: str) -> float:
    return valor_df(d, codigo, [trimestre]) or 0.0


def ebitda(d: Dados, tri: str) -> float:
    """Medida [EBITDA]: lucro − IR/CSLL − resultado financeiro + depreciação (DFC)."""
    return v(d, "3.11", tri) - v(d, "3.08", tri) - v(d, "3.06", tri) + v(d, "6.01.01.02", tri)


def ano_anterior(tri: str) -> str:
    return f"{tri[0]}T{int(tri[2:]) - 1:02d}"


def indicador(d: Dados, codigo: str, tri: str) -> float | None:
    f = d.t["fato_indicador"]
    valor = f[(f.codigo == codigo) & (f.trimestre == tri)].valor
    return None if valor.empty or pd.isna(valor.iat[0]) else float(valor.iat[0])


def divida_liquida(d: Dados, tri: str) -> float:
    return v(d, "2.01.04", tri) + v(d, "2.02.01", tri) - v(d, "1.01.01", tri)


def caixa_pelo_razao(d: Dados, tri: str) -> float:
    """Medida [Caixa pelo Razão]: saldo acumulado das contas da linha 1.01.01 até o fim do trimestre."""
    lanc = d.t["fato_lancamento"].merge(d.t["dim_conta"][["codigo", "linha_bp_dre"]],
                                        left_on="conta", right_on="codigo")
    fim = d.t["fato_demonstracao"].query("trimestre == @tri").data.max()
    return round(float(lanc[(lanc.linha_bp_dre == "1.01.01") & (lanc.data <= fim)].movimento.sum()), 2)


# ---------------------------------------------------------------- blocos das páginas

def destaques(d: Dados, tri: str) -> dict[str, float | None]:
    ant = ano_anterior(tri)
    receita, lucro = v(d, "3.01", tri), v(d, "3.11", tri)
    receita_ant = valor_df(d, "3.01", [ant])
    lucro_ant = valor_df(d, "3.11", [ant])
    return {
        "receita": receita, "var_receita": receita / receita_ant - 1 if receita_ant else None,
        "ebitda": ebitda(d, tri), "margem_ebitda": ebitda(d, tri) / receita if receita else None,
        "lucro": lucro, "var_lucro": lucro / lucro_ant - 1 if lucro_ant else None,
        "margem_bruta": v(d, "3.03", tri) / receita if receita else None,
        "margem_liquida": lucro / receita if receita else None,
        "caixa": v(d, "1.01.01", tri), "pl": v(d, "2.03", tri), "divida_liquida": divida_liquida(d, tri),
    }


def serie_resultado(d: Dados) -> pd.DataFrame:
    linhas = []
    for tri in d.trimestres:
        receita = v(d, "3.01", tri)
        linhas.append({"trimestre": tri, "Receita líquida": receita, "EBITDA": ebitda(d, tri),
                       "Lucro líquido": v(d, "3.11", tri),
                       "Margem bruta": v(d, "3.03", tri) / receita, "Margem EBITDA": ebitda(d, tri) / receita,
                       "Margem líquida": v(d, "3.11", tri) / receita})
    return pd.DataFrame(linhas)


def demonstracoes(d: Dados) -> list[tuple[str, str]]:
    l = d.t["dim_linha"].drop_duplicates("demonstracao").sort_values("demonstracao_ordem")
    return list(zip(l.demonstracao, l.demonstracao_nome))


def matriz(d: Dados, demonstracao: str, trimestres: list[str]) -> pd.DataFrame:
    """Linhas da demonstração × trimestres, mais a coluna Período (regra semiaditiva). Em R$ mil."""
    linhas = d.t["dim_linha"].query("demonstracao == @demonstracao").sort_values("ordem")
    tabela = pd.DataFrame({
        "Linha": [NBSP * 3 * (n - 1) + f"{c}  {t}" for n, c, t in zip(linhas.nivel, linhas.codigo, linhas.descricao)],
        "destaque": linhas.destaque.to_numpy(),
    })
    for tri in trimestres + ["Período"]:
        periodo = [tri] if tri != "Período" else trimestres
        tabela[tri] = [None if (x := valor_df(d, c, periodo)) is None else round(x / 1000) for c in linhas.codigo]
    return tabela


def formatar_indicador(valor: float | None, unidade: str) -> str:
    if valor is None or pd.isna(valor):
        return "n.d."
    if unidade == "%":
        return f"{valor:.1%}".replace(".", ",")
    if unidade == "x":
        return f"{valor:.2f}x".replace(".", ",")
    if unidade == "dias":
        return f"{valor:.0f}"
    return f"{valor / 1000:,.0f}".replace(",", ".")


def tabela_indicadores(d: Dados) -> pd.DataFrame:
    dim = d.t["dim_indicador"].sort_values("ordem")
    linhas = []
    for i in dim.itertuples():
        linha = {"Grupo": i.grupo, "Indicador": i.nome + (" (R$ mil)" if i.unidade == "R$" else ""),
                 "Fórmula": i.formula}
        linha.update({tri: formatar_indicador(indicador(d, i.codigo, tri), i.unidade) for tri in d.trimestres})
        linhas.append(linha)
    return pd.DataFrame(linhas)


def serie_prazos(d: Dados) -> pd.DataFrame:
    nomes = {"pmr": "PMR", "pme": "PME", "pmp": "PMP", "ciclo_financeiro": "Ciclo financeiro"}
    return pd.DataFrame([{"trimestre": tri, "prazo": nome, "dias": indicador(d, codigo, tri)}
                         for codigo, nome in nomes.items() for tri in d.trimestres])


def conferencias(d: Dados, tri: str) -> pd.DataFrame:
    """As mesmas conferências da página 4 do Power BI. Todas devem dar zero."""
    itens = [
        ("EBITDA do painel − EBITDA do sistema", ebitda(d, tri) - v(d, "E.05", tri)),
        ("Caixa pelo razão − caixa do BP", caixa_pelo_razao(d, tri) - v(d, "1.01.01", tri)),
        ("Dívida líquida pelo BP − indicador", divida_liquida(d, tri) - (indicador(d, "divida_liquida", tri) or 0)),
        ("Ativo − (Passivo + PL)", v(d, "1", tri) - v(d, "2", tri)),
    ]
    tabela = pd.DataFrame(itens, columns=["Conferência", "Diferença (R$)"])
    tabela["Diferença (R$)"] = tabela["Diferença (R$)"].round(2) + 0.0  # evita "-0,00"
    tabela["OK"] = tabela["Diferença (R$)"].abs() < 0.01
    return tabela


# ---------------------------------------------------------------- gráficos do painel (versão 2)

def periodo(trimestres: list[str]) -> str:
    """Rótulo do período escolhido: '3T26' ou '1T26 a 3T26'."""
    return trimestres[0] if len(trimestres) == 1 else f"{trimestres[0]} a {trimestres[-1]}"


def cascata_resultado(d: Dados, trimestres: list[str]) -> pd.DataFrame:
    """Da receita ao lucro líquido, em degraus (gráfico de cascata). Em R$."""
    passos = [("Receita líquida", "3.01", "total"), ("Custo das vendas", "3.02", "passo"),
              ("Despesas com vendas", "3.04.01", "passo"), ("Despesas gerais", "3.04.02", "passo"),
              ("Perda de crédito", "3.04.03", "passo"),
              ("Outras operacionais", ("3.04.04", "3.04.05"), "passo"),
              ("Resultado financeiro", "3.06", "passo"), ("IR e CSLL", "3.08", "passo")]
    linhas, acumulado = [], 0.0
    for nome, codigos, tipo in passos:
        codigos = codigos if isinstance(codigos, tuple) else (codigos,)
        valor = sum(valor_df(d, c, trimestres) or 0.0 for c in codigos)
        inicio = 0.0 if tipo == "total" else acumulado
        acumulado = valor if tipo == "total" else acumulado + valor
        linhas.append({"etapa": nome, "inicio": inicio, "fim": acumulado, "valor": valor, "tipo": tipo})
    lucro = valor_df(d, "3.11", trimestres) or 0.0
    linhas.append({"etapa": "Lucro líquido", "inicio": 0.0, "fim": lucro, "valor": lucro, "tipo": "total"})
    return pd.DataFrame(linhas)


def ponte_caixa(d: Dados, trimestres: list[str]) -> pd.DataFrame:
    """Saldo inicial de caixa + atividades = saldo final (DFC em degraus). Em R$."""
    passos = [("Saldo inicial", "6.05.01", "total"), ("Operacional", "6.01", "passo"),
              ("Investimento", "6.02", "passo"), ("Financiamento", "6.03", "passo")]
    linhas, acumulado = [], 0.0
    for nome, codigo, tipo in passos:
        valor = valor_df(d, codigo, trimestres) or 0.0
        inicio = 0.0 if tipo == "total" else acumulado
        acumulado = valor if tipo == "total" else acumulado + valor
        linhas.append({"etapa": nome, "inicio": inicio, "fim": acumulado, "valor": valor, "tipo": tipo})
    final = valor_df(d, "6.05.02", trimestres) or 0.0
    linhas.append({"etapa": "Saldo final", "inicio": 0.0, "fim": final, "valor": final, "tipo": "total"})
    return pd.DataFrame(linhas)


COMPOSICAO_ATIVO = [("Caixa", "1.01.01"), ("Clientes", "1.01.03"), ("Estoques", "1.01.04"),
                    ("Tributos", "1.01.06"), ("Outros", ("1.01.07", "1.01.08")),
                    ("IR diferido", "1.02.01"), ("Imobilizado", "1.02.03"), ("Intangível", "1.02.04")]


def composicao_ativo(d: Dados, tri: str) -> pd.DataFrame:
    linhas = []
    for nome, codigos in COMPOSICAO_ATIVO:
        codigos = codigos if isinstance(codigos, tuple) else (codigos,)
        linhas.append({"item": nome, "valor": sum(v(d, c, tri) for c in codigos)})
    df = pd.DataFrame(linhas)
    df["participacao"] = df.valor / v(d, "1", tri)
    return df


def estrutura_capital(d: Dados, tri: str) -> pd.DataFrame:
    df = pd.DataFrame([{"item": "Passivo circulante", "valor": v(d, "2.01", tri)},
                       {"item": "Passivo não circulante", "valor": v(d, "2.02", tri)},
                       {"item": "Patrimônio líquido", "valor": v(d, "2.03", tri)}])
    df["participacao"] = df.valor / v(d, "2", tri)
    return df


def distribuicao_valor_adicionado(d: Dados, trimestres: list[str]) -> pd.DataFrame:
    itens = [("Pessoal", "7.08.01"), ("Impostos", "7.08.02"), ("Capital de terceiros", "7.08.03"),
             ("Acionistas", "7.08.04")]
    df = pd.DataFrame([{"item": n, "valor": valor_df(d, c, trimestres) or 0.0} for n, c in itens])
    df["participacao"] = df.valor / (valor_df(d, "7.08", trimestres) or 1)
    return df


def serie_balanco(d: Dados) -> pd.DataFrame:
    """Caixa, dívida bruta e PL no fim de cada trimestre. Em R$."""
    return pd.DataFrame([{"trimestre": t, "Caixa e equivalentes": v(d, "1.01.01", t),
                          "Dívida bruta": v(d, "2.01.04", t) + v(d, "2.02.01", t),
                          "Patrimônio líquido": v(d, "2.03", t)} for t in d.trimestres])


def serie_indicador(d: Dados, codigos: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame([{"trimestre": t, "indicador": nome, "valor": indicador(d, c, t)}
                         for c, nome in codigos.items() for t in d.trimestres])
