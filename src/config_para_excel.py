"""
Gera config/plano_de_contas_e_mapeamentos.xlsx, uma planilha de CONSULTA da configuração.

A fonte da verdade são os arquivos .csv da pasta config (o Git mostra exatamente o que mudou
em cada linha). Para alterar uma regra, edite o .csv e rode este script de novo.

Uso:
    python src/config_para_excel.py
"""
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from checar_config import PASTA_CONFIG, carregar

COR_CABECALHO = PatternFill("solid", fgColor="1F3864")
COR_SINTETICA = PatternFill("solid", fgColor="D9E1F2")
FONTE_CABECALHO = Font(bold=True, color="FFFFFF")


def montar_plano(cfg) -> pd.DataFrame:
    """Plano de contas lado a lado com as linhas de cada demonstração."""
    linhas = cfg["dim_linha_df"].set_index(["demonstracao", "codigo"])["descricao"]

    def descr(dem, cod):
        return linhas.get((dem, cod), cod)

    plano = cfg["plano_de_contas"].merge(
        cfg["map_conta_df"], left_on="codigo", right_on="codigo_conta", how="left").fillna("")
    plano["descricao_indentada"] = plano.apply(
        lambda r: "   " * (int(r["nivel"]) - 1) + r["descricao"], axis=1)
    plano["linha_bp_dre_desc"] = plano.apply(
        lambda r: "" if not r["linha_bp_dre"] else
        f"{r['linha_bp_dre']} {descr('BP' if r['codigo'][0] in '12' else 'DRE', r['linha_bp_dre'])}",
        axis=1)
    plano["linha_dfc_desc"] = plano["linha_dfc"].map(
        lambda c: c if c in ("", "CAIXA", "EVENTO") else f"{c} {descr('DFC', c)}")
    plano["linha_dva_desc"] = plano["linha_dva"].map(
        lambda c: f"{c} {descr('DVA', c)}" if c else "")
    return plano[["codigo", "descricao_indentada", "tipo", "natureza", "redutora",
                  "linha_bp_dre_desc", "linha_dfc_desc", "linha_dva_desc", "coluna_dmpl",
                  "observacao"]].rename(columns={
        "codigo": "Conta", "descricao_indentada": "Descrição", "tipo": "Tipo",
        "natureza": "Natureza", "redutora": "Redutora", "linha_bp_dre_desc": "Linha BP / DRE",
        "linha_dfc_desc": "DFC", "linha_dva_desc": "DVA", "coluna_dmpl": "Coluna DMPL",
        "observacao": "Observação"})


def montar_eventos(cfg) -> pd.DataFrame:
    ev = cfg["dim_evento"].merge(cfg["map_evento_df"], left_on="codigo", right_on="codigo_evento")
    return ev[["codigo", "nome", "grupo", "contas_debito", "contas_credito", "dfc_classe",
               "dfc_linha_caixa", "exclui_do_giro", "dmpl_linha", "dva_regra", "descricao"]].rename(
        columns={"codigo": "Evento", "nome": "Nome", "grupo": "Grupo", "contas_debito": "Débito",
                 "contas_credito": "Crédito", "dfc_classe": "Fluxo de caixa",
                 "dfc_linha_caixa": "Linha DFC", "exclui_do_giro": "Fora do giro?",
                 "dmpl_linha": "Linha DMPL", "dva_regra": "Regra DVA", "descricao": "Descrição"})


def escrever_aba(wb, titulo, df, larguras, destacar_sinteticas=False):
    ws = wb.create_sheet(titulo)
    ws.append(list(df.columns))
    for linha in df.itertuples(index=False):
        ws.append(list(linha))
    for cel in ws[1]:
        cel.fill, cel.font = COR_CABECALHO, FONTE_CABECALHO
        cel.alignment = Alignment(vertical="center", wrap_text=True)
    for i, largura in enumerate(larguras, start=1):
        ws.column_dimensions[get_column_letter(i)].width = largura
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    if destacar_sinteticas:
        col_tipo = list(df.columns).index("Tipo") + 1
        for row in ws.iter_rows(min_row=2):
            if row[col_tipo - 1].value == "S":
                for cel in row:
                    cel.fill, cel.font = COR_SINTETICA, Font(bold=True)
    return ws


def main() -> None:
    cfg = carregar()
    wb = Workbook()
    leia = wb.active
    leia.title = "Leia-me"
    texto = [
        "Orbe Suprimentos S.A. (fictícia) — Plano de contas e mapeamentos",
        "",
        "Planilha só de consulta, gerada por src/config_para_excel.py.",
        "Para alterar, edite os arquivos .csv da pasta config e gere de novo.",
        "",
        "Coluna DFC das contas patrimoniais:",
        "  CAIXA  = compõe caixa e equivalentes (é o que a DFC explica)",
        "  EVENTO = variação explicada pelos eventos (investimento, financiamento, ajustes)",
        "  6.01.02.xx = entra em Variações nos Ativos e Passivos",
        "Coluna DFC das contas de resultado: linha 6.01.01.xx = ajuste ao lucro (não afeta caixa).",
        "",
        "Fora do giro? = S: o movimento do evento não entra na variação de capital de giro.",
    ]
    for t in texto:
        leia.append([t])
    leia["A1"].font = Font(bold=True, size=14)
    leia.column_dimensions["A"].width = 100

    escrever_aba(wb, "Plano de contas", montar_plano(cfg),
                 [13, 55, 6, 9, 9, 45, 42, 45, 11, 60], destacar_sinteticas=True)
    escrever_aba(wb, "Eventos", montar_eventos(cfg),
                 [8, 42, 14, 40, 40, 14, 10, 10, 11, 40, 60])
    escrever_aba(wb, "Linhas das DFs", cfg["dim_linha_df"], [12, 14, 55, 7, 12, 10, 28, 11, 7])
    escrever_aba(wb, "Colunas DMPL", cfg["dim_coluna_dmpl"], [10, 60, 8])

    destino = PASTA_CONFIG / "plano_de_contas_e_mapeamentos.xlsx"
    wb.save(destino)
    print(f"Gerado: {destino}")


if __name__ == "__main__":
    main()
