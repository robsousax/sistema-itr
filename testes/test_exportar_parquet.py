"""
Testes da exportação para o Power BI (Etapa 11).

O ponto central: o Power BI só agrega o que o motor calculou por trimestre. Estes testes simulam
em pandas a mesma regra da medida DAX "Valor DF" (soma / último / primeiro) e conferem que somar
1T26 + 2T26 + 3T26 reproduz o 9M26 do ITR, linha por linha.
"""
import shutil
import sqlite3
from datetime import date

import pandas as pd
import pytest

from checar_config import carregar
from demonstracoes import balanco, resultado
from dfc_dmpl import dfc
from dra_dva import dra, dva
from exportar_parquet import exportar
from gerar_dados import gerar as gerar_orbe
from gerar_modelo_entrada import gerar_modelo
from importar_entrada import importar
from indicadores import serie

INICIO, FIM = date(2026, 1, 1), date(2026, 9, 30)
TRIS_9M26 = ["1T26", "2T26", "3T26"]


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("parquet")
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
def t(con, tmp_path_factory):
    """As tabelas lidas de volta dos arquivos Parquet, como o Power BI vai ler."""
    arquivos = exportar(con, tmp_path_factory.mktemp("exportacao"))
    return {nome: pd.read_parquet(caminho) for nome, caminho in arquivos.items()}


def valor_df(t, trimestres: list[str]) -> dict[str, int]:
    """Mesma regra da medida DAX [Valor DF], em centavos."""
    fato = t["fato_demonstracao"][t["fato_demonstracao"].trimestre.isin(trimestres)]
    fato = fato.merge(t["dim_linha"][["chave", "agregacao"]], left_on="chave_linha", right_on="chave")
    resultado_ = {}
    for chave, g in fato.sort_values("data").groupby("chave_linha"):
        regra = g.agregacao.iat[0]
        v = g.valor.sum() if regra == "soma" else g.valor.iat[-1] if regra == "ultimo" else g.valor.iat[0]
        resultado_[chave] = round(v * 100)
    return resultado_


# ---------------------------------------------------------------- estrutura do modelo

def test_nove_tabelas(t):
    assert sorted(t) == sorted(["dim_calendario", "dim_conta", "dim_evento", "dim_linha", "dim_indicador",
                                "fato_lancamento", "fato_demonstracao", "fato_indicador", "fato_qualidade"])


def test_calendario_continuo_em_anos_completos(t):
    datas = pd.to_datetime(t["dim_calendario"].data)
    assert datas.min() == pd.Timestamp("2024-01-01") and datas.max() == pd.Timestamp("2026-12-31")
    assert datas.diff().dropna().dt.days.eq(1).all()
    itr = t["dim_calendario"].query("periodo_itr == 'Sim'").trimestre.unique().tolist()
    assert itr == ["1T25", "2T25", "3T25", "4T25", "1T26", "2T26", "3T26"]


@pytest.mark.parametrize("fato,coluna,dim,chave", [
    ("fato_lancamento", "conta", "dim_conta", "codigo"),
    ("fato_lancamento", "evento", "dim_evento", "codigo"),
    ("fato_lancamento", "data", "dim_calendario", "data"),
    ("fato_demonstracao", "chave_linha", "dim_linha", "chave"),
    ("fato_demonstracao", "data", "dim_calendario", "data"),
    ("fato_indicador", "codigo", "dim_indicador", "codigo"),
    ("fato_indicador", "data", "dim_calendario", "data"),
])
def test_toda_chave_do_fato_existe_na_dimensao(t, fato, coluna, dim, chave):
    assert t[dim][chave].is_unique
    assert set(t[fato][coluna]) <= set(t[dim][chave])


def test_rotulo_unico_para_classificar_por_coluna(t):
    """O 'Classificar por coluna' do Power BI exige um rótulo para cada ordem."""
    linhas = t["dim_linha"]
    assert linhas.rotulo.is_unique and linhas.ordem.is_unique


def test_regras_de_agregacao(t):
    regra = t["dim_linha"].set_index("chave").agregacao
    assert regra["1.01.01"] == "ultimo" and regra["2.03"] == "ultimo"
    assert regra["3.01"] == "soma" and regra["6.01"] == "soma"
    assert regra["6.05.01"] == "primeiro" and regra["6.05.02"] == "ultimo"
    assert "3.99.01.01" not in regra.index  # lucro por ação não se soma


