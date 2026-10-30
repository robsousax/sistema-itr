"""
Testes do contrato de entrada e da importação (Etapa 3).

O primeiro grupo garante que um conjunto de dados coerente passa e chega à base em centavos.
Os demais estragam os dados de propósito, um defeito por teste, e conferem se o erro é pego.
"""
import sqlite3
from datetime import date

import pytest
from openpyxl import load_workbook

import validar_entrada
from gerar_modelo_entrada import gerar_modelo
from importar_entrada import importar
from validar_entrada import ValorInvalido, para_centavos, validar


def partidas(id_lanc, data, evento, *linhas):
    """Monta as linhas de um lançamento. Cada linha: (conta, débito, crédito)."""
    return [{"id_lancamento": id_lanc, "data": data, "codigo_evento": evento,
             "codigo_conta": conta, "debito": d, "credito": c} for conta, d, c in linhas]


def dados_validos() -> dict[str, list[dict]]:
    """Uma Orbe em miniatura, coerente: balancete fecha e todo quadro bate com as contas."""
    saldos = [
        ("1.1.01.002", 5_121_000.00, None),     # Bancos
        ("1.1.01.003", 2_000_000.00, None),     # CDB
        ("1.1.02.001", 7_500_000.00, None),     # Clientes
        ("1.1.02.009", None, 250_000.00),       # (-) Perda esperada
        ("1.1.03.001", 14_000_000.00, None),    # Mercadorias
        ("1.1.03.009", None, 100_000.00),       # (-) Provisão para perdas em estoques
        ("1.2.01.001", 87_500.00, None),        # IRPJ diferido: 350.000 x 25%
        ("1.2.01.002", 31_500.00, None),        # CSLL diferida: 350.000 x 9%
        ("1.2.02.001", 3_000_000.00, None),     # Terrenos
        ("1.2.02.002", 8_000_000.00, None),     # Edificações
        ("1.2.02.092", None, 640_000.00),
        ("1.2.02.004", 1_200_000.00, None),     # Veículos
        ("1.2.02.094", None, 480_000.00),
        ("1.2.03.001", 300_000.00, None),       # Softwares
        ("1.2.03.091", None, 60_000.00),
        ("2.1.02.001", None, 5_000_000.00),     # Fornecedores
        ("2.1.04.001", None, 240_000.00),       # FINAME CP
        ("2.2.01.001", None, 720_000.00),       # FINAME LP
        ("2.1.04.002", None, 500_000.00),       # CCB CP
        ("2.2.01.002", None, 1_000_000.00),     # CCB LP
        ("2.1.05.001", None, 450_000.00),       # Dividendos a pagar
        ("2.3.01.001", None, 30_000_000.00),    # Capital social
        ("2.3.02.001", None, 600_000.00),       # Reserva legal
        ("2.3.02.002", None, 1_200_000.00),     # Retenção de lucros
    ]
    lancamentos = (
        partidas(1, date(2025, 1, 15), "EV01",
                 ("1.1.02.001", 100_000.00, None), ("3.1.01.001", None, 100_000.00))
        + partidas(2, date(2025, 1, 15), "EV02",
                   ("3.1.02.001", 18_000.00, None), ("3.1.02.002", 1_650.00, None),
                   ("3.1.02.003", 7_600.00, None), ("2.1.03.001", None, 18_000.00),
                   ("2.1.03.002", None, 1_650.00), ("2.1.03.003", None, 7_600.00))
        + partidas(3, date(2025, 1, 31), "EV05",
                   ("1.1.01.002", 50_000.00, None), ("1.1.02.001", None, 50_000.00))
        # Reversão de perda esperada: lançamento inverso do EV26, permitido
        + partidas(4, date(2025, 3, 31), "EV26",
                   ("1.1.02.009", 5_000.00, None), ("3.3.03.001", None, 5_000.00))
    )
    return {
        "saldos_abertura": [{"codigo_conta": c, "debito": d, "credito": cr} for c, d, cr in saldos],
        "lancamentos": lancamentos,
        "imobilizado": [
            {"id_bem": "B001", "descricao": "Terreno do CD", "classe": "terrenos",
             "data_aquisicao": date(2018, 3, 1), "custo": 3_000_000.00},
            {"id_bem": "B002", "descricao": "Galpão do CD", "classe": "edificacoes",
             "data_aquisicao": date(2022, 12, 15), "custo": 8_000_000.00,
             "depreciacao_acumulada_abertura": 640_000.00},
            {"id_bem": "B003", "descricao": "Caminhões de entrega", "classe": "veiculos",
             "data_aquisicao": date(2023, 1, 10), "custo": 1_200_000.00,
             "depreciacao_acumulada_abertura": 480_000.00},
            {"id_bem": "S001", "descricao": "Licença do ERP", "classe": "softwares",
             "data_aquisicao": date(2024, 1, 5), "custo": 300_000.00,
             "depreciacao_acumulada_abertura": 60_000.00},
            {"id_bem": "B004", "descricao": "Empilhadeira", "classe": "maquinas_e_equipamentos",
             "data_aquisicao": date(2025, 3, 10), "custo": 150_000.00},
        ],
        "emprestimos": [
            {"id_contrato": "E001", "modalidade": "FINAME", "credor": "Banco Alfa",
             "data_contratacao": date(2023, 6, 1), "valor_contratado": 1_200_000.00,
             "taxa_juros_aa": 0.095, "prazo_meses": 60, "carencia_meses": 6,
             "sistema_amortizacao": "SAC", "saldo_cp_abertura": 240_000.00,
             "saldo_lp_abertura": 720_000.00},
            {"id_contrato": "E002", "modalidade": "CCB", "credor": "Banco Beta",
             "data_contratacao": date(2024, 7, 1), "valor_contratado": 1_500_000.00,
             "taxa_juros_aa": 0.145, "prazo_meses": 36, "sistema_amortizacao": "PRICE",
             "saldo_cp_abertura": 500_000.00, "saldo_lp_abertura": 1_000_000.00},
        ],
        "patrimonio_liquido": [
            {"data": date(2024, 12, 31), "tipo_ato": "posicao_inicial",
             "valor": 30_000_000.00, "quantidade_acoes": 30_000_000},
        ],
        "diferencas_temporarias": [
            {"data_base": date(2024, 12, 31), "tipo": "perda_esperada_creditos",
             "valor_base": 250_000.00},
            {"data_base": date(2024, 12, 31), "tipo": "provisao_perdas_estoques",
             "valor_base": 100_000.00},
        ],
    }


