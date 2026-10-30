"""
Notas explicativas (Etapa 7): o conteúdo das 10 notas da V1, calculado a partir da base.

Cada nota tem parágrafos de texto e quadros. Os números dos quadros são calculados aqui, nunca
digitados, e cada quadro que corresponde a uma linha das demonstrações é conferido com ela
(conferir_notas). A apresentação (Excel e PDF) fica para a Etapa 10; aqui o resultado é uma
estrutura de dados e uma impressão simples no terminal.

Notas da V1 (CPC 21 admite notas selecionadas nas demonstrações intermediárias):
   1 Contexto operacional            6 Imobilizado e intangível
   2 Base de preparação              7 Empréstimos e financiamentos
   3 Caixa e equivalentes            8 IR e CSLL (alíquota efetiva e diferidos)
   4 Contas a receber                9 Patrimônio líquido e lucro por ação
   5 Estoques                       10 Receita líquida

Uso:
    python src/notas.py             # notas do ITR do 3T26
"""
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import yaml

from checar_config import PASTA_CONFIG, carregar
from contrato_entrada import CLASSES_IMOBILIZADO, CONTAS_EMPRESTIMO
from demonstracoes import (BASE_PADRAO, balanco, formatar, media_ponderada_acoes, periodos_itr,
                           reais_mil, resultado, saldos_em)
from dfc_dmpl import partidas, transacoes_sem_caixa
from gerar_dados import cronograma, principal_a_vencer, somar_meses


@dataclass
class Linha:
    rotulo: str
    valores: list            # centavos (int), texto (str) ou None
    destaque: bool = False   # linha de total


@dataclass
class Quadro:
    titulo: str
    colunas: list[str]
    linhas: list[Linha] = field(default_factory=list)
    unidade: str = "R$ mil"

    def total(self, rotulo: str) -> list:
        return next(l.valores for l in self.linhas if l.rotulo == rotulo)


@dataclass
class Nota:
    numero: int
    titulo: str
    paragrafos: list[str] = field(default_factory=list)
    quadros: list[Quadro] = field(default_factory=list)


def data_br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def mil(c: int) -> str:
    return formatar(reais_mil(c))


