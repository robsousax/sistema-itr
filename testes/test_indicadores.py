"""
Testes dos indicadores (Etapa 8), sobre a Orbe gerada na Etapa 4.

Cada fórmula é refeita "à mão" a partir do BP e da DRE do motor e comparada com o indicador.
Depois, a história do roteiro: o que deveria acontecer com prazos e margens em cada trimestre.
"""
import sqlite3
from datetime import date

import pytest

from checar_config import carregar
from demonstracoes import balanco, montar_bp, montar_dre, resultado
from gerar_dados import gerar
from gerar_modelo_entrada import gerar_modelo
from importar_entrada import importar
from indicadores import (INDICADORES, TRIMESTRES, analise_vertical_horizontal, anterior, calcular,
                         datas_do_trimestre, ebitda, formatar_valor, reconciliacao_ebitda, serie)


@pytest.fixture(scope="module")
def cfg():
    return carregar()


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("indicadores")
    arquivo = gerar_modelo(pasta / "entrada_itr.xlsx", gerar().quadros())
    base = pasta / "itr.sqlite"
    assert importar(arquivo, base)[0] == []
    conexao = sqlite3.connect(base)
    yield conexao
    conexao.close()


@pytest.fixture(scope="module")
def ind(con, cfg):
    return {t: calcular(con, t, cfg) for t in TRIMESTRES}


# ---------------------------------------------------------------- períodos

def test_datas_dos_trimestres():
    assert datas_do_trimestre("4T25") == (date(2025, 10, 1), date(2025, 12, 31))
    assert datas_do_trimestre("1T26") == (date(2026, 1, 1), date(2026, 3, 31))
    assert anterior("1T26") == "4T25" and anterior("3T26", 3) == "4T25"


# ---------------------------------------------------------------- fórmulas refeitas à mão

def test_liquidez(con, cfg, ind):
    bp = balanco(con, date(2026, 9, 30), cfg)
    v = ind["3T26"]
    assert v["liq_corrente"] == pytest.approx(bp["1.01"] / bp["2.01"])
    assert v["liq_seca"] == pytest.approx((bp["1.01"] - bp["1.01.04"] - bp["1.01.07"]) / bp["2.01"])
    assert v["liq_imediata"] == pytest.approx(bp["1.01.01"] / bp["2.01"])
    assert v["liq_geral"] == pytest.approx((bp["1.01"] + bp["1.02.01"]) / (bp["2.01"] + bp["2.02"]))


def test_endividamento(con, cfg, ind):
    bp = balanco(con, date(2026, 9, 30), cfg)
    v = ind["3T26"]
    divida = bp["2.01.04"] + bp["2.02.01"]
    assert v["divida_bruta"] == pytest.approx(divida / 100)
    assert v["divida_liquida"] == pytest.approx((divida - bp["1.01.01"]) / 100)
    assert v["pl_ativo"] == pytest.approx(bp["2.03"] / bp["1"])


def test_margens(con, cfg, ind):
    dre = resultado(con, date(2026, 7, 1), date(2026, 9, 30), cfg)
    v = ind["3T26"]
    assert v["margem_bruta"] == pytest.approx(dre["3.03"] / dre["3.01"])
    assert v["margem_ebit"] == pytest.approx(dre["3.05"] / dre["3.01"])
    assert v["margem_liquida"] == pytest.approx(dre["3.11"] / dre["3.01"])


def test_ebitda_e_ebit_mais_depreciacao(con, cfg):
    # Dois caminhos para o mesmo número: de cima (EBIT + D&A) e de baixo (Res. CVM 156)
    inicio, fim = datas_do_trimestre("3T26")
    e = ebitda(con, inicio, fim, cfg)
    dre = resultado(con, inicio, fim, cfg)
    assert e["ebitda"] == dre["3.05"] + e["depreciacao_amortizacao"]
    assert e["ebitda"] == (e["lucro_liquido"] + e["ir_csll"] + e["resultado_financeiro"]
                           + e["depreciacao_amortizacao"])


def test_depreciacao_do_ebitda_igual_a_da_dfc(con, cfg):
    from dfc_dmpl import dfc
    inicio, fim = date(2026, 1, 1), date(2026, 9, 30)
    assert ebitda(con, inicio, fim, cfg)["depreciacao_amortizacao"] == dfc(con, inicio, fim, cfg)["6.01.01.02"]