@pytest.fixture
def dados():
    return dados_validos()


def erros_de(dados, tmp_path) -> list[str]:
    arquivo = gerar_modelo(tmp_path / "entrada.xlsx", dados)
    return validar(arquivo)[1]


def tem_erro(erros: list[str], *trechos: str) -> bool:
    """Algum erro contém todos os trechos?"""
    return any(all(t in e for t in trechos) for e in erros)


def saldo(dados, conta) -> dict:
    return next(s for s in dados["saldos_abertura"] if s["codigo_conta"] == conta)


# ---------------------------------------------------------------- conversão para centavos

def test_reais_viram_centavos_inteiros():
    assert para_centavos(1234.56) == 123456
    assert para_centavos(0.1 + 0.2) == 30          # 0.30000000000000004 no Python
    assert para_centavos(1234.5600000000002) == 123456  # resíduo de fórmula do Excel
    assert para_centavos(7) == 700


@pytest.mark.parametrize("valor", [10.005, -5.00, "1.234,56", True])
def test_valores_invalidos_sao_recusados(valor):
    with pytest.raises(ValorInvalido):
        para_centavos(valor)


# ---------------------------------------------------------------- caminho feliz

def test_modelo_em_branco_traz_as_contas_analiticas(tmp_path):
    arquivo = gerar_modelo(tmp_path / "modelo.xlsx")
    ws = load_workbook(arquivo)["saldos_abertura"]
    assert ws["A2"].value == "1.1.01.001"
    contas = [c.value for c in ws["A"][1:] if c.value]
    assert len(contas) == 120  # todas as contas analíticas do plano


def test_dados_coerentes_passam(dados, tmp_path):
    assert erros_de(dados, tmp_path) == []


