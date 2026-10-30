"""
Indicadores econômico-financeiros (Etapa 8).

Todos calculados a partir do BP e da DRE produzidos pelo motor (nunca de números digitados), para
cada fim de trimestre. Fórmulas documentadas em docs/08_indicadores.md.

Convenções:
  - Indicadores de posição (liquidez, endividamento) usam o BP do fim do trimestre.
  - Margens usam a DRE do trimestre.
  - Prazos médios usam o saldo MÉDIO do trimestre (início e fim) contra o fluxo do trimestre, em
    dias (90 por trimestre).
  - ROE, ROA, giro do ativo e dívida líquida/EBITDA usam os últimos 12 meses (UDM) e saldos
    médios. Como o histórico começa em jan/2025, só existem a partir do 4T25; antes disso o valor
    é None ("não disponível"), e não uma anualização inventada.
  - EBITDA conforme a Resolução CVM 156/2022: lucro líquido + IR e CSLL + resultado financeiro
    líquido + depreciação e amortização, com a reconciliação publicada. Sem ajustes na V1.

Uso:
    python src/indicadores.py           # painel de indicadores e EBITDA, 1T25 a 3T26
"""
import calendar
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from checar_config import carregar
from demonstracoes import BASE_PADRAO, balanco, formatar, reais_mil, resultado
from dfc_dmpl import partidas

TRIMESTRES = ["1T25", "2T25", "3T25", "4T25", "1T26", "2T26", "3T26"]
DIAS_TRIMESTRE = 90


@dataclass(frozen=True)
class Indicador:
    codigo: str
    nome: str
    grupo: str
    unidade: str     # "x" (vezes), "%", "dias", "R$"
    formula: str


INDICADORES = [
    Indicador("liq_corrente", "Liquidez corrente", "Liquidez", "x", "Ativo circulante / Passivo circulante"),
    Indicador("liq_seca", "Liquidez seca", "Liquidez", "x",
              "(Ativo circulante - Estoques - Despesas antecipadas) / Passivo circulante"),
    Indicador("liq_imediata", "Liquidez imediata", "Liquidez", "x", "Caixa e equivalentes / Passivo circulante"),
    Indicador("liq_geral", "Liquidez geral", "Liquidez", "x",
              "(Ativo circulante + Realizável a longo prazo) / (Passivo circulante + Passivo não circulante)"),
    Indicador("divida_bruta", "Dívida bruta", "Endividamento", "R$",
              "Empréstimos e financiamentos de curto e de longo prazo"),
    Indicador("divida_liquida", "Dívida líquida", "Endividamento", "R$",
              "Dívida bruta - Caixa e equivalentes (negativo = caixa líquido)"),
    Indicador("divida_liquida_ebitda", "Dívida líquida / EBITDA UDM", "Endividamento", "x",
              "Dívida líquida / EBITDA dos últimos 12 meses"),
    Indicador("pl_ativo", "Patrimônio líquido / Ativo total", "Endividamento", "%", "PL / Ativo total"),
    Indicador("composicao_endividamento", "Composição do endividamento", "Endividamento", "%",
              "Passivo circulante / (Passivo circulante + Passivo não circulante)"),
    Indicador("margem_bruta", "Margem bruta", "Rentabilidade", "%", "Resultado bruto / Receita líquida"),
    Indicador("margem_ebitda", "Margem EBITDA", "Rentabilidade", "%", "EBITDA / Receita líquida"),
    Indicador("margem_ebit", "Margem EBIT", "Rentabilidade", "%",
              "Resultado antes do resultado financeiro e dos tributos / Receita líquida"),
    Indicador("margem_liquida", "Margem líquida", "Rentabilidade", "%", "Lucro líquido / Receita líquida"),
    Indicador("roe", "ROE (UDM)", "Rentabilidade", "%", "Lucro líquido UDM / PL médio (início e fim dos 12 meses)"),
    Indicador("roa", "ROA (UDM)", "Rentabilidade", "%", "Lucro líquido UDM / Ativo total médio"),
    Indicador("pmr", "Prazo médio de recebimento", "Atividade", "dias",
              "Clientes (bruto) médio / Receita bruta do trimestre x 90"),
    Indicador("pme", "Prazo médio de estocagem", "Atividade", "dias",
              "Estoque de mercadorias médio / CMV do trimestre x 90"),
    Indicador("pmp", "Prazo médio de pagamento", "Atividade", "dias",
              "Fornecedores de mercadorias médio / Compras brutas do trimestre x 90"),
    Indicador("ciclo_operacional", "Ciclo operacional", "Atividade", "dias", "PMR + PME"),
    Indicador("ciclo_financeiro", "Ciclo financeiro", "Atividade", "dias", "PMR + PME - PMP"),
    Indicador("giro_ativo", "Giro do ativo (UDM)", "Atividade", "x", "Receita líquida UDM / Ativo total médio"),
]
POR_CODIGO = {i.codigo: i for i in INDICADORES}


