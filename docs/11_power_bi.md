# Etapa 11 — Painel no Power BI

```bash
python src/exportar_parquet.py          # gera os 9 arquivos Parquet em exportacao/
pytest testes/test_exportar_parquet.py
```

Depois, o painel é montado no Power BI Desktop seguindo o roteiro abaixo e salvo como
`powerbi/painel_itr.pbix`. Arquivos de apoio:

- `powerbi/consultas_power_query.pq`: as consultas M que leem os Parquet;
- `powerbi/medidas.dax`: todas as medidas, comentadas.

## A decisão principal: o Power BI não recalcula a contabilidade

A contabilidade (saldos, DFC indireta, DVA, imposto diferido) já foi calculada e conferida pelo
Python nas etapas 5 a 9. Se o Power BI refizesse tudo em DAX, haveria dois motores que podem
divergir. Por isso o Python exporta o valor de **cada linha de cada demonstração em cada trimestre**,
e o Power BI só agrega e mostra.

A agregação depende da linha:

| Regra (`dim_linha[agregacao]`) | Linhas | Exemplo no período 1T26 a 3T26 |
| --- | --- | --- |
| `soma` | DRE, DRA, DFC, DVA, EBITDA | Receita 9M26 = 1T26 + 2T26 + 3T26 |
| `ultimo` | BP e saldo final de caixa da DFC | Caixa no 9M26 = caixa em 30/09/2026 |
| `primeiro` | Saldo inicial de caixa da DFC | Saldo inicial do 9M26 = caixa em 31/12/2025 |

Uma medida que não se soma ao longo do tempo, como um saldo de balanço, é chamada de
**semiaditiva**: ela se soma entre contas, mas não entre datas. A medida `Valor DF` aplica a regra de
cada linha. Os testes conferem, linha por linha, que essa regra reproduz o 9M26 do ITR.

Os indicadores (liquidez, prazos médios, ROE) também chegam prontos, em `fato_indicador`. O EBITDA é
a exceção, de propósito: ele é calculado em DAX e conferido contra o valor do sistema.

## O modelo estrela

```
                      dim_calendario (data)
                 ┌──────────┼──────────────┐
                 │          │              │
dim_conta ── fato_lancamento   fato_demonstracao ── dim_linha
dim_evento ──┘                     fato_indicador ── dim_indicador

fato_qualidade (sem relação: mostra a execução da Central que liberou a exportação)
```

| Tabela | Grão (uma linha por...) | Linhas |
| --- | --- | --- |
| `dim_calendario` | dia, de 01/01/2024 a 31/12/2026 (anos completos) | 1.096 |
| `dim_conta` | conta do plano de contas | 165 |
| `dim_evento` | evento contábil, mais "ABERTURA" | 60 |
| `dim_linha` | linha das demonstrações (BP, DRE, DRA, DFC, DVA, EBITDA) | 148 |
| `dim_indicador` | indicador da Etapa 8 | 21 |
| `fato_lancamento` | partida do razão; a abertura entra como movimento de 31/12/2024 | ~3.000 |
| `fato_demonstracao` | linha × trimestre, com valor em reais | ~1.100 |
| `fato_indicador` | indicador × trimestre | 147 |
| `fato_qualidade` | verificação da Central | 20 |

A DMPL fica fora do painel: ela é uma matriz (contas do PL nas colunas) que não cabe no formato
linha × trimestre. A evolução do PL aparece pelo BP.

## Roteiro de montagem (Power BI Desktop em português)

### 1. Antes de carregar

**Arquivo > Opções e configurações > Opções > Arquivo atual > Carregamento de Dados**: desmarque
**"Detectar automaticamente novos relacionamentos após o carregamento dos dados"**. Várias tabelas
têm colunas com o mesmo nome (`codigo`, `demonstracao`), e o Power BI criaria relações erradas.

### 2. Carregar os dados

