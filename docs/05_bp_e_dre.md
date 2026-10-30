# Etapa 5 — Balanço Patrimonial e Demonstração do Resultado

O motor (`src/demonstracoes.py`) lê a base e monta o BP e a DRE nas linhas e códigos do formulário
ITR da CVM. Nenhum número é digitado: tudo vem dos saldos e movimentos das contas, do mapeamento
conta → linha (`config/map_conta_df.csv`) e da estrutura das linhas (`config/dim_linha_df.csv`).

```bash
python src/importar_entrada.py        # se a base ainda não existir
python src/demonstracoes.py           # ITR do 3T26 no terminal, em R$ mil
python src/demonstracoes.py 2T26      # qualquer outro trimestre
pytest testes/test_demonstracoes.py
```

## Como o motor calcula

1. **Lê a base.** Saldo de cada conta numa data (abertura + lançamentos até a data) para o BP;
   movimento de cada conta no período para a DRE.
2. **Soma por linha.** Cada conta analítica cai na sua linha (`linha_bp_dre`). Ativo com débito
   positivo; passivo, PL e DRE com crédito positivo. Por isso as despesas aparecem negativas, como no
   formulário da CVM.
3. **Calcula grupos e subtotais.** Linha de tipo `grupo` = soma das filhas; linha de tipo `formula` =
   soma das linhas citadas (3.03 = 3.01 + 3.02). O motor repete até resolver tudo. Se uma fórmula for
   impossível, por exemplo uma linha que depende de si mesma, ele avisa qual linha.

Duas regras contábeis ficam explícitas no código:

| Regra | Por quê |
| --- | --- |
| No BP, o resultado do exercício ainda não encerrado entra em **Lucros/Prejuízos Acumulados (2.03.05)** | Durante o ano, as contas de resultado continuam abertas; o BP só fecha se o lucro do período estiver no PL |
| A DRE **ignora o encerramento (EV52)** | Em 31/12 o EV52 zera as contas de resultado; se entrasse, apagaria a DRE do 4º trimestre e do ano |

## Períodos (CPC 21, item 20)

| Demonstração | Colunas no ITR do 3T26 |
| --- | --- |
| BP | 30/09/2026 e 31/12/2025 |
| DRE | 3T26, 9M26, 3T25 e 9M25 |

`periodos_itr("3T26")` monta as datas a partir do rótulo do trimestre. O mesmo código serve para
qualquer ITR.

## Lucro por ação (CPC 41)

Lucro do período dividido pela média ponderada de ações em circulação. Cada lote pesa pelos dias em
que esteve em circulação, a partir da tabela `ato_pl` (posição inicial e aumentos de capital). Sem
instrumentos diluidores, o diluído é igual ao básico.

## Apresentação

Os cálculos são em centavos. A conversão para R$ mil acontece só na saída, linha a linha, com
arredondamento de meio para cima. Como no ITR das companhias reais, uma soma pode diferir em 1 da
linha de total por arredondamento.

## O que os testes garantem (`testes/test_demonstracoes.py`)

| Teste | O que prova |
| --- | --- |
| Ativo = passivo + PL nos 7 fins de trimestre | O mapeamento cobre todas as contas e o resultado não encerrado está no PL |
| Lucros acumulados em 30/09/2026 = lucro 9M26 da DRE | BP e DRE estão ligados |
| Lucros acumulados zerados em 31/12/2025 | O lucro de 2025 foi todo destinado |
| Variação do PL em 2026 = lucro 9M26 | Não há movimento de PL sem explicação (prévia da DMPL) |
| DRE 9M = 1T + 2T + 3T, linha a linha | A DRE é aditiva; nenhum período se sobrepõe |
| Subtotais seguem as fórmulas da CVM | 3.03, 3.05, 3.07, 3.09 e 3.11 corretos |
| Lucro da DRE = movimento das contas de resultado somado direto no SQL | O motor não perde nem duplica contas |
| Lucro de 2025 = valor do encerramento | DRE anual bate com o EV52 |
| DRE do 4T25 não é zerada | O encerramento está fora da DRE |
| Clientes, imobilizado e dívida conferidos direto na base | Linhas-chave conferidas por fora do motor |

Para provar que os testes funcionam, duas regras foram desligadas de propósito: tirar o resultado do
período de lucros acumulados e deixar o EV52 entrar na DRE. Dez testes falharam.
