"""
Testes da DRA, da DVA e das notas explicativas (Etapa 7), sobre a Orbe gerada na Etapa 4.
"""
import sqlite3
from datetime import date

import pytest

from checar_config import carregar
from demonstracoes import resultado
from dfc_dmpl import partidas
from dra_dva import conferir_dva, dra, dva, montar
from gerar_dados import gerar
from gerar_modelo_entrada import gerar_modelo
from importar_entrada import importar
from notas import conferir_notas, montar_notas

PERIODOS = {"9M25": (date(2025, 1, 1), date(2025, 9, 30)),
            "2025": (date(2025, 1, 1), date(2025, 12, 31)),
            "9M26": (date(2026, 1, 1), date(2026, 9, 30))}


@pytest.fixture(scope="module")
def cfg():
    return carregar()


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("dra_dva")
    arquivo = gerar_modelo(pasta / "entrada_itr.xlsx", gerar().quadros())
    base = pasta / "itr.sqlite"
    assert importar(arquivo, base)[0] == []
    conexao = sqlite3.connect(base)
    yield conexao
    conexao.close()


@pytest.fixture(scope="module")
def notas(con, cfg):
    return {n.numero: n for n in montar_notas(con, "3T26", cfg)}


# ---------------------------------------------------------------- DRA

def test_dra_parte_do_lucro_e_soma_o_ora(con, cfg):
    d = dra(con, *PERIODOS["9M26"], cfg)
    assert d["4.01"] == resultado(con, *PERIODOS["9M26"], cfg)["3.11"]
    assert d["4.02"] == 0  # a Orbe não tem outros resultados abrangentes na V1
    assert d["4.03"] == d["4.01"] + d["4.02"]


# ---------------------------------------------------------------- DVA

@pytest.mark.parametrize("periodo", PERIODOS)
def test_dva_confere(con, cfg, periodo):
    assert conferir_dva(con, *PERIODOS[periodo], cfg) == []


def test_dva_parte_da_receita_bruta(con, cfg):
    # Vendas na DVA = receita bruta - devoluções - descontos (com os tributos dentro)
    inicio, fim = PERIODOS["9M26"]
    mov = {}
    for _, conta, valor in partidas(con, inicio, fim):
        mov[conta] = mov.get(conta, 0) - valor
    esperado = mov["3.1.01.001"] + mov["3.1.02.004"] + mov["3.1.02.005"]
    assert dva(con, inicio, fim, cfg)["7.01.01"] == esperado


def test_insumos_incluem_os_tributos_recuperaveis(con, cfg):
    # CPC 09, item 14: insumos com ICMS, PIS e COFINS; tributos distribuídos pelo líquido
    inicio, fim = PERIODOS["9M26"]
    creditos = sum(v for e, c, v in partidas(con, inicio, fim)
                   if e == "EV09" and c in ("1.1.04.001", "1.1.04.002", "1.1.04.003"))
    cmv = sum(v for _, c, v in partidas(con, inicio, fim) if c == "3.2.01.001")
    d = dva(con, inicio, fim, cfg)
    assert d["7.02.01"] == -(cmv + creditos)
    icms_vendas = sum(v for _, c, v in partidas(con, inicio, fim) if c == "3.1.02.001")
    icms_compras = sum(v for e, c, v in partidas(con, inicio, fim) if e == "EV09" and c == "1.1.04.001")
    assert d["7.08.02.02"] == icms_vendas - icms_compras


def test_dividendos_de_2025_aparecem_na_distribuicao(con, cfg):
    d = dva(con, *PERIODOS["2025"], cfg)
    dividendo, = con.execute("SELECT credito_centavos FROM lancamento WHERE codigo_evento = 'EV54' "
                             "AND codigo_conta = '2.1.05.001'").fetchone()
    assert d["7.08.04.02"] == dividendo
    assert d["7.08.04.02"] + d["7.08.04.03"] == resultado(con, *PERIODOS["2025"], cfg)["3.11"]


def test_inss_patronal_vai_para_tributos_e_fgts_para_pessoal(con, cfg):
    inicio, fim = PERIODOS["9M26"]
    fgts = sum(v for _, c, v in partidas(con, inicio, fim) if c in ("3.3.01.005", "3.3.02.004"))
    assert dva(con, inicio, fim, cfg)["7.08.01.03"] == fgts


