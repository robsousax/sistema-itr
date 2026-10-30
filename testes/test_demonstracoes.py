"""
Testes do motor do BP e da DRE (Etapa 5).

Usam a Orbe gerada na Etapa 4, importada para uma base temporária. Conferem:
  - os períodos do ITR (CPC 21);
  - o BP fecha em todo fim de trimestre e o lucro do período aparece em lucros acumulados;
  - a DRE é aditiva (9M = 1T + 2T + 3T) e os subtotais seguem as fórmulas da CVM;
  - linhas do motor batem com somas feitas direto na base, por fora do motor.
"""
import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from checar_config import carregar
from demonstracoes import (balanco, calcular_linhas, linhas_da, lucro_por_acao, montar_bp,
                           montar_dre, periodos_itr, reais_mil, resultado, saldos_em)
from gerar_dados import gerar
from gerar_modelo_entrada import gerar_modelo
from importar_entrada import importar

FINS_DE_TRIMESTRE = [date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31),
                     date(2026, 3, 31), date(2026, 6, 30), date(2026, 9, 30)]


@pytest.fixture(scope="module")
def cfg():
    return carregar()


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("demonstracoes")
    arquivo = gerar_modelo(pasta / "entrada_itr.xlsx", gerar().quadros())
    base = pasta / "itr.sqlite"
    erros, _ = importar(arquivo, base)
    assert erros == []
    conexao = sqlite3.connect(base)
    yield conexao
    conexao.close()


def soma_direta(con, contas_prefixo: tuple[str, ...], data: date) -> int:
    """Saldo somado direto no SQL, sem passar pelo motor (débito positivo)."""
    return sum(v for c, v in saldos_em(con, data).items() if c.startswith(contas_prefixo))


# ---------------------------------------------------------------- períodos

def test_periodos_do_itr_do_3t26():
    p = periodos_itr("3T26")
    assert (p["bp_atual"].fim, p["bp_comparativo"].fim) == (date(2026, 9, 30), date(2025, 12, 31))
    assert (p["tri_atual"].inicio, p["tri_atual"].fim) == (date(2026, 7, 1), date(2026, 9, 30))
    assert (p["acum_atual"].inicio, p["acum_atual"].rotulo) == (date(2026, 1, 1), "9M26")
    assert (p["tri_anterior"].inicio, p["tri_anterior"].fim) == (date(2025, 7, 1), date(2025, 9, 30))
    assert p["acum_anterior"].rotulo == "9M25"


def test_periodos_do_1t26_comparam_com_31_12_2025():
    p = periodos_itr("1T26")
    assert p["bp_comparativo"].fim == date(2025, 12, 31)
    assert p["acum_atual"].rotulo == "3M26"
    assert p["tri_atual"].fim == date(2026, 3, 31)


# ---------------------------------------------------------------- balanço

@pytest.mark.parametrize("data", FINS_DE_TRIMESTRE)
def test_ativo_igual_passivo_mais_pl(con, cfg, data):
    bp = balanco(con, data, cfg)
    assert bp["1"] == bp["2"]
    assert bp["1"] == bp["1.01"] + bp["1.02"]
    assert bp["2"] == bp["2.01"] + bp["2.02"] + bp["2.03"]


def test_lucro_do_periodo_aparece_em_lucros_acumulados(con, cfg):
    bp = balanco(con, date(2026, 9, 30), cfg)
    dre = resultado(con, date(2026, 1, 1), date(2026, 9, 30), cfg)
    assert bp["2.03.05"] == dre["3.11"]


def test_lucros_acumulados_zerados_depois_do_encerramento(con, cfg):
    assert balanco(con, date(2025, 12, 31), cfg)["2.03.05"] == 0


def test_variacao_do_pl_em_2026_e_o_lucro(con, cfg):
    # Em 2026 não houve aumento de capital nem dividendo declarado: o PL só cresce pelo lucro
    inicio, fim = balanco(con, date(2025, 12, 31), cfg), balanco(con, date(2026, 9, 30), cfg)
    lucro = resultado(con, date(2026, 1, 1), date(2026, 9, 30), cfg)["3.11"]
    assert fim["2.03"] - inicio["2.03"] == lucro


def test_clientes_liquido_da_perda_esperada(con, cfg):
    data = date(2026, 9, 30)
    assert balanco(con, data, cfg)["1.01.03.01"] == soma_direta(con, ("1.1.02",), data)


def test_imobilizado_liquido_da_depreciacao(con, cfg):
    data = date(2026, 9, 30)
    assert balanco(con, data, cfg)["1.02.03"] == soma_direta(con, ("1.2.02",), data)


