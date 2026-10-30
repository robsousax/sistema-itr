"""
Valida o Excel de entrada antes de gravar qualquer coisa na base.

Nível 1 — integridade: abas e colunas existem, cada célula tem o tipo certo, valores com no
          máximo 2 casas decimais, códigos de conta e evento existem, datas dentro do período,
          sem chaves repetidas.
Nível 2 — coerência contábil: débitos = créditos, conta compatível com o evento e com o lado,
          e cada quadro auxiliar bate com os saldos de abertura.

O nível 2 só roda se o nível 1 passar: com dados mal formados as somas não significam nada.

Uso (só valida, não grava):
    python src/validar_entrada.py entrada/entrada_itr.xlsx
"""
import numbers
import sys
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd
import yaml

from checar_config import PASTA_CONFIG, carregar
from contrato_entrada import (ABAS, CHAVES, CLASSES_IMOBILIZADO, CONTAS_DIFERENCA_TEMPORARIA,
                              CONTAS_EMPRESTIMO, EVENTOS_REVERSIVEIS)

FINS_DE_TRIMESTRE = {(3, 31), (6, 30), (9, 30), (12, 31)}


class ValorInvalido(ValueError):
    """Célula que não pode ser convertida para o tipo da coluna."""


# ---------------------------------------------------------------- conversões de célula

def vazio(v) -> bool:
    if isinstance(v, str):
        return not v.strip()
    return v is None or pd.isna(v)


def para_texto(v) -> str:
    if isinstance(v, float) and v.is_integer():  # 1 digitado no Excel chega como 1.0
        v = int(v)
    return str(v).strip()


def para_centavos(v) -> int:
    """Reais (como vêm do Excel) -> centavos inteiros. R$ 1.234,56 -> 123456."""
    if isinstance(v, bool) or not isinstance(v, numbers.Real):
        raise ValorInvalido(f"'{v}' não é um número (a célula está como texto?)")
    centavos = Decimal(str(v)) * 100
    inteiro = centavos.to_integral_value(rounding=ROUND_HALF_UP)
    # Fórmulas do Excel podem trazer resíduos como 1234.5600000000002: tolera só isso
    if abs(centavos - inteiro) > Decimal("0.0001"):
        raise ValorInvalido(f"{v} tem mais de 2 casas decimais")
    if inteiro < 0:
        raise ValorInvalido(f"{v} é negativo; os valores são sempre positivos")
    return int(inteiro)


def para_data(v) -> date:
    if isinstance(v, datetime):  # inclui o Timestamp do pandas
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        for formato in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(v.strip(), formato).date()
            except ValueError:
                pass
    raise ValorInvalido(f"'{v}' não é uma data válida (use dd/mm/aaaa)")


def para_inteiro(v) -> int:
    if isinstance(v, bool) or not isinstance(v, numbers.Real) or v != int(v):
        raise ValorInvalido(f"'{v}' não é um número inteiro")
    if v < 0:
        raise ValorInvalido(f"{v} é negativo")
    return int(v)


def para_taxa(v) -> float:
    if isinstance(v, bool) or not isinstance(v, numbers.Real):
        raise ValorInvalido(f"'{v}' não é um número")
    if not 0 < v < 1:
        raise ValorInvalido(f"{v} fora do intervalo entre 0 e 1 (12% ao ano se escreve 0,12)")
    return float(v)


CONVERSORES = {"texto": para_texto, "data": para_data, "valor": para_centavos,
               "inteiro": para_inteiro, "taxa": para_taxa}


def nome_convertido(coluna) -> str:
    """Colunas de valor ganham o sufixo _centavos depois de convertidas."""
    return f"{coluna.nome}_centavos" if coluna.tipo == "valor" else coluna.nome


def rs(centavos: int) -> str:
    """Centavos -> texto em reais para as mensagens. 123456 -> 'R$ 1.234,56'."""
    sinal = "-" if centavos < 0 else ""
    reais, cent = divmod(abs(int(centavos)), 100)
    return f"{sinal}R$ {reais:,}".replace(",", ".") + f",{cent:02d}"


def fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


# ---------------------------------------------------------------- leitura

