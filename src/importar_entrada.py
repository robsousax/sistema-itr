"""
Importa o Excel de entrada para base/itr.sqlite.

Tudo ou nada: valida primeiro (níveis 1 e 2) e, com qualquer erro, a base não é tocada.
A base nova é montada num arquivo temporário e só substitui a anterior no final.

Uso:
    python src/importar_entrada.py                     # lê entrada/entrada_itr.xlsx
    python src/importar_entrada.py outro_arquivo.xlsx
"""
import hashlib
import math
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from checar_config import carregar
from contrato_entrada import CLASSES_IMOBILIZADO, CONTAS_DIFERENCA_TEMPORARIA
from validar_entrada import carregar_empresa, imprimir_erros, periodos, rs, validar

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA_PADRAO = RAIZ / "entrada" / "entrada_itr.xlsx"
BASE_PADRAO = RAIZ / "base" / "itr.sqlite"
ESQUEMA = Path(__file__).resolve().parent / "esquema_base.sql"


def para_sql(v):
    """Ajusta um valor do Python para o SQLite: data vira texto ISO, vazio vira NULL."""
    if isinstance(v, date):
        return v.isoformat()
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return v


def inserir(con: sqlite3.Connection, tabela: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    colunas = list(df.columns)
    sql = (f"INSERT INTO {tabela} ({', '.join(colunas)}) "
           f"VALUES ({', '.join('?' for _ in colunas)})")
    linhas = [tuple(para_sql(v) for v in r.values()) for r in df.to_dict("records")]
    con.executemany(sql, linhas)


def sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def gravar(dados: dict[str, pd.DataFrame], arquivo: Path, destino: Path) -> None:
    cfg = carregar()
    empresa = carregar_empresa()
    abertura, _, _ = periodos(empresa)
    vidas = empresa["politicas"]["vida_util_anos"]

    plano = cfg["plano_de_contas"].copy()
    plano["nivel"] = plano["nivel"].astype(int)
    plano["codigo_pai"] = plano["codigo_pai"].replace("", None)

    saldos = dados["saldos_abertura"].drop(columns=["linha", "descricao"])
    saldos.insert(1, "data", abertura)

    lanc = dados["lancamentos"].rename(columns={"linha": "linha_excel"})

    imob = dados["imobilizado"].rename(columns={"linha": "linha_excel"})
    imob["conta_custo"] = imob["classe"].map(lambda c: CLASSES_IMOBILIZADO[c][0])
    imob["conta_depreciacao"] = imob["classe"].map(lambda c: CLASSES_IMOBILIZADO[c][1])
    imob["vida_util_anos"] = imob["classe"].map(
        lambda c: vidas[CLASSES_IMOBILIZADO[c][2]] if CLASSES_IMOBILIZADO[c][2] else None)

    dif = dados["diferencas_temporarias"].rename(columns={"linha": "linha_excel"})
    dif["conta_origem"] = dif["tipo"].map(CONTAS_DIFERENCA_TEMPORARIA)

    temporario = destino.with_suffix(".tmp")
    temporario.unlink(missing_ok=True)
    destino.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(temporario)
    try:
        con.executescript(ESQUEMA.read_text(encoding="utf-8"))
        inserir(con, "importacao", pd.DataFrame([{
            "arquivo": arquivo.name, "sha256": sha256(arquivo),
            "importado_em": datetime.now().isoformat(timespec="seconds")}]))
        inserir(con, "plano_de_contas", plano)
        inserir(con, "dim_evento", cfg["dim_evento"])
        inserir(con, "saldo_abertura", saldos)
        inserir(con, "lancamento", lanc)
        inserir(con, "imobilizado", imob)
        inserir(con, "emprestimo", dados["emprestimos"].rename(columns={"linha": "linha_excel"}))
        inserir(con, "ato_pl", dados["patrimonio_liquido"].rename(columns={"linha": "linha_excel"}))
        inserir(con, "diferenca_temporaria", dif)
        con.commit()
    finally:
        con.close()
    temporario.replace(destino)  # só agora a base antiga é substituída


def importar(arquivo: Path, destino: Path = BASE_PADRAO) -> list[str]:
    """Valida e grava. Devolve a lista de erros; lista vazia = base gravada."""
    dados, erros = validar(arquivo)
    if not erros:
        gravar(dados, arquivo, destino)
    return erros


def main() -> None:
    arquivo = Path(sys.argv[1]) if len(sys.argv) > 1 else ENTRADA_PADRAO
    if not arquivo.exists():
        raise SystemExit(f"Arquivo não encontrado: {arquivo}\n"
                         f"Gere o modelo com: python src/gerar_modelo_entrada.py")
    erros = importar(arquivo)
    if erros:
        imprimir_erros(erros)
        raise SystemExit("\nNada foi gravado. Corrija o Excel e rode de novo.")

    con = sqlite3.connect(BASE_PADRAO)
    partidas, lancamentos, debitos = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT id_lancamento), COALESCE(SUM(debito_centavos), 0) "
        "FROM lancamento").fetchone()
    contas, = con.execute("SELECT COUNT(*) FROM saldo_abertura").fetchone()
    con.close()
    print(f"Importado: {arquivo.name} -> {BASE_PADRAO}")
    print(f"  Saldos de abertura: {contas} contas com saldo")
    print(f"  Lançamentos: {lancamentos} ({partidas} partidas, débitos de {rs(debitos)})")


if __name__ == "__main__":
    main()
