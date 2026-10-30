"""
Contrato de entrada (Etapa 3): o formato que o Excel de entrada precisa seguir.

Este arquivo não executa nada, só declara as regras. O gerador do modelo
(gerar_modelo_entrada.py), o validador (validar_entrada.py) e os testes leem tudo daqui.
Para criar ou mudar uma coluna, altere só este arquivo.
"""
import numbers
from collections.abc import Callable
from dataclasses import dataclass

# Tipos de coluna aceitos:
#   texto   -> códigos e descrições (guardados como texto, para "1.10" não virar 1.1)
#   data    -> data do Excel (ou texto dd/mm/aaaa)
#   valor   -> reais com no máximo 2 casas decimais, nunca negativo; gravado em centavos
#   inteiro -> número sem casas decimais (prazos, quantidade de ações)
#   taxa    -> decimal entre 0 e 1 (12% ao ano = 0,12)
TIPOS = {"texto", "data", "valor", "inteiro", "taxa"}


@dataclass(frozen=True)
class Coluna:
    nome: str
    tipo: str
    obrigatoria: bool = True
    dominio: tuple[str, ...] = ()   # valores aceitos; vazio = qualquer valor
    descricao: str = ""
    # Obrigatória só em alguns casos: função que recebe a linha do Excel (ainda sem conversão)
    # e diz se a coluna precisa estar preenchida; `quando` explica o caso em palavras.
    obrigatoria_se: Callable | None = None
    quando: str = ""


def _texto_da_celula(v) -> str:
    """Texto de uma célula ainda não convertida (vazia ou NaN viram '')."""
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return str(v).strip()


def _numero_positivo(v) -> bool:
    return isinstance(v, numbers.Real) and not isinstance(v, bool) and v > 0


# Classes do imobilizado e intangível -> (conta de custo, conta redutora, chave da vida útil
# em empresa.yaml). Terrenos e obras em andamento não são depreciados.
CLASSES_IMOBILIZADO = {
    "terrenos": ("1.2.02.001", None, None),
    "edificacoes": ("1.2.02.002", "1.2.02.092", "edificacoes"),
    "maquinas_e_equipamentos": ("1.2.02.003", "1.2.02.093", "maquinas_e_equipamentos"),
    "veiculos": ("1.2.02.004", "1.2.02.094", "veiculos"),
    "moveis_e_utensilios": ("1.2.02.005", "1.2.02.095", "moveis_e_utensilios"),
    "equipamentos_de_informatica": ("1.2.02.006", "1.2.02.096", "equipamentos_de_informatica"),
    "imobilizado_em_andamento": ("1.2.02.007", None, None),
    "softwares": ("1.2.03.001", "1.2.03.091", "softwares"),
}

# Modalidade do empréstimo -> (conta do curto prazo, conta do longo prazo)
CONTAS_EMPRESTIMO = {
    "FINAME": ("2.1.04.001", "2.2.01.001"),
    "CCB": ("2.1.04.002", "2.2.01.002"),
}

# Tipo de diferença temporária -> conta da provisão contábil que a origina
CONTAS_DIFERENCA_TEMPORARIA = {
    "perda_esperada_creditos": "1.1.02.009",
    "provisao_perdas_estoques": "1.1.03.009",
}

ATOS_PL = ("posicao_inicial", "aumento_capital", "integralizacao_capital",
           "aprovacao_dividendo_adicional")

# Atos que mudam a quantidade de ações: a quantidade é obrigatória, porque o lucro por ação usa
# a média ponderada de ações em circulação (CPC 41). Aumento sem emissão de ações: informar 0.
ATOS_COM_QUANTIDADE = ("posicao_inicial", "aumento_capital")

# Tratamento dos juros durante a carência do empréstimo (necessário para o cronograma)
JUROS_NA_CARENCIA = ("pagos", "capitalizados")

