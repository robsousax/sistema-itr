"""
Testes do painel web (Etapa 12): a lógica de src/painel_dados.py e o app Streamlit rodando sem erro.
"""
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import painel_dados as pdados
from checar_config import carregar as carregar_cfg
from demonstracoes import balanco, resultado
from dfc_dmpl import dfc
from exportar_parquet import exportar
from gerar_dados import gerar as gerar_orbe
from gerar_modelo_entrada import gerar_modelo
from importar_entrada import importar

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("painel")
    arquivo = gerar_modelo(pasta / "entrada_itr.xlsx", gerar_orbe().quadros())
    caminho = pasta / "itr.sqlite"
    assert importar(arquivo, caminho)[0] == []
    return caminho


@pytest.fixture(scope="module")
def con(base):
    conexao = sqlite3.connect(base)
    yield conexao
    conexao.close()


@pytest.fixture(scope="module")
def d(con, tmp_path_factory):
    pasta = tmp_path_factory.mktemp("exportacao")
    exportar(con, pasta)
    return pdados.carregar(pasta)


def test_sem_exportacao_avisa_o_que_rodar(tmp_path):
    with pytest.raises(FileNotFoundError, match="exportar_parquet"):
        pdados.carregar(tmp_path)


def test_trimestres_do_itr(d):
    assert d.trimestres == ["1T25", "2T25", "3T25", "4T25", "1T26", "2T26", "3T26"]


def test_destaques_do_3t26(d, con):
    cfg = carregar_cfg()
    dre = resultado(con, date(2026, 7, 1), date(2026, 9, 30), cfg)
    dre_ant = resultado(con, date(2025, 7, 1), date(2025, 9, 30), cfg)
    k = pdados.destaques(d, "3T26")
    assert k["receita"] == dre["3.01"] / 100 and k["lucro"] == dre["3.11"] / 100
    assert k["var_receita"] == pytest.approx(dre["3.01"] / dre_ant["3.01"] - 1)
    assert k["caixa"] == balanco(con, date(2026, 9, 30), cfg)["1.01.01"] / 100


def test_sem_ano_anterior_a_variacao_fica_vazia(d):
    assert pdados.destaques(d, "1T25")["var_receita"] is None


@pytest.mark.parametrize("demo,motor", [("DRE", resultado), ("DFC", dfc)])
def test_coluna_periodo_e_o_9m26_do_itr(d, con, demo, motor):
    tabela = pdados.matriz(d, demo, ["1T26", "2T26", "3T26"])
    esperado = motor(con, date(2026, 1, 1), date(2026, 9, 30), carregar_cfg())
    codigos = d.t["dim_linha"].query("demonstracao == @demo").sort_values("ordem").codigo
    for codigo, obtido in zip(codigos, tabela["Período"]):
        assert obtido == round(esperado.get(codigo, 0) / 100 / 1000), codigo


def test_matriz_do_bp_fica_com_o_ultimo_saldo(d, con):
    tabela = pdados.matriz(d, "BP", ["1T26", "2T26", "3T26"])
    assert (tabela["Período"] == tabela["3T26"]).all()


def test_conferencias_zeradas_em_todos_os_trimestres(d):
    for tri in d.trimestres:
        conf = pdados.conferencias(d, tri)
        assert conf.OK.all(), (tri, conf[~conf.OK])


def test_conferencia_acusa_diferenca(d):
    """Se o EBITDA do sistema mudar, a conferência deixa de dar zero."""
    fato = d.t["fato_demonstracao"]
    alterado = pdados.Dados(d.pasta, {**d.t, "fato_demonstracao": fato.assign(
        valor=fato.valor.where(~((fato.chave_linha == "E.05") & (fato.trimestre == "3T26")), fato.valor + 1))})
    conf = pdados.conferencias(alterado, "3T26").set_index("Conferência")
    assert not conf.loc["EBITDA do painel − EBITDA do sistema", "OK"]


def test_indicadores_formatados(d):
    tabela = pdados.tabela_indicadores(d).set_index("Indicador")
    assert tabela.loc["ROE (UDM)", "3T25"] == "n.d."
    assert tabela.loc["Margem bruta", "3T26"].endswith("%")
    assert tabela.loc["Liquidez corrente", "3T26"].endswith("x")


@pytest.mark.parametrize("valor,unidade,texto", [
    (0.2974, "%", "29,7%"), (2.1889, "x", "2,19x"), (47.2, "dias", "47"),
    (-13086281.0, "R$", "-13.086"), (None, "%", "n.d."),
])
def test_formatar_indicador(valor, unidade, texto):
    assert pdados.formatar_indicador(valor, unidade) == texto


def test_exemplo_publicado_esta_atualizado(d):
    """exemplos/exportacao/ é o que o app publicado na web mostra: tem que bater com o motor."""
    exemplo = RAIZ / "exemplos" / "exportacao" / "fato_demonstracao.parquet"
    if not exemplo.exists():
        pytest.skip("exemplos/exportacao/ ainda não gerado")
    copia = pd.read_parquet(exemplo).sort_values(["chave_linha", "data"]).reset_index(drop=True)
    atual = d.t["fato_demonstracao"].sort_values(["chave_linha", "data"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(copia, atual)


def test_app_streamlit_roda_sem_erro():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    try:
        pdados.carregar()
    except FileNotFoundError:
        pytest.skip("sem exportação para o app ler")
    app = AppTest.from_file(str(RAIZ / "app" / "painel.py"), default_timeout=60).run()
    assert not app.exception
    rotulos = {m.label for m in app.metric}
    assert {"Receita líquida", "EBITDA", "Lucro líquido", "Publicação"} <= rotulos
    assert next(m for m in app.metric if m.label == "Publicação").value == "Liberada"
