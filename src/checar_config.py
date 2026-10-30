"""
Confere a configuração contábil antes de qualquer cálculo.

Critério de pronto da Etapa 2: toda conta analítica e todo evento têm classificação válida
em todas as demonstrações onde aparecem.

Uso:
    python src/checar_config.py
"""
from pathlib import Path

import pandas as pd

PASTA_CONFIG = Path(__file__).resolve().parent.parent / "config"

# Marcadores especiais aceitos na coluna linha_dfc do map_conta_df:
#   CAIXA  -> a conta compõe o caixa e equivalentes (é o que a DFC explica)
#   EVENTO -> a variação da conta é explicada pelos eventos (investimento, financiamento,
#             ajustes ao lucro), e não entra em "Variações nos Ativos e Passivos"
MARCADORES_DFC = {"CAIXA", "EVENTO"}


def ler_csv(nome: str) -> pd.DataFrame:
    """Lê um CSV da pasta config. Tudo como texto, para '1.10' não virar 1.1."""
    return pd.read_csv(PASTA_CONFIG / nome, sep=";", dtype=str, encoding="utf-8-sig").fillna("")


def carregar() -> dict[str, pd.DataFrame]:
    nomes = ["plano_de_contas", "dim_linha_df", "dim_coluna_dmpl",
             "map_conta_df", "dim_evento", "map_evento_df"]
    return {n: ler_csv(f"{n}.csv") for n in nomes}


