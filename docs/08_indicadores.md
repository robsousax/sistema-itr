# Etapa 8 — Indicadores

```bash
python src/indicadores.py             # indicadores do 1T25 ao 3T26 e reconciliação do EBITDA
pytest testes/test_indicadores.py
```

Todos os indicadores saem do BP e da DRE do motor, nunca de números digitados. A função
`serie()` devolve a tabela longa (indicador × trimestre) que o Power BI vai consumir na Etapa 11.

## Convenções

| Tipo | Base de cálculo |
| --- | --- |
| Posição (liquidez, endividamento) | BP do fim do trimestre |
| Margens | DRE do trimestre |
| Prazos médios | Saldo **médio** do trimestre (início + fim ÷ 2) contra o fluxo do trimestre, × 90 dias |
| ROE, ROA, giro do ativo, dívida líquida/EBITDA | Últimos 12 meses (UDM) e saldos médios |

Como o histórico começa em jan/2025, os indicadores UDM só existem a partir do 4T25. Antes disso
aparecem como **n.d.** (não disponível). Anualizar um trimestre inventaria um número que não existe.

## Fórmulas

| Grupo | Indicador | Fórmula |
| --- | --- | --- |
| Liquidez | Corrente | Ativo circulante / Passivo circulante |
| | Seca | (Ativo circulante − Estoques − Despesas antecipadas) / Passivo circulante |
| | Imediata | Caixa e equivalentes / Passivo circulante |
| | Geral | (Ativo circulante + Realizável a longo prazo) / (Passivo circulante + Passivo não circulante) |
| Endividamento | Dívida bruta | Empréstimos e financiamentos de curto e de longo prazo |
| | Dívida líquida | Dívida bruta − Caixa e equivalentes (negativo = caixa líquido) |
| | Dívida líquida / EBITDA | Dívida líquida / EBITDA dos últimos 12 meses |
| | PL / Ativo | Patrimônio líquido / Ativo total |
| | Composição do endividamento | Passivo circulante / (Passivo circulante + Passivo não circulante) |
| Rentabilidade | Margem bruta | Resultado bruto / Receita líquida |
| | Margem EBITDA | EBITDA / Receita líquida |
| | Margem EBIT | Resultado antes do resultado financeiro e dos tributos / Receita líquida |
| | Margem líquida | Lucro líquido / Receita líquida |
| | ROE (UDM) | Lucro líquido UDM / PL médio |
| | ROA (UDM) | Lucro líquido UDM / Ativo total médio |
| Atividade | PMR | Clientes (valor bruto) médio / Receita bruta × 90 |
| | PME | Estoque de mercadorias médio / CMV × 90 |
| | PMP | Fornecedores de mercadorias médio / Compras brutas × 90 |
| | Ciclo operacional | PMR + PME |
| | Ciclo financeiro | PMR + PME − PMP |
| | Giro do ativo (UDM) | Receita líquida UDM / Ativo total médio |

Por que as bases de cada prazo médio são diferentes: clientes e receita bruta incluem os tributos; o
estoque é registrado sem os tributos recuperáveis, por isso é comparado com o CMV; fornecedores incluem
os tributos, por isso são comparados com as compras brutas. Numerador e denominador estão sempre na
mesma base.

## EBITDA (Resolução CVM 156/2022)

| Linha | Origem |
| --- | --- |
| Lucro líquido | DRE 3.11 |
| (+) IR e CSLL | DRE 3.08 |
| (+/−) Resultado financeiro líquido | DRE 3.06 |
| (+) Depreciação e amortização | Contas de depreciação e amortização (as mesmas do ajuste 6.01.01.02 da DFC) |
| = EBITDA | |

O EBITDA é medida não contábil. A resolução exige publicar a reconciliação com o lucro e manter o
cálculo consistente ao longo do tempo, e é isso que a tabela faz. Na V1 não há EBITDA ajustado: um
ajuste só poderia entrar com natureza e justificativa documentadas. O teste confere o mesmo número por
dois caminhos (EBIT + D&A e lucro + IR + resultado financeiro + D&A) e confere que a D&A é a mesma da
DFC.

## Análises vertical e horizontal

`analise_vertical_horizontal(tabela, atual, comparativo, base)` recebe o BP ou a DRE montados pelo
motor e devolve, linha a linha:
- **AV:** participação de cada linha no ativo total (BP) ou na receita líquida (DRE);
- **AH:** variação contra o período comparativo.

## O que a Orbe mostra

| Fato do roteiro | Indicador |
| --- | --- |
| Inadimplência no 1T26 | PMR sobe de 45 para 50 dias; ciclo financeiro de 47 para 52 dias |
| Expansão comercial no 4T25 | Margem EBITDA cai de 7,6% para 5,6% |
| Eficiência no 2T26 | Margem EBITDA volta para 8,1% |
| CCB de R$ 8 milhões no 3T26 | Dívida bruta mais que dobra e o PL/ativo cai, mas a dívida líquida continua negativa: a Orbe tem mais caixa que dívida |

## Testes

Cada fórmula é refeita à mão a partir do BP e da DRE e comparada com o indicador: liquidez,
endividamento, margens, ROE, ciclo financeiro, EBITDA por dois caminhos, D&A igual à da DFC. Também
são testados a ausência de anualização antes do 4T25, a história do roteiro, as análises vertical e
horizontal e a formatação.

Para provar que os testes funcionam, duas fórmulas foram estragadas de propósito: a liquidez seca sem
as despesas antecipadas e o ROE com o lucro de um trimestre só. Os dois testes correspondentes
falharam.
