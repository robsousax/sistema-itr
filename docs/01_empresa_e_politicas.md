# Etapa 1 — A empresa e as políticas contábeis

> Equivale à **Nota 1 (Contexto operacional)** e à **Nota 2 (Base de preparação e políticas
> contábeis)** do ITR. Os parâmetros numéricos ficam em `config/empresa.yaml`.

## 1. Contexto operacional

A **Orbe Suprimentos S.A.** ("Orbe" ou "Companhia") é uma sociedade anônima de capital aberto
**fictícia**, com sede em Duque de Caxias (RJ). Distribui no atacado, para empresas (B2B),
suprimentos empresariais: material de escritório, produtos de limpeza e higiene, equipamentos de
proteção individual (EPI) e suprimentos de informática.

- Opera a partir de um centro de distribuição próprio (terreno e edificação).
- Entrega com frota própria de veículos e, nos picos, com transportadoras contratadas.
- Não tem controladas, coligadas nem operações no exterior. Apresenta apenas demonstrações
  individuais.
- Tem um único segmento operacional (distribuição), por isso não divulga informação por segmento.
- Capital social de R$ 30.000 mil, dividido em 30.000.000 de ações ordinárias.

## 2. Base de preparação

- As informações intermediárias seguem o **CPC 21 (R1) — Demonstração Intermediária** e a
  estrutura do formulário ITR da CVM.
- Base de mensuração: custo histórico.
- Moeda funcional e de apresentação: real (R$). Valores apresentados em **R$ mil**.
- Períodos do ITR do 3T26, conforme o item 20 do CPC 21:

| Demonstração | Período atual | Comparativo |
| --- | --- | --- |
| Balanço Patrimonial | 30/09/2026 | 31/12/2025 |
| DRE e DRA | 3T26 (jul–set) e 9M26 (jan–set) | 3T25 e 9M25 |
| DFC, DMPL e DVA | 9M26 | 9M25 |

- Saldos de abertura do histórico: 31/12/2024.

## 3. Políticas contábeis

### 3.1 Caixa e equivalentes de caixa (CPC 03)
Saldos em caixa, contas bancárias de movimento e aplicações em CDB com liquidez diária, sem
risco relevante de mudança de valor. Os rendimentos são reconhecidos em receita financeira pela
competência.

### 3.2 Receita (CPC 47)
- **Contrato:** pedido do cliente aceito, com preço e condições definidos.
- **Obrigação de desempenho:** única, a entrega das mercadorias.
- **Reconhecimento:** em um ponto no tempo, na entrega, quando o controle passa ao cliente.
- **Preço:** líquido de descontos comerciais concedidos na nota fiscal e dos tributos sobre a
  venda (ICMS, PIS e COFINS).
- **Componente de financiamento:** prazo médio de 45 dias. Como é inferior a 12 meses, a
  Companhia usa o expediente prático e não ajusta a receita a valor presente.
- **Adiantamentos de clientes:** registrados como passivo de contrato até a entrega.
- **Devoluções:** historicamente inferiores a 1% da receita. Reconhecidas quando ocorrem
  (julgamento de materialidade: ver Limitações).

### 3.3 Contas a receber e perda esperada (CPC 48)
Contas a receber são ativos financeiros ao custo amortizado. A perda esperada segue a
**abordagem simplificada**, por matriz de provisão sobre a idade do saldo:

| Faixa | Perda esperada |
| --- | --- |
| A vencer | 0,5% |
| Vencidos de 1 a 30 dias | 2% |
| Vencidos de 31 a 90 dias | 10% |
| Vencidos de 91 a 180 dias | 40% |
| Vencidos há mais de 180 dias | 100% |

Créditos considerados incobráveis são baixados contra a provisão. A despesa aparece em linha
própria da DRE ("Perdas pela não recuperabilidade de ativos"), como exige o CPC 26.

### 3.4 Estoques (CPC 16)
- Mensurados pelo menor valor entre custo e valor realizável líquido.
- **Custo médio ponderado móvel.** O custo inclui o preço de compra e o frete de compra, líquidos
  dos tributos recuperáveis (ICMS, PIS e COFINS).
- Perdas por obsolescência, avaria e validade vencida são provisionadas e registradas no custo
  das mercadorias vendidas.

### 3.5 Imobilizado (CPC 27)
Custo de aquisição menos depreciação acumulada. Depreciação linear, sem valor residual. Terrenos
não são depreciados.

| Classe | Vida útil |
| --- | --- |
| Edificações (centro de distribuição) | 25 anos |
| Máquinas e equipamentos (empilhadeiras, porta-paletes, estantes) | 10 anos |
| Veículos | 5 anos |
| Móveis e utensílios | 10 anos |
| Equipamentos de informática | 5 anos |

Ganhos e perdas na venda de bens vão para outras receitas ou despesas operacionais. Compras
financiadas diretamente pelo fornecedor ou pelo banco (FINAME) não passam pelo caixa. Por isso
não entram na DFC e são divulgadas como transação que não afeta caixa (CPC 03, item 43).

### 3.6 Intangível (CPC 04)
Licenças de software de uso perpétuo, amortizadas em 5 anos. Assinaturas de software (SaaS) vão
direto para a despesa.

### 3.7 Arrendamentos (CPC 06)
A Companhia não tem arrendamentos no escopo do CPC 06 na V1. O único aluguel é de um showroom
com contrato de até 12 meses, tratado pela isenção de curto prazo (despesa linear).

