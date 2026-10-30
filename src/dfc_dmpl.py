"""
Motor da DFC e da DMPL (Etapa 6).

DFC — método indireto (CPC 03), conferido pelo método direto:
  6.01.01  lucro do período + ajustes (contas de resultado com linha 6.01.01.xx no mapeamento)
  6.01.02  variação do capital de giro (contas com linha 6.01.02.xx), sem os eventos marcados
           como "fora do giro" (baixas de incobrável e de estoque perdido)
  6.01.03, 6.02, 6.03  perna de caixa de cada lançamento cujo evento tem linha de DFC
  6.05     variação do caixa; saldo inicial e final
  Conferências: o operacional pelo indireto tem de ser igual à soma do dinheiro que entrou e saiu
  nos eventos operacionais (método direto), e o saldo final tem de ser igual ao caixa do BP.

DMPL — por coluna (capital, reservas de capital, reservas de lucros, lucros acumulados, ORA):
  saldo inicial = PL do BP no dia anterior ao período; movimentos pela linha da DMPL de cada evento;
  lucro do período vindo da DRE; saldo final conferido com o PL do BP, coluna por coluna.

Uso:
    python src/dfc_dmpl.py           # DFC e DMPL do ITR do 3T26 (acumulados 9M26 e 9M25)
    python src/dfc_dmpl.py 2T26
"""
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd

from checar_config import carregar
from demonstracoes import (BASE_PADRAO, calcular_linhas, formatar, linhas_da, periodos_itr,
                           reais_mil, resultado, saldos_em)

# Compras de ativos que não passam pelo caixa: não entram na DFC e são divulgadas em nota
# (CPC 03, item 43). EV43: compra a prazo com o fornecedor; EV45: compra financiada via FINAME.
TRANSACOES_SEM_CAIXA = {"EV43", "EV45"}


def partidas(con: sqlite3.Connection, inicio: date, fim: date) -> list[tuple[str, str, int]]:
    """(evento, conta, débito - crédito) de cada partida do período, sem o encerramento (EV52)."""
    sql = """SELECT codigo_evento, codigo_conta, debito_centavos - credito_centavos
               FROM lancamento
              WHERE data BETWEEN ? AND ? AND codigo_evento <> 'EV52'"""
    return con.execute(sql, (inicio.isoformat(), fim.isoformat())).fetchall()


def mapas(cfg: dict) -> tuple[dict, dict]:
    linha_dfc = cfg["map_conta_df"].set_index("codigo_conta")["linha_dfc"].to_dict()
    eventos = cfg["map_evento_df"].set_index("codigo_evento").to_dict("index")
    return linha_dfc, eventos


# ---------------------------------------------------------------- DFC

def caixa_em(con, data: date, cfg: dict) -> int:
    linha_dfc, _ = mapas(cfg)
    return sum(v for c, v in saldos_em(con, data).items() if linha_dfc.get(c) == "CAIXA")


def dfc(con: sqlite3.Connection, inicio: date, fim: date, cfg: dict) -> dict[str, int]:
    """DFC pelo método indireto. Entradas de caixa positivas, saídas negativas."""
    linha_dfc, eventos = mapas(cfg)
    dados: dict[str, int] = defaultdict(int)
    dados["6.01.01.01"] = resultado(con, inicio, fim, cfg)["3.11"]
    for evento, conta, valor in partidas(con, inicio, fim):
        linha = linha_dfc[conta]
        if conta.startswith("3") and linha:
            # Despesa que não saiu do caixa volta somando; ganho que não entrou volta subtraindo
            dados[linha] += valor
        elif linha.startswith("6.01.02") and eventos[evento]["exclui_do_giro"] == "N":
            # Ativo que aumenta consome caixa; passivo que aumenta gera caixa
            dados[linha] -= valor
        elif linha == "CAIXA" and eventos[evento]["dfc_linha_caixa"]:
            dados[eventos[evento]["dfc_linha_caixa"]] += valor
    dados["6.05.01"] = caixa_em(con, inicio - timedelta(days=1), cfg)
    return calcular_linhas(linhas_da("DFC", cfg), dict(dados))


