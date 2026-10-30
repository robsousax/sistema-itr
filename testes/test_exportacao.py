"""
Testes da exportação do ITR (Etapa 10): Excel, HTML, PDF e comentário de desempenho.

Conferem que os arquivos trazem os mesmos números do motor, que as conferências do Excel são
fórmulas, que o comentário só usa números do sistema e que a Central impede a geração quando há
erro (nenhum arquivo é criado).
"""
import shutil
import sqlite3
from datetime import date

import pytest
from openpyxl import load_workbook

from checar_config import carregar
from comentario import escrever_comentario, mil, pp
from demonstracoes import balanco, resultado
from gerar_dados import gerar as gerar_orbe
import gerar_itr
from gerar_itr import ArquivoAberto, gerar
from gerar_modelo_entrada import gerar_modelo
from importar_entrada import importar


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("exportacao")
    arquivo = gerar_modelo(pasta / "entrada_itr.xlsx", gerar_orbe().quadros())
    caminho = pasta / "itr.sqlite"
    assert importar(arquivo, caminho)[0] == []
    return caminho


@pytest.fixture(scope="module")
def saida(base, tmp_path_factory):
    pasta = tmp_path_factory.mktemp("saidas")
    con = sqlite3.connect(base)
    arquivos = gerar(con, "3T26", pasta)
    con.close()
    return arquivos


@pytest.fixture(scope="module")
def con(base):
    conexao = sqlite3.connect(base)
    yield conexao
    conexao.close()


# ---------------------------------------------------------------- Excel

def test_excel_tem_uma_aba_por_demonstracao(saida):
    wb = load_workbook(saida["xlsx"])
    assert wb.sheetnames == ["Capa", "Comentário", "BP Ativo", "BP Passivo", "DRE", "DRA", "DFC",
                             "DMPL 9M26", "DMPL 9M25", "DVA", "Notas", "Indicadores", "EBITDA",
                             "Central de qualidade"]


def test_excel_grava_reais_e_exibe_em_mil(saida, con):
    ws = load_workbook(saida["xlsx"])["BP Ativo"]
    assert ws["A5"].value == "1" and ws["B5"].value == "Ativo Total"
    ativo = balanco(con, date(2026, 9, 30), carregar())["1"]
    assert ws["C5"].value == ativo / 100          # valor exato, em reais
    assert ws["C5"].number_format.startswith("#,##0,")  # exibido em milhares


def test_excel_lucro_por_acao_na_dre(saida):
    ws = load_workbook(saida["xlsx"])["DRE"]
    linha = next(r for r in ws.iter_rows(min_row=5) if r[0].value == "3.99.01.01")
    assert linha[2].number_format == "0.00000" and 0 < linha[2].value < 1


def test_excel_conferencias_sao_formulas(saida):
    wb = load_workbook(saida["xlsx"])
    for aba, trecho in (("BP Passivo", "'BP Ativo'!"), ("DFC", "'BP Ativo'!"),
                        ("DMPL 9M26", "'BP Passivo'!"), ("DVA", "-"), ("EBITDA", "SUM(")):
        formulas = [c.value for linha in wb[aba].iter_rows() for c in linha
                    if isinstance(c.value, str) and c.value.startswith("=")]
        assert formulas and any(trecho in f for f in formulas), aba


def test_excel_tem_as_dez_notas_e_as_vinte_verificacoes(saida):
    wb = load_workbook(saida["xlsx"])
    titulos = [c.value for c in wb["Notas"]["A"] if isinstance(c.value, str) and c.value[:2].rstrip(".").isdigit()]
    assert len([t for t in titulos if ". " in t[:4]]) == 10
    status = [c.value for c in wb["Central de qualidade"]["D"][4:] if c.value]
    assert len(status) == 20 and set(status) == {"aprovado"}


def test_capa_tem_indice_com_links(saida):
    ws = load_workbook(saida["xlsx"])["Capa"]
    links = [c.hyperlink.location for c in ws["A"] if c.hyperlink]
    assert "'DFC'!A1" in links and "'Central de qualidade'!A1" in links


# ---------------------------------------------------------------- HTML e PDF

def test_html_tem_todas_as_secoes(saida):
    html = saida["html"].read_text(encoding="utf-8")
    for ancora in ("comentario", "bp-ativo", "bp-passivo", "dre", "dra", "dfc", "dmpl-9m26",
                   "dmpl-9m25", "dva", "notas", "indicadores", "qualidade"):
        assert f'id="{ancora}"' in html, ancora
    assert "Simulação acadêmica" in html


def test_pdf_gerado(saida):
    if saida["pdf"] is None:
        pytest.skip("Playwright não instalado")
    pypdf = pytest.importorskip("pypdf")
    leitor = pypdf.PdfReader(saida["pdf"])
    assert len(leitor.pages) >= 15
    texto = "".join(p.extract_text() or "" for p in leitor.pages)
    assert "Orbe Suprimentos" in texto and "Central de qualidade" in texto
    assert "Página 1 de" in leitor.pages[0].extract_text()


# ---------------------------------------------------------------- bloqueio

def test_central_bloqueia_e_nenhum_arquivo_e_gerado(base, tmp_path):
    copia = tmp_path / "itr.sqlite"
    shutil.copy(base, copia)
    con = sqlite3.connect(copia)
    con.execute("UPDATE lancamento SET debito_centavos = debito_centavos + 100 WHERE id = "
                "(SELECT MIN(id) FROM lancamento WHERE debito_centavos > 0)")
    with pytest.raises(PermissionError, match="bloqueada"):
        gerar(con, "3T26", tmp_path / "saidas")
    con.close()
    assert not (tmp_path / "saidas").exists()


def test_arquivo_aberto_no_excel_tem_mensagem_propria(base, tmp_path, monkeypatch):
    """No Windows, sobrescrever um .xlsx aberto dá PermissionError; não pode virar 'bloqueado'."""
    def aberto(r, destino):
        raise PermissionError(13, "Permission denied", str(destino))
    monkeypatch.setattr(gerar_itr, "exportar_excel", aberto)
    con = sqlite3.connect(base)
    with pytest.raises(ArquivoAberto, match="feche e rode de novo"):
        gerar(con, "3T26", tmp_path)
    con.close()


# ---------------------------------------------------------------- comentário de desempenho

def test_comentario_usa_os_numeros_do_motor(con):
    cfg = carregar()
    c = escrever_comentario(con, "3T26", cfg)
    receita = resultado(con, date(2026, 7, 1), date(2026, 9, 30), cfg)["3.01"]
    lucro = resultado(con, date(2026, 7, 1), date(2026, 9, 30), cfg)["3.11"]
    assert mil(receita) in c.destaques[0]
    assert mil(lucro) in c.destaques[3]


def test_comentario_so_cita_causa_registrada(con):
    c = escrever_comentario(con, "3T26", carregar())
    fato = dict(c.paragrafos)["Fato do trimestre"]
    assert "CCB de capital de giro" in fato  # vem do evento do 3T26 no roteiro


@pytest.mark.parametrize("variacao,texto", [(0.0004, "estável"), (0.01, "+1,0 p.p."), (-0.006, "-0,6 p.p.")])
def test_pontos_percentuais(variacao, texto):
    assert pp(variacao) == texto