### 3.8 Fornecedores e empréstimos (CPC 48)
- Fornecedores: custo amortizado. Prazo médio de 60 dias, sem ajuste a valor presente por
  materialidade.
- Empréstimos e financiamentos: custo amortizado, com juros apropriados pela competência. A parcela
  que vence em até 12 meses fica no passivo circulante.
- Linhas da V1: **FINAME** (financia máquinas e veículos) e **capital de giro (CCB)**.

### 3.9 Benefícios a empregados (CPC 33)
Salários, encargos, férias, 13º salário e participação nos lucros (PLR) reconhecidos pela
competência. Não há planos de benefício pós-emprego.

### 3.10 Provisões e contingências (CPC 25)
Na V1, a Companhia não tem processos com perda provável ou possível de valor relevante. A nota de
provisões entra quando o roteiro da empresa criar um evento desse tipo.

### 3.11 Tributos sobre o lucro (CPC 32)
- **Lucro Real trimestral.** IRPJ de 15%, mais adicional de 10% sobre o lucro tributável que passar
  de R$ 60 mil no trimestre. CSLL de 9%.
- **Tributos diferidos:** reconhecidos sobre as diferenças temporárias. As principais são a
  perda esperada com créditos (dedutível só quando atende ao art. 9 da Lei 9.430/96) e a provisão
  para perdas em estoques (indedutível até a baixa efetiva).
- O ativo diferido é reconhecido porque há lucro tributável futuro provável.
- **Alíquota do diferido: 34%** (IRPJ 15% + adicional 10% + CSLL 9%). O diferido é mensurado
  pela alíquota esperada quando a diferença reverter (CPC 32, item 47). Como a Orbe tem lucro
  tributável acima do limite do adicional de IRPJ (R$ 60 mil por trimestre), as reversões
  também sofrem o adicional. O IRPJ diferido usa 25% e a CSLL diferida usa 9%. Parâmetro:
  `tributacao.aliquota_diferido` em `config/empresa.yaml`.
- Depreciação contábil e fiscal são iguais (sem diferença temporária).

### 3.12 Tributos sobre vendas e compras
- **PIS e COFINS não cumulativos** (1,65% e 7,6%), com créditos só sobre mercadorias para revenda.
- **ICMS** com alíquota única simplificada de 18% nas vendas e nas compras.
- Os créditos sobre compras são registrados em tributos a recuperar e compensados na apuração
  mensal.

### 3.13 Patrimônio líquido e dividendos (Lei 6.404/76)
- Reserva legal: 5% do lucro líquido, até 20% do capital social.
- **Dividendo mínimo obrigatório: 25%** do lucro líquido ajustado, reconhecido como passivo no
  encerramento do exercício.
- Dividendo acima do mínimo fica no PL como "dividendo adicional proposto" até a assembleia
  aprovar.
- O saldo restante vai para a reserva de retenção de lucros, com base em orçamento de capital.
- Durante o exercício, o lucro do período fica em **lucros acumulados**. As destinações só ocorrem
  em 31/12.

### 3.14 Lucro por ação (CPC 41)
Lucro líquido dividido pela média ponderada de ações ordinárias em circulação. Sem instrumentos
diluidores, portanto o LPA diluído é igual ao básico.

### 3.15 Demonstração dos fluxos de caixa (CPC 03)
**Método indireto.** As escolhas que o CPC 03 permite foram feitas assim:

| Item | Classificação |
| --- | --- |
| Juros recebidos (aplicações e clientes) | Atividades operacionais |
| Juros pagos sobre empréstimos | Atividades de financiamento |
| Dividendos pagos | Atividades de financiamento |
| IR e CSLL pagos | Atividades operacionais |

### 3.16 Demonstração do valor adicionado (CPC 09)
- Receitas pelo valor bruto, com os tributos sobre vendas.
- Insumos adquiridos de terceiros incluem os tributos recuperáveis (ICMS, PIS e COFINS), como pede o
  CPC 09. Os tributos distribuídos ao governo ficam pelo valor líquido (débitos menos créditos).
- INSS patronal é distribuído como tributo federal; FGTS como pessoal.

## 4. Limitações e simplificações da V1

Itens deixados de fora conscientemente. Em uma empresa real, cada um exigiria tratamento próprio.

| Simplificação | Efeito na vida real |
| --- | --- |
| ICMS com alíquota única de 18% | Na prática há alíquotas internas e interestaduais, FECP no RJ, substituição tributária e DIFAL |
| Fase de teste da CBS e do IBS em 2026 não modelada | Alíquotas simbólicas, sem efeito de caixa para quem cumpre as obrigações acessórias |
| Devoluções reconhecidas quando ocorrem | O CPC 47 pede estimar devoluções e registrar passivo de reembolso quando material |
| Sem ajuste a valor presente de clientes e fornecedores | Justificado pelo prazo curto e pela materialidade |
| Sem arrendamentos no escopo do CPC 06 | Centros de distribuição alugados gerariam direito de uso e passivo de arrendamento |
| Sem juros sobre capital próprio | Seria um planejamento tributário comum em companhia lucrativa |
| Sem contingências | Empresas reais quase sempre têm processos trabalhistas e fiscais |
| Depreciação fiscal igual à contábil | Diferenças de taxa gerariam passivo fiscal diferido |
| Sem controladas, segmentos ou moeda estrangeira | Exigiriam consolidação, CPC 22 e CPC 02 |
