# Etapa 7 — DRA, DVA e notas explicativas

```bash
python src/dra_dva.py      # DRA e DVA do ITR do 3T26, com a conferência da DVA
python src/notas.py        # as 10 notas explicativas, com a conferência contra as demonstrações
pytest testes/test_dra_dva_notas.py
```

## DRA (CPC 26)

4.01 vem da DRE; 4.02 é o movimento da conta de outros resultados abrangentes; 4.03 = 4.01 + 4.02.
A Orbe não tem ORA na V1, mas a linha existe e aparece zerada, como pede a norma.

## DVA (CPC 09)

| Bloco | De onde vem |
| --- | --- |
| 7.01 Receitas | Receita bruta (com os tributos dentro), menos devoluções e descontos; outras receitas; perda esperada |
| 7.02 Insumos | CMV, serviços de terceiros, energia, fretes; perdas de estoque |
| 7.04 Retenções | Depreciação e amortização |
| 7.06 Recebido em transferência | Receitas financeiras |
| 7.08 Distribuição | Pessoal (salários, benefícios, FGTS), tributos (federais, estaduais, municipais), juros e aluguéis, dividendos e lucros retidos |

Cada conta de resultado tem a sua linha da DVA em `map_conta_df.csv`. As contas de geração entram
com o sinal da riqueza (receita positiva, insumo negativo); as de distribuição, positivas.

**Ajuste do CPC 09 (item 14).** Os insumos aparecem com ICMS, PIS e COFINS recuperáveis, e os
tributos distribuídos ficam pelo líquido (débitos nas vendas menos créditos nas compras). Como o
estoque é registrado sem esses tributos, o motor soma aos insumos os créditos das compras do período
(EV09) e tira o mesmo valor dos tributos distribuídos.

**Classificações que costumam confundir:** INSS patronal vai para tributos federais, FGTS vai para
pessoal, IOF vai para tributos federais e o aluguel do showroom vai para remuneração de capitais de
terceiros.

**Limite da conferência.** "Valor a distribuir (7.07) = distribuição (7.08)" fecha por construção,
porque toda conta de resultado está de um lado ou do outro. Essa conferência pega erro de programação,
como aplicar o ajuste do CPC 09 em um lado só, mas **não** pega conta classificada na linha errada.
Por isso existem testes linha a linha (vendas, insumos com tributos, ICMS distribuído, FGTS,
dividendos). Um dos testes documenta essa limitação: energia classificada como "outras remunerações"
mantém a DVA fechada, mas muda as linhas.

## Notas explicativas (`src/notas.py`)

| Nota | Conteúdo | Conferida com |
| --- | --- | --- |
| 1 Contexto operacional | Empresa, atividade, estrutura, capital (de `empresa.yaml`) | — |
| 2 Base de preparação | CPC 21, períodos comparativos, políticas, classificação na DFC | — |
| 3 Caixa e equivalentes | Caixa, bancos e CDB | BP 1.01.01 |
| 4 Contas a receber | Clientes e perda esperada; movimentação da provisão; matriz de perda | BP 1.01.03.01 |
| 5 Estoques | Mercadorias e provisão; movimentação da provisão | BP 1.01.04 |
| 6 Imobilizado e intangível | Movimentação por classe (adições, baixas, transferência da obra, depreciação), taxas, transações sem caixa | BP 1.02.03 e 1.02.04 |
| 7 Empréstimos | Contrato a contrato (taxa, vencimento, circulante, não circulante); movimentação; vencimentos do longo prazo por ano | BP 2.01.04 e 2.02.01 |
| 8 IR e CSLL | Reconciliação da alíquota efetiva (34% nominal, efeito da faixa sem adicional); composição do ativo diferido (IRPJ 25% e CSLL 9%) | DRE 3.08 e BP 1.02.01.07.01 |
| 9 PL e LPA | Composição do PL; dividendos declarados e pagos; lucro por ação | BP 2.03 e DRE 3.99 |
| 10 Receita | Receita bruta → tributos, devoluções e descontos → receita líquida | DRE 3.01 |

Os textos usam os parâmetros da empresa e os números da base, nunca valores digitados. Exemplo: a
nota 9 encontra o dividendo declarado e a data do pagamento nos lançamentos.

`conferir_notas` faz 21 conferências entre os quadros das notas e as demonstrações. A diferença
permitida é zero, com uma exceção: na reconciliação da alíquota efetiva, até R$ 1 de arredondamento,
porque cada tributo é arredondado ao centavo em cada trimestre.

## Erros encontrados durante a construção

- **Ativo diferido com 1 centavo de diferença no 2T26.** A nota calculava 34% sobre a base, de uma vez
  só; a contabilidade calcula IRPJ (25%) e CSLL (9%) separados, cada um com o seu arredondamento. A
  nota passou a mostrar os dois tributos, que é também a divulgação correta.
- **Resíduo de 2 centavos na alíquota efetiva.** Vem do arredondamento trimestral de cada tributo. A
  linha foi rotulada "Outros (arredondamentos trimestrais)" e a conferência aceita até R$ 1.

Para provar que os testes funcionam, dois erros foram plantados de propósito: o CDB foi retirado da
nota de caixa e o ajuste do CPC 09 foi aplicado em um lado só da DVA. Sete testes falharam.
