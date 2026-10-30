"""
ITR em PDF (Etapa 10).

O modelo (modelos/itr.html e modelos/itr.css) é preenchido com o Jinja2 e impresso em A4 pelo
Chromium, controlado pelo Playwright. O mesmo HTML também é salvo, para abrir no navegador.

No Windows, depois do `pip install -r requirements.txt`, rode uma vez:
    python -m playwright install chromium
"""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from demonstracoes import formatar, reais_mil
from indicadores import INDICADORES, formatar_valor
from relatorio import Relatorio

MODELOS = Path(__file__).resolve().parent.parent / "modelos"


def mil(c) -> str:
    return formatar(reais_mil(int(c)))


def linhas_df(tabela, demonstracao: str, r: Relatorio, colunas: list[str]) -> list[dict]:
    linhas = []
    for _, l in tabela.iterrows():
        if l.codigo.startswith("3.99"):
            continue
        tipo = r.tipo_linha.get((demonstracao, l.codigo), "dado")
        classe = tipo + (" total" if l.codigo in ("1", "2", "3.11", "6.05.02", "5.07", "7.08") else "")
        linhas.append({"codigo": l.codigo, "descricao": l.descricao, "nivel": min(int(l.nivel), 5),
                       "classe": classe, "valores": [mil(l[c]) for c in colunas]})
    return linhas


def montar_contexto(r: Relatorio) -> dict:
    p = r.periodos
    e = r.empresa["empresa"]
    datas_bp = [p["bp_atual"].rotulo, p["bp_comparativo"].rotulo]
    cab_bp = [f'{p["bp_atual"].rotulo}<span class="sub">atual</span>',
              f'{p["bp_comparativo"].rotulo}<span class="sub">exercício anterior</span>']

    def periodo_cab(chave):
        per = p[chave]
        return f'{per.rotulo}<span class="sub">{per.inicio:%d/%m} a {per.fim:%d/%m/%Y}</span>'

    quatro = ["tri_atual", "acum_atual", "tri_anterior", "acum_anterior"]
    dois = ["acum_atual", "acum_anterior"]
    rot = lambda chaves: [p[k].rotulo for k in chaves]
    nomes_dmpl = {"CAP": "Capital social", "RCAP": "Reservas de capital", "RLUC": "Reservas de lucros",
                  "LACUM": "Lucros acumulados", "ORA": "Outros result. abrangentes", "PL": "Patrimônio líquido"}

    dre = linhas_df(r.dre, "DRE", r, rot(quatro))
    dre.append({"codigo": "3.99.01.01", "descricao": "ON — Lucro básico e diluído por ação (R$)",
                "nivel": 2, "classe": "dado",
                "valores": [str(r.lpa[c]).replace(".", ",") for c in rot(quatro)]})

    demonstracoes = [
        {"id": "bp-ativo", "titulo": "Balanço Patrimonial — Ativo", "subtitulo": "R$ mil",
         "colunas": cab_bp, "linhas": linhas_df(r.bp[r.bp.codigo.str.startswith("1")], "BP", r, datas_bp)},
        {"id": "bp-passivo", "titulo": "Balanço Patrimonial — Passivo e Patrimônio Líquido",
         "subtitulo": "R$ mil. Lucros acumulados recebem o resultado do período, ainda não encerrado.",
         "colunas": cab_bp, "linhas": linhas_df(r.bp[r.bp.codigo.str.startswith("2")], "BP", r, datas_bp)},
        {"id": "dre", "titulo": "Demonstração do Resultado", "subtitulo": "R$ mil, exceto lucro por ação",
         "colunas": [periodo_cab(k) for k in quatro], "linhas": dre},
        {"id": "dra", "titulo": "Demonstração do Resultado Abrangente", "subtitulo": "R$ mil",
         "colunas": [periodo_cab(k) for k in quatro], "linhas": linhas_df(r.dra, "DRA", r, rot(quatro))},
        {"id": "dfc", "titulo": "Demonstração dos Fluxos de Caixa — Método Indireto",
         "subtitulo": "R$ mil. Juros pagos e dividendos em financiamento; juros recebidos e IR pago em operacional.",
         "colunas": [periodo_cab(k) for k in dois], "linhas": linhas_df(r.dfc, "DFC", r, rot(dois)),
         "rodape": ("Transações sem efeito caixa (CPC 03, item 43): " + "; ".join(
             f"{t['historico']} (R$ {mil(t['valor'])} mil)" for t in r.sem_caixa) + ".") if r.sem_caixa else ""},
    ]
    for rotulo, tabela in r.dmpl.items():
        colunas = ["CAP", "RCAP", "RLUC", "LACUM", "ORA", "PL"]
        demonstracoes.append({"id": f"dmpl-{rotulo.lower()}", "titulo": f"Mutações do Patrimônio Líquido — {rotulo}",
                              "subtitulo": "R$ mil", "colunas": [nomes_dmpl[c] for c in colunas],
                              "linhas": linhas_df(tabela, "DMPL", r, colunas)})
    demonstracoes.append({"id": "dva", "titulo": "Demonstração do Valor Adicionado",
                          "subtitulo": "R$ mil. Insumos com os tributos recuperáveis (CPC 09).",
                          "colunas": [periodo_cab(k) for k in dois], "linhas": linhas_df(r.dva, "DVA", r, rot(dois))})

    notas = [{"numero": n.numero, "titulo": n.titulo, "paragrafos": n.paragrafos,
              "quadros": [{"titulo": q.titulo, "unidade": q.unidade, "colunas": q.colunas,
                           "linhas": [{"rotulo": l.rotulo, "destaque": l.destaque,
                                       "valores": [mil(v) if isinstance(v, int) else (v or "") for v in l.valores]}
                                      for l in q.linhas]} for q in n.quadros]} for n in r.notas]

    trims = list(dict.fromkeys(r.indicadores.trimestre))
    grupos = []
    for grupo in dict.fromkeys(i.grupo for i in INDICADORES):
        itens = []
        for i in [i for i in INDICADORES if i.grupo == grupo]:
            valores = r.indicadores[r.indicadores.codigo == i.codigo].set_index("trimestre")["valor"]
            nome = i.nome + (" (R$ mil)" if i.unidade == "R$" else "")
            itens.append({"nome": nome, "formula": i.formula,
                          "valores": [formatar_valor(valores[t], i.unidade) for t in trims]})
        grupos.append({"grupo": grupo, "itens": itens})
    ebitda = [{"rotulo": nome, "destaque": chave == "ebitda",
               "valores": [mil(r.ebitda.loc[chave, t]) for t in trims]}
              for chave, nome in (("lucro_liquido", "Lucro líquido"), ("ir_csll", "(+) IR e CSLL"),
                                  ("resultado_financeiro", "(+/−) Resultado financeiro líquido"),
                                  ("depreciacao_amortizacao", "(+) Depreciação e amortização"),
                                  ("ebitda", "EBITDA"))]
    ebitda.append({"rotulo": "Margem EBITDA", "destaque": False,
                   "valores": [formatar_valor(r.ebitda.loc["margem_ebitda", t], "%") for t in trims]})

    q = r.qualidade
    origem = [v.encontrado for v in q.verificacoes if v.codigo == "N1.04"]
    arquivo = origem[0].split(" (")[0] if origem else ""
    sha = origem[0].split("(")[-1].rstrip("…)") if origem else ""
    secoes = ([{"id": "comentario", "titulo": "Comentário de desempenho"}]
              + [{"id": d["id"], "titulo": d["titulo"]} for d in demonstracoes]
              + [{"id": "notas", "titulo": "Notas explicativas"},
                 {"id": "indicadores", "titulo": "Indicadores e reconciliação do EBITDA"},
                 {"id": "qualidade", "titulo": "Central de qualidade"}])
    return {
        "css": (MODELOS / "itr.css").read_text(encoding="utf-8"),
        "empresa": e["razao_social"], "data_base": f"{r.data_base:%d/%m/%Y}", "trimestre": r.trimestre,
        "destaques": r.comentario.destaques, "comentario": r.comentario.paragrafos,
        "gerado_em": r.gerado_em, "secoes": secoes, "demonstracoes": demonstracoes, "notas": notas,
        "trimestres": trims, "indicadores": grupos, "ebitda": ebitda,
        "qualidade": {"run_id": q.run_id, "total": len(q.verificacoes), "aprovadas": q.contar("aprovado"),
                      "alertas": q.contar("alerta"), "erros": q.contar("erro"), "arquivo": arquivo,
                      "sha": sha, "verificacoes": q.verificacoes},
    }