def test_importacao_grava_centavos(dados, tmp_path):
    arquivo = gerar_modelo(tmp_path / "entrada.xlsx", dados)
    base = tmp_path / "itr.sqlite"
    assert importar(arquivo, base) == []

    con = sqlite3.connect(base)
    total_d, total_c = con.execute(
        "SELECT SUM(debito_centavos), SUM(credito_centavos) FROM saldo_abertura").fetchone()
    assert total_d == total_c == 4_124_000_000  # R$ 41.240.000,00
    tipo, = con.execute("SELECT typeof(debito_centavos) FROM lancamento LIMIT 1").fetchone()
    assert tipo == "integer"
    assert con.execute("SELECT COUNT(DISTINCT id_lancamento) FROM lancamento").fetchone() == (4,)
    conta, vida = con.execute(
        "SELECT conta_depreciacao, vida_util_anos FROM imobilizado WHERE id_bem = 'B003'").fetchone()
    assert (conta, vida) == ("1.2.02.094", 5)
    con.close()


# ---------------------------------------------------------------- nível 1: integridade

def test_aba_faltando_e_detectada(dados, tmp_path):
    arquivo = gerar_modelo(tmp_path / "entrada.xlsx", dados)
    wb = load_workbook(arquivo)
    wb.remove(wb["emprestimos"])
    wb.save(arquivo)
    assert tem_erro(validar(arquivo)[1], "emprestimos", "não encontrada")


def test_coluna_faltando_e_detectada(dados, tmp_path):
    arquivo = gerar_modelo(tmp_path / "entrada.xlsx", dados)
    wb = load_workbook(arquivo)
    wb["lancamentos"]["C1"] = "evento"  # renomeia codigo_evento
    wb.save(arquivo)
    assert tem_erro(validar(arquivo)[1], "lancamentos", "codigo_evento")


def test_valor_com_tres_casas_decimais_e_detectado(dados, tmp_path):
    dados["lancamentos"][0]["debito"] = 100_000.005
    assert tem_erro(erros_de(dados, tmp_path), "linha 2", "2 casas decimais")


def test_valor_negativo_e_detectado(dados, tmp_path):
    dados["imobilizado"][0]["custo"] = -3_000_000.00
    assert tem_erro(erros_de(dados, tmp_path), "imobilizado", "negativo")


def test_texto_em_coluna_de_valor_e_detectado(dados, tmp_path):
    saldo(dados, "1.1.01.002")["debito"] = "5.121.000,00"
    assert tem_erro(erros_de(dados, tmp_path), "saldos_abertura", "não é um número")


def test_campo_obrigatorio_vazio_e_detectado(dados, tmp_path):
    dados["lancamentos"][0]["data"] = None
    assert tem_erro(erros_de(dados, tmp_path), "lancamentos, linha 2", "'data' é obrigatória")


def test_data_invalida_e_detectada(dados, tmp_path):
    dados["lancamentos"][0]["data"] = "31/02/2025"
    assert tem_erro(erros_de(dados, tmp_path), "31/02/2025", "não é uma data válida")


def test_debito_e_credito_na_mesma_linha_sao_detectados(dados, tmp_path):
    dados["lancamentos"][0]["credito"] = 100_000.00
    assert tem_erro(erros_de(dados, tmp_path), "lancamentos, linha 2", "débito OU a crédito")


def test_conta_inexistente_e_detectada(dados, tmp_path):
    dados["lancamentos"][0]["codigo_conta"] = "1.1.02.999"
    assert tem_erro(erros_de(dados, tmp_path), "1.1.02.999", "não existe")


def test_conta_sintetica_e_detectada(dados, tmp_path):
    saldo(dados, "1.1.01.002")["codigo_conta"] = "1.1.01"
    assert tem_erro(erros_de(dados, tmp_path), "1.1.01", "sintética")


def test_evento_inexistente_e_detectado(dados, tmp_path):
    for p in dados["lancamentos"][:2]:
        p["codigo_evento"] = "EV99"
    assert tem_erro(erros_de(dados, tmp_path), "EV99", "não existe")


def test_saldo_de_abertura_lancado_como_evento_e_detectado(dados, tmp_path):
    for p in dados["lancamentos"][:2]:
        p["codigo_evento"] = "EV00"
    assert tem_erro(erros_de(dados, tmp_path), "EV00", "saldos_abertura")


def test_lancamento_fora_do_periodo_e_detectado(dados, tmp_path):
    for p in dados["lancamentos"][:2]:
        p["data"] = date(2026, 10, 1)
    assert tem_erro(erros_de(dados, tmp_path), "01/10/2026", "fora do período")


def test_bem_repetido_e_detectado(dados, tmp_path):
    dados["imobilizado"][4]["id_bem"] = "B001"
    assert tem_erro(erros_de(dados, tmp_path), "id_bem = B001 repetido")


