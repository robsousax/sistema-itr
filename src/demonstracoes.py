"""
Motor das demonstrações (Etapa 5): Balanço Patrimonial e Demonstração do Resultado.

Tudo sai da base (base/itr.sqlite) e da configuração (config/dim_linha_df.csv e
config/map_conta_df.csv). Nenhum número é digitado aqui: o motor só
  1. soma saldos (BP) ou movimentos (DRE) das contas analíticas;
  2. joga cada soma na linha da CVM indicada no mapeamento;
  3. calcula grupos (soma das linhas-filhas) e subtotais (coluna `formula`).

Valores em centavos. A conversão para R$ mil acontece só na apresentação.

Períodos do ITR (CPC 21, item 20), exemplo para o 3T26:
  BP:  30/09/2026 comparado com 31/12/2025
  DRE: 3T26 e 9M26 comparados com 3T25 e 9M25

Uso:
    python src/demonstracoes.py           # ITR do 3T26
    python src/demonstracoes.py 2T26      # outro trimestre
"""
import calendar
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd

from checar_config import carregar

RAIZ = Path(__file__).resolve().parent.parent
BASE_PADRAO = RAIZ / "base" / "itr.sqlite"
LUCROS_ACUMULADOS = "2.03.05"


# ---------------------------------------------------------------- períodos

@dataclass(frozen=True)
class Periodo:
    rotulo: str      # "3T26", "9M26", "31/12/2025"...
    inicio: date     # para posição (BP), inicio == fim
    fim: date


def ultimo_dia_do_trimestre(t: int, ano: int) -> date:
    mes = 3 * t
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def periodos_itr(trimestre: str) -> dict[str, Periodo]:
    """'3T26' -> as colunas do ITR desse trimestre."""
    t, ano = int(trimestre[0]), 2000 + int(trimestre[2:])
    fim = ultimo_dia_do_trimestre(t, ano)
    inicio_tri = date(ano, 3 * t - 2, 1)
    fim_ant = ultimo_dia_do_trimestre(t, ano - 1)
    return {
        "bp_atual": Periodo(fim.strftime("%d/%m/%Y"), fim, fim),
        "bp_comparativo": Periodo(f"31/12/{ano - 1}", date(ano - 1, 12, 31), date(ano - 1, 12, 31)),
        "tri_atual": Periodo(trimestre, inicio_tri, fim),
        "acum_atual": Periodo(f"{3 * t}M{ano % 100}", date(ano, 1, 1), fim),
        "tri_anterior": Periodo(f"{t}T{(ano - 1) % 100}", date(ano - 1, 3 * t - 2, 1), fim_ant),
        "acum_anterior": Periodo(f"{3 * t}M{(ano - 1) % 100}", date(ano - 1, 1, 1), fim_ant),
    }


# ---------------------------------------------------------------- leitura da base

def saldos_em(con: sqlite3.Connection, data: date) -> dict[str, int]:
    """Saldo de cada conta no fim do dia (débito positivo, crédito negativo)."""
    sql = """
        SELECT conta, SUM(valor) FROM (
            SELECT codigo_conta AS conta, debito_centavos - credito_centavos AS valor
              FROM saldo_abertura WHERE data <= :data
            UNION ALL
            SELECT codigo_conta, debito_centavos - credito_centavos
              FROM lancamento WHERE data <= :data
        ) GROUP BY conta"""
    return {c: v for c, v in con.execute(sql, {"data": data.isoformat()}) if v}


def movimentos(con: sqlite3.Connection, inicio: date, fim: date) -> dict[str, int]:
    """
    Movimento de cada conta no período (débito positivo). O encerramento do exercício (EV52)
    fica de fora: ele zera as contas de resultado em 31/12 e apagaria a DRE do 4º trimestre.
    """
    sql = """
        SELECT codigo_conta, SUM(debito_centavos - credito_centavos)
          FROM lancamento
         WHERE data BETWEEN ? AND ? AND codigo_evento <> 'EV52'
         GROUP BY codigo_conta"""
    return {c: v for c, v in con.execute(sql, (inicio.isoformat(), fim.isoformat())) if v}