1. **Página Inicial > Transformar dados** abre o Power Query.
2. **Gerenciar Parâmetros > Novo Parâmetro**. Nome `PastaExportacao`, tipo Texto, valor atual
   `C:\Portifolio\sistema-itr\exportacao\` (com a barra no final).
3. Para cada uma das 9 tabelas: **Nova Fonte > Consulta Nula**, depois **Editor Avançado**. Cole o
   bloco correspondente de `powerbi/consultas_power_query.pq` e renomeie a consulta com o nome exato
   (`dim_calendario`, `dim_conta`...).
4. **Fechar e Aplicar**.

Com o parâmetro, se a pasta mudar, basta trocar um valor.

### 3. Preparar o modelo

Na **Exibição de modelo**:

1. **Marcar como tabela de datas**: selecione `dim_calendario`, **Ferramentas de tabela > Marcar como
   tabela de datas**, coluna `data`. As funções de tempo (`SAMEPERIODLASTYEAR`, `DATESINPERIOD`)
   dependem disso.
2. **Relações** (**Página Inicial > Gerenciar relações > Novo**). Todas de 1 para muitos, com a
   direção de filtro única:

| De (lado 1) | Para (lado muitos) |
| --- | --- |
| `dim_calendario[data]` | `fato_lancamento[data]` |
| `dim_calendario[data]` | `fato_demonstracao[data]` |
| `dim_calendario[data]` | `fato_indicador[data]` |
| `dim_conta[codigo]` | `fato_lancamento[conta]` |
| `dim_evento[codigo]` | `fato_lancamento[evento]` |
| `dim_linha[chave]` | `fato_demonstracao[chave_linha]` |
| `dim_indicador[codigo]` | `fato_indicador[codigo]` |

3. **Classificar por coluna** (selecione a coluna, **Ferramentas de coluna > Classificar por coluna**):
   - `dim_linha[rotulo]` por `dim_linha[ordem]`, para a matriz seguir a ordem da CVM;
   - `dim_calendario[trimestre]` por `dim_calendario[trimestre_ordem]`, senão o 1T26 vem antes do 2T25;
   - `dim_indicador[nome]` por `dim_indicador[ordem]`.
4. **Ocultar** as colunas de chave dos fatos (`data`, `conta`, `evento`, `chave_linha`, `codigo`). Os
   filtros devem vir das dimensões.
5. **Tabela de medidas**: **Página Inicial > Inserir dados**, tabela `_Medidas` com uma coluna
   qualquer. Crie as medidas de `powerbi/medidas.dax` nela (**Nova medida**, cole a fórmula) e depois
   oculte a coluna. Formatos: R$ com `#,##0`, margens e variações em porcentagem com uma casa.

Se uma fórmula der erro de sintaxe com a vírgula, veja **Opções > Configurações regionais**: o padrão
do Desktop é o separador do DAX em inglês (vírgula entre argumentos).

### 4. As quatro páginas

Use **Exibição > Temas** com cores sóbrias (o tema "Executivo" funciona) e um título em cada página.

**Página 1 — Visão geral**
- Segmentação de dados: `dim_calendario[trimestre]`, seleção única, com filtro `periodo_itr = Sim`.
- Seis cartões: `Receita Líquida`, `Var. Receita a/a`, `Margem EBITDA`, `Lucro Líquido`,
  `Caixa e Equivalentes`, `Dívida Líquida` (R$ em milhares: **Formatar > Valor do balão > Unidades
  de exibição: Milhares**).
- Gráfico de colunas: eixo `dim_calendario[trimestre]`, valores `Receita Líquida` e `EBITDA`.
- Gráfico de linhas: `Margem Bruta`, `Margem EBITDA`, `Margem Líquida` por trimestre.
- Nos dois gráficos: **Formatar > Editar interações** e desligue o filtro da segmentação. Os
  gráficos mostram a série toda e os cartões, o trimestre escolhido.

**Página 2 — Demonstrações**
- Segmentação `dim_linha[demonstracao_nome]`, seleção única.
- Segmentação `dim_calendario[trimestre]`, seleção múltipla, com filtro `periodo_itr = Sim`.
- Matriz: linhas `dim_linha[rotulo]`, colunas `dim_calendario[trimestre]`, valores
  `Valor DF (R$ mil)`. Desligue os subtotais de linha e ligue os de coluna, com rótulo "Período".