# ---------------------------------------------------------------- períodos

def datas_do_trimestre(rotulo: str) -> tuple[date, date]:
    t, ano = int(rotulo[0]), 2000 + int(rotulo[2:])
    mes_final = 3 * t
    return date(ano, mes_final - 2, 1), date(ano, mes_final, calendar.monthrange(ano, mes_final)[1])


def anterior(rotulo: str, n: int = 1) -> str:
    t, ano = int(rotulo[0]), int(rotulo[2:])
    total = ano * 4 + t - 1 - n
    return f"{total % 4 + 1}T{total // 4:02d}"


# ---------------------------------------------------------------- insumos

def ebitda(con, inicio: date, fim: date, cfg: dict) -> dict[str, int]:
    """Reconciliação do EBITDA (Res. CVM 156): parte do lucro líquido."""
    dre = resultado(con, inicio, fim, cfg)
    mapa = cfg["map_conta_df"].set_index("codigo_conta")["linha_dfc"].to_dict()
    deprec = sum(v for _, c, v in partidas(con, inicio, fim)
                 if c.startswith("3") and mapa[c] == "6.01.01.02")
    r = {"lucro_liquido": dre["3.11"], "ir_csll": -dre["3.08"], "resultado_financeiro": -dre["3.06"],
         "depreciacao_amortizacao": deprec}
    r["ebitda"] = sum(r.values())
    r["receita_liquida"] = dre["3.01"]
    return r


def compras_brutas(con, inicio: date, fim: date) -> int:
    sql = ("SELECT SUM(credito_centavos) FROM lancamento WHERE codigo_evento = 'EV09' "
           "AND codigo_conta = '2.1.02.001' AND data BETWEEN ? AND ?")
    valor, = con.execute(sql, (inicio.isoformat(), fim.isoformat())).fetchone()
    return valor or 0


def saldo_contas(con, data: date, contas: tuple[str, ...]) -> int:
    sql = f"""SELECT SUM(v) FROM (
                SELECT debito_centavos - credito_centavos v FROM saldo_abertura
                 WHERE codigo_conta IN ({','.join('?' * len(contas))}) AND data <= ?
                UNION ALL
                SELECT debito_centavos - credito_centavos FROM lancamento
                 WHERE codigo_conta IN ({','.join('?' * len(contas))}) AND data <= ?)"""
    valor, = con.execute(sql, (*contas, data.isoformat(), *contas, data.isoformat())).fetchone()
    return valor or 0


def razao(a, b):
    return None if a is None or not b else a / b


# ---------------------------------------------------------------- cálculo