def fluxo_direto(con, inicio: date, fim: date, cfg: dict) -> dict[str, int]:
    """Dinheiro que entrou e saiu, por classe do evento (método direto)."""
    linha_dfc, eventos = mapas(cfg)
    por_classe: dict[str, int] = defaultdict(int)
    for evento, conta, valor in partidas(con, inicio, fim):
        if linha_dfc[conta] == "CAIXA":
            por_classe[eventos[evento]["dfc_classe"] or "entre_contas_de_caixa"] += valor
    return dict(por_classe)


def conferir_dfc(con, inicio: date, fim: date, cfg: dict) -> list[str]:
    """Conciliações da DFC. Lista vazia = DFC confere."""
    d = dfc(con, inicio, fim, cfg)
    direto = fluxo_direto(con, inicio, fim, cfg)
    problemas = []

    def confere(descricao, a, b):
        if a != b:
            problemas.append(f"{descricao}: {a / 100:,.2f} x {b / 100:,.2f} (diferença "
                             f"{(a - b) / 100:,.2f})")

    confere("Operacional indireto x direto", d["6.01"], direto.get("operacional", 0))
    confere("Investimento x pernas de caixa", d["6.02"], direto.get("investimento", 0))
    confere("Financiamento x pernas de caixa", d["6.03"], direto.get("financiamento", 0))
    confere("Movimentos entre contas de caixa", direto.get("entre_contas_de_caixa", 0), 0)
    confere("Saldo final x caixa do BP", d["6.05.02"], caixa_em(con, fim, cfg))
    return problemas


def transacoes_sem_caixa(con, inicio: date, fim: date) -> list[dict]:
    """Compras de ativos sem caixa no período, para divulgação (CPC 03, item 43)."""
    sql = f"""SELECT data, codigo_evento, historico, SUM(debito_centavos)
                FROM lancamento
               WHERE data BETWEEN ? AND ?
                 AND codigo_evento IN ({','.join('?' * len(TRANSACOES_SEM_CAIXA))})
               GROUP BY id_lancamento ORDER BY data"""
    linhas = con.execute(sql, (inicio.isoformat(), fim.isoformat(), *sorted(TRANSACOES_SEM_CAIXA)))
    return [{"data": d, "evento": e, "historico": h, "valor": v} for d, e, h, v in linhas]


# ---------------------------------------------------------------- DMPL

def pl_por_coluna(con, data: date, cfg: dict) -> dict[str, int]:
    """PL numa data, por coluna da DMPL (crédito positivo). Resultado não encerrado em LACUM."""
    coluna = cfg["map_conta_df"].set_index("codigo_conta")["coluna_dmpl"].to_dict()
    saldos = saldos_em(con, data)
    colunas: dict[str, int] = defaultdict(int)
    for conta, valor in saldos.items():
        if conta.startswith("2.3"):
            colunas[coluna[conta]] -= valor
        elif conta.startswith("3"):
            colunas["LACUM"] -= valor
    return dict(colunas)


def dmpl(con: sqlite3.Connection, inicio: date, fim: date, cfg: dict) -> pd.DataFrame:
    """DMPL do período: linhas da CVM x colunas da DMPL, em centavos."""
    coluna_da_conta = cfg["map_conta_df"].set_index("codigo_conta")["coluna_dmpl"].to_dict()
    _, eventos = mapas(cfg)
    colunas = [c for c in cfg["dim_coluna_dmpl"]["codigo"] if c != "PL"]
    linhas = linhas_da("DMPL", cfg)

    dados = {c: defaultdict(int) for c in colunas}
    for c, valor in pl_por_coluna(con, inicio - timedelta(days=1), cfg).items():
        dados[c]["5.01"] += valor
    dados["LACUM"]["5.05.01"] += resultado(con, inicio, fim, cfg)["3.11"]
    for evento, conta, valor in partidas(con, inicio, fim):
        if not conta.startswith("2.3"):
            continue
        linha = eventos[evento]["dmpl_linha"]
        if not linha:
            raise ValueError(f"Evento {evento} movimenta o PL sem linha da DMPL")
        if linha != "IGNORAR":
            dados[coluna_da_conta[conta]][linha] -= valor

    tabela = linhas[["codigo", "descricao", "nivel"]].copy()
    for c in colunas:
        valores = calcular_linhas(linhas, dict(dados[c]))
        tabela[c] = tabela.codigo.map(valores).fillna(0).astype("int64")
    tabela["PL"] = tabela[colunas].sum(axis=1)
    return tabela


