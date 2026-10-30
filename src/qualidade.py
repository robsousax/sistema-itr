"""
Central de qualidade (Etapa 9).

Reúne num só lugar as verificações das Etapas 2 a 8 e decide se o ITR pode ser publicado.

Três níveis:
  1. Integridade: configuração completa, cada lançamento fecha, abertura fecha, origem registrada.
  2. Coerência contábil: exercícios encerrados direito, alertas da importação, saldos invertidos.
  3. Conciliação: BP fecha, BP x DRE, DRE acumulada, DFC (indireto x direto), DMPL x BP, DVA,
     notas x demonstrações, EBITDA.

Três resultados possíveis por verificação:
  aprovado  tudo certo
  alerta    pede revisão humana, não bloqueia (ex.: cliente com saldo credor)
  erro      bloqueia a publicação do ITR

Cada execução recebe um run_id e fica registrada na base (tabelas execucao_qualidade e
log_qualidade), com o resultado de cada verificação, o valor esperado e o encontrado. Assim dá para
dizer exatamente com quais dados e com quais checagens um relatório foi liberado.

Uso:
    python src/qualidade.py          # roda a Central para o ITR do 3T26; sai com código 1 se bloqueado
    python src/qualidade.py 2T26
"""
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime

from checar_config import carregar, checar
from demonstracoes import BASE_PADRAO, balanco, periodos_itr, resultado, saldos_em
from dfc_dmpl import conferir_dfc, conferir_dmpl, dfc
from dra_dva import conferir_dva
from indicadores import datas_do_trimestre, ebitda
from notas import conferir_notas

APROVADO, ALERTA, ERRO = "aprovado", "alerta", "erro"
NIVEIS = {1: "Integridade", 2: "Coerência contábil", 3: "Conciliação das demonstrações"}

ESQUEMA_LOG = """
CREATE TABLE IF NOT EXISTS execucao_qualidade (
    run_id         TEXT PRIMARY KEY,
    executado_em   TEXT NOT NULL,
    trimestre      TEXT NOT NULL,
    arquivo        TEXT,
    sha256         TEXT,
    verificacoes   INTEGER NOT NULL,
    aprovadas      INTEGER NOT NULL,
    alertas        INTEGER NOT NULL,
    erros          INTEGER NOT NULL,
    publicacao     TEXT NOT NULL CHECK (publicacao IN ('liberada', 'bloqueada'))
);
CREATE TABLE IF NOT EXISTS log_qualidade (
    run_id      TEXT NOT NULL REFERENCES execucao_qualidade (run_id),
    ordem       INTEGER NOT NULL,
    codigo      TEXT NOT NULL,
    nivel       INTEGER NOT NULL,
    descricao   TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('aprovado', 'alerta', 'erro')),
    esperado    TEXT,
    encontrado  TEXT,
    detalhe     TEXT,
    PRIMARY KEY (run_id, ordem)
);
"""


@dataclass
class Verificacao:
    codigo: str
    nivel: int
    descricao: str
    status: str
    esperado: str = ""
    encontrado: str = ""
    detalhe: str = ""


@dataclass
class Execucao:
    run_id: str
    trimestre: str
    executado_em: str
    verificacoes: list[Verificacao]

    def contar(self, status: str) -> int:
        return sum(v.status == status for v in self.verificacoes)

    @property
    def liberada(self) -> bool:
        return self.contar(ERRO) == 0


def rs(centavos: int) -> str:
    sinal = "-" if centavos < 0 else ""
    reais, cent = divmod(abs(int(centavos)), 100)
    return f"{sinal}R$ {reais:,}".replace(",", ".") + f",{cent:02d}"


def igualdade(codigo, nivel, descricao, esperado: int, encontrado: int) -> Verificacao:
    """Verificação de valores que têm de ser iguais ao centavo."""
    ok = esperado == encontrado
    return Verificacao(codigo, nivel, descricao, APROVADO if ok else ERRO, rs(esperado), rs(encontrado),
                       "" if ok else f"diferença de {rs(encontrado - esperado)}")


def lista(codigo, nivel, descricao, problemas: list[str], status_se_houver=ERRO) -> Verificacao:
    """Verificação que devolve uma lista de problemas: vazia = aprovada."""
    if not problemas:
        return Verificacao(codigo, nivel, descricao, APROVADO, "nenhum problema", "nenhum problema")
    return Verificacao(codigo, nivel, descricao, status_se_houver, "nenhum problema",
                       f"{len(problemas)} problema(s)", "; ".join(problemas[:5])
                       + (" ..." if len(problemas) > 5 else ""))


# ---------------------------------------------------------------- verificações