- Formatação condicional > Cor da tela de fundo > Valor do campo > `Cor da Linha`.

O teste da página: selecione 1T26, 2T26 e 3T26 e escolha "Fluxos de Caixa". A coluna "Período" tem
que mostrar o 9M26 do ITR, com o saldo inicial de 31/12/2025 e o saldo final de 30/09/2026. É a
medida semiaditiva funcionando.

**Página 3 — Indicadores e capital de giro**
- Matriz: linhas `dim_indicador[grupo]` e `dim_indicador[nome]`, colunas `dim_calendario[trimestre]`,
  valores `Indicador (texto)`.
- Gráfico de linhas: `PMR (dias)`, `PME (dias)`, `PMP (dias)` e `Ciclo Financeiro (dias)` por trimestre.

**Página 4 — Qualidade e conferências**
- Cartões: `Situação da Publicação`, `Verificações Aprovadas`, `Alertas`, `Erros`.
- Cartão de várias linhas com as conferências: `Conferência EBITDA`, `Conferência Caixa`,
  `Conferência Dívida Líquida`, `Conferência Balanço`. Todas devem mostrar 0 em qualquer trimestre.
- Tabela: `fato_qualidade` com `codigo`, `nivel_nome`, `descricao`, `status` e formatação condicional
  na cor do `status`.

### 5. Salvar e atualizar

Salve como `powerbi/painel_itr.pbix`. Quando os dados mudarem:

```bash
python src/importar_entrada.py
python src/exportar_parquet.py
```

e, no Power BI, **Página Inicial > Atualizar**.

## Problemas comuns

| Sintoma | Causa e solução |
| --- | --- |
| Total da matriz soma Ativo com Receita | A matriz está usando `Fluxo` em vez de `Valor DF` |
| Coluna "Período" do BP mostra a soma dos trimestres | Mesma causa: o BP precisa do `Saldo Final` |
| Trimestres fora de ordem (1T26 antes de 2T25) | Falta classificar `trimestre` por `trimestre_ordem` |
| `Var. Receita a/a` em branco no 1T25 | Correto: não há 1T24 na base |
| `Receita Líquida UDM` em branco até o 3T25 | Correto: são necessários 4 trimestres de história |
| Relação ambígua ou medida com número estranho | Confira se a detecção automática criou relações extras |
| `exportar_parquet.py` diz "Publicação bloqueada" | A Central achou um erro: `python src/qualidade.py` |

## Testes (`testes/test_exportar_parquet.py`, 24 testes)

- **A regra semiaditiva reproduz o ITR:** somar 1T26 a 3T26 com soma, último e primeiro dá
  exatamente o 9M26 de DRE, DRA, DFC e DVA, e o BP de 30/09/2026, em centavos.
- O saldo inicial de caixa do 9M26 é o de 31/12/2025.
- Toda chave dos fatos existe na dimensão, e a chave da dimensão é única (relação 1 para muitos).
- Calendário contínuo, em anos completos. Rótulo e ordem das linhas únicos.
- O razão exportado fecha (débitos = créditos).
- As conferências do painel: EBITDA pela fórmula do DAX = EBITDA do sistema; caixa pelo razão = caixa
  do BP; dívida líquida pelo BP = indicador; indicadores iguais aos da Etapa 8.
- Com erro na Central, nada é exportado.

Testes de mutação: trocar a regra do saldo inicial de caixa para `ultimo`, ou a do BP para `soma`,
faz 3 testes falharem.

## Limitações

- O `.pbix` é montado à mão no Power BI Desktop. Os testes conferem os dados e simulam a regra das
  medidas em Python, mas não abrem o Power BI. Por isso a página 4 tem as conferências, que mostram na
  tela se alguma medida saiu errada.
- O Power BI só funciona no Windows. A versão web (Etapa 12) mostra os mesmos números para quem não
  tem o Power BI.