def test_classe_fora_da_lista_e_detectada(dados, tmp_path):
    dados["imobilizado"][2]["classe"] = "caminhoes"
    assert tem_erro(erros_de(dados, tmp_path), "caminhoes", "não é aceito")


def test_taxa_digitada_em_percentual_e_detectada(dados, tmp_path):
    dados["emprestimos"][0]["taxa_juros_aa"] = 9.5  # deveria ser 0,095
    assert tem_erro(erros_de(dados, tmp_path), "taxa_juros_aa", "entre 0 e 1")


def test_data_base_fora_de_fim_de_trimestre_e_detectada(dados, tmp_path):
    dados["diferencas_temporarias"][0]["data_base"] = date(2025, 2, 28)
    assert tem_erro(erros_de(dados, tmp_path), "28/02/2025", "fim de trimestre")


def test_nivel2_nao_roda_com_erro_de_nivel1(dados, tmp_path):
    dados["lancamentos"][0]["debito"] = "abc"  # erro de nível 1 que também desbalancearia
    erros = erros_de(dados, tmp_path)
    assert erros and all(e.startswith("[nível 1]") for e in erros)


# ---------------------------------------------------------------- nível 2: coerência contábil

def test_balancete_de_abertura_desbalanceado_e_detectado(dados, tmp_path):
    saldo(dados, "1.1.01.002")["debito"] = 5_121_000.01
    assert tem_erro(erros_de(dados, tmp_path), "saldos_abertura", "débitos", "R$ 0,01")


def test_conta_de_resultado_com_saldo_na_abertura_e_detectada(dados, tmp_path):
    dados["saldos_abertura"] += [{"codigo_conta": "3.1.01.001", "credito": 1_000.00},
                                 {"codigo_conta": "1.1.01.001", "debito": 1_000.00}]
    assert tem_erro(erros_de(dados, tmp_path), "3.1.01.001", "começam zeradas")


def test_lucros_acumulados_credores_na_abertura_sao_detectados(dados, tmp_path):
    # Retenção vira lucros acumulados: o balancete continua fechando
    saldo(dados, "2.3.02.002")["codigo_conta"] = "2.3.03.001"
    assert tem_erro(erros_de(dados, tmp_path), "2.3.03.001", "art. 202")


def test_redutora_com_saldo_invertido_e_detectada(dados, tmp_path):
    s = saldo(dados, "1.1.03.009")
    s["debito"], s["credito"] = 100_000.00, None
    assert tem_erro(erros_de(dados, tmp_path), "1.1.03.009", "redutora")


def test_lancamento_desbalanceado_e_detectado(dados, tmp_path):
    dados["lancamentos"][1]["credito"] = 99_999.99
    assert tem_erro(erros_de(dados, tmp_path), "id 1", "débitos R$ 100.000,00", "R$ 99.999,99")


def test_lancamento_com_duas_datas_e_detectado(dados, tmp_path):
    dados["lancamentos"][1]["data"] = date(2025, 1, 16)
    assert tem_erro(erros_de(dados, tmp_path), "id 1", "uma data só")


def test_conta_estranha_ao_evento_e_detectada(dados, tmp_path):
    # Venda debitando bancos em vez de clientes: fecha D = C, mas o evento está errado
    dados["lancamentos"][0]["codigo_conta"] = "1.1.01.002"
    assert tem_erro(erros_de(dados, tmp_path), "1.1.01.002", "não faz parte do evento EV01")


def test_lado_invertido_e_detectado(dados, tmp_path):
    # Venda com débito na receita e crédito em clientes; EV01 não é reversível
    venda = dados["lancamentos"][:2]
    venda[0]["debito"], venda[0]["credito"] = None, 100_000.00
    venda[1]["debito"], venda[1]["credito"] = 100_000.00, None
    assert tem_erro(erros_de(dados, tmp_path), "EV01", "vai a débito, não a crédito")


def test_encerramento_fora_de_31_12_e_detectado(dados, tmp_path):
    dados["lancamentos"] += partidas(9, date(2025, 6, 30), "EV52",
                                     ("3.1.01.001", 100_000.00, None),
                                     ("2.3.03.001", None, 100_000.00))
    assert tem_erro(erros_de(dados, tmp_path), "EV52", "31/12")