def nivel_1(con, cfg) -> list[Verificacao]:
    v = [lista("N1.01", 1, "Configuração contábil completa (contas, linhas e eventos)", checar(cfg))]
    desbalanceados = con.execute("""
        SELECT id_lancamento, SUM(debito_centavos) - SUM(credito_centavos) FROM lancamento
         GROUP BY id_lancamento HAVING SUM(debito_centavos) <> SUM(credito_centavos)""").fetchall()
    v.append(lista("N1.02", 1, "Cada lançamento tem débitos = créditos",
                   [f"{i}: diferença de {rs(d)}" for i, d in desbalanceados]))
    d, c = con.execute("SELECT SUM(debito_centavos), SUM(credito_centavos) FROM saldo_abertura").fetchone()
    v.append(igualdade("N1.03", 1, "Balancete de abertura fecha (débitos = créditos)", d or 0, c or 0))
    origem = con.execute("SELECT arquivo, sha256 FROM importacao").fetchone()
    v.append(Verificacao("N1.04", 1, "Origem dos dados registrada (arquivo e SHA-256)",
                         APROVADO if origem else ERRO, "arquivo e SHA-256",
                         f"{origem[0]} ({origem[1][:12]}…)" if origem else "sem registro"))
    return v


def nivel_2(con, cfg, fim: date) -> list[Verificacao]:
    v = []
    alertas = [m for m, in con.execute("SELECT mensagem FROM alerta_validacao")]
    v.append(lista("N2.01", 2, "Alertas registrados na importação", alertas, ALERTA))

    problemas = []
    for ano in range(2025, fim.year + 1):
        fim_ano = date(ano, 12, 31)
        if fim_ano > fim:
            continue
        saldos = saldos_em(con, fim_ano)
        abertos = [c for c, s in saldos.items() if c.startswith("3") and s]
        if abertos:
            problemas.append(f"{fim_ano:%d/%m/%Y}: {len(abertos)} conta(s) de resultado com saldo")
        if saldos.get("2.3.03.001", 0) < 0:
            problemas.append(f"{fim_ano:%d/%m/%Y}: lucros acumulados com saldo credor")
    v.append(lista("N2.02", 2, "Exercícios encerrados: resultado zerado e lucro todo destinado", problemas))

    plano = cfg["plano_de_contas"].set_index("codigo")
    invertidos = []
    for conta, saldo in saldos_em(con, fim).items():
        if conta.startswith("3") or plano.loc[conta, "redutora"] == "S":
            continue
        if (saldo > 0) != (plano.loc[conta, "natureza"] == "D"):
            invertidos.append(f"{conta} {plano.loc[conta, 'descricao']} ({rs(saldo)})")
    v.append(lista("N2.03", 2, f"Saldos contrários à natureza em {fim:%d/%m/%Y}", invertidos, ALERTA))
    return v


def nivel_3(con, cfg, trimestre: str) -> list[Verificacao]:
    p = periodos_itr(trimestre)
    atual, comp = p["bp_atual"].fim, p["bp_comparativo"].fim
    ini_ac, fim_ac = p["acum_atual"].inicio, p["acum_atual"].fim
    ini_aa, fim_aa = p["acum_anterior"].inicio, p["acum_anterior"].fim
    bp, bp_comp = balanco(con, atual, cfg), balanco(con, comp, cfg)
    dre = resultado(con, ini_ac, fim_ac, cfg)
    v = [igualdade("N3.01", 3, f"Ativo = Passivo + PL em {atual:%d/%m/%Y}", bp["1"], bp["2"]),
         igualdade("N3.02", 3, f"Ativo = Passivo + PL em {comp:%d/%m/%Y}", bp_comp["1"], bp_comp["2"]),
         igualdade("N3.03", 3, f"Lucros acumulados do BP = lucro {p['acum_atual'].rotulo} da DRE",
                   dre["3.11"], bp["2.03.05"])]

    ano, t_atual = trimestre[2:], int(trimestre[0])
    lucros = [resultado(con, *datas_do_trimestre(f"{t}T{ano}"), cfg)["3.11"]
              for t in range(1, t_atual + 1)]
    v.append(igualdade("N3.04", 3, f"DRE {p['acum_atual'].rotulo} = soma dos trimestres",
                       sum(lucros), dre["3.11"]))

    for codigo, rotulo, ini, fim in (("N3.05", p["acum_atual"].rotulo, ini_ac, fim_ac),
                                     ("N3.06", p["acum_anterior"].rotulo, ini_aa, fim_aa)):
        v.append(lista(codigo, 3, f"DFC {rotulo}: indireto = direto, saldo final = caixa do BP",
                       conferir_dfc(con, ini, fim, cfg)))
    for codigo, rotulo, ini, fim in (("N3.07", p["acum_atual"].rotulo, ini_ac, fim_ac),
                                     ("N3.08", p["acum_anterior"].rotulo, ini_aa, fim_aa)):
        v.append(lista(codigo, 3, f"DMPL {rotulo} = PL do BP, coluna por coluna",
                       conferir_dmpl(con, ini, fim, cfg)))
    for codigo, rotulo, ini, fim in (("N3.09", p["acum_atual"].rotulo, ini_ac, fim_ac),
                                     ("N3.10", p["acum_anterior"].rotulo, ini_aa, fim_aa)):
        v.append(lista(codigo, 3, f"DVA {rotulo}: valor a distribuir = distribuição",
                       conferir_dva(con, ini, fim, cfg)))
    v.append(lista("N3.11", 3, "Notas explicativas = demonstrações (21 conferências)",
                   conferir_notas(con, trimestre, cfg)))

    e = ebitda(con, ini_ac, fim_ac, cfg)
    v.append(igualdade("N3.12", 3, f"EBITDA {p['acum_atual'].rotulo} pelos dois caminhos (Res. CVM 156)",
                       dre["3.05"] + e["depreciacao_amortizacao"], e["ebitda"]))
    v.append(igualdade("N3.13", 3, "Depreciação do EBITDA = ajuste de depreciação da DFC",
                       dfc(con, ini_ac, fim_ac, cfg)["6.01.01.02"], e["depreciacao_amortizacao"]))
    return v