def conferir_dmpl(con, inicio: date, fim: date, cfg: dict) -> list[str]:
    """Saldo final de cada coluna da DMPL = PL do BP na data final."""
    tabela = dmpl(con, inicio, fim, cfg).set_index("codigo")
    bp = pl_por_coluna(con, fim, cfg)
    problemas = []
    for c in tabela.columns:
        if c in ("descricao", "nivel", "PL"):
            continue
        if tabela.loc["5.07", c] != bp.get(c, 0):
            problemas.append(f"DMPL coluna {c}: saldo final {tabela.loc['5.07', c] / 100:,.2f} "
                             f"x BP {bp.get(c, 0) / 100:,.2f}")
    if tabela.loc["5.07", "PL"] != sum(bp.values()):
        problemas.append("DMPL: PL total diferente do BP")
    return problemas


# ---------------------------------------------------------------- montagem e apresentação

def montar_dfc(con, trimestre: str, cfg: dict | None = None) -> pd.DataFrame:
    cfg = cfg or carregar()
    p = periodos_itr(trimestre)
    tabela = linhas_da("DFC", cfg)[["codigo", "descricao", "nivel"]].copy()
    for chave in ("acum_atual", "acum_anterior"):
        per = p[chave]
        valores = dfc(con, per.inicio, per.fim, cfg)
        tabela[per.rotulo] = tabela.codigo.map(valores).fillna(0).astype("int64")
    return tabela


def montar_dmpl(con, trimestre: str, cfg: dict | None = None) -> dict[str, pd.DataFrame]:
    cfg = cfg or carregar()
    p = periodos_itr(trimestre)
    return {p[k].rotulo: dmpl(con, p[k].inicio, p[k].fim, cfg) for k in ("acum_atual", "acum_anterior")}


def imprimir_tabela(titulo: str, tabela: pd.DataFrame) -> None:
    colunas = [c for c in tabela.columns if c not in ("codigo", "descricao", "nivel")]
    print(f"\n{titulo} (R$ mil)")
    print(f"{'Código':<12}{'Descrição':<52}" + "".join(f"{c:>11}" for c in colunas))
    for _, l in tabela.iterrows():
        descricao = ("  " * (int(l.nivel) - 1) + l.descricao)[:50]
        print(f"{l.codigo:<12}{descricao:<52}"
              + "".join(f"{formatar(reais_mil(l[c])):>11}" for c in colunas))


def main() -> None:
    trimestre = sys.argv[1] if len(sys.argv) > 1 else "3T26"
    if not BASE_PADRAO.exists():
        raise SystemExit("Base não encontrada. Rode antes: python src/importar_entrada.py")
    con = sqlite3.connect(BASE_PADRAO)
    cfg = carregar()
    p = periodos_itr(trimestre)
    imprimir_tabela("DEMONSTRAÇÃO DOS FLUXOS DE CAIXA — MÉTODO INDIRETO", montar_dfc(con, trimestre, cfg))
    for rotulo, tabela in montar_dmpl(con, trimestre, cfg).items():
        imprimir_tabela(f"DEMONSTRAÇÃO DAS MUTAÇÕES DO PATRIMÔNIO LÍQUIDO — {rotulo}", tabela)
    print("\nConferências")
    for chave in ("acum_atual", "acum_anterior"):
        per = p[chave]
        problemas = conferir_dfc(con, per.inicio, per.fim, cfg) + conferir_dmpl(con, per.inicio, per.fim, cfg)
        print(f"  {per.rotulo}: " + ("DFC e DMPL conferem" if not problemas else "; ".join(problemas)))
        for t in transacoes_sem_caixa(con, per.inicio, per.fim):
            print(f"    Transação sem caixa ({t['evento']}, {t['data']}): {t['historico']}: "
                  f"R$ {formatar(reais_mil(t['valor']))} mil")
    con.close()


if __name__ == "__main__":
    main()