def test_roe_usa_lucro_dos_ultimos_12_meses_e_pl_medio(con, cfg, ind):
    lucro = resultado(con, date(2025, 10, 1), date(2026, 9, 30), cfg)["3.11"]
    pl_ini = balanco(con, date(2025, 9, 30), cfg)["2.03"]
    pl_fim = balanco(con, date(2026, 9, 30), cfg)["2.03"]
    assert ind["3T26"]["roe"] == pytest.approx(lucro / ((pl_ini + pl_fim) / 2))


def test_indicadores_udm_nao_inventam_historico(ind):
    # Antes do 4T25 não há 12 meses de dados: o valor fica vazio, não é anualizado
    for t in ("1T25", "2T25", "3T25"):
        assert ind[t]["roe"] is None and ind[t]["divida_liquida_ebitda"] is None
    assert ind["4T25"]["roe"] is not None


def test_ciclo_financeiro(ind):
    v = ind["3T26"]
    assert v["ciclo_operacional"] == pytest.approx(v["pmr"] + v["pme"])
    assert v["ciclo_financeiro"] == pytest.approx(v["pmr"] + v["pme"] - v["pmp"])


def test_serie_tem_todos_os_indicadores_e_trimestres(con, cfg):
    s = serie(con, cfg)
    assert len(s) == len(INDICADORES) * len(TRIMESTRES)
    assert set(s.codigo) == {i.codigo for i in INDICADORES}


def test_reconciliacao_do_ebitda_por_trimestre(con, cfg):
    rec = reconciliacao_ebitda(con, cfg)
    for t in TRIMESTRES:
        partes = rec.loc[["lucro_liquido", "ir_csll", "resultado_financeiro",
                          "depreciacao_amortizacao"], t].sum()
        assert rec.loc["ebitda", t] == partes


# ---------------------------------------------------------------- a história do roteiro

def test_inadimplencia_alonga_o_prazo_de_recebimento_no_1t26(ind):
    assert ind["1T26"]["pmr"] > ind["4T25"]["pmr"] + 3


def test_margem_ebitda_cai_na_expansao_e_volta_com_a_eficiencia(ind):
    assert ind["4T25"]["margem_ebitda"] < ind["3T25"]["margem_ebitda"] - 0.01
    assert ind["2T26"]["margem_ebitda"] > ind["1T26"]["margem_ebitda"] + 0.01


def test_ccb_aumenta_divida_mas_a_orbe_segue_com_caixa_liquido(ind):
    assert ind["3T26"]["divida_bruta"] > ind["2T26"]["divida_bruta"] * 2
    assert ind["3T26"]["divida_liquida"] < 0  # mais caixa do que dívida
    assert ind["3T26"]["pl_ativo"] < ind["2T26"]["pl_ativo"]  # alavancagem sobe


# ---------------------------------------------------------------- análises vertical e horizontal

def test_analise_vertical_do_bp_soma_100_por_cento(con, cfg):
    bp = montar_bp(con, "3T26", cfg)
    av = analise_vertical_horizontal(bp, "30/09/2026", "31/12/2025", "1").set_index("codigo")
    assert av.loc["1", "av_atual"] == 1
    assert av.loc["1.01", "av_atual"] + av.loc["1.02", "av_atual"] == pytest.approx(1)


def test_analise_horizontal_da_dre(con, cfg):
    dre, _ = montar_dre(con, "3T26", cfg)
    ah = analise_vertical_horizontal(dre, "3T26", "3T25", "3.01").set_index("codigo")
    receita = dre.set_index("codigo").loc["3.01"]
    assert ah.loc["3.01", "ah"] == pytest.approx((receita["3T26"] - receita["3T25"]) / receita["3T25"])
    assert ah.loc["3.01", "av_atual"] == 1


@pytest.mark.parametrize("valor,unidade,texto", [(0.2961, "%", "29,6%"), (2.1849, "x", "2,18x"),
                                                 (47.4, "dias", "47"), (None, "%", "n.d."),
                                                 (12_060_000.0, "R$", "12.060")])
def test_formatacao(valor, unidade, texto):
    assert formatar_valor(valor, unidade) == texto