def checar(cfg: dict[str, pd.DataFrame]) -> list[str]:
    """Devolve a lista de erros encontrados. Lista vazia = configuração OK."""
    erros: list[str] = []
    plano = cfg["plano_de_contas"]
    linhas = cfg["dim_linha_df"]
    mapa = cfg["map_conta_df"]
    eventos = cfg["dim_evento"]
    map_ev = cfg["map_evento_df"]
    colunas_dmpl = set(cfg["dim_coluna_dmpl"]["codigo"])

    # ---------- 1. Plano de contas bem formado
    duplicadas = plano[plano["codigo"].duplicated()]["codigo"].tolist()
    if duplicadas:
        erros.append(f"Contas duplicadas no plano: {duplicadas}")

    codigos = set(plano["codigo"])
    for _, c in plano.iterrows():
        if c["codigo_pai"] and c["codigo_pai"] not in codigos:
            erros.append(f"Conta {c['codigo']}: conta-pai {c['codigo_pai']} não existe")
        if c["natureza"] not in ("D", "C"):
            erros.append(f"Conta {c['codigo']}: natureza '{c['natureza']}' inválida (use D ou C)")

    tem_filho = set(plano["codigo_pai"])
    for _, c in plano.iterrows():
        esperado = "S" if c["codigo"] in tem_filho else "A"
        if c["tipo"] != esperado:
            erros.append(f"Conta {c['codigo']}: tipo '{c['tipo']}' deveria ser '{esperado}'")

    analiticas = set(plano.loc[plano["tipo"] == "A", "codigo"])

    # ---------- 2. Toda conta analítica mapeada exatamente uma vez
    mapeadas = mapa["codigo_conta"]
    for cod in sorted(analiticas - set(mapeadas)):
        erros.append(f"Conta analítica {cod} sem mapeamento em map_conta_df")
    for cod in sorted(set(mapeadas) - analiticas):
        erros.append(f"map_conta_df tem a conta {cod}, que não é analítica no plano")
    for cod in mapeadas[mapeadas.duplicated()]:
        erros.append(f"Conta {cod} mapeada mais de uma vez")

    # ---------- 3. Linhas usadas precisam existir e receber valores (tipo 'dado')
    linhas_dado = {(r["demonstracao"], r["codigo"])
                   for _, r in linhas.iterrows() if r["tipo_linha"] == "dado"}
    codigos_dado = {cod for _, cod in linhas_dado}

    def linha_ok(dem: str, cod: str) -> bool:
        return (dem, cod) in linhas_dado

    for _, m in mapa.iterrows():
        cod = m["codigo_conta"]
        grupo = cod[0]
        bp_dre, dfc, dva, col = m["linha_bp_dre"], m["linha_dfc"], m["linha_dva"], m["coluna_dmpl"]

        if grupo in ("1", "2"):  # contas patrimoniais
            if not linha_ok("BP", bp_dre):
                erros.append(f"Conta {cod}: linha do BP '{bp_dre}' inexistente ou não é linha de dado")
            if bp_dre and bp_dre[0] != grupo:
                erros.append(f"Conta {cod}: conta do grupo {grupo} mapeada para linha {bp_dre}")
            if dfc not in MARCADORES_DFC and not (linha_ok("DFC", dfc) and dfc.startswith("6.01.02")):
                erros.append(f"Conta {cod}: linha_dfc '{dfc}' deve ser CAIXA, EVENTO ou uma linha 6.01.02.xx")
            if dva:
                erros.append(f"Conta {cod}: conta patrimonial não deve ter linha de DVA")
            if cod.startswith("2.3") and col not in colunas_dmpl:
                erros.append(f"Conta {cod}: conta do PL sem coluna da DMPL válida")
            if not cod.startswith("2.3") and col:
                erros.append(f"Conta {cod}: só contas do PL têm coluna da DMPL")

        elif grupo == "3":  # contas de resultado
            if not (linha_ok("DRE", bp_dre)):
                erros.append(f"Conta {cod}: linha da DRE '{bp_dre}' inexistente ou não é linha de dado")
            if not linha_ok("DVA", dva):
                erros.append(f"Conta {cod}: linha da DVA '{dva}' inexistente ou não é linha de dado")
            if dfc and not (linha_ok("DFC", dfc) and dfc.startswith("6.01.01")):
                erros.append(f"Conta {cod}: ajuste da DFC '{dfc}' deve ser uma linha 6.01.01.xx")
            if col:
                erros.append(f"Conta {cod}: conta de resultado não tem coluna da DMPL")
        else:
            erros.append(f"Conta {cod}: grupo '{grupo}' desconhecido")

    # ---------- 4. Eventos: cadastro, contas e classificação
    for cod in sorted(set(eventos["codigo"]) ^ set(map_ev["codigo_evento"])):
        erros.append(f"Evento {cod} precisa estar em dim_evento e em map_evento_df")

    for _, e in eventos.iterrows():
        for lado in ("contas_debito", "contas_credito"):
            for conta in filter(None, e[lado].split(",")):
                if conta != "TODAS_RESULTADO" and conta not in analiticas:
                    erros.append(f"Evento {e['codigo']}: conta {conta} ({lado}) não é analítica no plano")

    classes_validas = {"", "operacional", "investimento", "financiamento"}
    prefixo_classe = {"investimento": "6.02", "financiamento": "6.03"}
    for _, m in map_ev.iterrows():
        ev, classe, linha = m["codigo_evento"], m["dfc_classe"], m["dfc_linha_caixa"]
        if classe not in classes_validas:
            erros.append(f"Evento {ev}: dfc_classe '{classe}' inválida")
        if classe in prefixo_classe and not linha.startswith(prefixo_classe[classe]):
            erros.append(f"Evento {ev}: evento de {classe} precisa de linha {prefixo_classe[classe]}.xx")
        if linha and not linha_ok("DFC", linha):
            erros.append(f"Evento {ev}: linha da DFC '{linha}' inexistente")
        if linha and not classe:
            erros.append(f"Evento {ev}: tem linha de caixa mas não tem classe de fluxo")
        if m["exclui_do_giro"] not in ("S", "N"):
            erros.append(f"Evento {ev}: exclui_do_giro deve ser S ou N")
        dmpl = m["dmpl_linha"]
        if dmpl and dmpl != "IGNORAR" and not linha_ok("DMPL", dmpl):
            erros.append(f"Evento {ev}: linha da DMPL '{dmpl}' inexistente")
        dva = m["dva_regra"]
        if dva.startswith("7.") and dva not in codigos_dado:
            erros.append(f"Evento {ev}: linha da DVA '{dva}' inexistente")

    # Eventos que mexem no PL precisam dizer onde entram na DMPL
    contas_pl = {c for c in analiticas if c.startswith("2.3")}
    dmpl_por_evento = dict(zip(map_ev["codigo_evento"], map_ev["dmpl_linha"]))
    for _, e in eventos.iterrows():
        contas = set((e["contas_debito"] + "," + e["contas_credito"]).split(","))
        if contas & contas_pl and e["codigo"] != "EV00" and not dmpl_por_evento.get(e["codigo"]):
            erros.append(f"Evento {e['codigo']}: movimenta o PL mas não tem linha da DMPL")

    # ---------- 5. Linhas de dado sem nenhuma origem (aviso tratado como erro: linha morta)
    usadas = set(mapa["linha_bp_dre"]) | set(mapa["linha_dfc"]) | set(mapa["linha_dva"]) \
        | set(map_ev["dfc_linha_caixa"]) | set(map_ev["dmpl_linha"]) | set(map_ev["dva_regra"])
    calculadas_pelo_motor = {"6.01.01.01", "6.05.01", "4.02", "5.01", "5.02",
                             "5.05.01", "5.05.02", "7.08.04.03"}
    for dem, cod in sorted(linhas_dado):
        if cod not in usadas and cod not in calculadas_pelo_motor:
            erros.append(f"Linha {dem} {cod} não recebe valor de nenhuma conta ou evento")

    return erros


def main() -> None:
    cfg = carregar()
    erros = checar(cfg)
    plano = cfg["plano_de_contas"]
    print(f"Plano de contas: {len(plano)} contas "
          f"({(plano['tipo'] == 'A').sum()} analíticas, {(plano['tipo'] == 'S').sum()} sintéticas)")
    print(f"Linhas de demonstrações: {len(cfg['dim_linha_df'])}")
    print(f"Eventos contábeis: {len(cfg['dim_evento'])}")
    if erros:
        print(f"\n{len(erros)} problema(s) encontrado(s):")
        for e in erros:
            print("  -", e)
        raise SystemExit(1)
    print("\nConfiguração OK: toda conta e todo evento têm classificação válida.")


if __name__ == "__main__":
    main()
