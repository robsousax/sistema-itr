# Etapa 6 — DFC e DMPL

O motor (`src/dfc_dmpl.py`) monta a Demonstração dos Fluxos de Caixa e a Demonstração das
Mutações do Patrimônio Líquido a partir da base, nas linhas da CVM. As duas trazem conferências
próprias e só são consideradas certas quando batem com o BP.

```bash
python src/dfc_dmpl.py          # DFC e DMPL do ITR do 3T26 (9M26 e 9M25) e as conferências
python src/dfc_dmpl.py 2T26
pytest testes/test_dfc_dmpl.py
```

## DFC — método indireto, conferido pelo direto

| Bloco | De onde vem |
| --- | --- |
| 6.01.01.01 Lucro líquido | Linha 3.11 da DRE do período |
| 6.01.01.02 a .07 Ajustes | Movimento das contas de resultado com linha 6.01.01.xx no mapeamento (depreciação, perda esperada, provisão de estoques, resultado na venda de bens, IR e CS, juros apropriados). Despesa que não saiu do caixa volta somando; ganho que não entrou volta subtraindo |
| 6.01.02 Variações nos ativos e passivos | Movimento das contas de capital de giro (linha 6.01.02.xx), **sem** os eventos marcados como fora do giro (baixa de incobrável e de estoque perdido). Ativo que aumenta consome caixa; passivo que aumenta gera caixa |
| 6.01.03.01 IR e CS pagos | Perna de caixa dos eventos de pagamento de IR e do IRRF retido nas aplicações |
| 6.02 Investimento e 6.03 Financiamento | Perna de caixa dos eventos com linha 6.02.xx ou 6.03.xx |
| 6.05.01 Saldo inicial | Caixa e equivalentes no dia anterior ao período |

Conferências (`conferir_dfc`), que bloqueiam a publicação na Etapa 9 se falharem:

1. **Indireto = direto.** O operacional calculado a partir do lucro tem de ser igual à soma do
   dinheiro que entrou e saiu nos eventos operacionais. Se o indireto fecha mas o direto não bate,
   algum evento está mal classificado.
2. **Investimento e financiamento = pernas de caixa** dos eventos dessas classes.
3. **Nenhum fluxo sem classe**, exceto aplicações e resgates entre contas de caixa, que se anulam.
4. **Saldo final = caixa do BP** na data final.

Transações sem caixa (CPC 03, item 43): `transacoes_sem_caixa` lista as compras de bens que não
passaram pelo caixa (EV43, compra a prazo; EV45, FINAME). Elas ficam fora da DFC e vão para a nota
explicativa. Na Orbe: R$ 4.000 mil de caminhões e empilhadeiras via FINAME em 2025 e R$ 300 mil de
porta-paletes a prazo em 2026.

## DMPL — por coluna

| Linha | Origem |
| --- | --- |
| 5.01 Saldos iniciais | PL do BP no dia anterior ao período, por coluna (`coluna_dmpl` das contas do PL) |
| 5.04 Transações com sócios | Eventos com linha 5.04.xx (aumento de capital, dividendos) |
| 5.05.01 Lucro líquido | Linha 3.11 da DRE, na coluna de lucros acumulados |
| 5.06 Mutações internas | Reserva legal, retenção de lucros, dividendo adicional proposto. Mudam a coluna, não o PL total |
| 5.07 Saldos finais | 5.03 + 5.04 + 5.05 + 5.06 |

O encerramento do exercício (EV52) é ignorado na DMPL, porque o lucro já entra pela linha 5.05.01.
Se entrasse também, seria contado duas vezes.

Conferência (`conferir_dmpl`): o saldo final de cada coluna é igual ao PL do BP na data final,
coluna por coluna, e o total também.

Na Orbe, o ITR mostra o 9M26 e o 9M25, e nos dois o PL só varia pelo lucro, porque dividendos e
reservas são destinados em 31/12. A DMPL do ano de 2025 inteiro (testada à parte) mostra as
destinações: dividendo mínimo em 5.04.06 e reserva legal e retenção em 5.06.01.

## O que os testes garantem (`testes/test_dfc_dmpl.py`)

| Grupo | Testes |
| --- | --- |
| Conciliações | DFC confere em 9M25, 2025, 9M26 e 3T26; saldo inicial e final batem com o BP; DFC começa pelo lucro da DRE |
| Linhas conferidas por fora | Fornecedores = variação do BP; contas a receber = variação de clientes mais as baixas contra a provisão |
| Linhas conhecidas pelo roteiro | Investimentos de 2026 (obra, porta-paletes, WMS, venda dos utilitários); FINAME fora da DFC e listado como transação sem caixa; CCB, dividendos e juros pagos |
| Erros plantados | Baixa de incobrável tratada como giro → conferência indireto x direto denuncia; evento no PL sem linha da DMPL → erro com o código do evento |
| DMPL | Confere com o BP nos quatro períodos; 2025 mostra as destinações; 2026 só tem o lucro; saldo inicial = PL de 31/12/2025 |

Para provar que os testes pegam erros, duas regras do motor foram desligadas de propósito:
- tratar a baixa de incobrável como capital de giro: 9 testes falharam;
- tirar o lucro da DMPL: 5 testes falharam.
