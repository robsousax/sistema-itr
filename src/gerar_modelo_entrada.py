"""
Gera entrada/modelo_entrada.xlsx, o Excel em branco que segue o contrato de entrada.

O formato vem todo de contrato_entrada.py. Para mudar uma coluna, altere o contrato e rode
este script de novo.

Uso:
    python src/gerar_modelo_entrada.py
"""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from checar_config import carregar
from config_para_excel import COR_CABECALHO, FONTE_CABECALHO
from contrato_entrada import ABAS

PASTA_ENTRADA = Path(__file__).resolve().parent.parent / "entrada"

# Quantas linhas recebem formato e lista suspensa (o importador lê qualquer quantidade)
LINHAS_FORMATADAS = 1000

FORMATO_EXCEL = {
    "texto": "@",            # texto: evita que 1.10 vire 1,1
    "data": "DD/MM/YYYY",
    "valor": "#,##0.00",
    "inteiro": "0",
    "taxa": "0.00%",         # digitar 12 vira 12% (0,12)
}

TEXTO_LEIA_ME = [
    "Orbe Suprimentos S.A. (fictícia) — Entrada de dados do ITR",
    "",
    "Como preencher:",
    "  1. Não renomeie abas nem colunas. Colunas extras são ignoradas.",
    "  2. Valores em reais, positivos, com no máximo 2 casas decimais. Débito OU crédito, nunca os dois.",
    "  3. Passe o mouse no cabeçalho de cada coluna para ver a explicação.",
    "  4. Linhas totalmente vazias são ignoradas.",
    "  5. A aba 'listas' traz os códigos aceitos (eventos, contas e opções). Não a altere.",
    "",
    "Abas:",
    "  saldos_abertura        Balancete de 31/12/2024 (só contas analíticas)",
    "  lancamentos            Partidas de 01/01/2025 a 30/09/2026; mesmo id = mesmo lançamento",
    "  imobilizado            Um bem por linha (imobilizado e softwares)",
    "  emprestimos            Um contrato por linha (FINAME e CCB)",
    "  patrimonio_liquido     Posição inicial do capital e atos societários",
    "  diferencas_temporarias Base dos tributos diferidos em cada fim de trimestre",
    "",
    "Depois de preencher, salve como entrada/entrada_itr.xlsx e rode:",
    "  python src/importar_entrada.py",
]


def escrever_listas(wb, cfg) -> dict[str, str]:
    """Cria a aba 'listas' e devolve, para cada coluna com opções, a fórmula da lista suspensa."""
    ws = wb.create_sheet("listas")
    eventos = cfg["dim_evento"]
    eventos = eventos[eventos["codigo"] != "EV00"]  # EV00 é o saldo de abertura, não se lança
    plano = cfg["plano_de_contas"]
    analiticas = plano[plano["tipo"] == "A"]

    listas = {
        "codigo_evento": list(eventos["codigo"]),
        "codigo_conta": list(analiticas["codigo"]),
    }
    for colunas in ABAS.values():
        for c in colunas:
            if c.dominio:
                listas[c.nome] = list(c.dominio)

    descricoes = {"codigo_evento": list(eventos["nome"]),
                  "codigo_conta": list(analiticas["descricao"])}

    formulas = {}
    col = 1
    for nome, valores in listas.items():
        letra = get_column_letter(col)
        ws.cell(row=1, column=col, value=nome).font = Font(bold=True)
        for i, v in enumerate(valores, start=2):
            ws.cell(row=i, column=col, value=v).number_format = "@"
        formulas[nome] = f"=listas!${letra}$2:${letra}${len(valores) + 1}"
        ws.column_dimensions[letra].width = 26
        col += 1
        if nome in descricoes:  # coluna ao lado com a descrição, só para consulta
            ws.cell(row=1, column=col, value=f"{nome} (descrição)").font = Font(bold=True)
            for i, v in enumerate(descricoes[nome], start=2):
                ws.cell(row=i, column=col, value=v)
            ws.column_dimensions[get_column_letter(col)].width = 50
            col += 1
    return formulas


def gerar_modelo(destino: Path, dados: dict[str, list[dict]] | None = None) -> Path:
    """
    Gera o Excel de entrada em `destino`.

    Sem `dados`, a aba saldos_abertura vem com todas as contas analíticas e as demais vazias.
    Com `dados` ({aba: [ {coluna: valor}, ... ]}), escreve essas linhas (usado nos testes).
    """
    cfg = carregar()
    wb = Workbook()
    leia = wb.active
    leia.title = "Leia-me"
    for t in TEXTO_LEIA_ME:
        leia.append([t])
    leia["A1"].font = Font(bold=True, size=14)
    leia.column_dimensions["A"].width = 100

    abas = {aba: wb.create_sheet(aba) for aba in ABAS}  # cria na ordem do contrato
    formulas = escrever_listas(wb, cfg)

    if dados is None:
        plano = cfg["plano_de_contas"]
        analiticas = plano[plano["tipo"] == "A"]
        dados = {"saldos_abertura": [{"codigo_conta": c, "descricao": d}
                                     for c, d in zip(analiticas["codigo"], analiticas["descricao"])]}

    for aba, colunas in ABAS.items():
        ws = abas[aba]
        for j, c in enumerate(colunas, start=1):
            cel = ws.cell(row=1, column=j, value=c.nome)
            cel.fill, cel.font = COR_CABECALHO, FONTE_CABECALHO
            if c.obrigatoria:
                obrig = "Obrigatória"
            elif c.obrigatoria_se:
                obrig = f"Obrigatória quando {c.quando}"
            else:
                obrig = "Opcional"
            cel.comment = Comment(f"{obrig}. {c.descricao}", "Sistema ITR")
            letra = get_column_letter(j)
            ws.column_dimensions[letra].width = max(14, len(c.nome) + 4)
            for i in range(2, LINHAS_FORMATADAS + 2):
                ws.cell(row=i, column=j).number_format = FORMATO_EXCEL[c.tipo]
            if c.nome in formulas:
                dv = DataValidation(type="list", formula1=formulas[c.nome], allow_blank=True,
                                    error="Use um valor da aba 'listas'.")
                dv.add(f"{letra}2:{letra}{LINHAS_FORMATADAS + 1}")
                ws.add_data_validation(dv)
        ws.freeze_panes = "A2"

        for i, registro in enumerate(dados.get(aba, []), start=2):
            for j, c in enumerate(colunas, start=1):
                ws.cell(row=i, column=j, value=registro.get(c.nome))

    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


def main() -> None:
    destino = gerar_modelo(PASTA_ENTRADA / "modelo_entrada.xlsx")
    print(f"Gerado: {destino}")


if __name__ == "__main__":
    main()