def test_razao_fecha_em_zero(t):
    """Débitos = créditos em todo o razão, abertura incluída."""
    assert abs(t["fato_lancamento"].movimento.sum()) < 0.005


# ---------------------------------------------------------------- a regra semiaditiva reproduz o ITR

@pytest.mark.parametrize("demo,motor", [("DRE", resultado), ("DRA", dra), ("DFC", dfc), ("DVA", dva)])
def test_soma_dos_trimestres_e_o_acumulado_do_itr(t, con, demo, motor):
    esperado = motor(con, INICIO, FIM, carregar())
    obtido = valor_df(t, TRIS_9M26)
    chaves = set(t["dim_linha"].query("demonstracao == @demo").chave)
    diferencas = {c: (obtido.get(c, 0), esperado.get(c, 0)) for c in chaves if obtido.get(c, 0) != esperado.get(c, 0)}
    assert diferencas == {}


def test_bp_no_9m26_e_o_saldo_de_30_09(t, con):
    esperado = balanco(con, FIM, carregar())
    obtido = valor_df(t, TRIS_9M26)
    chaves = set(t["dim_linha"].query("demonstracao == 'BP'").chave)
    assert {c: obtido[c] for c in chaves} == {c: esperado.get(c, 0) for c in chaves}


def test_saldo_inicial_de_caixa_do_9m26_e_o_de_31_12_2025(t, con):
    assert valor_df(t, TRIS_9M26)["6.05.01"] == balanco(con, date(2025, 12, 31), carregar())["1.01.01"]


# ---------------------------------------------------------------- medidas do painel × sistema

def test_ebitda_pela_formula_do_dax_bate_com_o_sistema(t):
    """[EBITDA] = Lucro − IR/CSLL − Resultado financeiro + Depreciação (DFC 6.01.01.02)."""
    for tri in t["fato_demonstracao"].query("demonstracao == 'DRE'").trimestre.unique():
        v = valor_df(t, [tri])
        assert v["3.11"] - v["3.08"] - v["3.06"] + v["6.01.01.02"] == v["E.05"], tri


def test_caixa_pelo_razao_bate_com_o_bp(t):
    """[Caixa pelo Razão]: saldo acumulado das contas da linha 1.01.01 até o fim do trimestre."""
    lanc = t["fato_lancamento"].merge(t["dim_conta"][["codigo", "linha_bp_dre"]], left_on="conta", right_on="codigo")
    caixa = lanc[lanc.linha_bp_dre == "1.01.01"]
    bp = t["fato_demonstracao"].query("chave_linha == '1.01.01'")
    for _, l in bp.iterrows():
        assert round(caixa[caixa.data <= l.data].movimento.sum(), 2) == l.valor, l.trimestre


def test_divida_liquida_do_bp_bate_com_o_indicador(t):
    ind = t["fato_indicador"].query("codigo == 'divida_liquida'").set_index("trimestre").valor
    for tri, valor in ind.items():
        v = valor_df(t, [tri])
        assert round((v["2.01.04"] + v["2.02.01"] - v["1.01.01"]) / 100, 2) == round(valor, 2), tri


def test_indicadores_iguais_aos_da_etapa_8(t, con):
    esperado = serie(con).set_index(["trimestre", "codigo"]).valor.astype("float64")
    obtido = t["fato_indicador"].set_index(["trimestre", "codigo"]).valor
    pd.testing.assert_series_equal(obtido.sort_index(), esperado.sort_index(), check_names=False)
    assert obtido.loc[("3T25", "roe")] != obtido.loc[("3T25", "roe")]  # n.d. (NaN) antes de 12 meses


def test_qualidade_traz_a_execucao_que_liberou(t):
    q = t["fato_qualidade"]
    assert len(q) == 20 and q.run_id.nunique() == 1 and "erro" not in set(q.status)


# ---------------------------------------------------------------- bloqueio

def test_central_bloqueia_a_exportacao(base, tmp_path):
    copia = tmp_path / "itr.sqlite"
    shutil.copy(base, copia)
    con = sqlite3.connect(copia)
    con.execute("UPDATE lancamento SET debito_centavos = debito_centavos + 100 WHERE id = "
                "(SELECT MIN(id) FROM lancamento WHERE debito_centavos > 0)")
    with pytest.raises(PermissionError, match="bloqueada"):
        exportar(con, tmp_path / "exportacao")
    con.close()
    assert not (tmp_path / "exportacao").exists()
