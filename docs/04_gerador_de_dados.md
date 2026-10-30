# Etapa 4 — Gerador de dados da Orbe

O gerador transforma o roteiro de negócio em contabilidade completa:

```
config/roteiro.yaml  →  src/gerar_dados.py  →  entrada/entrada_itr.xlsx  →  validação (Etapa 3)  →  base/itr.sqlite
```

A planilha gerada segue o contrato da Etapa 3 e passa pelo mesmo validador. Se o gerador errasse a
contabilidade, a importação seria recusada, como aconteceria com uma planilha feita à mão.

```bash
python src/gerar_dados.py        # gera entrada/entrada_itr.xlsx e mostra o resumo por trimestre
python src/importar_entrada.py   # valida e grava a base
pytest testes/test_gerador.py    # testes desta etapa
```

## O que é gerado

| Item | Quantidade |
| --- | --- |
| Balanço de abertura (31/12/2024) | 43 contas com saldo |
| Lançamentos (jan/2025 a set/2026) | 798 lançamentos, 2.964 partidas, 46 eventos diferentes |
| Bens no quadro de imobilizado | 16 (9 na abertura, 7 adquiridos no período, 1 vendido) |
| Contratos de empréstimo | 3 (FINAME de 2023, FINAME de 2025, CCB de 2026) |
| Bases de diferenças temporárias | 2 por fim de trimestre, de 31/12/2024 a 30/09/2026 |

Os lançamentos são **resumos mensais por natureza**, como a integração do faturamento, da folha e do
contas a pagar num ERP: "Faturamento do mês", "Folha de pagamento do mês", "Pagamentos a
fornecedores". Não há nota a nota.

## A história contada pelos números

| Trimestre | Evento do roteiro | Como aparece na contabilidade |
| --- | --- | --- |
| 1T25 | Operação regular | Receita bruta de ~R$ 30 milhões; margem bruta de ~30% |
| 2T25 | Expansão de vendas | Mais clientes a receber e mais estoque |
| 3T25 | Investimento em estrutura | Caminhões e empilhadeiras de R$ 4 milhões via FINAME, sem passar pelo caixa |
| 4T25 | Expansão comercial | Equipe comercial 12% maior, marketing maior, margem cai para ~28%; dividendos declarados em 31/12 |
| 1T26 | Aumento da inadimplência | Prazo de recebimento sobe para 53 dias; perda esperada vai de 2,7% para 4% dos clientes |
| 2T26 | Ganho de eficiência | Margem volta a ~30%; incobráveis do 1T26 baixados contra a provisão; dividendos de 2025 pagos |
| 3T26 | Crescimento com crédito | CCB de R$ 8 milhões; obra de ampliação do galpão concluída |

Todos os números são hipotéticos. Mesma semente (`semente` no roteiro) gera os mesmos lançamentos,
centavo por centavo.

## Como cada mês é montado

Os eventos de cada mês acontecem em datas fixas e são lançados em ordem cronológica:

| Dia | O que acontece | Eventos |
| --- | --- | --- |
| 1 | Planejamento: receita do mês, metas de prazo médio, compras e pagamentos | — |
| 5 | Salários líquidos e férias | EV16, EV18 |
| 10 | Fornecedores de mercadorias e serviços (com desconto obtido); PLR em fevereiro; seguro em agosto | EV11, EV20, EV22 |
| 15 | 1ª quinzena de recebimentos; juros e amortizações de empréstimos | EV05, EV08, EV38–EV40 |
| 20 | Tributos e encargos do mês anterior; adiantamento de cliente no fim de trimestre; 13º em dezembro | EV14, EV06, EV17, EV18 |
| Último | Faturamento, devoluções, 2ª quinzena, compras, CMV, folha, despesas, depreciação, provisões, rendimento do CDB, apuração de ICMS/PIS/COFINS, reclassificação de empréstimos | EV01–EV05, EV07, EV09, EV10, EV13, EV15, EV17, EV19, EV21, EV23, EV24, EV26–EV32, EV41, EV47, EV48 |
| Fim de trimestre | IRPJ e CSLL correntes e diferidos; compensação do IRRF | EV33–EV35 |
| 31/12 | Encerramento do resultado e destinações | EV52, EV53, EV54, EV58 |