def test_imobilizado_que_nao_bate_com_a_conta_e_detectado(dados, tmp_path):
    dados["imobilizado"][1]["custo"] = 7_900_000.00
    assert tem_erro(erros_de(dados, tmp_path), "conta 1.2.02.002", "diferença -R$ 100.000,00")


def test_depreciacao_acima_do_possivel_e_detectada(dados, tmp_path):
    # Software comprado em jan/2024, vida de 5 anos: no máximo 12/60 do custo em 31/12/2024
    s = saldo(dados, "1.2.03.091")
    s["credito"] = 90_000.00
    saldo(dados, "1.2.03.001")["debito"] = 330_000.00  # mantém o balancete fechado
    dados["imobilizado"][3].update(custo=330_000.00, depreciacao_acumulada_abertura=90_000.00)
    assert tem_erro(erros_de(dados, tmp_path), "S001", "máximo possível", "R$ 66.000,00")


def test_terreno_com_depreciacao_e_detectado(dados, tmp_path):
    dados["imobilizado"][0]["depreciacao_acumulada_abertura"] = 10_000.00
    assert tem_erro(erros_de(dados, tmp_path), "B001", "não é depreciado")


def test_emprestimo_que_nao_bate_com_o_circulante_e_detectado(dados, tmp_path):
    # Reclassificar entre curto e longo prazo mantém o total, mas não bate com as contas
    e = dados["emprestimos"][0]
    e["saldo_cp_abertura"], e["saldo_lp_abertura"] = 200_000.00, 760_000.00
    assert tem_erro(erros_de(dados, tmp_path), "FINAME curto prazo", "2.1.04.001")


def test_carencia_maior_que_o_prazo_e_detectada(dados, tmp_path):
    dados["emprestimos"][0]["carencia_meses"] = 60
    assert tem_erro(erros_de(dados, tmp_path), "E001", "carência")


def test_capital_do_quadro_de_pl_diferente_do_balancete_e_detectado(dados, tmp_path):
    dados["patrimonio_liquido"][0]["valor"] = 25_000_000.00
    assert tem_erro(erros_de(dados, tmp_path), "2.3.01.001", "capital")


def test_diferido_que_nao_bate_com_a_base_e_detectado(dados, tmp_path):
    dados["diferencas_temporarias"][1]["valor_base"] = 80_000.00
    erros = erros_de(dados, tmp_path)
    assert tem_erro(erros, "IRPJ diferido", "1.2.01.001")
    assert tem_erro(erros, "CSLL diferido", "1.2.01.002")


def test_reversao_da_provisao_de_estoques_e_aceita(dados, tmp_path):
    # EV28 invertido: o valor realizável líquido voltou a subir (CPC 16, item 33)
    dados["lancamentos"] += partidas(10, date(2025, 6, 30), "EV28",
                                     ("1.1.03.009", 20_000.00, None),
                                     ("3.2.01.002", None, 20_000.00))
    assert erros_de(dados, tmp_path) == []


def test_aliquota_do_diferido_vem_do_empresa_yaml(dados, tmp_path, monkeypatch):
    # Com 30% no parâmetro, o IRPJ diferido esperado cai para 21% de 350 mil = 73.500
    empresa = validar_entrada.carregar_empresa()
    empresa["tributacao"]["aliquota_diferido"] = 0.30
    monkeypatch.setattr(validar_entrada, "carregar_empresa", lambda: empresa)
    erros = erros_de(dados, tmp_path)
    assert tem_erro(erros, "IRPJ diferido", "21%", "R$ 73.500,00")
    assert not tem_erro(erros, "CSLL diferido")


def test_diferenca_maior_que_a_provisao_e_detectada(dados, tmp_path):
    # Em 31/03/2025 a provisão de créditos caiu para 245 mil (reversão de 5 mil)
    dados["diferencas_temporarias"].append(
        {"data_base": date(2025, 3, 31), "tipo": "perda_esperada_creditos",
         "valor_base": 250_000.00})
    assert tem_erro(erros_de(dados, tmp_path), "31/03/2025", "maior que a provisão",
                    "R$ 245.000,00")


def test_importacao_com_erro_nao_cria_a_base(dados, tmp_path):
    dados["lancamentos"][1]["credito"] = 1.00
    arquivo = gerar_modelo(tmp_path / "entrada.xlsx", dados)
    base = tmp_path / "itr.sqlite"
    assert importar(arquivo, base) != []
    assert not base.exists()
