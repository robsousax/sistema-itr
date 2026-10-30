# Etapa 9 — Central de qualidade

```bash
python src/qualidade.py          # roda as 20 verificações do ITR do 3T26; código de saída 1 se bloqueado
python src/qualidade.py 2T26
pytest testes/test_qualidade.py
```

A Central reúne num só lugar as verificações construídas nas etapas 2 a 8 e decide se o ITR pode
ser publicado. Os exportadores da Etapa 10 chamam `exigir_liberacao()` antes de gerar o Excel e o
PDF: com qualquer erro, a geração é interrompida.

## As 20 verificações

| Código | Nível | Verificação | Se falhar |
| --- | --- | --- | --- |
| N1.01 | Integridade | Configuração contábil completa (contas, linhas, eventos) | Erro |
| N1.02 | Integridade | Cada lançamento tem débitos = créditos | Erro |
| N1.03 | Integridade | Balancete de abertura fecha | Erro |
| N1.04 | Integridade | Origem dos dados registrada (arquivo e SHA-256) | Erro |
| N2.01 | Coerência | Alertas registrados na importação | Alerta |
| N2.02 | Coerência | Exercícios encerrados: resultado zerado e lucro todo destinado | Erro |
| N2.03 | Coerência | Saldos contrários à natureza no fim do trimestre | Alerta |
| N3.01–02 | Conciliação | Ativo = Passivo + PL nas duas datas do BP | Erro |
| N3.03 | Conciliação | Lucros acumulados do BP = lucro acumulado da DRE | Erro |
| N3.04 | Conciliação | DRE acumulada = soma dos trimestres | Erro |
| N3.05–06 | Conciliação | DFC: indireto = direto e saldo final = caixa do BP (atual e anterior) | Erro |
| N3.07–08 | Conciliação | DMPL = PL do BP, coluna por coluna (atual e anterior) | Erro |
| N3.09–10 | Conciliação | DVA: valor a distribuir = distribuição (atual e anterior) | Erro |
| N3.11 | Conciliação | Notas explicativas = demonstrações (21 conferências) | Erro |
| N3.12 | Conciliação | EBITDA pelos dois caminhos (Res. CVM 156) | Erro |
| N3.13 | Conciliação | Depreciação do EBITDA = ajuste de depreciação da DFC | Erro |

**Erro × alerta.** Erro é algo que deixa a demonstração errada, e bloqueia. Alerta é algo que pode
ser legítimo, como cliente com saldo credor por adiantamento, mas precisa de um olhar humano. O alerta
fica registrado e não bloqueia.

## Registro de cada execução

Cada execução recebe um `run_id` (data, hora e um sufixo aleatório) e grava duas tabelas na base:

| Tabela | Conteúdo |
| --- | --- |
| `execucao_qualidade` | run_id, data e hora, trimestre, arquivo e SHA-256 da entrada, contagens e situação (liberada ou bloqueada) |
| `log_qualidade` | Uma linha por verificação: código, nível, descrição, status, valor esperado, valor encontrado e detalhe |

Assim, para qualquer relatório publicado, dá para responder: de qual arquivo vieram os números
(SHA-256), quando foi conferido e quais verificações passaram. É a mesma lógica de trilha de auditoria
de um sistema de fechamento real.

## Testes com erros plantados

A Orbe passa nas 20 verificações. Cada teste estraga uma cópia da base ou da configuração, do jeito
que um erro real aconteceria:

| Erro plantado | O que a Central faz |
| --- | --- |
| Valor de um lançamento alterado direto no banco, sem passar pelo validador | Erro em N1.02 e N3.01; publicação bloqueada; `exigir_liberacao` interrompe |
| Registro de origem apagado | Erro em N1.04 |
| Encerramento de 2025 apagado | Erro em N2.02: a DRE de 2026 ficaria contaminada pelo lucro de 2025 |
| Conta sem mapeamento | Erro em N1.01 |
| Baixa de incobrável classificada como capital de giro | Erro em N3.05: o indireto deixa de bater com o direto |
| Alerta na importação | Alerta em N2.01; a publicação continua liberada |

O bloqueio também fica registrado no log, com o valor esperado e o encontrado.