def empresa() -> dict:
    with open(PASTA_CONFIG / "empresa.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def movimento_por_evento(con, inicio: date, fim: date, contas: set[str]) -> dict[str, int]:
    """Soma (débito - crédito) das contas indicadas, por evento, no período."""
    total: dict[str, int] = defaultdict(int)
    for evento, conta, valor in partidas(con, inicio, fim):
        if conta in contas:
            total[evento] += valor
    return dict(total)


# ---------------------------------------------------------------- notas 1 e 2: texto

def nota_contexto(emp: dict) -> Nota:
    e, cap = emp["empresa"], emp["capital"]
    return Nota(1, "Contexto operacional", [
        f"A {e['razao_social']} (\"Orbe\" ou \"Companhia\") é uma sociedade anônima de capital "
        f"aberto, com sede em {e['sede']}. {e['atividade']}",
        "A Companhia opera a partir de um centro de distribuição próprio e entrega com frota "
        "própria. Não possui controladas, coligadas nem operações no exterior; por isso apresenta "
        "apenas informações individuais e um único segmento operacional (distribuição).",
        f"O capital social é de R$ {cap['capital_social_rs'] / 1000:,.0f} mil, dividido em "
        f"{cap['acoes_ordinarias']:,} ações ordinárias.".replace(",", "."),
        "Empresa e números fictícios: simulação acadêmica, sem relação com companhia real.",
    ])


def nota_base(trimestre: str) -> Nota:
    p = periodos_itr(trimestre)
    return Nota(2, "Base de preparação e políticas contábeis", [
        "As informações financeiras intermediárias foram elaboradas de acordo com o CPC 21 (R1) "
        "— Demonstração Intermediária, na estrutura do formulário de Informações Trimestrais (ITR) "
        "da CVM, em reais (R$), com valores apresentados em milhares.",
        f"O balanço patrimonial de {p['bp_atual'].rotulo} é comparado com o de "
        f"{p['bp_comparativo'].rotulo}. A DRE e a DRA apresentam o trimestre ({p['tri_atual'].rotulo}) "
        f"e o acumulado do ano ({p['acum_atual'].rotulo}), comparados com {p['tri_anterior'].rotulo} e "
        f"{p['acum_anterior'].rotulo}. A DFC, a DMPL e a DVA apresentam os acumulados.",
        "As políticas contábeis são as mesmas das demonstrações anuais: receita na entrega "
        "(CPC 47), perda esperada pela abordagem simplificada (CPC 48), estoques ao custo médio "
        "ponderado (CPC 16), imobilizado ao custo com depreciação linear (CPC 27) e tributos "
        "diferidos sobre diferenças temporárias (CPC 32).",
        "Na DFC, juros pagos e dividendos são classificados em financiamento; juros recebidos e "
        "IR e CSLL pagos, em operacional.",
    ])


# ---------------------------------------------------------------- nota 3: caixa

def nota_caixa(con, datas: list[date], cfg) -> Nota:
    contas = [("1.1.01.001", "Caixa"), ("1.1.01.002", "Bancos conta movimento"),
              ("1.1.01.003", "Aplicações financeiras (CDB, liquidez diária)")]
    saldos = [saldos_em(con, d) for d in datas]
    q = Quadro("Composição", [data_br(d) for d in datas])
    for conta, rotulo in contas:
        q.linhas.append(Linha(rotulo, [s.get(conta, 0) for s in saldos]))
    q.linhas.append(Linha("Total", [sum(s.get(c, 0) for c, _ in contas) for s in saldos], True))
    return Nota(3, "Caixa e equivalentes de caixa", [
        "As aplicações são CDBs de bancos de primeira linha, com liquidez diária e remuneração "
        "atrelada ao CDI, sem risco relevante de mudança de valor (CPC 03)."], [q])


# ---------------------------------------------------------------- nota 4: contas a receber

def nota_clientes(con, inicio: date, fim: date, cfg) -> Nota:
    anterior = inicio - timedelta(days=1)
    datas = [fim, anterior]
    saldos = [saldos_em(con, d) for d in datas]
    q = Quadro("Composição", [data_br(d) for d in datas])
    q.linhas.append(Linha("Clientes — mercado interno", [s.get("1.1.02.001", 0) for s in saldos]))
    q.linhas.append(Linha("(-) Perda esperada com créditos", [s.get("1.1.02.009", 0) for s in saldos]))
    q.linhas.append(Linha("Total", [s.get("1.1.02.001", 0) + s.get("1.1.02.009", 0) for s in saldos], True))

    mov = movimento_por_evento(con, inicio, fim, {"1.1.02.009"})
    inicial = -saldos[1].get("1.1.02.009", 0)
    constituicao = -mov.get("EV26", 0)
    baixas = -mov.get("EV27", 0)
    m = Quadro(f"Movimentação da perda esperada ({inicio.strftime('%d/%m')} a {data_br(fim)})", ["Valor"])
    m.linhas += [Linha(f"Saldo em {data_br(anterior)}", [inicial]),
                 Linha("Constituição líquida de reversões", [constituicao]),
                 Linha("Baixa de créditos incobráveis", [baixas]),
                 Linha(f"Saldo em {data_br(fim)}", [inicial + constituicao + baixas], True)]
    matriz = empresa()["politicas"]["matriz_perda_esperada"]
    faixas = "; ".join(f"{k.replace('_', ' ')}: {v:.1%}".replace(".", ",") for k, v in matriz.items())
    return Nota(4, "Contas a receber de clientes", [
        "A perda esperada segue a abordagem simplificada do CPC 48, por matriz de provisão sobre a "
        f"idade dos saldos ({faixas}).",
        "Créditos considerados incobráveis são baixados contra a provisão; a despesa é apresentada "
        "na linha \"Perdas pela não recuperabilidade de ativos\" da DRE."], [q, m])


# ---------------------------------------------------------------- nota 5: estoques

def nota_estoques(con, inicio: date, fim: date, cfg) -> Nota:
    anterior = inicio - timedelta(days=1)
    datas = [fim, anterior]
    saldos = [saldos_em(con, d) for d in datas]
    q = Quadro("Composição", [data_br(d) for d in datas])
    q.linhas.append(Linha("Mercadorias para revenda", [s.get("1.1.03.001", 0) + s.get("1.1.03.002", 0) for s in saldos]))
    q.linhas.append(Linha("(-) Provisão para perdas", [s.get("1.1.03.009", 0) for s in saldos]))
    q.linhas.append(Linha("Total", [s.get("1.1.03.001", 0) + s.get("1.1.03.002", 0) + s.get("1.1.03.009", 0)
                                    for s in saldos], True))
    mov = movimento_por_evento(con, inicio, fim, {"1.1.03.009"})
    inicial = -saldos[1].get("1.1.03.009", 0)
    m = Quadro("Movimentação da provisão para perdas", ["Valor"])
    m.linhas += [Linha(f"Saldo em {data_br(anterior)}", [inicial]),
                 Linha("Constituição líquida de reversões", [-mov.get("EV28", 0)]),
                 Linha("Baixa de mercadorias avariadas e vencidas", [-mov.get("EV29", 0)]),
                 Linha(f"Saldo em {data_br(fim)}", [inicial - mov.get("EV28", 0) - mov.get("EV29", 0)], True)]
    return Nota(5, "Estoques", [
        "Os estoques são mensurados pelo menor valor entre o custo médio ponderado móvel e o valor "
        "realizável líquido (CPC 16). O custo inclui o preço de compra e o frete, líquidos de ICMS, "
        "PIS e COFINS recuperáveis.",
        "A provisão cobre obsolescência, avarias e validade vencida, e é registrada no custo das "
        "mercadorias vendidas."], [q, m])


# ---------------------------------------------------------------- nota 6: imobilizado

CLASSES_NA_NOTA = [("terrenos", "Terrenos"), ("edificacoes", "Edificações"),
                   ("maquinas_e_equipamentos", "Máquinas e equip."), ("veiculos", "Veículos"),
                   ("moveis_e_utensilios", "Móveis"), ("equipamentos_de_informatica", "Informática"),
                   ("imobilizado_em_andamento", "Em andamento")]


def quadro_movimentacao(con, inicio, fim, classes, titulo) -> Quadro:
    anterior = inicio - timedelta(days=1)
    s0, s1 = saldos_em(con, anterior), saldos_em(con, fim)
    custo = {c: CLASSES_IMOBILIZADO[c][0] for c, _ in classes}
    dep = {c: CLASSES_IMOBILIZADO[c][1] for c, _ in classes}
    contas = set(custo.values()) | {d for d in dep.values() if d}
    por_evento_conta: dict[tuple[str, str], int] = defaultdict(int)
    for evento, conta, valor in partidas(con, inicio, fim):
        if conta in contas:
            por_evento_conta[(evento, conta)] += valor

    def mov(eventos, conta):
        return sum(por_evento_conta.get((e, conta), 0) for e in eventos) if conta else 0

    colunas = [r for _, r in classes] + ["Total"]
    linhas_def = [
        (f"Custo em {data_br(anterior)}", lambda c: s0.get(custo[c], 0), False),
        ("Adições", lambda c: mov(("EV42", "EV43", "EV45", "EV50"), custo[c]), False),
        ("Baixas", lambda c: mov(("EV49",), custo[c]), False),
        ("Transferências", lambda c: mov(("EV46",), custo[c]), False),
        (f"Custo em {data_br(fim)}", lambda c: s1.get(custo[c], 0), True),
        (f"Depreciação acumulada em {data_br(anterior)}", lambda c: s0.get(dep[c], 0) if dep[c] else 0, False),
        ("Depreciação e amortização do período", lambda c: mov(("EV47", "EV48"), dep[c]), False),
        ("Baixas", lambda c: mov(("EV49",), dep[c]), False),
        (f"Depreciação acumulada em {data_br(fim)}", lambda c: s1.get(dep[c], 0) if dep[c] else 0, True),
        (f"Saldo líquido em {data_br(anterior)}", lambda c: s0.get(custo[c], 0) + (s0.get(dep[c], 0) if dep[c] else 0), True),
        (f"Saldo líquido em {data_br(fim)}", lambda c: s1.get(custo[c], 0) + (s1.get(dep[c], 0) if dep[c] else 0), True),
    ]
    q = Quadro(titulo, colunas)
    for rotulo, f, destaque in linhas_def:
        valores = [f(c) for c, _ in classes]
        q.linhas.append(Linha(rotulo, valores + [sum(valores)], destaque))
    return q


def nota_imobilizado(con, inicio: date, fim: date, cfg) -> Nota:
    vidas = empresa()["politicas"]["vida_util_anos"]
    imob = quadro_movimentacao(con, inicio, fim, CLASSES_NA_NOTA, "Imobilizado — movimentação")
    taxas = []
    for c, r in CLASSES_NA_NOTA:
        chave = CLASSES_IMOBILIZADO[c][2]
        taxas.append(f"{100 / vidas[chave]:.0f}%" if chave else "—")
    imob.linhas.append(Linha("Taxa anual de depreciação", taxas + [""]))
    intang = quadro_movimentacao(con, inicio, fim, [("softwares", "Softwares")], "Intangível — movimentação")
    intang.linhas.append(Linha("Taxa anual de amortização", [f"{100 / vidas['softwares']:.0f}%", ""]))
    sem_caixa = transacoes_sem_caixa(con, inicio, fim)
    paragrafos = ["Imobilizado ao custo de aquisição, menos depreciação acumulada, pelo método linear "
                  "(CPC 27). Terrenos e obras em andamento não são depreciados."]
    if sem_caixa:
        itens = "; ".join(f"{t['historico']} (R$ {mil(t['valor'])} mil)" for t in sem_caixa)
        paragrafos.append(f"Adições que não afetaram o caixa, fora da DFC (CPC 03, item 43): {itens}.")
    paragrafos.append("Não foram identificados indicadores de perda por redução ao valor "
                      "recuperável (CPC 01) no período.")
    return Nota(6, "Imobilizado e intangível", paragrafos, [imob, intang])


# ---------------------------------------------------------------- nota 7: empréstimos

def contratos(con) -> list[dict]:
    sql = ("SELECT id_contrato, modalidade, credor, data_contratacao, valor_contratado_centavos, "
           "taxa_juros_aa, prazo_meses, carencia_meses, sistema_amortizacao, juros_na_carencia "
           "FROM emprestimo ORDER BY data_contratacao")
    return [{"id": r[0], "modalidade": r[1], "credor": r[2], "data": r[3], "valor": r[4] / 100,
             "taxa_aa": r[5], "prazo_meses": r[6], "carencia_meses": r[7], "sistema": r[8],
             "juros_na_carencia": r[9]} for r in con.execute(sql)]


def nota_emprestimos(con, inicio: date, fim: date, cfg) -> Nota:
    anterior = inicio - timedelta(days=1)
    q = Quadro(f"Composição em {data_br(fim)}", ["Taxa a.a.", "Vencimento", "Circulante",
                                                 "Não circulante", "Total"])
    total_cp = total_lp = 0
    vencimentos_lp: dict[int, int] = defaultdict(int)
    for c in contratos(con):
        if date.fromisoformat(c["data"]) > fim:
            continue
        parcelas = cronograma(c)
        pago = sum(p["principal"] for p in parcelas if p["data"] <= fim)
        saldo = round(c["valor"] * 100) - pago
        cp = principal_a_vencer(parcelas, fim, somar_meses(fim, 12))
        for p in parcelas:
            if p["data"] > somar_meses(fim, 12):
                vencimentos_lp[p["data"].year] += p["principal"]
        total_cp, total_lp = total_cp + cp, total_lp + saldo - cp
        q.linhas.append(Linha(f"{c['modalidade']} {c['id']} — {c['credor']}",
                              [f"{c['taxa_aa']:.2%}".replace(".", ","),
                               parcelas[-1]["data"].strftime("%m/%Y"), cp, saldo - cp, saldo]))
    q.linhas.append(Linha("Total", ["", "", total_cp, total_lp, total_cp + total_lp], True))

    contas = {conta for par in CONTAS_EMPRESTIMO.values() for conta in par}
    mov = movimento_por_evento(con, inicio, fim, contas)
    s0 = saldos_em(con, anterior)
    inicial = -sum(s0.get(c, 0) for c in contas)
    linhas = [(f"Saldo em {data_br(anterior)}", inicial), ("Captações", -mov.get("EV37", 0)),
              ("Financiamento de bens sem caixa (FINAME)", -mov.get("EV45", 0)),
              ("Juros apropriados", -mov.get("EV38", 0)), ("Juros pagos", -mov.get("EV39", 0)),
              ("Amortização de principal", -mov.get("EV40", 0))]
    m = Quadro("Movimentação", ["Valor"])
    m.linhas += [Linha(r, [v]) for r, v in linhas]
    m.linhas.append(Linha(f"Saldo em {data_br(fim)}", [sum(v for _, v in linhas)], True))

    v = Quadro("Vencimentos do não circulante, por ano", ["Valor"])
    v.linhas += [Linha(str(ano), [valor]) for ano, valor in sorted(vencimentos_lp.items())]
    v.linhas.append(Linha("Total", [sum(vencimentos_lp.values())], True))
    return Nota(7, "Empréstimos e financiamentos", [
        "Empréstimos mensurados ao custo amortizado, com juros apropriados pela competência. A parcela "
        "com vencimento em até 12 meses é apresentada no passivo circulante.",
        "Os FINAMEs são repasses do BNDES para máquinas e veículos, garantidos pelos próprios bens. "
        "A CCB financia capital de giro. Não há cláusulas restritivas (covenants) financeiras."],
        [q, m, v])


# ---------------------------------------------------------------- nota 8: IR e CSLL

def nota_ir(con, trimestre: str, cfg) -> Nota:
    emp = empresa()["tributacao"]
    aliq = Decimal(str(emp["aliquota_diferido"]))
    p = periodos_itr(trimestre)
    chaves = ("acum_atual", "acum_anterior")
    q = Quadro("Reconciliação da alíquota efetiva", [p[k].rotulo for k in chaves])
    colunas = []
    for k in chaves:
        dre = resultado(con, p[k].inicio, p[k].fim, cfg)
        lair = dre["3.07"]
        teorico = -int((Decimal(lair) * aliq).to_integral_value(rounding=ROUND_HALF_UP))
        efetivo = dre["3.08"]
        trimestres = ((p[k].fim.month - p[k].inicio.month) // 3) + 1
        isencao = round(emp["irpj_adicional_limite_trimestral_rs"] * 100
                        * emp["irpj_adicional_aliquota"]) * trimestres
        outros = efetivo - teorico - isencao
        colunas.append([lair, teorico, isencao, outros, efetivo, efetivo / lair if lair else 0])
    rotulos = ["Lucro antes do IR e da CSLL", f"IR e CSLL à alíquota nominal de {aliq:.0%}",
               "Parcela do lucro trimestral isenta do adicional de 10% (R$ 60 mil por trimestre)",
               "Outros (arredondamentos trimestrais)", "IR e CSLL no resultado", "Alíquota efetiva"]
    for i, rotulo in enumerate(rotulos):
        valores = [col[i] for col in colunas]
        if i == 5:
            valores = [f"{-v:.1%}".replace(".", ",") for v in valores]
        q.linhas.append(Linha(rotulo, valores, i in (4, 5)))

    datas = [p["bp_atual"].fim, p["bp_comparativo"].fim]
    bases = {d: dict(con.execute("SELECT tipo, valor_base_centavos FROM diferenca_temporaria "
                                 "WHERE data_base = ?", (d.isoformat(),)).fetchall()) for d in datas}
    d = Quadro("Ativo fiscal diferido — composição", [data_br(x) for x in datas])
    for tipo, rotulo in (("perda_esperada_creditos", "Perda esperada com créditos"),
                         ("provisao_perdas_estoques", "Provisão para perdas em estoques")):
        d.linhas.append(Linha(f"Base: {rotulo}", [bases[x].get(tipo, 0) for x in datas]))
    # IRPJ (25%, com o adicional) e CSLL (9%) em contas separadas, cada um arredondado ao centavo,
    # do mesmo jeito que na contabilidade
    aliq_cs = Decimal(str(emp["csll_aliquota"]))
    irpj = [int((Decimal(sum(bases[x].values())) * (aliq - aliq_cs)).to_integral_value(ROUND_HALF_UP))
            for x in datas]
    csll = [int((Decimal(sum(bases[x].values())) * aliq_cs).to_integral_value(ROUND_HALF_UP))
            for x in datas]
    d.linhas.append(Linha(f"IRPJ diferido ({aliq - aliq_cs:.0%})", irpj))
    d.linhas.append(Linha(f"CSLL diferida ({aliq_cs:.0%})", csll))
    d.linhas.append(Linha(f"Ativo fiscal diferido ({aliq:.0%})", [i + c for i, c in zip(irpj, csll)], True))
    return Nota(8, "Imposto de renda e contribuição social", [
        "A Companhia apura IRPJ e CSLL pelo Lucro Real trimestral: IRPJ de 15%, mais adicional de 10% "
        "sobre o lucro que excede R$ 60 mil no trimestre, e CSLL de 9%.",
        "Os tributos diferidos são reconhecidos sobre diferenças temporárias, à alíquota de 34%, pois "
        "a Companhia excede o limite do adicional. A realização é esperada nos próximos 12 meses, "
        "conforme a baixa efetiva dos créditos e dos estoques provisionados (CPC 32)."], [q, d])


# ---------------------------------------------------------------- nota 9: PL e LPA

def nota_pl(con, trimestre: str, cfg) -> Nota:
    p = periodos_itr(trimestre)
    datas = [p["bp_atual"].fim, p["bp_comparativo"].fim]
    bps = [balanco(con, d, cfg) for d in datas]
    q = Quadro("Composição", [data_br(d) for d in datas])
    for linha, rotulo in (("2.03.01", "Capital social realizado"), ("2.03.04.01", "Reserva legal"),
                          ("2.03.04.05", "Reserva de retenção de lucros"),
                          ("2.03.04.08", "Dividendo adicional proposto"),
                          ("2.03.05", "Lucros acumulados (resultado do período)")):
        q.linhas.append(Linha(rotulo, [b[linha] for b in bps]))
    q.linhas.append(Linha("Total do patrimônio líquido", [b["2.03"] for b in bps], True))

    chaves = ("tri_atual", "acum_atual", "tri_anterior", "acum_anterior")
    lpa = Quadro("Lucro por ação", [p[k].rotulo for k in chaves], unidade="R$")
    lucros, medias = [], []
    for k in chaves:
        lucros.append(resultado(con, p[k].inicio, p[k].fim, cfg)["3.11"])
        medias.append(media_ponderada_acoes(con, p[k].inicio, p[k].fim))
    lpa.linhas += [
        Linha("Lucro líquido do período (R$ mil)", [mil(v) for v in lucros]),
        Linha("Média ponderada de ações ordinárias", [f"{int(m):,}".replace(",", ".") for m in medias]),
        Linha("Lucro básico e diluído por ação (R$)",
              [f"{Decimal(l) / 100 / m:.5f}".replace(".", ",") for l, m in zip(lucros, medias)], True)]

    dividendo = con.execute("SELECT data, credito_centavos FROM lancamento WHERE codigo_evento = "
                            "'EV54' AND codigo_conta = '2.1.05.001' ORDER BY data DESC").fetchone()
    pagamento = con.execute("SELECT data FROM lancamento WHERE codigo_evento = 'EV57' AND data > ? "
                            "ORDER BY data LIMIT 1", (dividendo[0],)).fetchone() if dividendo else None
    paragrafos = ["O capital social é composto por 30.000.000 de ações ordinárias nominativas, sem valor "
                  "nominal. O estatuto prevê dividendo mínimo obrigatório de 25% do lucro líquido "
                  "ajustado, reserva legal de 5% do lucro até 20% do capital e retenção do saldo para "
                  "o orçamento de capital."]
    if dividendo:
        paragrafos.append(
            f"Em {data_br(date.fromisoformat(dividendo[0]))} foram declarados dividendos mínimos de "
            f"R$ {mil(dividendo[1])} mil sobre o lucro do exercício"
            + (f", pagos em {data_br(date.fromisoformat(pagamento[0]))}." if pagamento and
               date.fromisoformat(pagamento[0]) <= p['bp_atual'].fim else "."))
    paragrafos.append("Não há instrumentos com efeito diluidor; o lucro diluído por ação é igual ao "
                      "básico (CPC 41).")
    return Nota(9, "Patrimônio líquido e lucro por ação", paragrafos, [q, lpa])


# ---------------------------------------------------------------- nota 10: receita

def nota_receita(con, trimestre: str, cfg) -> Nota:
    p = periodos_itr(trimestre)
    chaves = ("tri_atual", "acum_atual", "tri_anterior", "acum_anterior")
    contas = [("3.1.01.001", "Receita bruta de vendas"), ("3.1.02.001", "(-) ICMS"),
              ("3.1.02.002", "(-) PIS"), ("3.1.02.003", "(-) COFINS"),
              ("3.1.02.004", "(-) Devoluções"), ("3.1.02.005", "(-) Descontos e abatimentos")]
    movimentos = []
    for k in chaves:
        m: dict[str, int] = defaultdict(int)
        for _, conta, valor in partidas(con, p[k].inicio, p[k].fim):
            m[conta] -= valor
        movimentos.append(m)
    q = Quadro("Reconciliação da receita bruta com a líquida", [p[k].rotulo for k in chaves])
    for conta, rotulo in contas:
        q.linhas.append(Linha(rotulo, [m.get(conta, 0) for m in movimentos]))
    q.linhas.append(Linha("Receita líquida", [sum(m.get(c, 0) for c, _ in contas) for m in movimentos], True))
    return Nota(10, "Receita líquida", [
        "A receita de venda de mercadorias é reconhecida em um ponto no tempo, na entrega ao cliente, "
        "quando o controle é transferido (CPC 47). O contrato tem uma única obrigação de desempenho. "
        "O prazo médio de recebimento é inferior a 12 meses, por isso não há componente de "
        "financiamento a ajustar.",
        "PIS e COFINS são calculados sem o ICMS na base (STF, Tema 69)."], [q])


# ---------------------------------------------------------------- todas as notas e conferências

def montar_notas(con, trimestre: str, cfg: dict | None = None) -> list[Nota]:
    cfg = cfg or carregar()
    p = periodos_itr(trimestre)
    ini, fim = p["acum_atual"].inicio, p["acum_atual"].fim
    datas = [p["bp_atual"].fim, p["bp_comparativo"].fim]
    return [nota_contexto(empresa()), nota_base(trimestre), nota_caixa(con, datas, cfg),
            nota_clientes(con, ini, fim, cfg), nota_estoques(con, ini, fim, cfg),
            nota_imobilizado(con, ini, fim, cfg), nota_emprestimos(con, ini, fim, cfg),
            nota_ir(con, trimestre, cfg), nota_pl(con, trimestre, cfg),
            nota_receita(con, trimestre, cfg)]


def conferir_notas(con, trimestre: str, cfg: dict | None = None) -> list[str]:
    """Cada quadro que corresponde a uma linha das demonstrações tem de bater com ela."""
    cfg = cfg or carregar()
    notas = {n.numero: n for n in montar_notas(con, trimestre, cfg)}
    p = periodos_itr(trimestre)
    bp = [balanco(con, p["bp_atual"].fim, cfg), balanco(con, p["bp_comparativo"].fim, cfg)]
    problemas = []

    def confere(descricao, nota_valor, df_valor):
        if nota_valor != df_valor:
            problemas.append(f"{descricao}: nota {nota_valor / 100:,.2f} x demonstração {df_valor / 100:,.2f}")

    for i in (0, 1):
        confere(f"Nota 3 x BP 1.01.01 (coluna {i + 1})", notas[3].quadros[0].total("Total")[i], bp[i]["1.01.01"])
        confere(f"Nota 4 x BP 1.01.03.01 (coluna {i + 1})", notas[4].quadros[0].total("Total")[i], bp[i]["1.01.03.01"])
        confere(f"Nota 5 x BP 1.01.04 (coluna {i + 1})", notas[5].quadros[0].total("Total")[i], bp[i]["1.01.04"])
        confere(f"Nota 9 x BP 2.03 (coluna {i + 1})", notas[9].quadros[0].total("Total do patrimônio líquido")[i], bp[i]["2.03"])
        diferido = notas[8].quadros[1].linhas[-1].valores[i]
        confere(f"Nota 8 x BP 1.02.01.07.01 (coluna {i + 1})", diferido, bp[i]["1.02.01.07.01"])
    imob, intang = notas[6].quadros
    confere("Nota 6 imobilizado líquido x BP 1.02.03", imob.linhas[10].valores[-1], bp[0]["1.02.03"])
    confere("Nota 6 intangível líquido x BP 1.02.04", intang.linhas[10].valores[-1], bp[0]["1.02.04"])
    confere("Nota 6 movimentação: custo inicial + movimentos = custo final",
            sum(imob.linhas[i].valores[-1] for i in range(4)), imob.linhas[4].valores[-1])
    composicao, movimentacao, vencimentos = notas[7].quadros
    total = composicao.total("Total")
    confere("Nota 7 circulante x BP 2.01.04", total[2], bp[0]["2.01.04"])
    confere("Nota 7 não circulante x BP 2.02.01", total[3], bp[0]["2.02.01"])
    confere("Nota 7 movimentação x composição", movimentacao.linhas[-1].valores[0], total[4])
    confere("Nota 7 vencimentos x não circulante", vencimentos.total("Total")[0], total[3])
    dre = resultado(con, p["acum_atual"].inicio, p["acum_atual"].fim, cfg)
    confere("Nota 8 IR no resultado x DRE 3.08", notas[8].quadros[0].linhas[4].valores[0], dre["3.08"])
    confere("Nota 10 receita líquida x DRE 3.01", notas[10].quadros[0].total("Receita líquida")[1], dre["3.01"])
    # Cada tributo é arredondado para o centavo em cada trimestre: até R$ 1 de resíduo é arredondamento
    for valor in notas[8].quadros[0].linhas[3].valores:
        if abs(valor) > 100:
            problemas.append(f"Nota 8: reconciliação da alíquota efetiva com diferença não explicada "
                             f"de R$ {valor / 100:,.2f}")
    return problemas


def imprimir_notas(notas: list[Nota]) -> None:
    for n in notas:
        print(f"\n{n.numero}. {n.titulo.upper()}")
        for par in n.paragrafos:
            print(f"   {par}")
        for q in n.quadros:
            print(f"\n   {q.titulo} ({q.unidade})")
            print(f"   {'':<58}" + "".join(f"{c[:16]:>18}" for c in q.colunas))
            for l in q.linhas:
                cel = [mil(v) if isinstance(v, int) else (v or "") for v in l.valores]
                print(f"   {l.rotulo[:56]:<58}" + "".join(f"{c:>18}" for c in cel))


def main() -> None:
    trimestre = sys.argv[1] if len(sys.argv) > 1 else "3T26"
    if not BASE_PADRAO.exists():
        raise SystemExit("Base não encontrada. Rode antes: python src/importar_entrada.py")
    con = sqlite3.connect(BASE_PADRAO)
    imprimir_notas(montar_notas(con, trimestre))
    problemas = conferir_notas(con, trimestre)
    print("\nConferência das notas com as demonstrações: "
          + ("todas conferem" if not problemas else "; ".join(problemas)))
    con.close()


if __name__ == "__main__":
    main()
