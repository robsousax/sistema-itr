"""
Gerador de dados da Orbe Suprimentos S.A. (Etapa 4).

Transforma o roteiro de negócio (config/roteiro.yaml) em contabilidade:
  - balanço de abertura em 31/12/2024, coerente com os quadros auxiliares;
  - lançamentos em partidas dobradas de 01/01/2025 a 30/09/2026, cada um com o seu evento;
  - quadros auxiliares (imobilizado, empréstimos, PL, diferenças temporárias).

O resultado é gravado no formato da Etapa 3 (entrada/entrada_itr.xlsx) e passa pelo mesmo
validador. Se o gerador errar a contabilidade, a importação recusa, como faria com um humano.

Princípios:
  - Valores em centavos inteiros do começo ao fim; reais só na hora de gravar o Excel.
  - Mesma semente = mesmos lançamentos. Nada depende do relógio ou do acaso não controlado.
  - Os lançamentos são resumos mensais por natureza (como a integração do faturamento, da
    folha e do contas a pagar num ERP), não nota a nota.

Uso:
    python src/gerar_dados.py              # grava entrada/entrada_itr.xlsx
    python src/importar_entrada.py         # valida e grava a base
"""
import calendar
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml

from checar_config import PASTA_CONFIG
from contrato_entrada import CLASSES_IMOBILIZADO, CONTAS_EMPRESTIMO
from gerar_modelo_entrada import gerar_modelo
from validar_entrada import carregar_empresa

RAIZ = Path(__file__).resolve().parent.parent
DESTINO_PADRAO = RAIZ / "entrada" / "entrada_itr.xlsx"

# Contas usadas pelo gerador (os nomes deixam o código legível como um lançamento)
CAIXA, BANCOS, CDB = "1.1.01.001", "1.1.01.002", "1.1.01.003"
CLIENTES, PECLD = "1.1.02.001", "1.1.02.009"
MERCADORIAS, PROV_ESTOQUE = "1.1.03.001", "1.1.03.009"
ICMS_REC, PIS_REC, COFINS_REC, IRRF_APLIC = "1.1.04.001", "1.1.04.002", "1.1.04.003", "1.1.04.006"
SEGUROS_A_APROPRIAR = "1.1.05.001"
IRPJ_DIF, CSLL_DIF = "1.2.01.001", "1.2.01.002"
IMOB_ANDAMENTO = "1.2.02.007"
SALARIOS_PAGAR, INSS_REC, FGTS_REC = "2.1.01.001", "2.1.01.002", "2.1.01.003"
PROV_FERIAS, PROV_13, PLR_PAGAR = "2.1.01.004", "2.1.01.005", "2.1.01.006"
FORN_MERC, FORN_SERV, FORN_IMOB = "2.1.02.001", "2.1.02.002", "2.1.02.003"
ICMS_RECOLHER, PIS_RECOLHER, COFINS_RECOLHER = "2.1.03.001", "2.1.03.002", "2.1.03.003"
IRRF_RECOLHER, ISS_RECOLHER, IRPJ_PAGAR, CSLL_PAGAR = ("2.1.03.004", "2.1.03.005",
                                                        "2.1.03.006", "2.1.03.007")
DIVIDENDOS_PAGAR, ADIANT_CLIENTES = "2.1.05.001", "2.1.05.002"
CAPITAL, RESERVA_LEGAL, RETENCAO, LUCROS_ACUM = "2.3.01.001", "2.3.02.001", "2.3.02.002", "2.3.03.001"
RECEITA = "3.1.01.001"
ICMS_VENDAS, PIS_VENDAS, COFINS_VENDAS = "3.1.02.001", "3.1.02.002", "3.1.02.003"
DEVOLUCOES, DESCONTOS_CONC = "3.1.02.004", "3.1.02.005"
CMV, PERDAS_ESTOQUE = "3.2.01.001", "3.2.01.002"
DEPREC_COMERCIAL, DEPREC_ADM, AMORT_INTANG = "3.3.01.010", "3.3.02.017", "3.3.02.018"
PERDA_ESPERADA = "3.3.03.001"
GANHO_ALIENACAO, PERDA_ALIENACAO = "3.3.04.001", "3.3.05.001"
REND_APLIC, JUROS_CLIENTES, DESCONTOS_OBTIDOS = "3.4.01.001", "3.4.01.002", "3.4.01.003"
JUROS_EMPREST, TARIFAS, IOF = "3.4.02.001", "3.4.02.002", "3.4.02.003"
IRPJ_CORRENTE, CSLL_CORRENTE, IRPJ_DIFERIDO, CSLL_DIFERIDA = ("3.5.01.001", "3.5.01.002",
                                                              "3.5.02.001", "3.5.02.002")

# Despesas de depreciação por classe: o que serve à logística vai para vendas
DESPESA_DEPRECIACAO = {
    "edificacoes": DEPREC_COMERCIAL, "maquinas_e_equipamentos": DEPREC_COMERCIAL,
    "veiculos": DEPREC_COMERCIAL, "moveis_e_utensilios": DEPREC_ADM,
    "equipamentos_de_informatica": DEPREC_ADM, "softwares": AMORT_INTANG,
}


# ---------------------------------------------------------------- utilitários