Depois de cada dia, a **tesouraria** confere o banco: abaixo de R$ 1 milhão, resgata do CDB; no
fim do mês, acima de R$ 4 milhões, aplica o excedente.

## Regras de cálculo

- **Clientes, estoques e fornecedores** são dirigidos pelos prazos médios do roteiro. O recebimento
  do mês é o que leva o saldo de clientes ao PMR; a compra é o que leva o estoque ao PME; o pagamento
  é o que leva fornecedores ao PMP, nunca mais do que se deve.
- **CMV** = receita líquida × (1 − margem bruta do trimestre).
- **Tributos sobre vendas e compras:** ICMS de 18%; PIS e COFINS sem o ICMS na base (STF, Tema 69),
  inclusive nos créditos das compras.
- **Folha:** salários com reajuste de 5% em maio; INSS patronal de 27,8% e FGTS de 8% sobre salários e
  comissões; férias (1/12 + 1/3) e 13º (1/12) provisionados todo mês com 36% de encargos; 13º pago em
  novembro (50%) e dezembro (saldo).
- **Perda esperada:** ajustada todo mês para a taxa do trimestre sobre o saldo de clientes. Se a
  provisão estiver acima do necessário, o lançamento é a reversão (EV26 invertido).
- **Provisão de estoques:** 1,2% do saldo de mercadorias; perdas sempre baixadas contra a provisão.
- **Depreciação:** linear, bem a bem, a partir do mês seguinte à entrada em uso e até o mês anterior
  à baixa.
- **Empréstimos:** cronograma SAC ou PRICE com juros mensais; o principal que vence em 12 meses é
  reclassificado para o circulante todo fim de mês.
- **IR e CSLL:** Lucro Real trimestral. Base = lucro antes do IR + aumento das provisões indedutíveis.
  O diferido é 34% (25% IRPJ, 9% CSLL) das provisões, e a alíquota efetiva fica um pouco abaixo de
  34% por causa da faixa sem adicional.
- **Encerramento:** em 31/12/2025 o resultado vai para lucros acumulados; reserva legal de 5%,
  dividendo mínimo de 25% do lucro ajustado e o restante retido.

## Testes (`testes/test_gerador.py`)

| Grupo | O que garante |
| --- | --- |
| Contabilidade | Planilha passa nos níveis 1 e 2 sem erro nem alerta e é importada; mesma semente gera os mesmos lançamentos; balanço fecha e nenhum saldo fica invertido em fim de trimestre; caixa nunca negativo; 2025 encerrado com lucro todo destinado; alíquota efetiva de IR entre 33% e 34,5% |
| DFC antecipada | Em 9M25, 9M26 e 2025, o caixa operacional pelo **método indireto** (lucro + ajustes + capital de giro + IR pago) é igual ao **método direto** (soma do dinheiro que entrou e saiu nos eventos operacionais), e operacional + investimento + financiamento = variação do caixa |
| História | Receita cresce todo trimestre; margem cai no 4T25 e se recupera no 2T26; perda esperada sobe no 1T26; FINAME e CCB aumentam a dívida; PMR segue o roteiro |

O teste da DFC é a prova de que a configuração da Etapa 2 funciona. Ao marcar a baixa de incobrável
como se fosse capital de giro, os três testes de DFC falham. O indireto mostraria um recebimento de
clientes que nunca entrou no banco.

## Simplificações desta etapa

Somam-se às da política contábil (`docs/01`, seção 4):

| Simplificação | Como seria na vida real |
| --- | --- |
| Juros dos empréstimos apropriados e pagos no dia da parcela | A competência exige provisionar no fim do mês os juros de dias corridos ainda não pagos |
| IOF da CCB lançado direto na despesa | Pelo CPC 48, custos de transação entram na taxa efetiva e são apropriados ao longo do contrato |
| Encargos de férias e 13º pagos junto com a remuneração | INSS e FGTS dessas verbas são recolhidos nas guias do mês |
| IRRF do CDB retido todo mês | A retenção acontece no resgate, com alíquota regressiva pelo prazo |
| PIS/COFINS sobre receitas financeiras não calculados | Empresas no regime não cumulativo recolhem 0,65% e 4% sobre receitas financeiras |
| Taxas do CDI hipotéticas | Seriam as taxas efetivas de cada mês |
