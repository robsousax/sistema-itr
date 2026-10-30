"""
Testes da DFC e da DMPL (Etapa 6), sobre a Orbe gerada na Etapa 4.

Conferem as conciliações (indireto x direto, DFC x caixa do BP, DMPL x PL do BP), linhas que
dá para saber de antemão pelo roteiro (compras de bens, captação, dividendos) e se um erro de
classificação plantado de propósito é denunciado.
"""
import sqlite3
from datetime import date, timedelta

import pytest

from checar_config import carregar
from demonstracoes import balanco, resultado, saldos_em
from dfc_dmpl import (caixa_em, conferir_dfc, conferir_dmpl, dfc, dmpl, montar_dfc, montar_dmpl,
                      transacoes_sem_caixa)
from gerar_dados import gerar
from gerar_modelo_entrada import gerar_modelo
from importar_entrada import importar

PERIODOS = {
    "9M25": (date(2025, 1, 1), date(2025, 9, 30)),
    "2025": (date(2025, 1, 1), date(2025, 12, 31)),
    "9M26": (date(2026, 1, 1), date(2026, 9, 30)),
    "3T26": (date(2026, 7, 1), date(2026, 9, 30)),
}


@pytest.fixture(scope="module")
def cfg():
    return carregar()


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("dfc_dmpl")
    arquivo = gerar_modelo(pasta / "entrada_itr.xlsx", gerar().quadros())
    base = pasta / "itr.sqlite"
    assert importar(arquivo, base)[0] == []
    conexao = sqlite3.connect(base)
    yield conexao
    conexao.close()


def mil(reais: float) -> int:
    return round(reais * 100)


# ---------------------------------------------------------------- DFC: conciliações

@pytest.mark.parametrize("periodo", PERIODOS)
def test_dfc_confere(con, cfg, periodo):
    assert conferir_dfc(con, *PERIODOS[periodo], cfg) == []


@pytest.mark.parametrize("periodo", PERIODOS)
def test_saldo_inicial_e_final_batem_com_o_bp(con, cfg, periodo):
    inicio, fim = PERIODOS[periodo]
    d = dfc(con, inicio, fim, cfg)
    assert d["6.05.01"] == balanco(con, inicio - timedelta(days=1), cfg)["1.01.01"]
    assert d["6.05.02"] == balanco(con, fim, cfg)["1.01.01"]
    assert d["6.05"] == d["6.01"] + d["6.02"] + d["6.03"]


def test_dfc_comeca_pelo_lucro_da_dre(con, cfg):
    inicio, fim = PERIODOS["9M26"]
    assert dfc(con, inicio, fim, cfg)["6.01.01.01"] == resultado(con, inicio, fim, cfg)["3.11"]


def test_variacao_de_fornecedores_e_a_variacao_do_balanco(con, cfg):
    # Fornecedores não tem eventos fora do giro: a linha da DFC é a variação pura do BP
    inicio, fim = PERIODOS["9M26"]
    contas = ("2.1.02.001", "2.1.02.002")
    antes, depois = saldos_em(con, date(2025, 12, 31)), saldos_em(con, fim)
    variacao = -sum(depois.get(c, 0) - antes.get(c, 0) for c in contas)
    assert dfc(con, inicio, fim, cfg)["6.01.02.05"] == variacao


def test_baixa_de_incobravel_nao_vira_recebimento(con, cfg):
    # Contas a receber na DFC = -(variação de clientes + baixas contra a provisão)
    inicio, fim = PERIODOS["9M26"]
    antes, depois = saldos_em(con, date(2025, 12, 31)), saldos_em(con, fim)
    baixas, = con.execute("SELECT SUM(credito_centavos) FROM lancamento WHERE codigo_evento = "
                          "'EV27' AND data BETWEEN ? AND ?", (inicio.isoformat(), fim.isoformat())
                          ).fetchone()
    variacao = depois["1.1.02.001"] - antes["1.1.02.001"]
    assert dfc(con, inicio, fim, cfg)["6.01.02.01"] == -(variacao + baixas)


# ---------------------------------------------------------------- DFC: linhas conhecidas pelo roteiro

def test_investimentos_de_2026(con, cfg):
    d = dfc(con, *PERIODOS["9M26"], cfg)
    assert d["6.02.01"] == -mil(2_300_000)   # obra do galpão (2,0 mi) + porta-paletes (0,3 mi)
    assert d["6.02.02"] == mil(90_000)       # venda dos utilitários
    assert d["6.02.03"] == -mil(240_000)     # módulo WMS do ERP


