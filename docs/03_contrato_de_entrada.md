# Etapa 3 — Contrato de entrada e base SQLite

## Fluxo

```
entrada/entrada_itr.xlsx  →  nível 1 (integridade)  →  nível 2 (coerência)  →  base/itr.sqlite
```

Tudo ou nada: com qualquer erro, nada é gravado e a base anterior continua intacta.

| Arquivo | O que faz |
| --- | --- |
| `src/contrato_entrada.py` | Define abas, colunas, tipos e valores aceitos. Fonte da verdade do formato |
| `src/gerar_modelo_entrada.py` | Gera `entrada/modelo_entrada.xlsx` (em branco, com listas suspensas) |
| `src/validar_entrada.py` | Lê o Excel, converte para centavos e roda os níveis 1 e 2 |
| `src/esquema_base.sql` | Estrutura das tabelas do SQLite |
| `src/importar_entrada.py` | Valida e grava `base/itr.sqlite` |
| `testes/test_entrada.py` | Dados coerentes passam; cada defeito plantado é pego |

## Regras gerais de preenchimento

- Não renomeie abas nem colunas. Colunas e abas extras são ignoradas.
- Valores em reais, **sempre positivos**, com no máximo 2 casas decimais. O lado vai na coluna
  (débito ou crédito), nunca no sinal.
- Campos numéricos opcionais vazios valem zero.
- Linhas totalmente vazias são ignoradas.
- Datas como data do Excel ou texto `dd/mm/aaaa`.
- Taxas em decimal: 12% ao ano = `0,12` (a coluna já vem formatada como %).

## Dicionário de dados

Na base, toda coluna de valor ganha o sufixo `_centavos` e é gravada como inteiro.
R$ 1.234,56 vira `123456`. O arredondamento para R$ mil acontece só na saída (Etapa 10).

### `saldos_abertura` — balancete de 31/12/2024
| Coluna | Tipo | Obrig. | Observação |
| --- | --- | --- | --- |
| codigo_conta | texto | sim | Conta analítica do plano |
| descricao | texto | não | Só para consulta |
| debito / credito | valor | não | Um dos dois; os dois vazios = saldo zero |

O modelo já vem com as 120 contas analíticas listadas.

### `lancamentos` — partidas de 01/01/2025 a 30/09/2026
| Coluna | Tipo | Obrig. | Observação |
| --- | --- | --- | --- |
| id_lancamento | texto | sim | Partidas com o mesmo id formam um lançamento |
| data | data | sim | |
| codigo_evento | texto | sim | De `config/dim_evento.csv`, exceto EV00 |
| codigo_conta | texto | sim | Conta analítica prevista no evento |
| debito / credito | valor | um dos dois | |
| historico | texto | não | |

### `imobilizado` — um bem por linha (inclui softwares do intangível)
| Coluna | Tipo | Obrig. | Observação |
| --- | --- | --- | --- |
| id_bem | texto | sim | Único |
| descricao | texto | sim | |
| classe | lista | sim | Define conta de custo, conta redutora e vida útil (ver abaixo) |
| data_aquisicao | data | sim | |
| custo | valor | sim | |
| depreciacao_acumulada_abertura | valor | não | Em 31/12/2024 |
| data_baixa | data | não | Venda ou baixa no período |
| valor_venda | valor | não | Zero = baixa sem venda |

| Classe | Conta de custo | Conta redutora | Vida útil |
| --- | --- | --- | --- |
| terrenos | 1.2.02.001 | — | não deprecia |
| edificacoes | 1.2.02.002 | 1.2.02.092 | 25 anos |
| maquinas_e_equipamentos | 1.2.02.003 | 1.2.02.093 | 10 anos |
| veiculos | 1.2.02.004 | 1.2.02.094 | 5 anos |
| moveis_e_utensilios | 1.2.02.005 | 1.2.02.095 | 10 anos |
| equipamentos_de_informatica | 1.2.02.006 | 1.2.02.096 | 5 anos |
| imobilizado_em_andamento | 1.2.02.007 | — | não deprecia |
| softwares | 1.2.03.001 | 1.2.03.091 | 5 anos |