# ---------------------------------------------------------------- execução e registro

def executar(con, trimestre: str = "3T26", cfg: dict | None = None, registrar: bool = True) -> Execucao:
    cfg = cfg or carregar()
    fim = periodos_itr(trimestre)["bp_atual"].fim
    verificacoes = nivel_1(con, cfg) + nivel_2(con, cfg, fim) + nivel_3(con, cfg, trimestre)
    agora = datetime.now()
    execucao = Execucao(f"{agora:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}", trimestre,
                        agora.isoformat(timespec="seconds"), verificacoes)
    if registrar:
        gravar(con, execucao)
    return execucao


def gravar(con, e: Execucao) -> None:
    con.executescript(ESQUEMA_LOG)
    origem = con.execute("SELECT arquivo, sha256 FROM importacao").fetchone() or (None, None)
    con.execute("INSERT INTO execucao_qualidade VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (e.run_id, e.executado_em, e.trimestre, *origem, len(e.verificacoes),
                 e.contar(APROVADO), e.contar(ALERTA), e.contar(ERRO),
                 "liberada" if e.liberada else "bloqueada"))
    con.executemany("INSERT INTO log_qualidade VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(e.run_id, i, v.codigo, v.nivel, v.descricao, v.status, v.esperado,
                      v.encontrado, v.detalhe) for i, v in enumerate(e.verificacoes, start=1)])
    con.commit()


def exigir_liberacao(con, trimestre: str, cfg: dict | None = None) -> Execucao:
    """Para os exportadores (Etapa 10): roda a Central e interrompe se houver erro."""
    e = executar(con, trimestre, cfg)
    if not e.liberada:
        erros = [f"{v.codigo} {v.descricao}" for v in e.verificacoes if v.status == ERRO]
        raise PermissionError(f"Publicação bloqueada pela Central de qualidade (run {e.run_id}): "
                              + "; ".join(erros))
    return e


def imprimir(e: Execucao) -> None:
    simbolo = {APROVADO: "✓", ALERTA: "!", ERRO: "✗"}
    print(f"\nCENTRAL DE QUALIDADE — ITR {e.trimestre}   run {e.run_id}")
    for nivel, nome in NIVEIS.items():
        print(f"\nNível {nivel}: {nome}")
        for v in [v for v in e.verificacoes if v.nivel == nivel]:
            print(f"  {simbolo[v.status]} {v.codigo} {v.descricao}")
            if v.status != APROVADO:
                print(f"      esperado: {v.esperado} | encontrado: {v.encontrado}")
                if v.detalhe:
                    print(f"      {v.detalhe}")
    print(f"\n{len(e.verificacoes)} verificações: {e.contar(APROVADO)} aprovadas, "
          f"{e.contar(ALERTA)} alertas, {e.contar(ERRO)} erros")
    print("PUBLICAÇÃO LIBERADA" if e.liberada else "PUBLICAÇÃO BLOQUEADA: corrija os erros acima")


def main() -> None:
    trimestre = sys.argv[1] if len(sys.argv) > 1 else "3T26"
    if not BASE_PADRAO.exists():
        raise SystemExit("Base não encontrada. Rode antes: python src/importar_entrada.py")
    con = sqlite3.connect(BASE_PADRAO)
    e = executar(con, trimestre)
    con.close()
    imprimir(e)
    if not e.liberada:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