def renderizar_html(r: Relatorio) -> str:
    ambiente = Environment(loader=FileSystemLoader(MODELOS), autoescape=select_autoescape(["html"]))
    return ambiente.get_template("itr.html").render(**montar_contexto(r))


def exportar_pdf(r: Relatorio, destino_pdf: Path) -> tuple[Path, Path | None]:
    """Grava o HTML e, se o Playwright estiver instalado, o PDF. Devolve (html, pdf ou None)."""
    destino_pdf.parent.mkdir(parents=True, exist_ok=True)
    html = renderizar_html(r)
    caminho_html = destino_pdf.with_suffix(".html")
    caminho_html.write_text(html, encoding="utf-8")
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        return caminho_html, None
    empresa = r.empresa["empresa"]["razao_social"]
    cabecalho = (f'<div style="font-size:7px;color:#5b6672;width:100%;padding:0 14mm;font-family:Arial">'
                 f'{empresa} · ITR {r.data_base:%d/%m/%Y} · R$ mil</div>')
    rodape = ('<div style="font-size:7px;color:#5b6672;width:100%;padding:0 14mm;text-align:right;'
              'font-family:Arial">Página <span class="pageNumber"></span> de <span class="totalPages"></span>'
              '</div>')
    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch()
            pagina = navegador.new_page()
            pagina.set_content(html, wait_until="load")
            pagina.pdf(path=str(destino_pdf), format="A4", print_background=True,
                       display_header_footer=True, header_template=cabecalho, footer_template=rodape,
                       margin={"top": "18mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
            navegador.close()
    except Error as erro:
        if "Executable doesn't exist" in str(erro):
            raise SystemExit("O Chromium do Playwright não está instalado. Rode uma vez:\n"
                             "    python -m playwright install chromium") from erro
        raise
    return caminho_html, destino_pdf