def test_finame_nao_passa_pela_dfc(con, cfg):
    d = dfc(con, *PERIODOS["9M25"], cfg)
    assert d["6.03.01"] == 0                  # o banco pagou o fornecedor direto
    assert d["6.02.01"] == -mil(150_000)      # só os notebooks à vista
    sem_caixa = transacoes_sem_caixa(con, *PERIODOS["9M25"])
    assert sum(t["valor"] for t in sem_caixa) == mil(4_000_000)
    assert {t["evento"] for t in sem_caixa} == {"EV45"}


def test_compra_a_prazo_aparece_quando_e_paga(con, cfg):
    sem_caixa = transacoes_sem_caixa(con, *PERIODOS["9M26"])
    assert [(t["evento"], t["valor"]) for t in sem_caixa] == [("EV43", mil(300_000))]


def test_financiamentos_de_2026(con, cfg):
    d = dfc(con, *PERIODOS["9M26"], cfg)
    assert d["6.03.01"] == mil(8_000_000)     # CCB
    dividendo_2025, = con.execute("SELECT credito_centavos FROM lancamento WHERE codigo_evento = "
                                  "'EV54' AND codigo_conta = '2.1.05.001'").fetchone()
    assert d["6.03.05"] == -dividendo_2025
    assert d["6.03.03"] == -d["6.01.01.07"]   # juros apropriados e pagos no mesmo dia


# ---------------------------------------------------------------- DFC: erro plantado

def test_classificacao_errada_e_denunciada(con, cfg):
    # Marcar a baixa de incobrável como se fosse capital de giro faz o indireto mostrar um
    # recebimento que nunca entrou no banco
    errado = {k: v.copy() for k, v in cfg.items()}
    mev = errado["map_evento_df"]
    mev.loc[mev.codigo_evento == "EV27", "exclui_do_giro"] = "N"
    problemas = conferir_dfc(con, *PERIODOS["9M26"], errado)
    assert any("indireto x direto" in p for p in problemas)


# ---------------------------------------------------------------- DMPL

@pytest.mark.parametrize("periodo", PERIODOS)
def test_dmpl_confere_com_o_bp(con, cfg, periodo):
    assert conferir_dmpl(con, *PERIODOS[periodo], cfg) == []


def test_dmpl_de_2025_mostra_as_destinacoes(con, cfg):
    t = dmpl(con, *PERIODOS["2025"], cfg).set_index("codigo")
    lucro = resultado(con, *PERIODOS["2025"], cfg)["3.11"]
    dividendo, = con.execute("SELECT credito_centavos FROM lancamento WHERE codigo_evento = "
                             "'EV54' AND codigo_conta = '2.1.05.001'").fetchone()
    assert t.loc["5.05.01", "LACUM"] == lucro
    assert t.loc["5.04.06", "LACUM"] == -dividendo
    assert t.loc["5.06.01", "RLUC"] == lucro - dividendo       # reserva legal + retenção
    assert t.loc["5.06.01", "PL"] == 0                          # mutação interna não muda o PL
    assert t.loc["5.07", "LACUM"] == 0                          # lucro todo destinado


def test_dmpl_de_2026_so_tem_o_lucro(con, cfg):
    t = dmpl(con, *PERIODOS["9M26"], cfg).set_index("codigo")
    movimentos = t.loc[["5.04.01", "5.04.06", "5.05.02", "5.06.01", "5.06.02"], "PL"]
    assert (movimentos == 0).all()
    assert t.loc["5.07", "PL"] - t.loc["5.01", "PL"] == t.loc["5.05.01", "PL"]


def test_dmpl_saldo_inicial_e_o_pl_do_fim_do_ano_anterior(con, cfg):
    t = dmpl(con, *PERIODOS["9M26"], cfg).set_index("codigo")
    assert t.loc["5.01", "PL"] == balanco(con, date(2025, 12, 31), cfg)["2.03"]


def test_evento_no_pl_sem_linha_da_dmpl_e_denunciado(con, cfg):
    errado = {k: v.copy() for k, v in cfg.items()}
    mev = errado["map_evento_df"]
    mev.loc[mev.codigo_evento == "EV54", "dmpl_linha"] = ""
    with pytest.raises(ValueError, match="EV54"):
        dmpl(con, *PERIODOS["2025"], errado)


# ---------------------------------------------------------------- montagem

def test_itr_traz_os_acumulados_do_cpc_21(con, cfg):
    assert list(montar_dfc(con, "3T26", cfg).columns[3:]) == ["9M26", "9M25"]
    assert list(montar_dmpl(con, "3T26", cfg)) == ["9M26", "9M25"]
    assert caixa_em(con, date(2026, 9, 30), cfg) == balanco(con, date(2026, 9, 30), cfg)["1.01.01"]