def media_ponderada_acoes(con: sqlite3.Connection, inicio: date, fim: date) -> Decimal:
    """
    Média ponderada de ações em circulação no período (CPC 41): cada lote pesa pelos dias em que
    esteve em circulação. Sem ações em tesouraria nem bonificações na V1.
    """
    atos = con.execute("SELECT data, quantidade_acoes FROM ato_pl "
                       "WHERE tipo_ato IN ('posicao_inicial', 'aumento_capital') "
                       "ORDER BY data").fetchall()
    dias = (fim - inicio).days + 1
    total = Decimal(0)
    for data_ato, quantidade in atos:
        desde = max(date.fromisoformat(data_ato) + timedelta(days=1), inicio)
        if desde <= fim:
            total += Decimal(quantidade) * Decimal((fim - desde).days + 1)
    return total / dias


# ---------------------------------------------------------------- cálculo das linhas

def calcular_linhas(linhas: pd.DataFrame, dados: dict[str, int]) -> dict[str, int]:
    """
    Recebe os valores das linhas de dado e devolve todas as linhas da demonstração:
    grupos = soma das filhas; fórmulas = soma das linhas citadas ("3.03 + 3.04").
    Repete até resolver tudo, porque um grupo pode depender de uma fórmula e vice-versa.
    """
    valores = {c: dados.get(c, 0) for c in linhas.loc[linhas.tipo_linha == "dado", "codigo"]}
    pendentes = linhas[linhas.tipo_linha.isin(["grupo", "formula"])]
    filhas = linhas.groupby("codigo_pai")["codigo"].apply(list).to_dict()
    tipo = dict(zip(linhas.codigo, linhas.tipo_linha))
    while len(valores) < len(linhas[linhas.tipo_linha != "info"]):
        avancou = False
        for _, l in pendentes.iterrows():
            if l.codigo in valores:
                continue
            partes = (filhas.get(l.codigo, []) if l.tipo_linha == "grupo"
                      else [p.strip() for p in l.formula.split("+")])
            partes = [p for p in partes if tipo.get(p) not in (None, "info")]
            if all(p in valores for p in partes):
                valores[l.codigo] = sum(valores[p] for p in partes)
                avancou = True
        if not avancou:
            faltam = set(pendentes.codigo) - set(valores)
            raise ValueError(f"Não consegui calcular as linhas {sorted(faltam)}")
    return valores


def linhas_da(demonstracao: str, cfg: dict) -> pd.DataFrame:
    linhas = cfg["dim_linha_df"]
    return linhas[linhas.demonstracao == demonstracao].sort_values(
        "ordem", key=lambda s: s.astype(int)).reset_index(drop=True)


def somar_por_linha(valores_conta: dict[str, int], cfg: dict, sinal: int) -> dict[str, int]:
    """Soma o valor de cada conta analítica na sua linha (sinal -1 = natureza credora)."""
    mapa = cfg["map_conta_df"].set_index("codigo_conta")["linha_bp_dre"]
    por_linha: dict[str, int] = {}
    for conta, valor in valores_conta.items():
        linha = mapa[conta]
        por_linha[linha] = por_linha.get(linha, 0) + sinal * valor
    return por_linha


def balanco(con: sqlite3.Connection, data: date, cfg: dict) -> dict[str, int]:
    """
    BP numa data. Ativo: débito positivo. Passivo e PL: crédito positivo.
    Durante o exercício o resultado ainda não foi encerrado: ele entra em lucros acumulados.
    """
    saldos = saldos_em(con, data)
    patrimoniais = {c: v for c, v in saldos.items() if c[0] in "12"}
    resultado = -sum(v for c, v in saldos.items() if c[0] == "3")
    ativo = somar_por_linha({c: v for c, v in patrimoniais.items() if c[0] == "1"}, cfg, +1)
    passivo = somar_por_linha({c: v for c, v in patrimoniais.items() if c[0] == "2"}, cfg, -1)
    passivo[LUCROS_ACUMULADOS] = passivo.get(LUCROS_ACUMULADOS, 0) + resultado
    return calcular_linhas(linhas_da("BP", cfg), {**ativo, **passivo})


def resultado(con: sqlite3.Connection, inicio: date, fim: date, cfg: dict) -> dict[str, int]:
    """DRE do período. Receitas positivas, custos e despesas negativos."""
    mov = {c: v for c, v in movimentos(con, inicio, fim).items() if c[0] == "3"}
    return calcular_linhas(linhas_da("DRE", cfg), somar_por_linha(mov, cfg, -1))


