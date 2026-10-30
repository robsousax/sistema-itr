"""
ITR em Excel (Etapa 10).

Uma aba por demonstração, no layout do formulário da CVM (código da conta, descrição, colunas do
CPC 21), mais capa, comentário de desempenho, notas, indicadores, EBITDA e Central de qualidade.

Os valores são gravados em REAIS (com centavos) e exibidos em R$ mil pelo formato de número
"#,##0,": quem clicar na célula vê o valor exato na barra de fórmulas. As conferências entre
demonstrações são fórmulas do Excel (ex.: Ativo total - Passivo total), para o leitor ver que fecham.
"""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.hyperlink import Hyperlink

from indicadores import POR_CODIGO
from relatorio import Relatorio

AZUL = "1F3864"
CINZA_FAIXA = "EEF2F5"
FONTE_TITULO = Font(name="Calibri", size=14, bold=True, color=AZUL)
FONTE_SUB = Font(name="Calibri", size=10, italic=True, color="5B6672")
FONTE_CAB = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
FUNDO_CAB = PatternFill("solid", fgColor=AZUL)
FUNDO_SUBTOTAL = PatternFill("solid", fgColor=CINZA_FAIXA)
LINHA_TOTAL = Border(top=Side(style="thin", color=AZUL))
MIL = '#,##0,;-#,##0,;"-"'          # reais exibidos em milhares
STATUS_COR = {"aprovado": "E3F1E8", "alerta": "FBF0D9", "erro": "F6DEDA"}


def reais(centavos) -> float:
    return round(int(centavos) / 100, 2)


def titulo(ws, texto: str, subtitulo: str) -> None:
    ws["A1"], ws["A2"] = texto, subtitulo
    ws["A1"].font, ws["A2"].font = FONTE_TITULO, FONTE_SUB


def cabecalho(ws, linha: int, rotulos: list[str]) -> None:
    for j, r in enumerate(rotulos, start=1):
        c = ws.cell(row=linha, column=j, value=r)
        c.font, c.fill = FONTE_CAB, FUNDO_CAB
        c.alignment = Alignment(horizontal="left" if j <= 2 else "right", vertical="center", wrap_text=True)
    ws.row_dimensions[linha].height = 30


# ---------------------------------------------------------------- demonstrações

def aba_demonstracao(wb, nome: str, titulo_aba: str, tabela, demonstracao: str, r: Relatorio,
                     rotulos_colunas: dict | None = None, extra_lpa: dict | None = None) -> dict[str, int]:
    """Escreve uma demonstração e devolve {código da linha: número da linha no Excel}."""
    ws = wb.create_sheet(nome)
    empresa = r.empresa["empresa"]["razao_social"]
    titulo(ws, f"{titulo_aba} — {empresa}", f"ITR de {r.data_base:%d/%m/%Y} · Valores em R$ mil")
    colunas = [c for c in tabela.columns if c not in ("codigo", "descricao", "nivel")]
    cabecalho(ws, 4, ["Código da conta", "Descrição da conta"]
              + [(rotulos_colunas or {}).get(c, c) for c in colunas])
    posicao = {}
    linha = 5
    for _, l in tabela.iterrows():
        if l.codigo.startswith("3.99"):
            continue
        tipo = r.tipo_linha.get((demonstracao, l.codigo), "dado")
        ws.cell(row=linha, column=1, value=l.codigo)
        d = ws.cell(row=linha, column=2, value=l.descricao)
        d.alignment = Alignment(indent=int(l.nivel) - 1)
        for j, c in enumerate(colunas, start=3):
            ws.cell(row=linha, column=j, value=reais(l[c])).number_format = MIL
        if tipo in ("grupo", "formula") or int(l.nivel) == 1:
            for j in range(1, len(colunas) + 3):
                ws.cell(row=linha, column=j).font = Font(bold=True)
        if tipo == "formula":
            for j in range(1, len(colunas) + 3):
                ws.cell(row=linha, column=j).fill = FUNDO_SUBTOTAL
        posicao[l.codigo] = linha
        linha += 1
    if extra_lpa:
        ws.cell(row=linha, column=1, value="3.99.01.01")
        ws.cell(row=linha, column=2, value="ON - Lucro Básico e Diluído por Ação (R$ / ação)")
        for j, c in enumerate(colunas, start=3):
            ws.cell(row=linha, column=j, value=float(extra_lpa[c])).number_format = "0.00000"
        posicao["3.99"] = linha
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 62
    for j in range(3, len(colunas) + 3):
        ws.column_dimensions[get_column_letter(j)].width = 16
    ws.freeze_panes = "C5"
    caber_na_pagina(ws, paisagem=len(colunas) > 3)
    return posicao