def centavos(reais) -> int:
    """Reais -> centavos inteiros, arredondando meio centavo para cima."""
    return int((Decimal(str(reais)) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def aplicar(valor: int, taxa) -> int:
    """valor (centavos) x taxa, arredondado para o centavo."""
    return int((Decimal(valor) * Decimal(str(taxa))).to_integral_value(rounding=ROUND_HALF_UP))


def ultimo_dia(ano: int, mes: int) -> date:
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


def somar_meses(d: date, n: int) -> date:
    total = d.year * 12 + d.month - 1 + n
    ano, mes = divmod(total, 12)
    return date(ano, mes + 1, min(d.day, calendar.monthrange(ano, mes + 1)[1]))


def meses_entre(inicio: date, fim: date) -> int:
    """Meses de calendário de inicio até fim (mesmo mês = 0)."""
    return (fim.year - inicio.year) * 12 + fim.month - inicio.month


def fim_do_mes_anterior(d: date, meses: int = 1) -> date:
    """Último dia do mês `meses` antes do mês de d. Ex.: (31/03/2025, 3) -> 31/12/2024."""
    m = somar_meses(date(d.year, d.month, 1), -meses)
    return ultimo_dia(m.year, m.month)


def trimestre(d: date) -> str:
    return f"{(d.month - 1) // 3 + 1}T{d.year % 100}"


def fim_de_trimestre(d: date) -> bool:
    return d.month in (3, 6, 9, 12) and d == ultimo_dia(d.year, d.month)


def taxa_mensal(taxa_aa: float) -> float:
    return (1 + taxa_aa) ** (1 / 12) - 1


# ---------------------------------------------------------------- livro diário

@dataclass
class Livro:
    """Diário em partidas dobradas. Saldo de cada conta: débito positivo, crédito negativo."""
    saldos: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    partidas: list[dict] = field(default_factory=list)
    lancamentos: int = 0

    def saldo(self, conta: str) -> int:
        return self.saldos[conta]

    def credor(self, conta: str) -> int:
        return -self.saldos[conta]

    def lancar(self, data: date, evento: str, linhas: list[tuple[str, int, int]],
               historico: str) -> None:
        """linhas: (conta, débito, crédito) em centavos. Linhas zeradas são descartadas."""
        linhas = [(c, d, cr) for c, d, cr in linhas if d or cr]
        if not linhas:
            return
        assert all(d >= 0 and cr >= 0 and not (d and cr) for _, d, cr in linhas), linhas
        total_d, total_c = sum(d for _, d, _ in linhas), sum(c for _, _, c in linhas)
        assert total_d == total_c, f"{data} {evento} {historico}: D {total_d} != C {total_c}"
        self.lancamentos += 1
        id_lanc = f"L{self.lancamentos:05d}"
        for conta, d, cr in linhas:
            self.partidas.append({"id_lancamento": id_lanc, "data": data, "codigo_evento": evento,
                                  "codigo_conta": conta, "debito": d, "credito": cr,
                                  "historico": historico})
            self.saldos[conta] += d - cr


def D(conta: str, valor: int) -> tuple[str, int, int]:
    return (conta, valor, 0) if valor >= 0 else (conta, 0, -valor)


def C(conta: str, valor: int) -> tuple[str, int, int]:
    return (conta, 0, valor) if valor >= 0 else (conta, -valor, 0)


# ---------------------------------------------------------------- empréstimos

def cronograma(contrato: dict) -> list[dict]:
    """
    Parcelas mensais: juros sobre o saldo e principal (SAC ou PRICE), em centavos.
    Juros na carência pagos mês a mês. A última parcela absorve o arredondamento.
    """
    if contrato["carencia_meses"] and contrato.get("juros_na_carencia") != "pagos":
        raise NotImplementedError("Gerador da V1 só trata juros pagos na carência")
    valor = centavos(contrato["valor"])
    i = taxa_mensal(contrato["taxa_aa"])
    n_amort = contrato["prazo_meses"] - contrato["carencia_meses"]
    inicio = date.fromisoformat(contrato["data"])
    saldo = valor
    pmt = valor * i / (1 - (1 + i) ** -n_amort)  # parcela fixa do PRICE
    parcelas = []
    for k in range(1, contrato["prazo_meses"] + 1):
        juros = aplicar(saldo, i)
        if k <= contrato["carencia_meses"]:
            principal = 0
        elif k == contrato["prazo_meses"]:
            principal = saldo
        elif contrato["sistema"] == "SAC":
            principal = valor // n_amort
        else:
            principal = int(round(pmt)) - juros
        saldo -= principal
        parcelas.append({"data": somar_meses(inicio, k), "juros": juros, "principal": principal})
    return parcelas


def principal_a_vencer(parcelas: list[dict], depois_de: date, ate: date) -> int:
    return sum(p["principal"] for p in parcelas if depois_de < p["data"] <= ate)


# ---------------------------------------------------------------- imobilizado

def depreciacao_acumulada(bem: dict, vidas: dict, ate: date) -> int:
    """
    Depreciação acumulada do bem no fim do mês de `ate`: linear, a partir do mês seguinte ao da
    entrada em uso, até o mês anterior ao da baixa. Nunca passa do custo.
    """
    chave_vida = CLASSES_IMOBILIZADO[bem["classe"]][2]
    if chave_vida is None:
        return 0
    entrada = date.fromisoformat(bem["data"])
    ultimo = ate
    if bem.get("data_baixa"):
        baixa = date.fromisoformat(bem["data_baixa"])
        if baixa <= ate:
            ultimo = somar_meses(baixa, -1)
    meses = max(0, meses_entre(entrada, ultimo))
    custo = centavos(bem["custo"])
    return min(custo, custo * meses // (vidas[chave_vida] * 12))


# ---------------------------------------------------------------- gerador

class Gerador:
    def __init__(self, roteiro: dict, empresa: dict):
        self.r = roteiro
        self.emp = empresa
        self.livro = Livro()
        self.sorteio = random.Random(roteiro["semente"])
        self.vidas = empresa["politicas"]["vida_util_anos"]
        trib = empresa["tributacao"]
        self.icms = trib["icms_aliquota_unica_simplificada"]
        self.pis, self.cofins = trib["pis_nao_cumulativo"], trib["cofins_nao_cumulativo"]
        self.periodo = empresa["periodos"]
        self.abertura = date.fromisoformat(self.periodo["saldos_de_abertura"])
        self.inicio = date.fromisoformat(self.periodo["inicio_movimento"])
        self.fim = date.fromisoformat(self.periodo["fim_movimento"])
        self.contratos = {c["id"]: c for c in roteiro["emprestimos"]}
        self.parcelas = {c["id"]: cronograma(c) for c in roteiro["emprestimos"]}
        self.fotos: dict[date, dict[str, int]] = {}  # saldos no fim de cada mês
        self.planos: dict[tuple[int, int], dict] = {}
        self.base_diferida: dict[date, dict[str, int]] = {}

    # ------------------------------------------------------------ parâmetros do mês

    def params_trimestre(self, d: date) -> dict:
        return self.r["trimestres"][trimestre(d)]

    def tributos_sobre(self, valor: int) -> tuple[int, int, int]:
        """ICMS, PIS e COFINS. PIS e COFINS sem o ICMS na base (STF, Tema 69)."""
        icms = aplicar(valor, self.icms)
        return icms, aplicar(valor - icms, self.pis), aplicar(valor - icms, self.cofins)

    def plano_vendas(self, receita: int, margem: float) -> dict:
        """Venda, devolução, desconto e custo de um mês, a partir da receita bruta e da margem."""
        v = self.r["vendas"]
        icms, pis, cofins = self.tributos_sobre(receita)
        devolucao = aplicar(receita, v["devolucoes"])
        icms_d, pis_d, cofins_d = self.tributos_sobre(devolucao)
        desconto = aplicar(receita, v["descontos_comerciais"])
        receita_liquida = (receita - icms - pis - cofins
                           - (devolucao - icms_d - pis_d - cofins_d) - desconto)
        custo_devolucao = aplicar(devolucao - icms_d - pis_d - cofins_d, 1 - margem)
        cmv_liquido = aplicar(receita_liquida, 1 - margem)
        return {"receita": receita, "icms": icms, "pis": pis, "cofins": cofins,
                "devolucao": devolucao, "icms_d": icms_d, "pis_d": pis_d, "cofins_d": cofins_d,
                "desconto": desconto, "receita_liquida": receita_liquida,
                "custo_devolucao": custo_devolucao, "cmv_liquido": cmv_liquido,
                "cmv_bruto": cmv_liquido + custo_devolucao}

    def compra_bruta(self, custo_liquido: int) -> dict:
        """Nota de compra cujo custo líquido de tributos recuperáveis é `custo_liquido`."""
        k = 1 - self.icms - (self.pis + self.cofins) * (1 - self.icms)
        bruto = aplicar(custo_liquido, 1 / k)
        icms, pis, cofins = self.tributos_sobre(bruto)
        return {"bruto": bruto, "icms": icms, "pis": pis, "cofins": cofins,
                "estoque": bruto - icms - pis - cofins}

    def fator_salarial(self, d: date) -> float:
        f = self.r["folha"]
        reajustes = sum(1 for ano in (2025, 2026) if d >= date(ano, f["mes_reajuste"], 1))
        return (1 + f["reajuste_anual"]) ** reajustes

    def plano_folha(self, d: date, receita: int) -> dict:
        f = self.r["folha"]
        fator = self.fator_salarial(d)
        expansao = 1 + f["expansao_comercial_4t25"] if d >= date(2025, 10, 1) else 1
        sal_com = centavos(f["salarios_comercial"] * fator * expansao)
        sal_adm = centavos(f["salarios_administrativo"] * fator)
        honor = centavos(f["honorarios_administracao"])
        comissoes = aplicar(receita, f["comissoes"])
        base_com, base_adm = sal_com + comissoes, sal_adm
        remuneracao = sal_com + comissoes + sal_adm + honor
        p = {
            "sal_com": sal_com, "sal_adm": sal_adm, "honor": honor, "comissoes": comissoes,
            "benef_com": centavos(f["beneficios_comercial"] * fator),
            "benef_adm": centavos(f["beneficios_administrativo"] * fator),
            "inss_com": aplicar(base_com, f["inss_patronal"]),
            "inss_adm": aplicar(base_adm, f["inss_patronal"]),
            "fgts_com": aplicar(base_com, f["fgts"]), "fgts_adm": aplicar(base_adm, f["fgts"]),
            "inss_emp": aplicar(remuneracao, f["inss_empregado"]),
            "irrf": aplicar(remuneracao, f["irrf_salarios"]),
        }
        p["liquido"] = remuneracao - p["inss_emp"] - p["irrf"]
        enc = 1 + f["encargos_sobre_ferias_13"]
        p["ferias_com"] = aplicar(base_com, Decimal(1) / 12 * Decimal(4) / 3 * Decimal(str(enc)))
        p["ferias_adm"] = aplicar(base_adm, Decimal(1) / 12 * Decimal(4) / 3 * Decimal(str(enc)))
        p["decimo_com"] = aplicar(base_com, Decimal(str(enc)) / 12)
        p["decimo_adm"] = aplicar(base_adm, Decimal(str(enc)) / 12)
        p["plr"] = centavos(f["plr_mensal"][d.year])
        return p

    def plano_despesas(self, d: date, receita: int) -> dict:
        e = self.r["despesas"]
        fixo = 1 + e["reajuste_fixas_2026"] if d.year == 2026 else 1
        marketing = e["marketing_4t25"] if trimestre(d) == "4T25" else e["marketing"]

        def fixa(chave):
            return centavos(e[chave] * fixo)

        p = {
            "3.3.01.007": aplicar(receita, e["fretes_sobre_vendas"]),
            "3.3.01.008": aplicar(receita, marketing),
            "3.3.01.009": aplicar(receita, e["combustivel_e_frota"]),
            "3.3.01.011": fixa("aluguel_showroom"),
            "3.3.02.008": fixa("energia_e_agua"),
            "3.3.02.009": fixa("telecom_e_internet"),
            "3.3.02.010": fixa("servicos_de_terceiros"),
            "3.3.02.011": fixa("auditoria_independente"),
            "3.3.02.013": fixa("manutencao_predial"),
            "3.3.02.014": fixa("software_saas"),
            "3.3.02.015": fixa("material_de_escritorio"),
            "3.3.02.016": fixa("iptu_e_taxas"),
            "3.3.05.002": fixa("outras_despesas"),
        }
        servicos = p["3.3.02.010"] + p["3.3.02.011"]
        retencoes = {"iss": aplicar(servicos, e["iss_retido"]),
                     "irrf": aplicar(servicos, e["irrf_terceiros"])}
        return {"contas": p, **retencoes}

    def planejar_mes(self, d: date) -> dict:
        """Calcula, no 1º dia do mês, tudo o que depende dos saldos de abertura do mês."""
        q = self.params_trimestre(d)
        variacao = self.r["variacao_mensal"]
        receita = centavos(q["receita_bruta_mensal"] * (1 + self.sorteio.uniform(-variacao, variacao)))
        vendas = self.plano_vendas(receita, q["margem_bruta"])
        fim_mes = ultimo_dia(d.year, d.month)
        trimestral = fim_de_trimestre(fim_mes)
        baixa_incobravel = centavos(q["baixas_incobraveis"]) if trimestral else 0
        baixa_estoque = centavos(self.r["estoques"]["baixa_trimestral"]) if trimestral else 0

        # Adiantamento recebido no último mês do trimestre é entregue (aplicado) no mês seguinte
        adiant_aplicado = self.livro.credor(ADIANT_CLIENTES)

        # Clientes: o recebimento é o que leva o saldo ao prazo médio do trimestre
        clientes_fim = aplicar(receita, Decimal(q["pmr_dias"]) / 30)
        recebimento = (self.livro.saldo(CLIENTES) + receita - vendas["devolucao"]
                       - vendas["desconto"] - baixa_incobravel - adiant_aplicado - clientes_fim)

        # Estoque: compra o necessário para fechar no prazo médio de estocagem
        estoque_fim = aplicar(vendas["cmv_liquido"], Decimal(q["pme_dias"]) / 30)
        custo_compra = (estoque_fim - self.livro.saldo(MERCADORIAS) - vendas["custo_devolucao"]
                        + vendas["cmv_bruto"] + baixa_estoque)
        assert custo_compra > 0, f"{d}: compra negativa"
        compra = self.compra_bruta(custo_compra)

        # Fornecedores: paga o que excede o prazo médio de pagamento (nunca mais do que deve)
        forn_inicio = self.livro.credor(FORN_MERC)
        forn_fim = aplicar(compra["bruto"], Decimal(q["pmp_dias"]) / 30)
        pagamento = max(0, min(forn_inicio, forn_inicio + compra["bruto"] - forn_fim))

        plano = {"q": q, "vendas": vendas, "compra": compra, "recebimento": recebimento,
                 "adiant_aplicado": adiant_aplicado, "pagamento_fornecedor": pagamento,
                 "baixa_incobravel": baixa_incobravel, "baixa_estoque": baixa_estoque,
                 "folha": self.plano_folha(d, receita),
                 "despesas": self.plano_despesas(d, receita),
                 "cdb_inicio": self.livro.saldo(CDB)}
        self.planos[(d.year, d.month)] = plano
        return plano

    # ------------------------------------------------------------ abertura

    def montar_abertura(self) -> None:
        """Balanço de 31/12/2024 em regime, a partir do mês-base de dezembro."""
        base = self.r["dezembro_2024"]
        ab = self.r["abertura"]
        receita = centavos(base["receita_bruta_mensal"])
        vendas = self.plano_vendas(receita, base["margem_bruta"])
        compra = self.compra_bruta(vendas["cmv_bruto"] - vendas["custo_devolucao"])
        folha = self.plano_folha(self.abertura, receita)
        folha["plr"] = centavos(self.r["folha"]["plr_mensal"][2024])
        desp = self.plano_despesas(self.abertura, receita)
        self.ferias_mes_anterior = folha["ferias_com"] + folha["ferias_adm"]

        s = {}
        s[CAIXA] = centavos(ab["caixa_geral"])
        s[BANCOS] = centavos(ab["bancos"])
        s[CDB] = centavos(ab["cdb"])
        s[CLIENTES] = aplicar(receita, Decimal(base["pmr_dias"]) / 30)
        s[PECLD] = -aplicar(s[CLIENTES], base["taxa_perda_esperada"])
        s[MERCADORIAS] = aplicar(vendas["cmv_liquido"], Decimal(base["pme_dias"]) / 30)
        s[PROV_ESTOQUE] = -aplicar(s[MERCADORIAS], self.r["estoques"]["taxa_provisao_perdas"])
        s[SEGUROS_A_APROPRIAR] = centavos(ab["seguros_a_apropriar"])
        base_dif = -s[PECLD] - s[PROV_ESTOQUE]
        aliq_cs = self.emp["tributacao"]["csll_aliquota"]
        aliq_ir = Decimal(str(self.emp["tributacao"]["aliquota_diferido"])) - Decimal(str(aliq_cs))
        s[IRPJ_DIF] = aplicar(base_dif, aliq_ir)
        s[CSLL_DIF] = aplicar(base_dif, aliq_cs)

        for bem in self.r["bens"]:
            if bem["forma"] != "abertura":
                continue
            conta_custo, conta_dep, _ = CLASSES_IMOBILIZADO[bem["classe"]]
            s[conta_custo] = s.get(conta_custo, 0) + centavos(bem["custo"])
            if conta_dep:
                s[conta_dep] = s.get(conta_dep, 0) - depreciacao_acumulada(bem, self.vidas, self.abertura)

        s[SALARIOS_PAGAR] = -folha["liquido"]
        s[INSS_REC] = -(folha["inss_com"] + folha["inss_adm"] + folha["inss_emp"])
        s[FGTS_REC] = -(folha["fgts_com"] + folha["fgts_adm"])
        s[PROV_FERIAS] = -self.ferias_mes_anterior * self.r["folha"]["meses_de_ferias_provisionados"]
        s[PLR_PAGAR] = -folha["plr"] * 12
        s[FORN_MERC] = -aplicar(compra["bruto"], Decimal(base["pmp_dias"]) / 30)
        s[FORN_SERV] = -(sum(desp["contas"].values()) - desp["iss"] - desp["irrf"]
                         + folha["benef_com"] + folha["benef_adm"])
        s[ICMS_RECOLHER] = -(vendas["icms"] - vendas["icms_d"] - compra["icms"])
        s[PIS_RECOLHER] = -(vendas["pis"] - vendas["pis_d"] - compra["pis"])
        s[COFINS_RECOLHER] = -(vendas["cofins"] - vendas["cofins_d"] - compra["cofins"])
        s[IRRF_RECOLHER] = -(folha["irrf"] + desp["irrf"])
        s[ISS_RECOLHER] = -desp["iss"]
        s[IRPJ_PAGAR] = -centavos(ab["irpj_a_pagar_4t24"])
        s[CSLL_PAGAR] = -centavos(ab["csll_a_pagar_4t24"])
        s[DIVIDENDOS_PAGAR] = -centavos(ab["dividendos_a_pagar_2024"])

        for cid, contrato in self.contratos.items():
            if date.fromisoformat(contrato["data"]) > self.abertura:
                continue
            conta_cp, conta_lp = CONTAS_EMPRESTIMO[contrato["modalidade"]]
            parcelas = self.parcelas[cid]
            saldo = centavos(contrato["valor"]) - sum(p["principal"] for p in parcelas
                                                      if p["data"] <= self.abertura)
            cp = principal_a_vencer(parcelas, self.abertura, somar_meses(self.abertura, 12))
            s[conta_cp] = s.get(conta_cp, 0) - cp
            s[conta_lp] = s.get(conta_lp, 0) - (saldo - cp)

        s[CAPITAL] = -centavos(ab["capital_social"])
        s[RESERVA_LEGAL] = -centavos(ab["reserva_legal"])
        s[RETENCAO] = -sum(s.values())  # fecha o balanço
        assert s[RETENCAO] < 0, "Reserva de retenção negativa: revise a abertura do roteiro"

        for conta, valor in s.items():
            if valor:
                self.livro.saldos[conta] = valor
        self.abertura_saldos = {c: v for c, v in s.items() if v}
        self.fotos[self.abertura] = dict(self.livro.saldos)
        self.base_diferida[self.abertura] = {"perda_esperada_creditos": -s[PECLD],
                                             "provisao_perdas_estoques": -s[PROV_ESTOQUE]}

    # ------------------------------------------------------------ eventos do mês

    def tarefas_do_mes(self, ano: int, mes: int) -> list[tuple[date, int, object]]:
        """(data, prioridade, função). Executadas em ordem de data e prioridade."""
        primeiro, fim = date(ano, mes, 1), ultimo_dia(ano, mes)
        t = [(primeiro, 0, lambda: self.planejar_mes(primeiro)),
             (date(ano, mes, 5), 10, lambda: self.pagar_folha(date(ano, mes, 5))),
             (date(ano, mes, 10), 10, lambda: self.pagar_fornecedores(date(ano, mes, 10))),
             (date(ano, mes, 15), 10, lambda: self.receber_clientes(date(ano, mes, 15), metade=1)),
             (date(ano, mes, 20), 10, lambda: self.recolher_tributos(date(ano, mes, 20))),
             (fim, 10, lambda: self.vender(fim)),
             (fim, 13, lambda: self.receber_clientes(fim, metade=2)),
             (fim, 20, lambda: self.comprar(fim)),
             (fim, 30, lambda: self.apropriar_folha(fim)),
             (fim, 31, lambda: self.apropriar_despesas(fim)),
             (fim, 40, lambda: self.depreciar(fim)),
             (fim, 46, lambda: self.ajustar_provisoes(fim)),
             (fim, 50, lambda: self.render_aplicacoes(fim)),
             (fim, 55, lambda: self.apurar_tributos_indiretos(fim)),
             (fim, 60, lambda: self.reclassificar_emprestimos(fim)),
             (fim, 99, lambda: self.fotografar(fim))]
        if mes % 3 == 0:
            t.append((date(ano, mes, 20), 11, lambda: self.receber_adiantamento(date(ano, mes, 20))))
            t.append((fim, 70, lambda: self.apurar_ir(fim)))
        if mes % 3 == 1:
            t.append((fim, 5, lambda: self.pagar_ir(fim)))
        if mes == self.r["despesas"]["mes_renovacao_seguro"]:
            t.append((date(ano, mes, 10), 11, lambda: self.renovar_seguro(date(ano, mes, 10))))
        if mes == 2:
            t.append((date(ano, mes, 10), 12, lambda: self.pagar_plr(date(ano, mes, 10))))
        if mes == 11:
            t.append((fim, 32, lambda: self.pagar_13(fim, parcela=1)))
        if mes == 12:
            t.append((date(ano, mes, 20), 12, lambda: self.pagar_13_dezembro(date(ano, mes, 20))))
            t.append((fim, 80, lambda: self.encerrar_exercicio(fim)))
        return t

    def tarefas_pontuais(self) -> list[tuple[date, int, object]]:
        """Datas que vêm do roteiro: empréstimos, bens, dividendos."""
        t = []
        for cid, contrato in self.contratos.items():
            data = date.fromisoformat(contrato["data"])
            if self.inicio <= data <= self.fim and contrato["modalidade"] == "CCB":
                t.append((data, 15, lambda c=contrato: self.captar(c)))
            for p in self.parcelas[cid]:
                if self.inicio <= p["data"] <= self.fim:
                    t.append((p["data"], 14, lambda c=cid, p=p: self.pagar_parcela(c, p)))
        for bem in self.r["bens"]:
            data = date.fromisoformat(bem["data"])
            if bem["forma"] == "a_vista":
                t.append((data, 16, lambda b=bem: self.comprar_bem_a_vista(b)))
            elif bem["forma"] == "a_prazo":
                t.append((data, 16, lambda b=bem: self.comprar_bem_a_prazo(b)))
                valor = centavos(bem["custo"])
                n = bem["parcelas"]
                for k in range(1, n + 1):
                    parcela = valor // n if k < n else valor - valor // n * (n - 1)
                    t.append((somar_meses(data, k), 16,
                              lambda b=bem, v=parcela: self.pagar_fornecedor_imobilizado(b, v)))
            elif bem["forma"] == "finame":
                t.append((data, 16, lambda b=bem: self.comprar_bem_finame(b)))
            elif bem["forma"] == "obra":
                pagamentos = bem["pagamentos"]
                valor = centavos(bem["custo"])
                for k, dp in enumerate(pagamentos):
                    parte = valor // len(pagamentos)
                    if k == len(pagamentos) - 1:
                        parte = valor - parte * (len(pagamentos) - 1)
                    t.append((date.fromisoformat(dp), 16,
                              lambda b=bem, v=parte: self.pagar_obra(b, v)))
                t.append((data, 41, lambda b=bem: self.concluir_obra(b)))
            if bem.get("data_baixa"):
                t.append((date.fromisoformat(bem["data_baixa"]), 17,
                          lambda b=bem: self.vender_bem(b)))
        for chave in ("pagamento_dividendos_2024", "pagamento_dividendos_2025"):
            data = date.fromisoformat(self.r["datas"][chave])
            t.append((data, 18, lambda d=data: self.pagar_dividendos(d)))
        return t

    def plano(self, d: date) -> dict:
        return self.planos[(d.year, d.month)]

    # vendas e clientes
    def vender(self, d: date) -> None:
        v = self.plano(d)["vendas"]
        L = self.livro
        L.lancar(d, "EV01", [D(CLIENTES, v["receita"]), C(RECEITA, v["receita"])],
                 "Faturamento do mês")
        L.lancar(d, "EV02", [D(ICMS_VENDAS, v["icms"]), D(PIS_VENDAS, v["pis"]),
                             D(COFINS_VENDAS, v["cofins"]), C(ICMS_RECOLHER, v["icms"]),
                             C(PIS_RECOLHER, v["pis"]), C(COFINS_RECOLHER, v["cofins"])],
                 "Tributos sobre o faturamento do mês")
        L.lancar(d, "EV04", [D(DEVOLUCOES, v["devolucao"]), C(CLIENTES, v["devolucao"]),
                             D(ICMS_RECOLHER, v["icms_d"]), C(ICMS_VENDAS, v["icms_d"]),
                             D(PIS_RECOLHER, v["pis_d"]), C(PIS_VENDAS, v["pis_d"]),
                             D(COFINS_RECOLHER, v["cofins_d"]), C(COFINS_VENDAS, v["cofins_d"]),
                             D(MERCADORIAS, v["custo_devolucao"]), C(CMV, v["custo_devolucao"])],
                 "Devoluções de vendas do mês")
        L.lancar(d, "EV03", [D(DESCONTOS_CONC, v["desconto"]), C(CLIENTES, v["desconto"])],
                 "Abatimentos concedidos no mês")
        aplicado = self.plano(d)["adiant_aplicado"]
        L.lancar(d, "EV07", [D(ADIANT_CLIENTES, aplicado), C(CLIENTES, aplicado)],
                 "Entrega de pedido adiantado")

    def receber_clientes(self, d: date, metade: int) -> None:
        total = self.plano(d)["recebimento"]
        valor = total // 2 if metade == 1 else total - total // 2
        self.livro.lancar(d, "EV05", [D(BANCOS, valor), C(CLIENTES, valor)],
                          f"Recebimentos de clientes ({metade}ª quinzena)")
        if metade == 1:
            juros = aplicar(total, self.r["vendas"]["juros_recebidos_clientes"])
            self.livro.lancar(d, "EV08", [D(BANCOS, juros), C(JUROS_CLIENTES, juros)],
                              "Juros e multas de clientes em atraso")

    def receber_adiantamento(self, d: date) -> None:
        valor = centavos(self.r["vendas"]["adiantamento_cliente"])
        self.livro.lancar(d, "EV06", [D(BANCOS, valor), C(ADIANT_CLIENTES, valor)],
                          "Adiantamento de cliente para pedido do mês seguinte")

    # compras e fornecedores
    def comprar(self, d: date) -> None:
        p = self.plano(d)
        c, v = p["compra"], p["vendas"]
        L = self.livro
        L.lancar(d, "EV09", [D(MERCADORIAS, c["estoque"]), D(ICMS_REC, c["icms"]),
                             D(PIS_REC, c["pis"]), D(COFINS_REC, c["cofins"]),
                             C(FORN_MERC, c["bruto"])], "Compras de mercadorias do mês")
        L.lancar(d, "EV10", [D(CMV, v["cmv_bruto"]), C(MERCADORIAS, v["cmv_bruto"])],
                 "Custo das mercadorias vendidas (custo médio)")

    def pagar_fornecedores(self, d: date) -> None:
        p = self.plano(d)
        merc = p["pagamento_fornecedor"]
        desconto = aplicar(merc, self.r["compras"]["desconto_obtido"])
        servicos = self.livro.credor(FORN_SERV)
        self.livro.lancar(d, "EV11", [D(FORN_MERC, merc), D(FORN_SERV, servicos),
                                      C(BANCOS, merc + servicos - desconto),
                                      C(DESCONTOS_OBTIDOS, desconto)],
                          "Pagamentos a fornecedores")

    # folha
    def apropriar_folha(self, d: date) -> None:
        f = self.plano(d)["folha"]
        L = self.livro
        L.lancar(d, "EV15", [
            D("3.3.01.001", f["sal_com"]), D("3.3.01.002", f["comissoes"]),
            D("3.3.01.003", f["benef_com"]), D("3.3.01.004", f["inss_com"]),
            D("3.3.01.005", f["fgts_com"]), D("3.3.02.001", f["sal_adm"]),
            D("3.3.02.002", f["benef_adm"]), D("3.3.02.003", f["inss_adm"]),
            D("3.3.02.004", f["fgts_adm"]), D("3.3.02.007", f["honor"]),
            C(SALARIOS_PAGAR, f["liquido"]),
            C(INSS_REC, f["inss_com"] + f["inss_adm"] + f["inss_emp"]),
            C(FGTS_REC, f["fgts_com"] + f["fgts_adm"]), C(IRRF_RECOLHER, f["irrf"]),
            C(FORN_SERV, f["benef_com"] + f["benef_adm"])], "Folha de pagamento do mês")
        if d.month != 12:  # em dezembro o 13º é provisionado antes do pagamento (dia 20)
            self.provisionar_ferias_13(d, f)
        else:
            self.provisionar_ferias_13(d, f, so_ferias=True)
        L.lancar(d, "EV19", [D("3.3.02.006", f["plr"]), C(PLR_PAGAR, f["plr"])],
                 "Provisão de participação nos lucros")
        self.ferias_mes_anterior = f["ferias_com"] + f["ferias_adm"]

    def provisionar_ferias_13(self, d: date, f: dict, so_ferias=False, so_13=False) -> None:
        ferias = 0 if so_13 else f["ferias_com"] + f["ferias_adm"]
        decimo = 0 if so_ferias else f["decimo_com"] + f["decimo_adm"]
        com = (0 if so_13 else f["ferias_com"]) + (0 if so_ferias else f["decimo_com"])
        adm = (0 if so_13 else f["ferias_adm"]) + (0 if so_ferias else f["decimo_adm"])
        self.livro.lancar(d, "EV17", [D("3.3.01.006", com), D("3.3.02.005", adm),
                                      C(PROV_FERIAS, ferias), C(PROV_13, decimo)],
                          "Provisão de férias e 13º salário")

    def pagar_folha(self, d: date) -> None:
        L = self.livro
        L.lancar(d, "EV16", [D(SALARIOS_PAGAR, L.credor(SALARIOS_PAGAR)),
                             C(BANCOS, L.credor(SALARIOS_PAGAR))], "Pagamento de salários")
        ferias = self.ferias_mes_anterior
        L.lancar(d, "EV18", [D(PROV_FERIAS, ferias), C(BANCOS, ferias)],
                 "Pagamento de férias do mês")

    def pagar_13(self, d: date, parcela: int) -> None:
        L = self.livro
        valor = L.credor(PROV_13) // 2 if parcela == 1 else L.credor(PROV_13)
        L.lancar(d, "EV18", [D(PROV_13, valor), C(BANCOS, valor)],
                 f"Pagamento do 13º salário ({parcela}ª parcela)")

    def pagar_13_dezembro(self, d: date) -> None:
        """Em 20/12 provisiona o 13º de dezembro e paga a 2ª parcela: o saldo zera no ano."""
        self.provisionar_ferias_13(d, self.plano(d)["folha"], so_13=True)
        self.pagar_13(d, parcela=2)

    def pagar_plr(self, d: date) -> None:
        dezembro = self.fotos[date(d.year - 1, 12, 31)]
        valor = -dezembro.get(PLR_PAGAR, 0)
        self.livro.lancar(d, "EV20", [D(PLR_PAGAR, valor), C(BANCOS, valor)],
                          f"Pagamento da PLR de {d.year - 1}")

    # despesas
    def apropriar_despesas(self, d: date) -> None:
        p = self.plano(d)["despesas"]
        total = sum(p["contas"].values())
        linhas = [D(conta, valor) for conta, valor in p["contas"].items()]
        linhas += [C(FORN_SERV, total - p["iss"] - p["irrf"]), C(ISS_RECOLHER, p["iss"]),
                   C(IRRF_RECOLHER, p["irrf"])]
        L = self.livro
        L.lancar(d, "EV21", linhas, "Despesas com serviços e consumo do mês")
        seguro = min(centavos(self.r["despesas"]["seguro_anual"]) // 12, L.saldo(SEGUROS_A_APROPRIAR))
        L.lancar(d, "EV23", [D("3.3.02.012", seguro), C(SEGUROS_A_APROPRIAR, seguro)],
                 "Apropriação do seguro")
        tarifas = centavos(self.r["despesas"]["tarifas_bancarias"])
        L.lancar(d, "EV24", [D(TARIFAS, tarifas), C(BANCOS, tarifas)], "Tarifas bancárias")

    def renovar_seguro(self, d: date) -> None:
        valor = centavos(self.r["despesas"]["seguro_anual"])
        self.livro.lancar(d, "EV22", [D(SEGUROS_A_APROPRIAR, valor), C(BANCOS, valor)],
                          "Renovação anual do seguro patrimonial")

    # tributos
    def apurar_tributos_indiretos(self, d: date) -> None:
        L = self.livro
        linhas = []
        for recolher, recuperar in ((ICMS_RECOLHER, ICMS_REC), (PIS_RECOLHER, PIS_REC),
                                    (COFINS_RECOLHER, COFINS_REC)):
            valor = min(L.credor(recolher), L.saldo(recuperar))
            linhas += [D(recolher, valor), C(recuperar, valor)]
        L.lancar(d, "EV13", linhas, "Apuração mensal de ICMS, PIS e COFINS")

    def recolher_tributos(self, d: date) -> None:
        anterior = self.fotos[fim_do_mes_anterior(d)]
        contas = (ICMS_RECOLHER, PIS_RECOLHER, COFINS_RECOLHER, IRRF_RECOLHER, ISS_RECOLHER,
                  INSS_REC, FGTS_REC)
        linhas = [D(c, -anterior.get(c, 0)) for c in contas]
        total = sum(-anterior.get(c, 0) for c in contas)
        self.livro.lancar(d, "EV14", linhas + [C(BANCOS, total)],
                          "Recolhimento de tributos e encargos do mês anterior")

    def apurar_ir(self, d: date) -> None:
        """IRPJ e CSLL do trimestre (Lucro Real trimestral) e tributos diferidos (CPC 32)."""
        L = self.livro
        inicio_tri = fim_do_mes_anterior(d, 3)
        antes = self.fotos[inicio_tri]
        lair = -sum(L.saldos[c] - antes.get(c, 0) for c in list(L.saldos)
                    if c.startswith("3") and not c.startswith("3.5"))
        base_fim = {"perda_esperada_creditos": L.credor(PECLD),
                    "provisao_perdas_estoques": L.credor(PROV_ESTOQUE)}
        base_ini = self.base_diferida[inicio_tri]
        adicoes = sum(base_fim.values()) - sum(base_ini.values())
        tributavel = lair + adicoes
        assert tributavel > 0, f"{d}: lucro tributável negativo"
        trib = self.emp["tributacao"]
        limite = centavos(trib["irpj_adicional_limite_trimestral_rs"])
        irpj = aplicar(tributavel, trib["irpj_aliquota"]) + aplicar(
            max(0, tributavel - limite), trib["irpj_adicional_aliquota"])
        csll = aplicar(tributavel, trib["csll_aliquota"])
        L.lancar(d, "EV33", [D(IRPJ_CORRENTE, irpj), D(CSLL_CORRENTE, csll),
                             C(IRPJ_PAGAR, irpj), C(CSLL_PAGAR, csll)],
                 f"IRPJ e CSLL correntes do {trimestre(d)}")

        base = sum(base_fim.values())
        aliq_cs = Decimal(str(trib["csll_aliquota"]))
        aliq_ir = Decimal(str(trib["aliquota_diferido"])) - aliq_cs
        ajuste_ir = aplicar(base, aliq_ir) - L.saldo(IRPJ_DIF)
        ajuste_cs = aplicar(base, aliq_cs) - L.saldo(CSLL_DIF)
        # Ativo diferido sobe: D ativo / C receita de diferido. Desce: o inverso.
        L.lancar(d, "EV34", [D(IRPJ_DIF, ajuste_ir), C(IRPJ_DIFERIDO, ajuste_ir),
                             D(CSLL_DIF, ajuste_cs), C(CSLL_DIFERIDA, ajuste_cs)],
                 f"IRPJ e CSLL diferidos do {trimestre(d)}")
        self.base_diferida[d] = base_fim

        compensa = min(L.saldo(IRRF_APLIC), L.credor(IRPJ_PAGAR))
        L.lancar(d, "EV35", [D(IRPJ_PAGAR, compensa), C(IRRF_APLIC, compensa)],
                 "Compensação do IRRF sobre aplicações com o IRPJ do trimestre")

    def pagar_ir(self, d: date) -> None:
        L = self.livro
        irpj, csll = L.credor(IRPJ_PAGAR), L.credor(CSLL_PAGAR)
        L.lancar(d, "EV36", [D(IRPJ_PAGAR, irpj), D(CSLL_PAGAR, csll), C(BANCOS, irpj + csll)],
                 "Pagamento de IRPJ e CSLL do trimestre anterior (quota única)")

    # provisões
    def ajustar_provisoes(self, d: date) -> None:
        p = self.plano(d)
        L = self.livro
        L.lancar(d, "EV27", [D(PECLD, p["baixa_incobravel"]), C(CLIENTES, p["baixa_incobravel"])],
                 "Baixa de créditos incobráveis contra a provisão")
        ajuste = aplicar(L.saldo(CLIENTES), p["q"]["taxa_perda_esperada"]) - L.credor(PECLD)
        # Constituição: D despesa / C provisão. Reversão (ajuste negativo): lançamento inverso.
        L.lancar(d, "EV26", [D(PERDA_ESPERADA, ajuste), C(PECLD, ajuste)],
                 "Perda esperada com créditos (matriz de provisão)")
        L.lancar(d, "EV29", [D(PROV_ESTOQUE, p["baixa_estoque"]),
                             C(MERCADORIAS, p["baixa_estoque"])],
                 "Baixa de mercadorias avariadas e vencidas contra a provisão")
        ajuste = (aplicar(L.saldo(MERCADORIAS), self.r["estoques"]["taxa_provisao_perdas"])
                  - L.credor(PROV_ESTOQUE))
        L.lancar(d, "EV28", [D(PERDAS_ESTOQUE, ajuste), C(PROV_ESTOQUE, ajuste)],
                 "Provisão para perdas em estoques (valor realizável líquido)")

    # imobilizado
    def depreciar(self, d: date) -> None:
        anterior = fim_do_mes_anterior(d)
        por_conta: dict[tuple[str, str], int] = defaultdict(int)
        for bem in self.r["bens"]:
            _, conta_dep, chave = CLASSES_IMOBILIZADO[bem["classe"]]
            if chave is None:
                continue
            valor = (depreciacao_acumulada(bem, self.vidas, d)
                     - depreciacao_acumulada(bem, self.vidas, anterior))
            if valor:
                por_conta[(DESPESA_DEPRECIACAO[bem["classe"]], conta_dep)] += valor
        deprec = [(dsp, dep, v) for (dsp, dep), v in por_conta.items() if dsp != AMORT_INTANG]
        amort = [(dsp, dep, v) for (dsp, dep), v in por_conta.items() if dsp == AMORT_INTANG]
        for evento, itens, hist in (("EV47", deprec, "Depreciação do mês"),
                                    ("EV48", amort, "Amortização do intangível")):
            despesas: dict[str, int] = defaultdict(int)
            redutoras: dict[str, int] = defaultdict(int)
            for dsp, dep, v in itens:
                despesas[dsp] += v
                redutoras[dep] += v
            self.livro.lancar(d, evento, [D(c, v) for c, v in sorted(despesas.items())]
                              + [C(c, v) for c, v in sorted(redutoras.items())], hist)

    def comprar_bem_a_vista(self, bem: dict) -> None:
        d, conta, valor = date.fromisoformat(bem["data"]), CLASSES_IMOBILIZADO[bem["classe"]][0], centavos(bem["custo"])
        evento = "EV50" if bem["classe"] == "softwares" else "EV42"
        self.livro.lancar(d, evento, [D(conta, valor), C(BANCOS, valor)], bem["descricao"])

    def comprar_bem_a_prazo(self, bem: dict) -> None:
        d, conta, valor = date.fromisoformat(bem["data"]), CLASSES_IMOBILIZADO[bem["classe"]][0], centavos(bem["custo"])
        self.livro.lancar(d, "EV43", [D(conta, valor), C(FORN_IMOB, valor)],
                          f"{bem['descricao']} (compra a prazo)")

    def pagar_fornecedor_imobilizado(self, bem: dict, valor: int) -> None:
        d = self.data_atual
        self.livro.lancar(d, "EV44", [D(FORN_IMOB, valor), C(BANCOS, valor)],
                          f"Parcela de {bem['descricao']}")

    def comprar_bem_finame(self, bem: dict) -> None:
        """O banco paga direto ao fornecedor: o bem entra contra o financiamento, sem caixa."""
        d = date.fromisoformat(bem["data"])
        contrato = self.contratos[bem["contrato"]]
        conta_cp, conta_lp = CONTAS_EMPRESTIMO[contrato["modalidade"]]
        valor = centavos(bem["custo"])
        # Cada bem leva a sua parte do contrato; o curto prazo é proporcional ao valor
        total = centavos(contrato["valor"])
        cp_total = principal_a_vencer(self.parcelas[contrato["id"]], d, somar_meses(d, 12))
        cp = cp_total * valor // total
        self.livro.lancar(d, "EV45", [D(CLASSES_IMOBILIZADO[bem["classe"]][0], valor),
                                      C(conta_cp, cp), C(conta_lp, valor - cp)],
                          f"{bem['descricao']} (financiado pelo {contrato['id']})")

    def pagar_obra(self, bem: dict, valor: int) -> None:
        self.livro.lancar(self.data_atual, "EV42", [D(IMOB_ANDAMENTO, valor), C(BANCOS, valor)],
                          f"Medição da obra: {bem['descricao']}")

    def concluir_obra(self, bem: dict) -> None:
        d, valor = date.fromisoformat(bem["data"]), centavos(bem["custo"])
        conta = CLASSES_IMOBILIZADO[bem["classe"]][0]
        self.livro.lancar(d, "EV46", [D(conta, valor), C(IMOB_ANDAMENTO, valor)],
                          f"Conclusão da obra: {bem['descricao']} entra em uso")

    def vender_bem(self, bem: dict) -> None:
        d = date.fromisoformat(bem["data_baixa"])
        conta_custo, conta_dep, _ = CLASSES_IMOBILIZADO[bem["classe"]]
        custo, venda = centavos(bem["custo"]), centavos(bem.get("valor_venda", 0))
        dep = depreciacao_acumulada(bem, self.vidas, d)
        resultado = venda - (custo - dep)
        linhas = [D(BANCOS, venda), D(conta_dep, dep), C(conta_custo, custo)]
        linhas.append(C(GANHO_ALIENACAO, resultado) if resultado >= 0 else D(PERDA_ALIENACAO, -resultado))
        self.livro.lancar(d, "EV49", linhas, f"Venda de {bem['descricao']}")

    # empréstimos
    def captar(self, contrato: dict) -> None:
        d = date.fromisoformat(contrato["data"])
        conta_cp, conta_lp = CONTAS_EMPRESTIMO[contrato["modalidade"]]
        valor = centavos(contrato["valor"])
        cp = principal_a_vencer(self.parcelas[contrato["id"]], d, somar_meses(d, 12))
        L = self.livro
        L.lancar(d, "EV37", [D(BANCOS, valor), C(conta_cp, cp), C(conta_lp, valor - cp)],
                 f"Captação {contrato['id']} ({contrato['modalidade']}, {contrato['credor']})")
        iof = aplicar(valor, self.r["financeiro"]["iof_credito"])
        L.lancar(d, "EV24", [D(IOF, iof), C(BANCOS, iof)], f"IOF sobre o {contrato['id']}")

    def pagar_parcela(self, cid: str, p: dict) -> None:
        conta_cp, _ = CONTAS_EMPRESTIMO[self.contratos[cid]["modalidade"]]
        d, L = p["data"], self.livro
        L.lancar(d, "EV38", [D(JUROS_EMPREST, p["juros"]), C(conta_cp, p["juros"])],
                 f"Juros do {cid}")
        L.lancar(d, "EV39", [D(conta_cp, p["juros"]), C(BANCOS, p["juros"])],
                 f"Pagamento de juros do {cid}")
        L.lancar(d, "EV40", [D(conta_cp, p["principal"]), C(BANCOS, p["principal"])],
                 f"Amortização do {cid}")

    def reclassificar_emprestimos(self, d: date) -> None:
        """Leva para o circulante o principal que vence nos próximos 12 meses (CPC 26)."""
        limite = somar_meses(d, 12)
        for modalidade, (conta_cp, conta_lp) in CONTAS_EMPRESTIMO.items():
            alvo = sum(principal_a_vencer(self.parcelas[cid], d, limite)
                       for cid, c in self.contratos.items()
                       if c["modalidade"] == modalidade and date.fromisoformat(c["data"]) <= d)
            transferir = alvo - self.livro.credor(conta_cp)
            assert transferir >= 0, f"{d}: curto prazo de {modalidade} acima do cronograma"
            self.livro.lancar(d, "EV41", [D(conta_lp, transferir), C(conta_cp, transferir)],
                              f"Transferência do longo para o curto prazo ({modalidade})")

    # aplicações e caixa
    def render_aplicacoes(self, d: date) -> None:
        f = self.r["financeiro"]
        rendimento = aplicar(self.plano(d)["cdb_inicio"], taxa_mensal(f["cdi_aa"][d.year]))
        L = self.livro
        L.lancar(d, "EV31", [D(CDB, rendimento), C(REND_APLIC, rendimento)],
                 "Rendimento do CDB")
        irrf = aplicar(rendimento, f["irrf_aplicacoes"])
        L.lancar(d, "EV32", [D(IRRF_APLIC, irrf), C(CDB, irrf)], "IRRF retido sobre o rendimento")

    def tesouraria(self, d: date, fim_do_mes: bool) -> None:
        """Mantém o saldo bancário entre o mínimo e o máximo, usando o CDB."""
        f = self.r["financeiro"]
        L = self.livro
        minimo, alvo, maximo = (centavos(f["caixa_minimo"]), centavos(f["caixa_alvo"]),
                                centavos(f["caixa_maximo"]))
        if L.saldo(BANCOS) < minimo:
            resgate = min(alvo - L.saldo(BANCOS), L.saldo(CDB))
            L.lancar(d, "EV30", [D(BANCOS, resgate), C(CDB, resgate)], "Resgate de CDB")
        elif fim_do_mes and L.saldo(BANCOS) > maximo:
            aplicacao = L.saldo(BANCOS) - alvo
            L.lancar(d, "EV30", [D(CDB, aplicacao), C(BANCOS, aplicacao)], "Aplicação em CDB")
        assert L.saldo(BANCOS) >= 0, f"{d}: saldo bancário negativo e sem CDB para resgatar"

    # patrimônio líquido
    def encerrar_exercicio(self, d: date) -> None:
        L = self.livro
        resultado = {c: v for c, v in L.saldos.items() if c.startswith("3") and v}
        lucro = -sum(resultado.values())
        assert lucro > 0, f"{d}: prejuízo no exercício; o roteiro prevê lucro"
        L.lancar(d, "EV52", [C(c, v) for c, v in sorted(resultado.items())] + [C(LUCROS_ACUM, lucro)],
                 f"Encerramento do resultado de {d.year}")
        ab = self.r["abertura"]
        limite = aplicar(centavos(ab["capital_social"]), 0.20) - L.credor(RESERVA_LEGAL)
        reserva = max(0, min(aplicar(lucro, self.emp["dividendos_e_reservas"]["reserva_legal"]), limite))
        dividendo = aplicar(lucro - reserva,
                            self.emp["dividendos_e_reservas"]["dividendo_minimo_obrigatorio"])
        retencao = lucro - reserva - dividendo
        L.lancar(d, "EV53", [D(LUCROS_ACUM, reserva), C(RESERVA_LEGAL, reserva)],
                 "Reserva legal (5% do lucro)")
        L.lancar(d, "EV54", [D(LUCROS_ACUM, dividendo), C(DIVIDENDOS_PAGAR, dividendo)],
                 "Dividendo mínimo obrigatório (25% do lucro ajustado)")
        L.lancar(d, "EV58", [D(LUCROS_ACUM, retencao), C(RETENCAO, retencao)],
                 "Retenção de lucros (orçamento de capital)")

    def pagar_dividendos(self, d: date) -> None:
        valor = self.livro.credor(DIVIDENDOS_PAGAR)
        self.livro.lancar(d, "EV57", [D(DIVIDENDOS_PAGAR, valor), C(BANCOS, valor)],
                          "Pagamento de dividendos")

    def fotografar(self, d: date) -> None:
        self.tesouraria(d, fim_do_mes=True)
        self.fotos[d] = dict(self.livro.saldos)

    # ------------------------------------------------------------ execução

    def executar(self) -> "Gerador":
        self.montar_abertura()
        tarefas = self.tarefas_pontuais()
        d = self.inicio
        while d <= self.fim:
            tarefas += self.tarefas_do_mes(d.year, d.month)
            d = somar_meses(d, 1)
        tarefas.sort(key=lambda t: (t[0], t[1]))
        datas = sorted({t[0] for t in tarefas})
        for data in datas:
            self.data_atual = data
            for _, _, funcao in (t for t in tarefas if t[0] == data):
                funcao()
            self.tesouraria(data, fim_do_mes=False)
        return self

    # ------------------------------------------------------------ saída no formato da Etapa 3

    def quadros(self) -> dict[str, list[dict]]:
        def reais(c):
            return None if not c else c / 100

        saldos = [{"codigo_conta": c, "debito": reais(max(v, 0)), "credito": reais(max(-v, 0))}
                  for c, v in sorted(self.abertura_saldos.items())]
        lancamentos = [{**p, "debito": reais(p["debito"]), "credito": reais(p["credito"])}
                       for p in self.livro.partidas]
        imobilizado = []
        for bem in self.r["bens"]:
            na_abertura = bem["forma"] == "abertura"
            imobilizado.append({
                "id_bem": bem["id"], "descricao": bem["descricao"], "classe": bem["classe"],
                "data_aquisicao": date.fromisoformat(bem["data"]), "custo": bem["custo"],
                "depreciacao_acumulada_abertura": reais(
                    depreciacao_acumulada(bem, self.vidas, self.abertura)) if na_abertura else None,
                "data_baixa": date.fromisoformat(bem["data_baixa"]) if bem.get("data_baixa") else None,
                "valor_venda": bem.get("valor_venda")})
        emprestimos = []
        for cid, c in self.contratos.items():
            linha = {"id_contrato": cid, "modalidade": c["modalidade"], "credor": c["credor"],
                     "data_contratacao": date.fromisoformat(c["data"]),
                     "valor_contratado": c["valor"], "taxa_juros_aa": c["taxa_aa"],
                     "prazo_meses": c["prazo_meses"], "carencia_meses": c["carencia_meses"],
                     "sistema_amortizacao": c["sistema"],
                     "juros_na_carencia": c.get("juros_na_carencia")}
            if date.fromisoformat(c["data"]) <= self.abertura:
                parcelas = self.parcelas[cid]
                saldo = centavos(c["valor"]) - sum(p["principal"] for p in parcelas
                                                   if p["data"] <= self.abertura)
                cp = principal_a_vencer(parcelas, self.abertura, somar_meses(self.abertura, 12))
                linha.update(saldo_cp_abertura=reais(cp), saldo_lp_abertura=reais(saldo - cp))
            emprestimos.append(linha)
        ab = self.r["abertura"]
        pl = [{"data": self.abertura, "tipo_ato": "posicao_inicial", "valor": ab["capital_social"],
               "quantidade_acoes": ab["acoes"], "descricao": "Capital subscrito e integralizado"}]
        diferencas = [{"data_base": data, "tipo": tipo, "valor_base": reais(valor),
                       "descricao": "Saldo da provisão, indedutível até a realização"}
                      for data, bases in sorted(self.base_diferida.items())
                      for tipo, valor in bases.items()]
        return {"saldos_abertura": saldos, "lancamentos": lancamentos, "imobilizado": imobilizado,
                "emprestimos": emprestimos, "patrimonio_liquido": pl,
                "diferencas_temporarias": diferencas}


def carregar_roteiro(caminho: Path | None = None) -> dict:
    with open(caminho or PASTA_CONFIG / "roteiro.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def gerar(roteiro: dict | None = None) -> Gerador:
    return Gerador(roteiro or carregar_roteiro(), carregar_empresa()).executar()


def resumo_trimestral(g: Gerador) -> list[dict]:
    """Números de controle por trimestre, para conferir a história do roteiro."""
    linhas = []
    for data in sorted(g.fotos):
        if data == g.abertura or not fim_de_trimestre(data):
            continue
        foto = g.fotos[data]
        inicio = fim_do_mes_anterior(data, 3)
        partidas = [p for p in g.livro.partidas if inicio < p["data"] <= data]

        def mov(prefixos, evento_excluido="EV52"):
            return sum(p["credito"] - p["debito"] for p in partidas
                       if p["codigo_conta"].startswith(prefixos) and p["codigo_evento"] != evento_excluido)

        receita_bruta = mov(RECEITA)
        receita_liquida = mov("3.1")
        lucro_bruto = receita_liquida + mov("3.2")
        lucro = mov("3")
        divida = -sum(foto.get(c, 0) for c in ("2.1.04.001", "2.1.04.002", "2.2.01.001", "2.2.01.002"))
        caixa = sum(foto.get(c, 0) for c in (CAIXA, BANCOS, CDB))
        linhas.append({
            "trimestre": trimestre(data), "receita_bruta": receita_bruta,
            "receita_liquida": receita_liquida, "margem_bruta": lucro_bruto / receita_liquida,
            "lucro_liquido": lucro, "caixa": caixa, "divida_bruta": divida,
            "clientes": foto.get(CLIENTES, 0), "perda_esperada": -foto.get(PECLD, 0),
            "estoques": foto.get(MERCADORIAS, 0)})
    return linhas


def rs_mil(c: int) -> str:
    return f"{c / 100_000:>10,.0f}".replace(",", ".")


def main() -> None:
    g = gerar()
    destino = gerar_modelo(DESTINO_PADRAO, g.quadros())
    print(f"Gerado: {destino}")
    print(f"  {g.livro.lancamentos} lançamentos, {len(g.livro.partidas)} partidas\n")
    print("  Trimestre  Rec. bruta  Rec. líq.  Margem   Lucro líq.     Caixa    Dívida  (R$ mil)")
    for r in resumo_trimestral(g):
        print(f"  {r['trimestre']:<9}{rs_mil(r['receita_bruta'])} {rs_mil(r['receita_liquida'])}"
              f"  {r['margem_bruta']:6.1%} {rs_mil(r['lucro_liquido'])} {rs_mil(r['caixa'])}"
              f"{rs_mil(r['divida_bruta'])}")
    print("\nPróximo passo: python src/importar_entrada.py")


if __name__ == "__main__":
    main()