def calcular(con, rotulo: str, cfg: dict) -> dict[str, float | None]:
    """Todos os indicadores de um trimestre."""
    inicio, fim = datas_do_trimestre(rotulo)
    abertura = inicio - timedelta(days=1)
    bp, bp0 = balanco(con, fim, cfg), balanco(con, abertura, cfg)
    dre = resultado(con, inicio, fim, cfg)
    e = ebitda(con, inicio, fim, cfg)

    v: dict[str, float | None] = {}
    ac, pc, pnc = bp["1.01"], bp["2.01"], bp["2.02"]
    v["liq_corrente"] = razao(ac, pc)
    v["liq_seca"] = razao(ac - bp["1.01.04"] - bp["1.01.07"], pc)
    v["liq_imediata"] = razao(bp["1.01.01"], pc)
    v["liq_geral"] = razao(ac + bp["1.02.01"], pc + pnc)
    divida = bp["2.01.04"] + bp["2.02.01"]
    v["divida_bruta"] = divida / 100
    v["divida_liquida"] = (divida - bp["1.01.01"]) / 100
    v["pl_ativo"] = razao(bp["2.03"], bp["1"])
    v["composicao_endividamento"] = razao(pc, pc + pnc)

    rl = dre["3.01"]
    v["margem_bruta"] = razao(dre["3.03"], rl)
    v["margem_ebitda"] = razao(e["ebitda"], rl)
    v["margem_ebit"] = razao(dre["3.05"], rl)
    v["margem_liquida"] = razao(dre["3.11"], rl)

    # Prazos médios: saldo médio do trimestre contra o fluxo do trimestre
    clientes = (saldo_contas(con, abertura, ("1.1.02.001",)) + saldo_contas(con, fim, ("1.1.02.001",))) / 2
    receita_bruta = -sum(val for _, c, val in partidas(con, inicio, fim) if c == "3.1.01.001")
    estoque = (saldo_contas(con, abertura, ("1.1.03.001", "1.1.03.002"))
               + saldo_contas(con, fim, ("1.1.03.001", "1.1.03.002"))) / 2
    fornecedores = -(saldo_contas(con, abertura, ("2.1.02.001",)) + saldo_contas(con, fim, ("2.1.02.001",))) / 2
    v["pmr"] = razao(clientes * DIAS_TRIMESTRE, receita_bruta)
    v["pme"] = razao(estoque * DIAS_TRIMESTRE, -dre["3.02"])
    v["pmp"] = razao(fornecedores * DIAS_TRIMESTRE, compras_brutas(con, inicio, fim))
    v["ciclo_operacional"] = v["pmr"] + v["pme"]
    v["ciclo_financeiro"] = v["ciclo_operacional"] - v["pmp"]

    # Últimos 12 meses: só quando há 4 trimestres de histórico
    inicio_udm = datas_do_trimestre(anterior(rotulo, 3))[0]
    if inicio_udm >= date(2025, 1, 1):
        dre_udm = resultado(con, inicio_udm, fim, cfg)
        e_udm = ebitda(con, inicio_udm, fim, cfg)
        bp_ini = balanco(con, inicio_udm - timedelta(days=1), cfg)
        pl_medio, ativo_medio = (bp_ini["2.03"] + bp["2.03"]) / 2, (bp_ini["1"] + bp["1"]) / 2
        v["roe"] = razao(dre_udm["3.11"], pl_medio)
        v["roa"] = razao(dre_udm["3.11"], ativo_medio)
        v["giro_ativo"] = razao(dre_udm["3.01"], ativo_medio)
        v["divida_liquida_ebitda"] = razao(divida - bp["1.01.01"], e_udm["ebitda"])
    else:
        v["roe"] = v["roa"] = v["giro_ativo"] = v["divida_liquida_ebitda"] = None
    return v


def serie(con, cfg: dict | None = None, trimestres=TRIMESTRES) -> pd.DataFrame:
    """Tabela longa (indicador x trimestre), pronta para o Power BI (fato_indicador)."""
    cfg = cfg or carregar()
    linhas = []
    for rotulo in trimestres:
        _, fim = datas_do_trimestre(rotulo)
        for codigo, valor in calcular(con, rotulo, cfg).items():
            i = POR_CODIGO[codigo]
            linhas.append({"trimestre": rotulo, "data": fim, "codigo": codigo, "indicador": i.nome,
                           "grupo": i.grupo, "unidade": i.unidade, "valor": valor})
    return pd.DataFrame(linhas)