def conferencia(ws, linha: int, texto: str, formulas: list[str]) -> None:
    """Linha de conferência com fórmulas do Excel; o resultado esperado é zero."""
    ws.cell(row=linha, column=2, value=texto).font = Font(italic=True, color="5B6672")
    for j, f in enumerate(formulas, start=3):
        c = ws.cell(row=linha, column=j, value=f)
        c.number_format = '#,##0.00;-#,##0.00;"0 (confere)"'
        c.font = Font(italic=True, color="2E7D4F")


# ---------------------------------------------------------------- abas de texto e quadros

def aba_capa(wb, r: Relatorio, abas: list[tuple[str, str]]) -> None:
    ws = wb.active
    ws.title = "Capa"
    e = r.empresa["empresa"]
    q = r.qualidade
    linhas = [
        (e["razao_social"], FONTE_TITULO),
        ("Informações Trimestrais (ITR) — demonstrações individuais", Font(size=12, bold=True)),
        (f"Data-base: {r.data_base:%d/%m/%Y} · Trimestre: {r.trimestre} · Valores em R$ mil", None),
        ("Simulação acadêmica: empresa e números fictícios, estrutura inspirada no formulário ITR da CVM.", FONTE_SUB),
        ("", None),
        ("Central de qualidade", Font(bold=True, color=AZUL)),
        (f"Execução {q.run_id} · {q.executado_em.replace('T', ' ')}", None),
        (f"{len(q.verificacoes)} verificações: {q.contar('aprovado')} aprovadas, {q.contar('alerta')} alertas, "
         f"{q.contar('erro')} erros · Publicação liberada", None),
        ("", None),
        ("Destaques do trimestre", Font(bold=True, color=AZUL)),
    ] + [(f"• {d}", None) for d in r.comentario.destaques] + [("", None), ("Índice", Font(bold=True, color=AZUL))]
    for i, (texto, fonte) in enumerate(linhas, start=1):
        c = ws.cell(row=i, column=1, value=texto)
        if fonte:
            c.font = fonte
    linha = len(linhas) + 1
    for nome, descricao in abas:
        c = ws.cell(row=linha, column=1, value=descricao)
        c.hyperlink = Hyperlink(ref=c.coordinate, location=f"'{nome}'!A1")  # link interno
        c.font = Font(color="1F5F7A", underline="single")
        linha += 1
    ws.cell(row=linha + 1, column=1, value=f"Gerado em {r.gerado_em} pelo Sistema ITR.").font = FONTE_SUB
    ws.column_dimensions["A"].width = 110