ABAS: dict[str, list[Coluna]] = {
    "saldos_abertura": [
        Coluna("codigo_conta", "texto", descricao="Conta analítica do plano de contas"),
        Coluna("descricao", "texto", obrigatoria=False,
               descricao="Só para consulta; o sistema usa a descrição do plano"),
        Coluna("debito", "valor", obrigatoria=False, descricao="Saldo devedor em 31/12/2024 (R$)"),
        Coluna("credito", "valor", obrigatoria=False, descricao="Saldo credor em 31/12/2024 (R$)"),
    ],
    "lancamentos": [
        Coluna("id_lancamento", "texto",
               descricao="Agrupa as partidas de um mesmo lançamento (débitos = créditos)"),
        Coluna("data", "data", descricao="Data do fato contábil (01/01/2025 a 30/09/2026)"),
        Coluna("codigo_evento", "texto", descricao="Evento de config/dim_evento.csv (EV01 a EV58)"),
        Coluna("codigo_conta", "texto", descricao="Conta analítica permitida para o evento"),
        Coluna("debito", "valor", obrigatoria=False, descricao="Valor a débito (R$)"),
        Coluna("credito", "valor", obrigatoria=False, descricao="Valor a crédito (R$)"),
        Coluna("historico", "texto", obrigatoria=False, descricao="Texto livre"),
    ],
    "imobilizado": [
        Coluna("id_bem", "texto", descricao="Código único do bem"),
        Coluna("descricao", "texto", descricao="Nome do bem"),
        Coluna("classe", "texto", dominio=tuple(CLASSES_IMOBILIZADO),
               descricao="Define a conta contábil e a vida útil"),
        Coluna("data_aquisicao", "data", descricao="Data em que o bem entrou em uso"),
        Coluna("custo", "valor", descricao="Custo de aquisição (R$)"),
        Coluna("depreciacao_acumulada_abertura", "valor", obrigatoria=False,
               descricao="Depreciação ou amortização acumulada em 31/12/2024 (R$)"),
        Coluna("data_baixa", "data", obrigatoria=False, descricao="Data da venda ou baixa, se houver"),
        Coluna("valor_venda", "valor", obrigatoria=False, descricao="Preço de venda na baixa (R$)"),
    ],
    "emprestimos": [
        Coluna("id_contrato", "texto", descricao="Código único do contrato"),
        Coluna("modalidade", "texto", dominio=tuple(CONTAS_EMPRESTIMO),
               descricao="FINAME ou CCB (capital de giro)"),
        Coluna("credor", "texto", obrigatoria=False, descricao="Banco credor"),
        Coluna("data_contratacao", "data", descricao="Data da liberação dos recursos"),
        Coluna("valor_contratado", "valor", descricao="Principal contratado (R$)"),
        Coluna("taxa_juros_aa", "taxa", descricao="Taxa efetiva ao ano em decimal (12% = 0,12)"),
        Coluna("prazo_meses", "inteiro", descricao="Prazo total, incluindo a carência"),
        Coluna("carencia_meses", "inteiro", obrigatoria=False,
               descricao="Meses sem amortização de principal"),
        Coluna("sistema_amortizacao", "texto", dominio=("SAC", "PRICE"), descricao="SAC ou PRICE"),
        Coluna("juros_na_carencia", "texto", obrigatoria=False, dominio=JUROS_NA_CARENCIA,
               descricao="Na carência, os juros são pagos periodicamente ou capitalizados "
                         "(somados ao saldo devedor)",
               obrigatoria_se=lambda linha: _numero_positivo(linha.get("carencia_meses")),
               quando="há carência (carencia_meses maior que zero)"),
        Coluna("saldo_cp_abertura", "valor", obrigatoria=False,
               descricao="Parcela de curto prazo em 31/12/2024 (R$)"),
        Coluna("saldo_lp_abertura", "valor", obrigatoria=False,
               descricao="Parcela de longo prazo em 31/12/2024 (R$)"),
    ],
    "patrimonio_liquido": [
        Coluna("data", "data", descricao="Data do ato societário"),
        Coluna("tipo_ato", "texto", dominio=ATOS_PL, descricao="Natureza do ato"),
        Coluna("valor", "valor", descricao="Valor do ato (R$)"),
        Coluna("quantidade_acoes", "inteiro", obrigatoria=False,
               descricao="Total de ações na posição inicial; ações emitidas no aumento de "
                         "capital (0 se o aumento não emitiu ações)",
               obrigatoria_se=lambda linha: _texto_da_celula(linha.get("tipo_ato"))
               in ATOS_COM_QUANTIDADE,
               quando="tipo_ato é posicao_inicial ou aumento_capital (base do LPA, CPC 41)"),
        Coluna("descricao", "texto", obrigatoria=False, descricao="Ata, assembleia etc."),
    ],
    "diferencas_temporarias": [
        Coluna("data_base", "data", descricao="Fim de trimestre (31/12/2024 a 30/09/2026)"),
        Coluna("tipo", "texto", dominio=tuple(CONTAS_DIFERENCA_TEMPORARIA),
               descricao="Provisão que gera a diferença"),
        Coluna("valor_base", "valor",
               descricao="Parte da provisão ainda indedutível na data-base (R$)"),
        Coluna("descricao", "texto", obrigatoria=False, descricao="Observação"),
    ],
}

# Colunas que, juntas, não podem se repetir dentro da aba
CHAVES = {
    "saldos_abertura": ("codigo_conta",),
    "imobilizado": ("id_bem",),
    "emprestimos": ("id_contrato",),
    "diferencas_temporarias": ("data_base", "tipo"),
}

# Eventos cujo lançamento pode vir com débitos e créditos todos invertidos (reversão).
# Ex.: EV26 constitui a perda esperada (D despesa / C provisão); a reversão é o inverso.
# EV28: reversão da provisão para perdas em estoques quando o valor realizável líquido
# volta a subir (CPC 16, item 33).
EVENTOS_REVERSIVEIS = {"EV26", "EV28"}
