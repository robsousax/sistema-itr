"""
Testes do gerador de dados da Orbe (Etapa 4).

Três famílias:
  1. Contabilidade: a planilha gerada passa no validador da Etapa 3 sem erro nem alerta, o
     balanço fecha, nenhum saldo fica invertido e o caixa nunca fica negativo.
  2. DFC antecipada: o método indireto bate com o método direto (dinheiro que de fato entrou e
     saiu). É a prova de que cada evento foi classificado do jeito certo.
  3. História: os números contam o que o roteiro promete (crescimento, inadimplência no 1T26,
     recuperação da margem no 2T26, dívida maior no 3T26).
"""
from collections import defaultdict
from datetime import date

import pytest

from checar_config import carregar
from gerar_dados import (BANCOS, CDB, LUCROS_ACUM, carregar_roteiro, fim_de_trimestre,
                         fim_do_mes_anterior, gerar, resumo_trimestral)
from gerar_modelo_entrada import gerar_modelo
from importar_entrada import importar
from validar_entrada import validar


@pytest.fixture(scope="module")
def g():
    return gerar()


@pytest.fixture(scope="module")
def resumo(g):
    return {r["trimestre"]: r for r in resumo_trimestral(g)}


@pytest.fixture(scope="module")
def arquivo(g, tmp_path_factory):
    return gerar_modelo(tmp_path_factory.mktemp("gerador") / "entrada_itr.xlsx", g.quadros())


# ---------------------------------------------------------------- contabilidade

def test_planilha_gerada_passa_sem_erros_nem_alertas(arquivo):
    _, erros, alertas = validar(arquivo)
    assert erros == []
    assert alertas == []


def test_planilha_gerada_e_importada(arquivo, tmp_path):
    erros, _ = importar(arquivo, tmp_path / "itr.sqlite")
    assert erros == []
    assert (tmp_path / "itr.sqlite").exists()


def test_mesma_semente_gera_os_mesmos_lancamentos(g):
    assert gerar().livro.partidas == g.livro.partidas


def test_outra_semente_gera_outros_numeros(g):
    roteiro = carregar_roteiro()
    roteiro["semente"] += 1
    assert gerar(roteiro).livro.partidas != g.livro.partidas


def test_balanco_fecha_e_nenhum_saldo_fica_invertido(g):
    plano = carregar()["plano_de_contas"].set_index("codigo")
    for data, saldos in g.fotos.items():
        if not fim_de_trimestre(data):
            continue
        assert sum(saldos.values()) == 0, data
        for conta, valor in saldos.items():
            if valor and not conta.startswith("3"):
                devedora = plano.loc[conta, "natureza"] == "D"
                assert (valor > 0) == devedora, f"{data}: {conta} com saldo invertido"


def test_caixa_nunca_fica_negativo(g):
    saldo = {BANCOS: g.abertura_saldos[BANCOS], CDB: g.abertura_saldos[CDB]}
    por_dia = defaultdict(lambda: defaultdict(int))
    for p in g.livro.partidas:
        if p["codigo_conta"] in saldo:
            por_dia[p["data"]][p["codigo_conta"]] += p["debito"] - p["credito"]
    for data in sorted(por_dia):
        for conta in saldo:
            saldo[conta] += por_dia[data][conta]
            assert saldo[conta] >= 0, f"{data}: {conta} negativo"


def test_exercicio_de_2025_encerrado(g):
    fim = g.fotos[date(2025, 12, 31)]
    assert all(v == 0 for c, v in fim.items() if c.startswith("3"))
    assert fim.get(LUCROS_ACUM, 0) == 0  # todo o lucro destinado


def test_aliquota_efetiva_de_ir_perto_de_34_por_cento(g):
    # IR corrente + diferido sobre o lucro antes do IR; o adicional de 10% começa
    # depois de R$ 60 mil por trimestre, então a taxa fica um pouco abaixo de 34%
    for data in [d for d in g.fotos if fim_de_trimestre(d) and d > g.abertura]:
        inicio = fim_do_mes_anterior(data, 3)
        partidas = [p for p in g.livro.partidas
                    if inicio < p["data"] <= data and p["codigo_evento"] != "EV52"]
        ir = sum(p["debito"] - p["credito"] for p in partidas if p["codigo_conta"].startswith("3.5"))
        lair = -sum(p["debito"] - p["credito"] for p in partidas
                    if p["codigo_conta"].startswith("3") and not p["codigo_conta"].startswith("3.5"))
        assert 0.33 < ir / lair < 0.345, f"{data}: alíquota efetiva {ir / lair:.2%}"