def caber_na_pagina(ws, paisagem: bool) -> None:
    """Na impressão, a aba ocupa a largura de uma página e quantas páginas precisar na altura."""
    ws.page_setup.orientation = "landscape" if paisagem else "portrait"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def escrever_paragrafo(ws, linha: int, texto: str, largura: int = 120, negrito=False) -> int:
    c = ws.cell(row=linha, column=1, value=texto)
    c.alignment = Alignment(wrap_text=True, vertical="top")
    if negrito:
        c.font = Font(bold=True)
    ws.merge_cells(start_row=linha, start_column=1, end_row=linha, end_column=6)
    ws.row_dimensions[linha].height = 15 * max(1, -(-len(texto) // largura))
    return linha + 1


def aba_comentario(wb, r: Relatorio) -> None:
    ws = wb.create_sheet("Comentário")
    titulo(ws, "Comentário de desempenho", f"{r.trimestre} · escrito por regras a partir dos números do sistema")
    linha = 4
    for t, p in r.comentario.paragrafos:
        ws.cell(row=linha, column=1, value=t).font = Font(bold=True, color=AZUL)
        linha = escrever_paragrafo(ws, linha + 1, p, largura=95) + 1
    for col in "ABCDEF":
        ws.column_dimensions[col].width = 17
    caber_na_pagina(ws, paisagem=False)


def aba_notas(wb, r: Relatorio) -> None:
    ws = wb.create_sheet("Notas")
    titulo(ws, "Notas explicativas", "Notas selecionadas (CPC 21) · Valores em R$ mil, exceto quando indicado")
    linha = 4
    for n in r.notas:
        ws.cell(row=linha, column=1, value=f"{n.numero}. {n.titulo}").font = Font(bold=True, size=12, color=AZUL)
        linha += 1
        for p in n.paragrafos:
            linha = escrever_paragrafo(ws, linha, p)
        for q in n.quadros:
            linha += 1
            ws.cell(row=linha, column=1, value=f"{q.titulo} ({q.unidade})").font = Font(bold=True)
            linha += 1
            cabecalho(ws, linha, [""] + q.colunas)
            linha += 1
            for l in q.linhas:
                ws.cell(row=linha, column=1, value=l.rotulo)
                for j, v in enumerate(l.valores, start=2):
                    c = ws.cell(row=linha, column=j)
                    if isinstance(v, int):
                        c.value, c.number_format = reais(v), MIL
                    else:
                        c.value = v
                        c.alignment = Alignment(horizontal="right")
                    if l.destaque:
                        c.font, c.border = Font(bold=True), LINHA_TOTAL
                if l.destaque:
                    ws.cell(row=linha, column=1).font = Font(bold=True)
                linha += 1
        linha += 2
    ws.column_dimensions["A"].width = 58
    for j in range(2, 10):
        ws.column_dimensions[get_column_letter(j)].width = 16
    caber_na_pagina(ws, paisagem=True)


def aba_indicadores(wb, r: Relatorio) -> None:
    ws = wb.create_sheet("Indicadores")
    titulo(ws, "Indicadores", "Por trimestre · n.d. = não disponível (histórico começa em jan/2025)")
    trims = list(dict.fromkeys(r.indicadores.trimestre))
    cabecalho(ws, 4, ["Grupo", "Indicador"] + trims + ["Fórmula"])
    formatos = {"%": "0.0%", "x": '0.00"x"', "dias": "0", "R$": MIL}
    linha = 5
    for codigo in dict.fromkeys(r.indicadores.codigo):
        sub = r.indicadores[r.indicadores.codigo == codigo].set_index("trimestre")
        primeiro = sub.iloc[0]
        ws.cell(row=linha, column=1, value=primeiro.grupo)
        ws.cell(row=linha, column=2, value=primeiro.indicador)
        for j, t in enumerate(trims, start=3):
            v = sub.loc[t, "valor"]
            c = ws.cell(row=linha, column=j)
            if v is None or v != v:
                c.value, c.alignment = "n.d.", Alignment(horizontal="right")
            else:
                c.value = float(v) if primeiro.unidade != "R$" else round(float(v), 2)
                c.number_format = formatos[primeiro.unidade]
        ws.cell(row=linha, column=len(trims) + 3, value=POR_CODIGO[codigo].formula).font = FONTE_SUB
        linha += 1
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 16, 34
    for j in range(3, len(trims) + 3):
        ws.column_dimensions[get_column_letter(j)].width = 11
    ws.column_dimensions[get_column_letter(len(trims) + 3)].width = 70
    ws.freeze_panes = "C5"
    caber_na_pagina(ws, paisagem=True)


def aba_ebitda(wb, r: Relatorio) -> None:
    ws = wb.create_sheet("EBITDA")
    titulo(ws, "Reconciliação do EBITDA (Resolução CVM 156)", "Medida não contábil, reconciliada com o lucro líquido · R$ mil")
    trims = list(r.ebitda.columns)
    cabecalho(ws, 4, ["", ""] + trims)
    rotulos = [("lucro_liquido", "Lucro líquido"), ("ir_csll", "(+) IR e CSLL"),
               ("resultado_financeiro", "(+/-) Resultado financeiro líquido"),
               ("depreciacao_amortizacao", "(+) Depreciação e amortização"), ("ebitda", "= EBITDA"),
               ("receita_liquida", "Receita líquida"), ("margem_ebitda", "Margem EBITDA")]
    for i, (chave, nome) in enumerate(rotulos, start=5):
        ws.cell(row=i, column=2, value=nome)
        for j, t in enumerate(trims, start=3):
            v = r.ebitda.loc[chave, t]
            c = ws.cell(row=i, column=j)
            if chave == "margem_ebitda":
                c.value, c.number_format = float(v), "0.0%"
            else:
                c.value, c.number_format = round(float(v) / 100, 2), MIL
            if chave == "ebitda":
                c.font, c.border = Font(bold=True), LINHA_TOTAL
    conferencia(ws, 13, "Conferência: EBITDA - soma das parcelas", [
        f"={get_column_letter(j)}9-SUM({get_column_letter(j)}5:{get_column_letter(j)}8)"
        for j in range(3, len(trims) + 3)])
    ws.column_dimensions["B"].width = 38
    for j in range(3, len(trims) + 3):
        ws.column_dimensions[get_column_letter(j)].width = 12


def aba_qualidade(wb, r: Relatorio) -> None:
    ws = wb.create_sheet("Central de qualidade")
    q = r.qualidade
    titulo(ws, "Central de qualidade", f"Execução {q.run_id} · {len(q.verificacoes)} verificações · "
                                       f"publicação {'liberada' if q.liberada else 'bloqueada'}")
    cabecalho(ws, 4, ["Código", "Nível", "Verificação", "Status", "Esperado", "Encontrado", "Detalhe"])
    for i, v in enumerate(q.verificacoes, start=5):
        valores = [v.codigo, v.nivel, v.descricao, v.status, v.esperado, v.encontrado, v.detalhe]
        for j, val in enumerate(valores, start=1):
            c = ws.cell(row=i, column=j, value=val)
            c.alignment = Alignment(horizontal="left")
        ws.cell(row=i, column=4).fill = PatternFill("solid", fgColor=STATUS_COR[v.status])
    for col, w in zip("ABCDEFG", (9, 7, 62, 11, 22, 22, 40)):
        ws.column_dimensions[col].width = w
    caber_na_pagina(ws, paisagem=True)


# ---------------------------------------------------------------- montagem

def exportar_excel(r: Relatorio, destino: Path) -> Path:
    wb = Workbook()
    p = r.periodos
    datas = {p["bp_atual"].rotulo: f"{p['bp_atual'].rotulo}\natual",
             p["bp_comparativo"].rotulo: f"{p['bp_comparativo'].rotulo}\nexercício anterior"}
    abas = [("Comentário", "Comentário de desempenho"), ("BP Ativo", "Balanço Patrimonial — Ativo"),
            ("BP Passivo", "Balanço Patrimonial — Passivo e PL"), ("DRE", "Demonstração do Resultado"),
            ("DRA", "Demonstração do Resultado Abrangente"), ("DFC", "Demonstração dos Fluxos de Caixa"),
            *[(f"DMPL {k}", f"Mutações do Patrimônio Líquido — {k}") for k in r.dmpl],
            ("DVA", "Demonstração do Valor Adicionado"), ("Notas", "Notas explicativas"),
            ("Indicadores", "Indicadores"), ("EBITDA", "Reconciliação do EBITDA"),
            ("Central de qualidade", "Central de qualidade")]
    aba_capa(wb, r, abas)
    aba_comentario(wb, r)

    ativo = aba_demonstracao(wb, "BP Ativo", "Balanço Patrimonial Ativo",
                             r.bp[r.bp.codigo.str.startswith("1")], "BP", r, datas)
    passivo = aba_demonstracao(wb, "BP Passivo", "Balanço Patrimonial Passivo",
                               r.bp[r.bp.codigo.str.startswith("2")], "BP", r, datas)
    ws = wb["BP Passivo"]
    conferencia(ws, max(passivo.values()) + 2, "Conferência: Ativo total - Passivo total",
                [f"='BP Ativo'!{c}{ativo['1']}-{c}{passivo['2']}" for c in "CD"])

    aba_demonstracao(wb, "DRE", "Demonstração do Resultado", r.dre, "DRE", r, extra_lpa=r.lpa)
    aba_demonstracao(wb, "DRA", "Demonstração do Resultado Abrangente", r.dra, "DRA", r)
    fluxo = aba_demonstracao(wb, "DFC", "Demonstração dos Fluxos de Caixa — Método Indireto", r.dfc, "DFC", r)
    conferencia(wb["DFC"], max(fluxo.values()) + 2, "Conferência: saldo final - caixa do BP (coluna atual)",
                [f"=C{fluxo['6.05.02']}-'BP Ativo'!C{ativo['1.01.01']}"])

    nomes_col = {"CAP": "Capital social", "RCAP": "Reservas de capital", "RLUC": "Reservas de lucros",
                 "LACUM": "Lucros acumulados", "ORA": "Outros resultados abrangentes", "PL": "Patrimônio líquido"}
    for k, tabela in r.dmpl.items():
        pos = aba_demonstracao(wb, f"DMPL {k}", f"Demonstração das Mutações do PL — {k}", tabela, "DMPL", r, nomes_col)
        if k == p["acum_atual"].rotulo:
            conferencia(wb[f"DMPL {k}"], max(pos.values()) + 2, "Conferência: PL final - PL do BP",
                        [f"=H{pos['5.07']}-'BP Passivo'!C{passivo['2.03']}"])
    valor = aba_demonstracao(wb, "DVA", "Demonstração do Valor Adicionado", r.dva, "DVA", r)
    conferencia(wb["DVA"], max(valor.values()) + 2, "Conferência: valor a distribuir - distribuição",
                [f"={c}{valor['7.07']}-{c}{valor['7.08']}" for c in "CD"])

    aba_notas(wb, r)
    aba_indicadores(wb, r)
    aba_ebitda(wb, r)
    aba_qualidade(wb, r)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino
