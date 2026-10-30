# Etapa 2 — Plano de contas e regras de montagem das demonstrações

## Arquivos

| Arquivo (pasta `config/`) | O que contém |
| --- | --- |
| `plano_de_contas.csv` | 165 contas (120 analíticas, 45 sintéticas), natureza D/C, contas redutoras |
| `dim_linha_df.csv` | 159 linhas de BP, DRE, DRA, DMPL, DFC e DVA, com os códigos do formulário ITR da CVM |
| `dim_coluna_dmpl.csv` | Colunas da DMPL (capital, reservas, lucros acumulados, ORA, PL) |
| `map_conta_df.csv` | Cada conta analítica → linha do BP ou da DRE, tratamento na DFC, linha da DVA, coluna da DMPL |
| `dim_evento.csv` | 59 eventos contábeis com as contas típicas a débito e a crédito |
| `map_evento_df.csv` | Cada evento → classe e linha da DFC, exclusão do capital de giro, linha da DMPL, regra da DVA |
| `empresa.yaml` | Cadastro e parâmetros (alíquotas, vidas úteis, matriz de perda esperada) |

Os CSVs usam `;` e UTF-8 com BOM, então abrem direto no Excel em português. A fonte da verdade
são eles. `plano_de_contas_e_mapeamentos.xlsx` é só uma visão de consulta, gerada por
`src/config_para_excel.py`.

Os códigos de linha seguem o formulário ITR da CVM até o 4º nível (conferidos com o ITR da Embraer
do 2T26). Abaixo disso, as subdivisões são da Orbe, como o formulário permite. Exemplos:
`2.01.05.02.02 Adiantamentos de Clientes` e `5.06.02 Dividendo Adicional Proposto`.

## Por que conta e evento são separados

O BP e a DRE dependem só da **conta**: "Fornecedores de mercadorias" está sempre na linha
2.01.02.01.

A DFC, a DMPL e a DVA dependem do **movimento**. Exemplo: uma máquina de R$ 50 mil.

| Como foi comprada | Lançamento | Efeito na DFC |
| --- | --- | --- |
| À vista (EV42) | D Máquinas / C Bancos | Saída de R$ 50 mil em 6.02.01 Aquisições de imobilizado |
| A prazo com o fornecedor (EV43) | D Máquinas / C Fornecedores de imobilizado | Nenhum agora; o pagamento futuro (EV44) vai para 6.02.01 |
| Via FINAME (EV45) | D Máquinas / C Financiamento | Nenhum; divulgada como transação sem caixa (CPC 03, item 43) |

As três fecham D = C. Só o evento diz qual DFC está certa.

## Como cada demonstração será montada (etapas 5 a 7)

### BP
Saldo final de cada conta analítica, somado na linha de `linha_bp_dre`. Tipo de valor: posição.
Durante o exercício, a linha 2.03.05 (Lucros acumulados) recebe também o resultado do período
ainda não encerrado.

### DRE
Movimento do período nas contas de resultado (grupo 3), somado em `linha_bp_dre`. Sinal: receita
positiva, despesa negativa. Os subtotais (3.03, 3.05, 3.07, 3.09, 3.11) usam a coluna `formula`
de `dim_linha_df`.

### DFC — método indireto, conferido pelo direto
1. **6.01.01.01 Lucro líquido**, vindo da DRE.
2. **Ajustes (6.01.01.xx):** movimento das contas de resultado com `linha_dfc` preenchida
   (depreciação, perda esperada, perdas em estoques, resultado na venda de imobilizado, IR e CS,
   juros apropriados). Entram com sinal invertido, porque reduziram o lucro sem sair caixa.
3. **Variações nos ativos e passivos (6.01.02.xx):** movimentos das contas com `linha_dfc` =
   6.01.02.xx, **exceto** os de eventos com `exclui_do_giro = S` (baixa de incobrável e de
   estoque perdido, que não são caixa).
4. **IR pago (6.01.03.01), investimento (6.02) e financiamento (6.03):** perna de caixa de cada
   lançamento cujo evento tem `dfc_linha_caixa` preenchida.
5. **Conferência 1:** 6.05.02 Saldo final = saldo das contas `CAIXA` no BP.
6. **Conferência 2:** total operacional do método indireto = soma das pernas de caixa dos eventos
   de classe `operacional` (é o método direto). Se o indireto fecha mas o direto não bate, algum
   evento está mal classificado.

Contas `EVENTO` nunca entram na variação de capital de giro. Sua movimentação é explicada pelos
ajustes e pelas linhas de investimento e financiamento.

### DMPL
- Saldo inicial e final por coluna (`coluna_dmpl` das contas do PL).
- Movimentos pelos eventos (`dmpl_linha`).
- 5.05.01 Lucro líquido vem da DRE. Por isso o encerramento do resultado (EV52) é ignorado na
  DMPL, para não contar o lucro duas vezes.
- **Conferência:** 5.07 Saldos finais = PL do BP, coluna por coluna.

### DRA
4.01 = lucro da DRE. 4.02 Outros resultados abrangentes: linha explícita, zerada na V1.

### DVA
- Contas de resultado distribuídas por `linha_dva`.
- Receitas pelo valor bruto. Ajuste do CPC 09: os créditos de ICMS, PIS e COFINS das compras
  (EV09) somam aos insumos (7.02.01) e saem dos tributos distribuídos (7.08.02). Assim os insumos
  ficam com os tributos e os tributos distribuídos ficam líquidos.
- Dividendos do período (EV54, EV55) em 7.08.04.02. Lucros retidos (7.08.04.03) = lucro menos
  dividendos.
- **Conferência:** 7.07 Valor adicionado a distribuir = 7.08 Distribuição.

## Verificação automática

`python src/checar_config.py` confere:
- plano bem formado (sem duplicadas, pai existente, tipo S/A coerente);
- toda conta analítica mapeada uma única vez, para linha existente e do grupo certo;
- contas de resultado com linha de DVA; contas do PL com coluna de DMPL;
- eventos com contas existentes, linha de DFC compatível com a classe (investimento só em 6.02,
  financiamento só em 6.03) e linha de DMPL quando movimentam o PL;
- nenhuma linha de demonstração "morta", sem conta ou evento que a alimente.

`pytest` roda os testes de `testes/test_config.py`. Eles estragam a configuração de propósito (por
exemplo, classificam compra de imobilizado como financiamento) e conferem se o erro é pego.