# ---------------------------------------------------------------- DFC: indireto x direto

def fluxos(g, inicio: date, fim: date) -> dict[str, int]:
    cfg = carregar()
    mapa = cfg["map_conta_df"].set_index("codigo_conta")["linha_dfc"].to_dict()
    mev = cfg["map_evento_df"].set_index("codigo_evento").to_dict("index")
    partidas = [p for p in g.livro.partidas
                if inicio < p["data"] <= fim and p["codigo_evento"] != "EV52"]

    def mov(p):
        return p["debito"] - p["credito"]

    def caixa(p):
        return mapa[p["codigo_conta"]] == "CAIXA"

    lucro = -sum(mov(p) for p in partidas if p["codigo_conta"].startswith("3"))
    ajustes = sum(mov(p) for p in partidas
                  if p["codigo_conta"].startswith("3") and mapa[p["codigo_conta"]])
    giro = -sum(mov(p) for p in partidas if mapa[p["codigo_conta"]].startswith("6.01.02")
                and mev[p["codigo_evento"]]["exclui_do_giro"] == "N")
    ir_pago = sum(mov(p) for p in partidas
                  if caixa(p) and mev[p["codigo_evento"]]["dfc_linha_caixa"] == "6.01.03.01")
    por_classe = defaultdict(int)
    for p in partidas:
        if caixa(p):
            por_classe[mev[p["codigo_evento"]]["dfc_classe"]] += mov(p)
    return {"indireto": lucro + ajustes + giro + ir_pago, "direto": por_classe["operacional"],
            "investimento": por_classe["investimento"],
            "financiamento": por_classe["financiamento"], "sem_classe": por_classe[""],
            "variacao_caixa": sum(mov(p) for p in partidas if caixa(p))}


@pytest.mark.parametrize("inicio,fim", [
    (date(2024, 12, 31), date(2025, 9, 30)),   # 9M25 (comparativo do ITR)
    (date(2025, 12, 31), date(2026, 9, 30)),   # 9M26 (período do ITR)
    (date(2024, 12, 31), date(2025, 12, 31)),  # exercício de 2025
])
def test_dfc_indireta_bate_com_a_direta(g, inicio, fim):
    f = fluxos(g, inicio, fim)
    assert f["indireto"] == f["direto"]
    assert f["sem_classe"] == 0  # só movimentos entre contas de caixa (aplicação e resgate)
    assert f["direto"] + f["investimento"] + f["financiamento"] == f["variacao_caixa"]


# ---------------------------------------------------------------- a história do roteiro

def test_receita_cresce_todo_trimestre(resumo):
    receitas = [r["receita_bruta"] for r in resumo.values()]
    assert receitas == sorted(receitas)


def test_expansao_comercial_aperta_a_margem_no_4t25(resumo):
    assert resumo["4T25"]["margem_bruta"] < resumo["3T25"]["margem_bruta"] - 0.01


def test_eficiencia_recupera_a_margem_no_2t26(resumo):
    assert resumo["2T26"]["margem_bruta"] > resumo["1T26"]["margem_bruta"] + 0.01


def test_inadimplencia_do_1t26_aumenta_a_perda_esperada(resumo):
    def taxa(r):
        return r["perda_esperada"] / r["clientes"]
    assert taxa(resumo["1T26"]) > taxa(resumo["4T25"]) + 0.01


def test_credito_do_3t26_aumenta_a_divida(resumo):
    assert resumo["3T26"]["divida_bruta"] > resumo["2T26"]["divida_bruta"] + 7_000_000_00


def test_finame_do_3t25_entra_na_divida(resumo):
    assert resumo["3T25"]["divida_bruta"] > resumo["2T25"]["divida_bruta"] + 3_500_000_00


def test_prazo_medio_de_recebimento_segue_o_roteiro(g):
    roteiro = carregar_roteiro()
    for data in [d for d in g.fotos if fim_de_trimestre(d) and d > g.abertura]:
        receita_do_mes = sum(p["credito"] for p in g.livro.partidas
                             if p["codigo_conta"] == "3.1.01.001" and p["data"] == data)
        pmr = g.fotos[data]["1.1.02.001"] / receita_do_mes * 30
        esperado = roteiro["trimestres"][f"{(data.month - 1) // 3 + 1}T{data.year % 100}"]["pmr_dias"]
        assert abs(pmr - esperado) < 1, f"{data}: PMR {pmr:.1f} dias, roteiro {esperado}"