### `emprestimos` — um contrato por linha
| Coluna | Tipo | Obrig. | Observação |
| --- | --- | --- | --- |
| id_contrato | texto | sim | Único |
| modalidade | lista | sim | FINAME (contas 2.1.04.001 / 2.2.01.001) ou CCB (2.1.04.002 / 2.2.01.002) |
| credor | texto | não | |
| data_contratacao | data | sim | |
| valor_contratado | valor | sim | |
| taxa_juros_aa | taxa | sim | Entre 0 e 1 |
| prazo_meses | inteiro | sim | Inclui a carência |
| carencia_meses | inteiro | não | |
| sistema_amortizacao | lista | sim | SAC ou PRICE |
| juros_na_carencia | lista | se houver carência | `pagos` (pagos periodicamente) ou `capitalizados` (somados ao saldo devedor). Necessário para o cronograma da Etapa 4 |
| saldo_cp_abertura / saldo_lp_abertura | valor | não | Em 31/12/2024 |

### `patrimonio_liquido` — capital e atos societários
| Coluna | Tipo | Obrig. | Observação |
| --- | --- | --- | --- |
| data | data | sim | |
| tipo_ato | lista | sim | posicao_inicial, aumento_capital, integralizacao_capital, aprovacao_dividendo_adicional |
| valor | valor | sim | |
| quantidade_acoes | inteiro | em posicao_inicial e aumento_capital | Total de ações na posição inicial; ações emitidas no aumento (0 se não houve emissão). Base da média ponderada do LPA (CPC 41) |
| descricao | texto | não | |

### `diferencas_temporarias` — base dos tributos diferidos (CPC 32)
| Coluna | Tipo | Obrig. | Observação |
| --- | --- | --- | --- |
| data_base | data | sim | Fim de trimestre, de 31/12/2024 a 30/09/2026 |
| tipo | lista | sim | perda_esperada_creditos (provisão 1.1.02.009) ou provisao_perdas_estoques (1.1.03.009) |
| valor_base | valor | sim | Parte da provisão ainda indedutível |
| descricao | texto | não | |

## Validações

### Nível 1 — integridade (formato)
- Todas as abas e colunas obrigatórias existem.
- Campos obrigatórios preenchidos; cada célula no tipo da coluna.
- Valores positivos com no máximo 2 casas decimais; taxas entre 0 e 1; inteiros sem decimais.
- Valores fora da lista (classe, modalidade, sistema, tipo de ato, tipo de diferença) recusados.
- Contas existem no plano e são analíticas; eventos existem em `dim_evento`; EV00 não é lançado.
- Cada partida tem débito **ou** crédito (nos saldos, no máximo um dos dois).
- Lançamentos dentro do período; aquisições e contratações até 30/09/2026; baixas no período;
  data-base das diferenças em fim de trimestre.
- Chaves sem repetição: conta nos saldos, `id_bem`, `id_contrato`, (data-base, tipo).

### Nível 2 — coerência contábil
Só roda se o nível 1 passar.

**Saldos de abertura**
- Total de débitos = total de créditos.
- Contas de resultado zeradas: o resultado de 2024 já foi encerrado contra o PL.
- Contas redutoras sem saldo contrário à sua natureza.
- Lucros acumulados sem saldo credor em 31/12 (Lei 6.404, art. 202, § 6º: o lucro precisa estar
  todo destinado).

**Lançamentos**
- Cada lançamento tem uma data, um evento, ao menos duas partidas e débitos = créditos.
- Cada conta faz parte do evento **e está no lado previsto**. Exemplo: no EV01 (venda),
  Clientes só a débito e Receita só a crédito. Exceção: eventos reversíveis aceitam o
  lançamento inteiro invertido. São o EV26 (reversão da perda esperada, CPC 48) e o EV28
  (reversão da provisão para perdas em estoques, CPC 16, item 33).
- Encerramento do resultado (EV52) só em 31/12, com contrapartida só em lucros acumulados
  (2.3.03.001), pela regra de contas do evento.

**Encerramento do exercício** (em cada 31/12 já encerrado)

