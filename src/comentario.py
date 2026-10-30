"""
Comentário de desempenho (Etapa 10), escrito por regras a partir dos números.

Princípios, combinados no planejamento:
  - Todo número do texto vem do motor (DRE, BP, DFC, indicadores). Nada é digitado.
  - O texto só cita uma causa quando ela está registrada: aqui, o evento do trimestre no roteiro
    (config/roteiro.yaml). Sem registro, o texto descreve o que aconteceu sem explicar por quê.
  - Uma IA pode, depois, melhorar a redação, mas não pode mudar valores nem inventar causas; e o
    texto passa pela revisão de uma pessoa antes de publicar. Na V1 o texto sai só das regras.
"""
from dataclasses import dataclass, field
from datetime import date

import yaml

from checar_config import PASTA_CONFIG
from demonstracoes import balanco, periodos_itr, resultado
from dfc_dmpl import dfc
from indicadores import calcular, ebitda


@dataclass
class Comentario:
    destaques: list[str] = field(default_factory=list)   # frases curtas para a capa
    paragrafos: list[tuple[str, str]] = field(default_factory=list)   # (título, texto)


def pct(v: float) -> str:
    return f"{v:.1%}".replace(".", ",")


def pp(v: float) -> str:
    """Variação em pontos percentuais, com sinal; abaixo de 0,05 p.p. é 'estável'."""
    pontos = v * 100
    if abs(pontos) < 0.05:
        return "estável"
    return f"{pontos:+.1f}".replace(".", ",") + " p.p."


def mil(c: int) -> str:
    return f"R$ {round(c / 100_000):,}".replace(",", ".") + " mil"


def variacao(atual: int, anterior: int) -> str:
    if not anterior:
        return "sem base de comparação"
    v = (atual - anterior) / abs(anterior)
    return f"{'alta' if v >= 0 else 'queda'} de {pct(abs(v))}"


def evento_do_roteiro(trimestre: str) -> str | None:
    caminho = PASTA_CONFIG / "roteiro.yaml"
    if not caminho.exists():
        return None
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f)["trimestres"].get(trimestre, {}).get("evento")


def escrever_comentario(con, trimestre: str, cfg: dict) -> Comentario:
    p = periodos_itr(trimestre)
    tri, tri_ant = p["tri_atual"], p["tri_anterior"]
    acum, acum_ant = p["acum_atual"], p["acum_anterior"]
    d, d_ant = resultado(con, tri.inicio, tri.fim, cfg), resultado(con, tri_ant.inicio, tri_ant.fim, cfg)
    e, e_ant = ebitda(con, tri.inicio, tri.fim, cfg), ebitda(con, tri_ant.inicio, tri_ant.fim, cfg)
    f, f_ant = dfc(con, acum.inicio, acum.fim, cfg), dfc(con, acum_ant.inicio, acum_ant.fim, cfg)
    ind = calcular(con, trimestre, cfg)
    t, ano = int(trimestre[0]), trimestre[2:]
    anterior_seq = f"{t - 1}T{ano}" if t > 1 else f"4T{int(ano) - 1:02d}"
    ind_seq = calcular(con, anterior_seq, cfg)
    bp = balanco(con, p["bp_atual"].fim, cfg)

    mb, mb_ant = d["3.03"] / d["3.01"], d_ant["3.03"] / d_ant["3.01"]
    me, me_ant = e["ebitda"] / e["receita_liquida"], e_ant["ebitda"] / e_ant["receita_liquida"]
    c = Comentario()
    c.destaques = [
        f"Receita líquida de {mil(d['3.01'])} no {tri.rotulo}, {variacao(d['3.01'], d_ant['3.01'])} "
        f"sobre o {tri_ant.rotulo}",
        f"Margem bruta de {pct(mb)} ({pp(mb - mb_ant)} sobre o {tri_ant.rotulo})",
        f"EBITDA de {mil(e['ebitda'])}, margem de {pct(me)} ({pp(me - me_ant)} sobre o {tri_ant.rotulo})",
        f"Lucro líquido de {mil(d['3.11'])}, {variacao(d['3.11'], d_ant['3.11'])}",
    ]

    evento = evento_do_roteiro(trimestre)
    if evento:
        c.paragrafos.append(("Fato do trimestre",
                             f"O principal fato registrado no {tri.rotulo} foi: {evento.rstrip('.')}."))

    c.paragrafos.append(("Receita e margem", (
        f"A receita líquida somou {mil(d['3.01'])} no {tri.rotulo}, {variacao(d['3.01'], d_ant['3.01'])} "
        f"em relação ao {tri_ant.rotulo}. No acumulado do ano, chegou a "
        f"{mil(resultado(con, acum.inicio, acum.fim, cfg)['3.01'])}. A margem bruta foi de {pct(mb)}, "
        f"{pp(mb - mb_ant)} na comparação anual e {pp(mb - ind_seq['margem_bruta'])} em relação ao "
        f"{anterior_seq}.")))

    c.paragrafos.append(("Resultado operacional", (
        f"O EBITDA, calculado conforme a Resolução CVM 156 e reconciliado na seção de indicadores, foi "
        f"de {mil(e['ebitda'])} no {tri.rotulo}, contra {mil(e_ant['ebitda'])} no {tri_ant.rotulo}. "
        f"A margem EBITDA passou de {pct(me_ant)} para {pct(me)}. O lucro líquido foi de "
        f"{mil(d['3.11'])}, com margem líquida de {pct(d['3.11'] / d['3.01'])}.")))

    c.paragrafos.append(("Capital de giro", (
        f"O prazo médio de recebimento terminou o trimestre em {ind['pmr']:.0f} dias "
        f"({ind_seq['pmr']:.0f} no {anterior_seq}) e o prazo médio de estocagem em {ind['pme']:.0f} "
        f"dias. Com prazo médio de pagamento de {ind['pmp']:.0f} dias, o ciclo financeiro ficou em "
        f"{ind['ciclo_financeiro']:.0f} dias, contra {ind_seq['ciclo_financeiro']:.0f} no "
        f"{anterior_seq}.")))

    divida = bp["2.01.04"] + bp["2.02.01"]
    liquida = divida - bp["1.01.01"]
    situacao = (f"dívida líquida de {mil(liquida)}" if liquida > 0
                else f"caixa líquido de {mil(-liquida)} (mais caixa do que dívida)")
    c.paragrafos.append(("Caixa e endividamento", (
        f"No {acum.rotulo}, as atividades operacionais geraram {mil(f['6.01'])} de caixa "
        f"({mil(f_ant['6.01'])} no {acum_ant.rotulo}). Os investimentos consumiram "
        f"{mil(-f['6.02'])} e as atividades de financiamento "
        f"{'geraram' if f['6.03'] >= 0 else 'consumiram'} {mil(abs(f['6.03']))}. A Companhia "
        f"terminou o trimestre com caixa de {mil(bp['1.01.01'])}, dívida bruta de {mil(divida)} e "
        f"{situacao}.")))
    return c