def test_divida_bruta_soma_curto_e_longo_prazo(con, cfg):
    data = date(2026, 9, 30)
    bp = balanco(con, data, cfg)
    direta = -soma_direta(con, ("2.1.04", "2.2.01"), data)
    assert bp["2.01.04"] + bp["2.02.01"] == direta


# ---------------------------------------------------------------- DRE

def test_dre_acumulada_e_a_soma_dos_trimestres(con, cfg):
    trimestres = [(date(2026, 1, 1), date(2026, 3, 31)), (date(2026, 4, 1), date(2026, 6, 30)),
                  (date(2026, 7, 1), date(2026, 9, 30))]
    acumulado = resultado(con, date(2026, 1, 1), date(2026, 9, 30), cfg)
    partes = [resultado(con, i, f, cfg) for i, f in trimestres]
    for linha, valor in acumulado.items():
        assert valor == sum(p[linha] for p in partes), linha


def test_subtotais_seguem_as_formulas_da_cvm(con, cfg):
    d = resultado(con, date(2026, 1, 1), date(2026, 9, 30), cfg)
    assert d["3.03"] == d["3.01"] + d["3.02"]
    assert d["3.04"] == d["3.04.01"] + d["3.04.02"] + d["3.04.03"] + d["3.04.04"] + d["3.04.05"]
    assert d["3.05"] == d["3.03"] + d["3.04"]
    assert d["3.07"] == d["3.05"] + d["3.06"]
    assert d["3.09"] == d["3.07"] + d["3.08"]
    assert d["3.11"] == d["3.09"]


def test_lucro_da_dre_igual_ao_movimento_das_contas_de_resultado(con, cfg):
    sql = ("SELECT SUM(credito_centavos - debito_centavos) FROM lancamento WHERE data BETWEEN "
           "'2026-01-01' AND '2026-09-30' AND codigo_conta LIKE '3%' AND codigo_evento <> 'EV52'")
    direto, = con.execute(sql).fetchone()
    assert resultado(con, date(2026, 1, 1), date(2026, 9, 30), cfg)["3.11"] == direto


def test_lucro_de_2025_igual_ao_encerramento(con, cfg):
    sql = ("SELECT credito_centavos FROM lancamento WHERE codigo_evento = 'EV52' "
           "AND codigo_conta = '2.3.03.001'")
    encerrado, = con.execute(sql).fetchone()
    assert resultado(con, date(2025, 1, 1), date(2025, 12, 31), cfg)["3.11"] == encerrado


def test_quarto_trimestre_nao_e_apagado_pelo_encerramento(con, cfg):
    dre_4t = resultado(con, date(2025, 10, 1), date(2025, 12, 31), cfg)
    assert dre_4t["3.01"] > 0 and dre_4t["3.11"] > 0


def test_receita_positiva_e_despesas_negativas(con, cfg):
    d = resultado(con, date(2026, 7, 1), date(2026, 9, 30), cfg)
    assert d["3.01"] > 0 and d["3.06.01"] > 0
    assert d["3.02"] < 0 and d["3.04.01"] < 0 and d["3.04.02"] < 0 and d["3.06.02"] < 0


def test_lucro_por_acao(con):
    lucro = 30_000_000_00  # R$ 30 milhões em centavos, 30 milhões de ações
    assert lucro_por_acao(con, date(2026, 1, 1), date(2026, 9, 30), lucro) == Decimal("1.00000")


# ---------------------------------------------------------------- montagem e apresentação

def test_itr_traz_as_colunas_do_cpc_21(con, cfg):
    bp = montar_bp(con, "3T26", cfg)
    dre, lpa = montar_dre(con, "3T26", cfg)
    assert list(bp.columns[3:]) == ["30/09/2026", "31/12/2025"]
    assert list(dre.columns[3:]) == ["3T26", "9M26", "3T25", "9M25"]
    assert set(lpa) == {"3T26", "9M26", "3T25", "9M25"}


def test_formula_impossivel_e_denunciada(cfg):
    linhas = linhas_da("DRE", cfg).copy()
    linhas.loc[linhas.codigo == "3.03", "formula"] = "3.01 + 3.03"  # depende de si mesma
    with pytest.raises(ValueError, match="3.03"):
        calcular_linhas(linhas, {"3.01": 100, "3.02": -60})


@pytest.mark.parametrize("centavos,mil", [(50_000, 1), (49_999, 0), (-50_000, -1),
                                          (123_456_789, 1_235), (0, 0)])
def test_arredondamento_para_reais_mil(centavos, mil):
    assert reais_mil(centavos) == mil