def test_limite_da_conferencia_da_dva(con, cfg):
    # A conferência "a distribuir = distribuído" fecha POR CONSTRUÇÃO: toda conta de resultado
    # está de um lado ou do outro, com sinais opostos. Ela pega erro de programação, não de
    # classificação. Energia classificada como remuneração de terceiros mantém a DVA fechada,
    # mas muda as linhas; quem pega esse tipo de erro são os testes linha a linha acima.
    errado = {k: v.copy() for k, v in cfg.items()}
    mapa = errado["map_conta_df"]
    mapa.loc[mapa.codigo_conta == "3.3.02.008", "linha_dva"] = "7.08.03.03"
    assert conferir_dva(con, *PERIODOS["9M26"], errado) == []
    certo, torto = dva(con, *PERIODOS["9M26"], cfg), dva(con, *PERIODOS["9M26"], errado)
    assert torto["7.02.02"] != certo["7.02.02"] and torto["7.08.03.03"] != certo["7.08.03.03"]


def test_itr_traz_dra_com_quatro_colunas_e_dva_com_acumulados(con, cfg):
    tab_dra, tab_dva = montar(con, "3T26", cfg)
    assert list(tab_dra.columns[3:]) == ["3T26", "9M26", "3T25", "9M25"]
    assert list(tab_dva.columns[3:]) == ["9M26", "9M25"]


# ---------------------------------------------------------------- notas

def test_dez_notas_na_ordem(notas):
    assert list(notas) == list(range(1, 11))
    assert all(n.paragrafos for n in notas.values())


def test_notas_conferem_com_as_demonstracoes(con, cfg):
    assert conferir_notas(con, "3T26", cfg) == []


def test_notas_do_2t26_tambem_conferem(con, cfg):
    assert conferir_notas(con, "2T26", cfg) == []


def test_movimentacao_da_perda_esperada_fecha(notas):
    m = notas[4].quadros[1]
    inicial, constituicao, baixas, final = (l.valores[0] for l in m.linhas)
    assert inicial + constituicao + baixas == final
    assert baixas == -61_000_000  # incobráveis baixados em 2026: 90 mil + 420 mil + 100 mil


def test_imobilizado_mostra_a_obra_transferida_e_a_venda(notas):
    imob = notas[6].quadros[0]
    baixas_custo, transferencias = imob.linhas[2].valores, imob.linhas[3].valores
    assert transferencias[1] == 200_000_000      # obra entra em edificações
    assert transferencias[6] == -200_000_000     # e sai de em andamento
    assert transferencias[-1] == 0
    assert baixas_custo[3] == -40_000_000        # utilitários vendidos (custo)


def test_compra_a_prazo_citada_na_nota_de_imobilizado(notas):
    assert any("Porta-paletes" in p and "CPC 03" in p for p in notas[6].paragrafos)


def test_emprestimos_por_contrato_somam_o_balanco(notas):
    composicao = notas[7].quadros[0]
    assert len(composicao.linhas) == 4  # E001, E002, E003 e total
    total = composicao.total("Total")
    assert total[2] + total[3] == total[4]


def test_aliquota_efetiva_explicada(notas):
    reconc = notas[8].quadros[0]
    outros = reconc.linhas[3].valores
    assert all(abs(v) <= 100 for v in outros)  # só arredondamento
    assert reconc.linhas[2].valores == [1_800_000, 1_800_000]  # 3 trimestres x R$ 6 mil


def test_lucro_por_acao_na_nota_igual_ao_da_dre(con, cfg, notas):
    from demonstracoes import montar_dre
    _, lpa = montar_dre(con, "3T26", cfg)
    na_nota = notas[9].quadros[1].linhas[-1].valores
    assert na_nota == [str(lpa[c]).replace(".", ",") for c in ("3T26", "9M26", "3T25", "9M25")]


def test_dividendo_declarado_e_pago_citado_na_nota_de_pl(notas):
    assert any("31/12/2025" in p and "pagos em 20/05/2026" in p for p in notas[9].paragrafos)
