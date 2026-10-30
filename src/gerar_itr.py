"""
Gera o ITR completo (Etapa 10): Excel, PDF e HTML em saidas/<trimestre>/.

Antes de qualquer arquivo, a Central de qualidade roda as 20 verificações. Com algum erro, nada é
gerado e a lista de problemas aparece no terminal.

Uso:
    python src/gerar_itr.py          # ITR do 3T26
    python src/gerar_itr.py 2T26
"""
import sqlite3
import sys
from pathlib import Path

from demonstracoes import BASE_PADRAO
from exportar_excel import exportar_excel
from exportar_pdf import exportar_pdf
from relatorio import coletar

SAIDAS = Path(__file__).resolve().parent.parent / "saidas"


class ArquivoAberto(Exception):
    """O Windows não deixa sobrescrever um arquivo aberto no Excel ou no leitor de PDF."""


def gerar(con, trimestre: str, pasta: Path = SAIDAS) -> dict[str, Path | None]:
    r = coletar(con, trimestre)  # PermissionError se a Central bloquear: nada é gravado
    destino = pasta / trimestre
    try:
        xlsx = exportar_excel(r, destino / f"{r.nome_arquivo}.xlsx")
        html, pdf = exportar_pdf(r, destino / f"{r.nome_arquivo}.pdf")
    except PermissionError as erro:
        raise ArquivoAberto(f"Não foi possível gravar {erro.filename}. O arquivo deve estar aberto "
                            "no Excel ou no leitor de PDF: feche e rode de novo.") from erro
    return {"xlsx": xlsx, "pdf": pdf, "html": html, "run_id": r.qualidade.run_id}


def main() -> None:
    trimestre = sys.argv[1] if len(sys.argv) > 1 else "3T26"
    if not BASE_PADRAO.exists():
        raise SystemExit("Base não encontrada. Rode antes: python src/importar_entrada.py")
    con = sqlite3.connect(BASE_PADRAO)
    try:
        arquivos = gerar(con, trimestre)
    except ArquivoAberto as erro:
        raise SystemExit(f"\n{erro}")
    except PermissionError as erro:
        raise SystemExit(f"\n{erro}\n\nNenhum arquivo foi gerado. Detalhes: python src/qualidade.py {trimestre}")
    finally:
        con.close()
    print(f"Central de qualidade: publicação liberada (run {arquivos['run_id']})")
    print(f"  Excel: {arquivos['xlsx']}")
    print(f"  HTML:  {arquivos['html']}")
    print(f"  PDF:   {arquivos['pdf'] or 'não gerado (instale o Playwright: veja docs/10)'}")


if __name__ == "__main__":
    main()
