"""
Testes da configuração contábil (Etapa 2).

O primeiro teste garante que a configuração real está OK. Os demais estragam a configuração de
propósito e conferem se o verificador percebe. Um verificador que nunca reclama não prova nada.
"""
import pytest

from checar_config import carregar, checar


@pytest.fixture
def cfg():
    # Cada teste recebe uma cópia nova, para um teste não contaminar o outro
    return {nome: df.copy() for nome, df in carregar().items()}


def test_configuracao_real_esta_ok(cfg):
    assert checar(cfg) == []


def test_conta_analitica_sem_mapeamento_e_detectada(cfg):
    mapa = cfg["map_conta_df"]
    cfg["map_conta_df"] = mapa[mapa["codigo_conta"] != "1.1.02.001"]
    assert any("1.1.02.001 sem mapeamento" in e for e in checar(cfg))


def test_conta_do_ativo_mapeada_no_passivo_e_detectada(cfg):
    mapa = cfg["map_conta_df"]
    mapa.loc[mapa["codigo_conta"] == "1.1.03.001", "linha_bp_dre"] = "2.01.02.01"
    assert any("1.1.03.001" in e and "grupo 1" in e for e in checar(cfg))


def test_linha_de_dfc_inexistente_e_detectada(cfg):
    mapa = cfg["map_conta_df"]
    mapa.loc[mapa["codigo_conta"] == "1.1.02.001", "linha_dfc"] = "6.01.02.99"
    assert any("1.1.02.001" in e and "linha_dfc" in e for e in checar(cfg))


def test_despesa_sem_linha_de_dva_e_detectada(cfg):
    mapa = cfg["map_conta_df"]
    mapa.loc[mapa["codigo_conta"] == "3.3.02.008", "linha_dva"] = ""
    assert any("3.3.02.008" in e and "DVA" in e for e in checar(cfg))


def test_conta_do_pl_sem_coluna_da_dmpl_e_detectada(cfg):
    mapa = cfg["map_conta_df"]
    mapa.loc[mapa["codigo_conta"] == "2.3.02.001", "coluna_dmpl"] = ""
    assert any("2.3.02.001" in e and "DMPL" in e for e in checar(cfg))


def test_evento_que_mexe_no_pl_sem_linha_da_dmpl_e_detectado(cfg):
    mev = cfg["map_evento_df"]
    mev.loc[mev["codigo_evento"] == "EV53", "dmpl_linha"] = ""
    assert any("EV53" in e and "DMPL" in e for e in checar(cfg))


def test_evento_de_investimento_em_linha_de_financiamento_e_detectado(cfg):
    # O erro da máquina: classificar compra de imobilizado como financiamento
    mev = cfg["map_evento_df"]
    mev.loc[mev["codigo_evento"] == "EV42", "dfc_linha_caixa"] = "6.03.01"
    assert any("EV42" in e and "6.02" in e for e in checar(cfg))


def test_evento_com_conta_inexistente_e_detectado(cfg):
    ev = cfg["dim_evento"]
    ev.loc[ev["codigo"] == "EV05", "contas_debito"] = "1.1.01.999"
    assert any("EV05" in e and "1.1.01.999" in e for e in checar(cfg))


def test_compras_financiadas_nao_tem_fluxo_de_caixa(cfg):
    # Regra contábil, não só de formato: compra a prazo e via FINAME não passam pelo caixa
    mev = cfg["map_evento_df"].set_index("codigo_evento")
    for ev in ("EV43", "EV45"):
        assert mev.loc[ev, "dfc_classe"] == ""
        assert mev.loc[ev, "dfc_linha_caixa"] == ""


def test_baixas_sem_caixa_ficam_fora_do_capital_de_giro(cfg):
    mev = cfg["map_evento_df"].set_index("codigo_evento")
    assert mev.loc["EV27", "exclui_do_giro"] == "S"  # baixa de incobrável
    assert mev.loc["EV29", "exclui_do_giro"] == "S"  # baixa de estoque perdido


def test_contas_de_caixa_estao_todas_no_grupo_de_caixa(cfg):
    mapa = cfg["map_conta_df"]
    caixa = set(mapa.loc[mapa["linha_dfc"] == "CAIXA", "codigo_conta"])
    assert caixa == {c for c in mapa["codigo_conta"] if c.startswith("1.1.01")}


def test_perdas_com_ajuste_na_dfc_nao_baixam_ativo_de_giro_direto(cfg):
    # Se um evento lança despesa que volta como ajuste na DFC e, no mesmo lançamento, credita
    # uma conta de capital de giro, a DFC conta o valor duas vezes. As perdas têm de passar
    # pela provisão (conta EVENTO), nunca direto contra estoque ou clientes.
    mapa = cfg["map_conta_df"].set_index("codigo_conta")
    com_ajuste = {c for c, linha in mapa["linha_dfc"].items() if c[0] == "3" and linha}
    de_giro = {c for c, linha in mapa["linha_dfc"].items() if linha.startswith("6.01.02")}
    for _, e in cfg["dim_evento"].iterrows():
        debitos = set(e["contas_debito"].split(","))
        creditos = set(e["contas_credito"].split(","))
        assert not (debitos & com_ajuste and creditos & de_giro), e["codigo"]