def lucro_por_acao(con, inicio: date, fim: date, lucro_centavos: int) -> Decimal:
    acoes = media_ponderada_acoes(con, inicio, fim)
    return (Decimal(lucro_centavos) / 100 / acoes).quantize(Decimal("0.00001"), ROUND_HALF_UP)


# ---------------------------------------------------------------- montagem do ITR

def montar_bp(con, trimestre: str, cfg: dict | None = None) -> pd.DataFrame:
    cfg = cfg or carregar()
    p = periodos_itr(trimestre)
    linhas = linhas_da("BP", cfg)
    colunas = {p["bp_atual"].rotulo: balanco(con, p["bp_atual"].fim, cfg),
               p["bp_comparativo"].rotulo: balanco(con, p["bp_comparativo"].fim, cfg)}
    tabela = linhas[["codigo", "descricao", "nivel"]].copy()
    for rotulo, valores in colunas.items():
        tabela[rotulo] = tabela.codigo.map(valores).fillna(0).astype("int64")
    return tabela


def montar_dre(con, trimestre: str, cfg: dict | None = None
               ) -> tuple[pd.DataFrame, dict[str, Decimal]]:
    """DRE com as 4 colunas do ITR e o lucro básico por ação de cada coluna."""
    cfg = cfg or carregar()
    p = periodos_itr(trimestre)
    linhas = linhas_da("DRE", cfg)
    tabela = linhas[["codigo", "descricao", "nivel"]].copy()
    lpa = {}
    for chave in ("tri_atual", "acum_atual", "tri_anterior", "acum_anterior"):
        per = p[chave]
        valores = resultado(con, per.inicio, per.fim, cfg)
        tabela[per.rotulo] = tabela.codigo.map(valores).fillna(0).astype("int64")
        lpa[per.rotulo] = lucro_por_acao(con, per.inicio, per.fim, valores["3.11"])
    return tabela, lpa


# ---------------------------------------------------------------- apresentação

def reais_mil(centavos: int) -> int:
    """Centavos -> R$ mil, arredondando meio para cima (cada linha arredonda sozinha)."""
    return int((Decimal(centavos) / 100_000).to_integral_value(rounding=ROUND_HALF_UP))


def formatar(n: int) -> str:
    texto = f"{abs(n):,}".replace(",", ".")
    return f"-{texto}" if n < 0 else texto


def imprimir(titulo: str, tabela: pd.DataFrame, extra: dict | None = None) -> None:
    colunas = [c for c in tabela.columns if c not in ("codigo", "descricao", "nivel")]
    print(f"\n{titulo} (R$ mil)")
    print(f"{'Código':<11}{'Descrição':<58}" + "".join(f"{c:>13}" for c in colunas))
    for _, l in tabela.iterrows():
        if l.codigo.startswith("3.99"):
            continue
        recuo = "  " * (int(l.nivel) - 1)
        descricao = (recuo + l.descricao)[:56]
        print(f"{l.codigo:<11}{descricao:<58}"
              + "".join(f"{formatar(reais_mil(l[c])):>13}" for c in colunas))
    if extra:
        print(f"{'3.99.01.01':<11}{'ON - Lucro Básico por Ação (R$)':<58}"
              + "".join(f"{str(extra[c]).replace('.', ','):>13}" for c in colunas))


def main() -> None:
    trimestre = sys.argv[1] if len(sys.argv) > 1 else "3T26"
    if not BASE_PADRAO.exists():
        raise SystemExit("Base não encontrada. Rode antes: python src/importar_entrada.py")
    con = sqlite3.connect(BASE_PADRAO)
    cfg = carregar()
    bp = montar_bp(con, trimestre, cfg)
    dre, lpa = montar_dre(con, trimestre, cfg)
    con.close()
    imprimir("BALANÇO PATRIMONIAL — ATIVO", bp[bp.codigo.str.startswith("1")])
    imprimir("BALANÇO PATRIMONIAL — PASSIVO E PATRIMÔNIO LÍQUIDO", bp[bp.codigo.str.startswith("2")])
    imprimir("DEMONSTRAÇÃO DO RESULTADO", dre, lpa)
    atual = bp.columns[3]
    diferenca = bp.set_index("codigo").loc["1", atual] - bp.set_index("codigo").loc["2", atual]
    print(f"\nConferência: ativo - (passivo + PL) em {atual} = {diferenca} centavos")


if __name__ == "__main__":
    main()