def carregar_empresa() -> dict:
    with open(PASTA_CONFIG / "empresa.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def periodos(empresa: dict) -> tuple[date, date, date]:
    p = empresa["periodos"]
    return (date.fromisoformat(p["saldos_de_abertura"]),
            date.fromisoformat(p["inicio_movimento"]),
            date.fromisoformat(p["fim_movimento"]))


def ler_planilha(caminho: Path) -> dict[str, pd.DataFrame]:
    """Lê todas as abas como estão (dtype=object: nada é convertido pelo pandas)."""
    return pd.read_excel(caminho, sheet_name=None, dtype=object)


# ---------------------------------------------------------------- nível 1

def converter_aba(aba: str, bruto: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Converte cada célula para o tipo da coluna. Linhas com erro ficam de fora do resultado
    (o erro já foi anotado). Valores e inteiros opcionais vazios valem zero.
    """
    colunas = ABAS[aba]
    erros = []
    registros = []
    for indice, linha in bruto.dropna(how="all").iterrows():
        n = indice + 2  # linha do Excel: o índice 0 é a linha 2 (a 1 é o cabeçalho)
        registro = {"linha": n}
        linha_ok = True
        for c in colunas:
            nome = nome_convertido(c)
            v = linha[c.nome]
            if vazio(v):
                registro[nome] = 0 if c.tipo in ("valor", "inteiro") else None
                if c.obrigatoria:
                    erros.append(f"{aba}, linha {n}: coluna '{c.nome}' é obrigatória")
                    linha_ok = False
                continue
            try:
                registro[nome] = CONVERSORES[c.tipo](v)
            except ValorInvalido as e:
                erros.append(f"{aba}, linha {n}, coluna '{c.nome}': {e}")
                linha_ok = False
                continue
            if c.dominio and registro[nome] not in c.dominio:
                erros.append(f"{aba}, linha {n}: '{c.nome}' = '{registro[nome]}' não é aceito "
                             f"(opções: {', '.join(c.dominio)})")
                linha_ok = False
        if linha_ok:
            registros.append(registro)
    nomes = ["linha"] + [nome_convertido(c) for c in colunas]
    return pd.DataFrame(registros, columns=nomes), erros


def problema_conta(codigo: str, tipo_conta: dict[str, str]) -> str | None:
    if codigo not in tipo_conta:
        return f"conta {codigo} não existe no plano de contas"
    if tipo_conta[codigo] != "A":
        return f"conta {codigo} é sintética; use uma conta analítica"
    return None


def validar_nivel1(brutos: dict[str, pd.DataFrame], cfg: dict, empresa: dict
                   ) -> tuple[dict[str, pd.DataFrame], list[str]]:
    erros: list[str] = []
    dados: dict[str, pd.DataFrame] = {}

    # ---------- 1. Abas, colunas e tipos
    for aba, colunas in ABAS.items():
        if aba not in brutos:
            erros.append(f"Aba '{aba}' não encontrada no arquivo")
            continue
        bruto = brutos[aba]
        bruto.columns = [str(c).strip() for c in bruto.columns]
        faltando = [c.nome for c in colunas if c.nome not in bruto.columns]
        if faltando:
            erros.append(f"Aba '{aba}': coluna(s) não encontrada(s): {', '.join(faltando)}")
            continue
        dados[aba], erros_aba = converter_aba(aba, bruto)
        erros += erros_aba
    if len(dados) < len(ABAS):  # sem todas as abas, as checagens abaixo não fazem sentido
        return dados, erros

    # ---------- 2. Chaves sem repetição
    for aba, chave in CHAVES.items():
        df = dados[aba]
        for _, r in df[df.duplicated(list(chave), keep=False)].iterrows():
            valores = ", ".join(str(r[c]) for c in chave)
            erros.append(f"{aba}, linha {r['linha']}: {' + '.join(chave)} = {valores} repetido")

    plano = cfg["plano_de_contas"]
    tipo_conta = dict(zip(plano["codigo"], plano["tipo"]))
    eventos = set(cfg["dim_evento"]["codigo"])
    abertura, inicio, fim = periodos(empresa)

    # ---------- 3. Saldos de abertura
    s = dados["saldos_abertura"]
    for r in s.itertuples():
        if p := problema_conta(r.codigo_conta, tipo_conta):
            erros.append(f"saldos_abertura, linha {r.linha}: {p}")
        if r.debito_centavos > 0 and r.credito_centavos > 0:
            erros.append(f"saldos_abertura, linha {r.linha}: preencha débito OU crédito, não os dois")
    # Linha sem valor = saldo zero: não precisa ir para a base
    dados["saldos_abertura"] = s[(s.debito_centavos > 0) | (s.credito_centavos > 0)]

    # ---------- 4. Lançamentos
    for r in dados["lancamentos"].itertuples():
        local = f"lancamentos, linha {r.linha}"
        if p := problema_conta(r.codigo_conta, tipo_conta):
            erros.append(f"{local}: {p}")
        if r.codigo_evento not in eventos:
            erros.append(f"{local}: evento {r.codigo_evento} não existe em dim_evento")
        elif r.codigo_evento == "EV00":
            erros.append(f"{local}: EV00 é o saldo de abertura; use a aba saldos_abertura")
        if (r.debito_centavos > 0) == (r.credito_centavos > 0):
            erros.append(f"{local}: cada linha precisa de um valor a débito OU a crédito")
        if not inicio <= r.data <= fim:
            erros.append(f"{local}: data {fmt(r.data)} fora do período "
                         f"({fmt(inicio)} a {fmt(fim)})")

    # ---------- 5. Datas dos quadros auxiliares
    for r in dados["imobilizado"].itertuples():
        if r.data_aquisicao > fim:
            erros.append(f"imobilizado, linha {r.linha}: aquisição depois de {fmt(fim)}")
        if r.data_baixa is not None and not inicio <= r.data_baixa <= fim:
            erros.append(f"imobilizado, linha {r.linha}: baixa fora do período "
                         f"({fmt(inicio)} a {fmt(fim)})")
    for r in dados["emprestimos"].itertuples():
        if r.data_contratacao > fim:
            erros.append(f"emprestimos, linha {r.linha}: contratação depois de {fmt(fim)}")
    for r in dados["patrimonio_liquido"].itertuples():
        if not abertura <= r.data <= fim:
            erros.append(f"patrimonio_liquido, linha {r.linha}: data fora de "
                         f"{fmt(abertura)} a {fmt(fim)}")
    for r in dados["diferencas_temporarias"].itertuples():
        d = r.data_base
        if (d.month, d.day) not in FINS_DE_TRIMESTRE or not abertura <= d <= fim:
            erros.append(f"diferencas_temporarias, linha {r.linha}: data_base {fmt(d)} precisa "
                         f"ser fim de trimestre entre {fmt(abertura)} e {fmt(fim)}")

    return dados, erros


# ---------------------------------------------------------------- nível 2

def saldos_ate(dados: dict[str, pd.DataFrame], data: date) -> dict[str, int]:
    """Saldo de cada conta (débito positivo, crédito negativo) no fim do dia `data`."""
    saldos: dict[str, int] = {}
    s = dados["saldos_abertura"]
    for conta, d, c in zip(s.codigo_conta, s.debito_centavos, s.credito_centavos):
        saldos[conta] = saldos.get(conta, 0) + int(d) - int(c)
    lanc = dados["lancamentos"]
    lanc = lanc[lanc.data <= data]
    for conta, d, c in zip(lanc.codigo_conta, lanc.debito_centavos, lanc.credito_centavos):
        saldos[conta] = saldos.get(conta, 0) + int(d) - int(c)
    return saldos


def comparar(erros: list[str], descricao: str, no_quadro: int, na_contabilidade: int,
             tolerancia: int = 0) -> None:
    if abs(no_quadro - na_contabilidade) > tolerancia:
        erros.append(f"{descricao}: quadro soma {rs(no_quadro)}, contabilidade tem "
                     f"{rs(na_contabilidade)} (diferença {rs(no_quadro - na_contabilidade)})")


def checar_saldos_abertura(dados, cfg, abertura) -> list[str]:
    erros = []
    s = dados["saldos_abertura"]
    total_d, total_c = int(s.debito_centavos.sum()), int(s.credito_centavos.sum())
    if total_d != total_c:
        erros.append(f"saldos_abertura: débitos {rs(total_d)} ≠ créditos {rs(total_c)} "
                     f"(diferença {rs(total_d - total_c)})")

    plano = cfg["plano_de_contas"].set_index("codigo")
    for r in s.itertuples():
        conta = plano.loc[r.codigo_conta]
        local = f"saldos_abertura, linha {r.linha}, conta {r.codigo_conta}"
        if r.codigo_conta.startswith("3"):
            erros.append(f"{local}: contas de resultado começam zeradas (o resultado de "
                         f"{abertura.year} já foi encerrado contra o PL)")
        elif conta["redutora"] == "S":
            contrario = r.debito_centavos > 0 if conta["natureza"] == "C" else r.credito_centavos > 0
            if contrario:
                erros.append(f"{local}: conta redutora com saldo contrário à sua natureza "
                             f"({conta['natureza']})")
        if r.codigo_conta == "2.3.03.001" and r.credito_centavos > 0:
            erros.append(f"{local}: lucros acumulados não podem ter saldo credor em 31/12; o "
                         f"lucro precisa estar todo destinado (Lei 6.404, art. 202, § 6º)")
    return erros


def checar_lancamentos(dados, cfg) -> list[str]:
    erros = []
    plano = cfg["plano_de_contas"]
    resultado = set(plano.loc[(plano["tipo"] == "A") & plano["codigo"].str.startswith("3"),
                              "codigo"])

    def contas(texto: str) -> set[str]:
        lista = set(filter(None, texto.split(",")))
        if "TODAS_RESULTADO" in lista:  # EV52 (encerramento) movimenta qualquer conta de resultado
            lista = (lista - {"TODAS_RESULTADO"}) | resultado
        return lista

    contas_evento = {e["codigo"]: (contas(e["contas_debito"]), contas(e["contas_credito"]))
                     for _, e in cfg["dim_evento"].iterrows()}

    for id_lanc, grupo in dados["lancamentos"].groupby("id_lancamento", sort=False):
        local = f"lancamentos, id {id_lanc} (linhas {', '.join(map(str, grupo.linha))})"
        datas = set(grupo.data)
        evs = set(grupo.codigo_evento)
        if len(datas) > 1:
            erros.append(f"{local}: um lançamento tem uma data só "
                         f"(achei {', '.join(fmt(d) for d in sorted(datas))})")
        if len(evs) > 1:
            erros.append(f"{local}: um lançamento tem um evento só (achei {', '.join(sorted(evs))})")
            continue
        total_d, total_c = int(grupo.debito_centavos.sum()), int(grupo.credito_centavos.sum())
        if total_d != total_c:
            erros.append(f"{local}: débitos {rs(total_d)} ≠ créditos {rs(total_c)}")

        ev = evs.pop()
        debito, credito = contas_evento[ev]

        def fora_do_lado(lado_d: set, lado_c: set) -> list:
            return [r for r in grupo.itertuples()
                    if r.codigo_conta not in (lado_d if r.debito_centavos > 0 else lado_c)]

        fora = fora_do_lado(debito, credito)
        if fora and ev in EVENTOS_REVERSIVEIS and not fora_do_lado(credito, debito):
            fora = []  # reversão: o lançamento inteiro está invertido, e isso é permitido
        for r in fora:
            lado, lado_certo = ("débito", "crédito") if r.debito_centavos > 0 else ("crédito", "débito")
            if r.codigo_conta in debito | credito:
                erros.append(f"lancamentos, linha {r.linha}: no evento {ev}, a conta "
                             f"{r.codigo_conta} vai a {lado_certo}, não a {lado}")
            else:
                erros.append(f"lancamentos, linha {r.linha}: a conta {r.codigo_conta} não faz parte "
                             f"do evento {ev} (veja config/dim_evento.csv)")

        if ev == "EV52" and any((d.month, d.day) != (12, 31) for d in datas):
            erros.append(f"{local}: o encerramento do resultado (EV52) só ocorre em 31/12")
    return erros


def checar_imobilizado(dados, empresa, saldos, abertura) -> list[str]:
    erros = []
    vidas = empresa["politicas"]["vida_util_anos"]
    imob = dados["imobilizado"]
    for r in imob.itertuples():
        local = f"imobilizado, linha {r.linha} ({r.id_bem})"
        _, conta_dep, chave_vida = CLASSES_IMOBILIZADO[r.classe]
        dep = r.depreciacao_acumulada_abertura_centavos
        if dep > 0 and conta_dep is None:
            erros.append(f"{local}: {r.classe} não é depreciado; depreciação acumulada deve ser zero")
        elif dep > 0 and r.data_aquisicao > abertura:
            erros.append(f"{local}: bem adquirido depois de {fmt(abertura)} não tem depreciação "
                         f"acumulada na abertura")
        elif dep > r.custo_centavos:
            erros.append(f"{local}: depreciação acumulada {rs(dep)} maior que o custo "
                         f"{rs(r.custo_centavos)}")
        elif chave_vida and dep > 0:
            # Teto generoso: deprecia desde o mês da aquisição, inclusive
            vida = vidas[chave_vida]
            meses = ((abertura.year - r.data_aquisicao.year) * 12
                     + abertura.month - r.data_aquisicao.month + 1)
            maximo = min(r.custo_centavos, -(-r.custo_centavos * meses // (vida * 12)))
            if dep > maximo:
                erros.append(f"{local}: depreciação acumulada {rs(dep)} passa do máximo possível "
                             f"{rs(maximo)} ({meses} meses de uso, vida útil de {vida} anos)")
        if r.data_baixa is not None and r.data_baixa < r.data_aquisicao:
            erros.append(f"{local}: baixa antes da aquisição")
        if r.data_baixa is None and r.valor_venda_centavos > 0:
            erros.append(f"{local}: valor de venda informado sem data de baixa")

    # Conciliação: bens em uso em 31/12/2024 = saldos das contas de custo e de depreciação
    na_abertura = imob[imob.data_aquisicao <= abertura]
    for classe, (conta_custo, conta_dep, _) in CLASSES_IMOBILIZADO.items():
        do_quadro = na_abertura[na_abertura.classe == classe]
        comparar(erros, f"imobilizado x conta {conta_custo} ({classe}) em {fmt(abertura)}",
                 int(do_quadro.custo_centavos.sum()), saldos.get(conta_custo, 0))
        if conta_dep:
            comparar(erros, f"imobilizado x conta {conta_dep} (depreciação de {classe}) em "
                     f"{fmt(abertura)}", int(do_quadro.depreciacao_acumulada_abertura_centavos.sum()),
                     -saldos.get(conta_dep, 0))
    return erros


def checar_emprestimos(dados, saldos, abertura) -> list[str]:
    erros = []
    emp = dados["emprestimos"]
    for r in emp.itertuples():
        local = f"emprestimos, linha {r.linha} ({r.id_contrato})"
        if r.prazo_meses == 0:
            erros.append(f"{local}: prazo_meses precisa ser maior que zero")
        elif r.carencia_meses >= r.prazo_meses:
            erros.append(f"{local}: carência ({r.carencia_meses}) precisa ser menor que o prazo "
                         f"({r.prazo_meses})")
        if r.data_contratacao > abertura and r.saldo_cp_abertura_centavos + r.saldo_lp_abertura_centavos:
            erros.append(f"{local}: contrato posterior a {fmt(abertura)} não tem saldo na abertura")

    for modalidade, (conta_cp, conta_lp) in CONTAS_EMPRESTIMO.items():
        da_modalidade = emp[emp.modalidade == modalidade]
        comparar(erros, f"emprestimos {modalidade} curto prazo x conta {conta_cp}",
                 int(da_modalidade.saldo_cp_abertura_centavos.sum()), -saldos.get(conta_cp, 0))
        comparar(erros, f"emprestimos {modalidade} longo prazo x conta {conta_lp}",
                 int(da_modalidade.saldo_lp_abertura_centavos.sum()), -saldos.get(conta_lp, 0))
    return erros


def checar_patrimonio_liquido(dados, saldos, abertura) -> list[str]:
    erros = []
    pl = dados["patrimonio_liquido"]
    iniciais = pl[pl.tipo_ato == "posicao_inicial"]
    if len(iniciais) != 1:
        erros.append(f"patrimonio_liquido: precisa de exatamente uma linha 'posicao_inicial' "
                     f"(achei {len(iniciais)})")
    else:
        r = next(iniciais.itertuples())
        local = f"patrimonio_liquido, linha {r.linha}"
        if r.data != abertura:
            erros.append(f"{local}: a posição inicial é de {fmt(abertura)}")
        if r.quantidade_acoes == 0:
            erros.append(f"{local}: informe a quantidade de ações na posição inicial")
        comparar(erros, "patrimonio_liquido posição inicial x conta 2.3.01.001 (capital subscrito)",
                 r.valor_centavos, -saldos.get("2.3.01.001", 0))
    for r in pl[pl.tipo_ato != "posicao_inicial"].itertuples():
        if r.data <= abertura:
            erros.append(f"patrimonio_liquido, linha {r.linha}: atos do período começam depois de "
                         f"{fmt(abertura)}")
    return erros


def checar_diferencas_temporarias(dados, empresa, abertura) -> list[str]:
    erros = []
    trib = empresa["tributacao"]
    # Alíquota total do diferido em empresa.yaml; a CSLL fica com a sua alíquota e o IRPJ
    # (com o adicional) com o restante, porque cada tributo tem a sua conta
    aliq_cs = Decimal(str(trib["csll_aliquota"]))
    aliq_ir = Decimal(str(trib["aliquota_diferido"])) - aliq_cs
    dif = dados["diferencas_temporarias"]

    # A diferença não pode ser maior que a provisão que a originou, na mesma data
    for data_base, grupo in dif.groupby("data_base"):
        saldos = saldos_ate(dados, data_base)
        for r in grupo.itertuples():
            conta = CONTAS_DIFERENCA_TEMPORARIA[r.tipo]
            provisao = -saldos.get(conta, 0)
            if r.valor_base_centavos > provisao:
                erros.append(f"diferencas_temporarias, linha {r.linha}: base {rs(r.valor_base_centavos)} "
                             f"maior que a provisão na conta {conta} em {fmt(data_base)} "
                             f"({rs(provisao)})")

    # Na abertura: base x alíquota = IR e CS diferidos ativos (tolerância de 1 centavo)
    saldos = saldos_ate(dados, abertura)
    base = int(dif.loc[dif.data_base == abertura, "valor_base_centavos"].sum())
    for conta, aliq, nome in (("1.2.01.001", aliq_ir, "IRPJ"), ("1.2.01.002", aliq_cs, "CSLL")):
        esperado = int((base * aliq).to_integral_value(rounding=ROUND_HALF_UP))
        comparar(erros, f"diferencas_temporarias x {nome} diferido (conta {conta}, "
                 f"{aliq:.0%} sobre {rs(base)})", esperado, saldos.get(conta, 0), tolerancia=1)
    return erros


def validar_nivel2(dados: dict[str, pd.DataFrame], cfg: dict, empresa: dict) -> list[str]:
    abertura, _, _ = periodos(empresa)
    saldos = saldos_ate(dados, abertura)
    return (checar_saldos_abertura(dados, cfg, abertura)
            + checar_lancamentos(dados, cfg)
            + checar_imobilizado(dados, empresa, saldos, abertura)
            + checar_emprestimos(dados, saldos, abertura)
            + checar_patrimonio_liquido(dados, saldos, abertura)
            + checar_diferencas_temporarias(dados, empresa, abertura))


# ---------------------------------------------------------------- tudo junto

def validar(caminho: Path) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Lê e valida o arquivo. Devolve (dados convertidos, erros). Sem erros = pode importar."""
    cfg = carregar()
    empresa = carregar_empresa()
    dados, erros = validar_nivel1(ler_planilha(caminho), cfg, empresa)
    if erros:
        return dados, [f"[nível 1] {e}" for e in erros]
    return dados, [f"[nível 2] {e}" for e in validar_nivel2(dados, cfg, empresa)]


def imprimir_erros(erros: list[str]) -> None:
    print(f"\n{len(erros)} problema(s) encontrado(s):")
    for e in erros:
        print("  -", e)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python src/validar_entrada.py caminho/do/arquivo.xlsx")
    _, erros = validar(Path(sys.argv[1]))
    if erros:
        imprimir_erros(erros)
        raise SystemExit(1)
    print("Entrada OK: níveis 1 e 2 sem problemas.")


if __name__ == "__main__":
    main()