O exercício é considerado encerrado quando já há lançamentos do ano seguinte ou quando há um
EV52 no próprio 31/12. Nesse caso:
- Todas as contas de resultado ficam zeradas depois do EV52. Se sobrar saldo, a DRE do ano
  seguinte começa contaminada pelo resultado do ano anterior.
- Lucros acumulados sem saldo credor depois das destinações (EV53 a EV58), pela mesma regra
  da abertura (Lei 6.404, art. 202, § 6º).

**Quadros × contabilidade** (em 31/12/2024)
- Imobilizado: custo dos bens em uso = saldo de cada conta de custo; depreciação acumulada =
  saldo de cada conta redutora.
- Depreciação acumulada de cada bem: não passa do custo, nem do máximo possível pela vida útil
  (contando desde o mês da aquisição, o teto mais generoso). Terrenos e obras em andamento não
  depreciam. Bem comprado depois da abertura não tem depreciação na abertura.
- Empréstimos: soma do curto e do longo prazo por modalidade = saldo das contas; carência menor
  que o prazo; contrato posterior à abertura sem saldo na abertura.
- PL: exatamente uma posição inicial, em 31/12/2024, com valor = capital subscrito (2.3.01.001)
  e quantidade de ações informada.
- Diferenças temporárias: em cada data-base, base ≤ saldo da provisão que a origina (saldo
  calculado com os lançamentos até a data). Na abertura, a base vezes a alíquota do diferido
  (`tributacao.aliquota_diferido` = 34% em `empresa.yaml`) tem de bater com o IR e a CS
  diferidos. A CSLL diferida (1.2.01.002) usa `csll_aliquota` (9%) e o IRPJ diferido
  (1.2.01.001) usa o restante (25%, já com o adicional). Tolerância de 1 centavo. Ver
  política 3.11 em `docs/01`.

### Erro × alerta

| Tipo | Efeito | Exemplo |
| --- | --- | --- |
| Erro | Bloqueia a importação; nada é gravado | Balancete desbalanceado, conta fora do evento, redutora invertida |
| Alerta | Não bloqueia; fica registrado na tabela `alerta_validacao` para revisão | Conta comum com saldo contrário à natureza na abertura (cliente credor, adiantamento credor, prejuízos acumulados) |

Saldo contrário à natureza pode ser legítimo (adiantamento recebido, pagamento em duplicidade),
mas também pode ser erro de classificação. Por isso pede revisão humana em vez de bloquear.
Esta é a primeira peça da Central de qualidade (Etapa 9).

### O que fica para depois
- Conferir os quadros contra os **lançamentos do período** (por exemplo, todo bem comprado em
  2025 ter um EV42, EV43 ou EV45 correspondente): Etapa 4, quando os lançamentos forem gerados
  a partir dos quadros.
- Conciliação entre demonstrações (DFC × BP, DMPL × BP, DVA): Etapa 9.

## Base SQLite (`base/itr.sqlite`)

| Tabela | Conteúdo |
| --- | --- |
| importacao | Nome do arquivo importado, SHA-256 e data e hora |
| plano_de_contas, dim_evento | Cópias da `config` (permitem as chaves estrangeiras) |
| saldo_abertura | Uma linha por conta com saldo em 31/12/2024 |
| lancamento | Uma linha por partida, com `linha_excel` para rastrear a origem |
| imobilizado | Bens, já com conta de custo, conta redutora e vida útil |
| emprestimo | Contratos |
| ato_pl | Atos societários |
| diferenca_temporaria | Bases dos diferidos, já com a conta da provisão |
| alerta_validacao | Alertas que não bloquearam a importação, para a Central de qualidade |

O próprio banco repete parte das regras (`CHECK` e `REFERENCES`): valores nunca negativos,
débito ou crédito na mesma partida, conta e evento existentes. É uma segunda linha de defesa,
caso alguém grave na base sem passar pelo validador.

## Comandos

```bash
python src/gerar_modelo_entrada.py                 # gera entrada/modelo_entrada.xlsx
python src/validar_entrada.py entrada/arquivo.xlsx # só valida, não grava; mostra erros e alertas
python src/importar_entrada.py                     # valida e grava entrada/entrada_itr.xlsx
pytest testes/test_entrada.py                      # testes desta etapa
```