def reconciliacao_ebitda(con, cfg: dict, trimestres=TRIMESTRES) -> pd.DataFrame:
    tabela = {}
    for rotulo in trimestres:
        tabela[rotulo] = ebitda(con, *datas_do_trimestre(rotulo), cfg)
    # Em float desde o início: a margem é decimal e não cabe numa coluna de inteiros (o pandas
    # novo recusa misturar). Centavos em float continuam exatos até R$ 90 trilhões.
    df = pd.DataFrame(tabela).astype("float64")
    df.loc["margem_ebitda"] = df.loc["ebitda"] / df.loc["receita_liquida"]
    return df


# ---------------------------------------------------------------- análises vertical e horizontal

def analise_vertical_horizontal(tabela: pd.DataFrame, atual: str, comparativo: str,
                                base_codigo: str) -> pd.DataFrame:
    """
    Recebe uma demonstração montada (montar_bp ou montar_dre) e devolve, linha a linha:
    AV = linha / linha-base (ativo total ou receita líquida); AH = variação contra o comparativo.
    """
    t = tabela[["codigo", "descricao", "nivel", atual, comparativo]].copy()
    base = t.set_index("codigo")
    t["av_atual"] = t[atual] / base.loc[base_codigo, atual]
    t["av_comparativo"] = t[comparativo] / base.loc[base_codigo, comparativo]
    t["ah"] = [None if c == 0 else (a - c) / abs(c) for a, c in zip(t[atual], t[comparativo])]
    return t


# ---------------------------------------------------------------- apresentação

def formatar_valor(valor, unidade: str) -> str:
    if valor is None or pd.isna(valor):  # na tabela do pandas, None vira NaN
        return "n.d."
    if unidade == "%":
        return f"{valor:.1%}".replace(".", ",")
    if unidade == "x":
        return f"{valor:.2f}x".replace(".", ",")
    if unidade == "dias":
        return f"{valor:.0f}"
    return formatar(reais_mil(round(valor * 100)))


def main() -> None:
    if not BASE_PADRAO.exists():
        raise SystemExit("Base não encontrada. Rode antes: python src/importar_entrada.py")
    con = sqlite3.connect(BASE_PADRAO)
    cfg = carregar()
    s = serie(con, cfg)
    print("\nINDICADORES (R$ mil quando em valor; n.d. = não disponível, histórico desde jan/2025)")
    print(f"{'':<42}" + "".join(f"{t:>10}" for t in TRIMESTRES))
    for grupo in dict.fromkeys(i.grupo for i in INDICADORES):
        print(f"\n{grupo}")
        for i in [i for i in INDICADORES if i.grupo == grupo]:
            valores = s[s.codigo == i.codigo].set_index("trimestre")["valor"]
            print(f"  {i.nome:<40}" + "".join(f"{formatar_valor(valores[t], i.unidade):>10}"
                                             for t in TRIMESTRES))
    rec = reconciliacao_ebitda(con, cfg)
    print("\nRECONCILIAÇÃO DO EBITDA (Resolução CVM 156) — R$ mil")
    rotulos = {"lucro_liquido": "Lucro líquido", "ir_csll": "(+) IR e CSLL",
               "resultado_financeiro": "(+/-) Resultado financeiro líquido",
               "depreciacao_amortizacao": "(+) Depreciação e amortização", "ebitda": "= EBITDA"}
    print(f"{'':<42}" + "".join(f"{t:>10}" for t in TRIMESTRES))
    for chave, nome in rotulos.items():
        print(f"  {nome:<40}" + "".join(f"{formatar(reais_mil(int(rec.loc[chave, t]))):>10}" for t in TRIMESTRES))
    print(f"  {'Margem EBITDA':<40}" + "".join(f"{formatar_valor(rec.loc['margem_ebitda', t], '%'):>10}"
                                               for t in TRIMESTRES))
    con.close()


if __name__ == "__main__":
    main()
