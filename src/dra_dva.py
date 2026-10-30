"""
Motor da DRA e da DVA (Etapa 7).

DRA (CPC 26): lucro do período + outros resultados abrangentes. A Orbe não tem ORA na V1, mas a
linha existe e é calculada pelo movimento da conta de ORA; zerada, ela aparece zerada.

DVA (CPC 09): quanto de riqueza a empresa gerou e como distribuiu.
  Geração (7.01 a 7.06): receitas pelo valor bruto, menos insumos de terceiros e depreciação,
  mais o que foi recebido em transferência (receitas financeiras).
  Distribuição (7.08): pessoal, governo (tributos), financiadores (juros, aluguéis) e acionistas
  (dividendos e lucros retidos).

Ajuste exigido pelo CPC 09 (item 14): os insumos aparecem COM os tributos recuperáveis (ICMS,
PIS e COFINS). Como o estoque é registrado líquido desses tributos, o motor soma aos insumos os
créditos tomados nas compras do período e tira o mesmo valor dos tributos distribuídos, que assim
ficam pelo valor líquido (débitos sobre vendas menos créditos sobre compras).

Conferência: 7.07 (valor adicionado a distribuir) = 7.08 (distribuição).

Uso:
    python src/dra_dva.py           # DRA e DVA do ITR do 3T26
"""
import sqlite3
import sys
from collections import defaultdict
from datetime import date

import pandas as pd

from checar_config import carregar
from demonstracoes import (BASE_PADRAO, calcular_linhas, linhas_da, periodos_itr, resultado)
from dfc_dmpl import imprimir_tabela, partidas

CONTA_ORA = "2.3.04.001"
# Créditos de tributos nas compras (EV09) e a linha da DVA de onde eles saem na distribuição
CREDITOS_NAS_COMPRAS = {"1.1.04.001": "7.08.02.02",   # ICMS: estadual
                        "1.1.04.002": "7.08.02.01",   # PIS: federal
                        "1.1.04.003": "7.08.02.01"}   # COFINS: federal
LINHA_INSUMOS = "7.02.01"


def dra(con, inicio: date, fim: date, cfg: dict) -> dict[str, int]:
    """4.01 vem da DRE; 4.02 é o movimento da conta de ORA no período; 4.03 = 4.01 + 4.02."""
    lucro = resultado(con, inicio, fim, cfg)["3.11"]
    ora = -sum(v for _, conta, v in partidas(con, inicio, fim) if conta == CONTA_ORA)
    return {"4.01": lucro, "4.02": ora, "4.03": lucro + ora}


def dva(con, inicio: date, fim: date, cfg: dict) -> dict[str, int]:
    """DVA do período. Geração com sinal da riqueza (insumos negativos); distribuição positiva."""
    linha_dva = cfg["map_conta_df"].set_index("codigo_conta")["linha_dva"].to_dict()
    regra_evento = cfg["map_evento_df"].set_index("codigo_evento")["dva_regra"].to_dict()
    dados: dict[str, int] = defaultdict(int)
    for evento, conta, valor in partidas(con, inicio, fim):
        if conta.startswith("3"):
            linha = linha_dva[conta]
            # Distribuição: despesa (débito) é riqueza entregue, positiva.
            # Geração: receita (crédito) positiva, insumo (débito) negativo.
            dados[linha] += valor if linha.startswith("7.08") else -valor
        elif evento == "EV09" and conta in CREDITOS_NAS_COMPRAS and valor > 0:
            dados[LINHA_INSUMOS] -= valor
            dados[CREDITOS_NAS_COMPRAS[conta]] -= valor
        elif regra_evento.get(evento, "").startswith("7.08.04") and conta.startswith("2.3"):
            # Dividendos do período, contados pela saída de lucros acumulados
            dados[regra_evento[evento]] += valor
    lucro = resultado(con, inicio, fim, cfg)["3.11"]
    dados["7.08.04.03"] = lucro - dados["7.08.04.02"]  # lucros retidos
    return calcular_linhas(linhas_da("DVA", cfg), dict(dados))


def conferir_dva(con, inicio: date, fim: date, cfg: dict) -> list[str]:
    d = dva(con, inicio, fim, cfg)
    problemas = []
    if d["7.07"] != d["7.08"]:
        problemas.append(f"DVA: a distribuir {d['7.07'] / 100:,.2f} x distribuído "
                         f"{d['7.08'] / 100:,.2f}")
    lucro = resultado(con, inicio, fim, cfg)["3.11"]
    if d["7.08.04"] != lucro:
        problemas.append("DVA: remuneração de capitais próprios diferente do lucro da DRE")
    return problemas


def montar(con, trimestre: str, cfg: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """DRA (trimestre e acumulado, atual e anterior) e DVA (acumulados), como no ITR."""
    cfg = cfg or carregar()
    p = periodos_itr(trimestre)
    tab_dra = linhas_da("DRA", cfg)[["codigo", "descricao", "nivel"]].copy()
    for chave in ("tri_atual", "acum_atual", "tri_anterior", "acum_anterior"):
        valores = dra(con, p[chave].inicio, p[chave].fim, cfg)
        tab_dra[p[chave].rotulo] = tab_dra.codigo.map(valores).fillna(0).astype("int64")
    tab_dva = linhas_da("DVA", cfg)[["codigo", "descricao", "nivel"]].copy()
    for chave in ("acum_atual", "acum_anterior"):
        valores = dva(con, p[chave].inicio, p[chave].fim, cfg)
        tab_dva[p[chave].rotulo] = tab_dva.codigo.map(valores).fillna(0).astype("int64")
    return tab_dra, tab_dva


def main() -> None:
    trimestre = sys.argv[1] if len(sys.argv) > 1 else "3T26"
    if not BASE_PADRAO.exists():
        raise SystemExit("Base não encontrada. Rode antes: python src/importar_entrada.py")
    con = sqlite3.connect(BASE_PADRAO)
    cfg = carregar()
    tab_dra, tab_dva = montar(con, trimestre, cfg)
    imprimir_tabela("DEMONSTRAÇÃO DO RESULTADO ABRANGENTE", tab_dra)
    imprimir_tabela("DEMONSTRAÇÃO DO VALOR ADICIONADO", tab_dva)
    p = periodos_itr(trimestre)
    print("\nConferências")
    for chave in ("acum_atual", "acum_anterior"):
        problemas = conferir_dva(con, p[chave].inicio, p[chave].fim, cfg)
        print(f"  {p[chave].rotulo}: " + ("DVA confere" if not problemas else "; ".join(problemas)))
    con.close()


if __name__ == "__main__":
    main()
