"""
Testes da Central de qualidade (Etapa 9).

A Orbe gerada passa em tudo. Depois, cada teste estraga uma cópia da base ou da configuração de
propósito, do jeito que um erro real aconteceria, e confere se a Central percebe, classifica
(erro ou alerta) e bloqueia a publicação quando deve.
"""
import shutil
import sqlite3

import pytest

from checar_config import carregar
from gerar_dados import gerar
from gerar_modelo_entrada import gerar_modelo
from importar_entrada import importar
from qualidade import ALERTA, APROVADO, ERRO, exigir_liberacao, executar


@pytest.fixture(scope="module")
def cfg():
    return carregar()


@pytest.fixture(scope="module")
def base_original(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("qualidade")
    arquivo = gerar_modelo(pasta / "entrada_itr.xlsx", gerar().quadros())
    base = pasta / "itr.sqlite"
    assert importar(arquivo, base)[0] == []
    return base


@pytest.fixture
def con(base_original, tmp_path):
    """Cópia nova da base para cada teste: um teste não estraga o outro."""
    copia = tmp_path / "itr.sqlite"
    shutil.copy(base_original, copia)
    conexao = sqlite3.connect(copia)
    yield conexao
    conexao.close()


def status(execucao, codigo):
    return next(v.status for v in execucao.verificacoes if v.codigo == codigo)


# ---------------------------------------------------------------- caminho feliz

def test_orbe_passa_em_todas_as_verificacoes(con, cfg):
    e = executar(con, "3T26", cfg)
    assert len(e.verificacoes) == 20
    assert all(v.status == APROVADO for v in e.verificacoes), [
        (v.codigo, v.detalhe) for v in e.verificacoes if v.status != APROVADO]
    assert e.liberada


def test_cada_execucao_fica_registrada_com_run_id(con, cfg):
    e1, e2 = executar(con, "3T26", cfg), executar(con, "2T26", cfg)
    assert e1.run_id != e2.run_id
    execucoes = con.execute("SELECT run_id, trimestre, publicacao, sha256 FROM execucao_qualidade "
                            "ORDER BY executado_em").fetchall()
    assert {r[0] for r in execucoes} == {e1.run_id, e2.run_id}
    assert all(r[2] == "liberada" and len(r[3]) == 64 for r in execucoes)
    linhas, = con.execute("SELECT COUNT(*) FROM log_qualidade WHERE run_id = ?", (e1.run_id,)).fetchone()
    assert linhas == 20


# ---------------------------------------------------------------- erros plantados na base

def test_lancamento_alterado_na_base_bloqueia(con, cfg):
    # Alguém mexeu num valor direto no banco, sem passar pelo validador
    con.execute("UPDATE lancamento SET debito_centavos = debito_centavos + 100 WHERE id = "
                "(SELECT MIN(id) FROM lancamento WHERE debito_centavos > 0)")
    e = executar(con, "3T26", cfg)
    assert status(e, "N1.02") == ERRO
    assert status(e, "N3.01") == ERRO  # o BP também deixa de fechar
    assert not e.liberada
    with pytest.raises(PermissionError, match="N1.02"):
        exigir_liberacao(con, "3T26", cfg)


def test_bloqueio_fica_registrado_no_log(con, cfg):
    con.execute("UPDATE lancamento SET debito_centavos = debito_centavos + 100 WHERE id = "
                "(SELECT MIN(id) FROM lancamento WHERE debito_centavos > 0)")
    e = executar(con, "3T26", cfg)
    publicacao, erros = con.execute("SELECT publicacao, erros FROM execucao_qualidade WHERE run_id = ?",
                                    (e.run_id,)).fetchone()
    assert publicacao == "bloqueada" and erros >= 2
    esperado, encontrado = con.execute("SELECT esperado, encontrado FROM log_qualidade WHERE run_id = ? "
                                       "AND codigo = 'N3.01'", (e.run_id,)).fetchone()
    assert esperado != encontrado


def test_alerta_da_importacao_nao_bloqueia(con, cfg):
    con.execute("INSERT INTO alerta_validacao (mensagem) VALUES ('cliente com saldo credor')")
    e = executar(con, "3T26", cfg)
    assert status(e, "N2.01") == ALERTA
    assert e.liberada


def test_origem_apagada_bloqueia(con, cfg):
    con.execute("DELETE FROM importacao")
    e = executar(con, "3T26", cfg)
    assert status(e, "N1.04") == ERRO and not e.liberada


def test_resultado_nao_encerrado_bloqueia(con, cfg):
    # Apagar o encerramento de 2025 deixa a DRE de 2026 contaminada com o lucro de 2025
    con.execute("DELETE FROM lancamento WHERE codigo_evento = 'EV52'")
    e = executar(con, "3T26", cfg)
    assert status(e, "N2.02") == ERRO and not e.liberada


# ---------------------------------------------------------------- erros plantados na configuração

def test_conta_sem_mapeamento_bloqueia(con, cfg):
    errado = {k: v.copy() for k, v in cfg.items()}
    mapa = errado["map_conta_df"]
    errado["map_conta_df"] = mapa[mapa.codigo_conta != "1.1.06.001"]
    e = executar(con, "3T26", errado)
    assert status(e, "N1.01") == ERRO and not e.liberada


def test_classificacao_errada_na_dfc_bloqueia(con, cfg):
    errado = {k: v.copy() for k, v in cfg.items()}
    mev = errado["map_evento_df"]
    mev.loc[mev.codigo_evento == "EV27", "exclui_do_giro"] = "N"
    e = executar(con, "3T26", errado)
    assert status(e, "N3.05") == ERRO  # DFC 9M26: indireto deixa de bater com o direto
    assert not e.liberada


def test_verificacoes_cobrem_os_tres_niveis(con, cfg):
    e = executar(con, "3T26", cfg, registrar=False)
    assert {v.nivel for v in e.verificacoes} == {1, 2, 3}
    assert len({v.codigo for v in e.verificacoes}) == len(e.verificacoes)
