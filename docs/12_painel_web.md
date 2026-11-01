# Etapa 12 — Painel web (Streamlit)

```bash
streamlit run app/painel.py      # abre o painel em http://localhost:8501
pytest testes/test_painel.py
```

O painel web mostra os mesmos números do Power BI para quem não tem o Power BI instalado: um
recrutador, um professor, alguém no celular. Ele lê os mesmos arquivos Parquet e aplica as mesmas
regras das medidas DAX.

## Como está organizado

| Arquivo | Papel |
| --- | --- |
| `src/painel_dados.py` | Toda a lógica: carregar os Parquet, a regra semiaditiva, destaques, matriz, indicadores e conferências. Não depende do Streamlit, por isso é testável |
| `app/painel.py` | Só a tela: menu lateral, filtros, cartões, gráficos (Altair), tabelas e o CSS do visual |
| `.streamlit/config.toml` | Cores do tema (azul royal, branco e vermelho tomate) para os controles nativos do Streamlit |
| `exemplos/exportacao/` | Cópia da exportação que vai para o GitHub. O app publicado na web lê daqui |

O app procura os dados primeiro em `exportacao/` (gerada por `python src/exportar_parquet.py`, fora do
Git) e, se não achar, em `exemplos/exportacao/`. Assim, na sua máquina ele mostra a base atual e, na
web, mostra a cópia publicada.

## As páginas

O menu lateral tem oito páginas. Cada uma tem um filtro no alto: um trimestre (posição do balanço) ou um
período de trimestres (fluxos como DRE e DFC, somados pela regra semiaditiva).

| Página | O que mostra |
| --- | --- |
| Visão geral | Cartão de destaque com a receita e as margens, composição do ativo, EBITDA, lucro, caixa líquido, receita por trimestre, cascata da receita ao lucro, liquidez, ciclo financeiro e ROE |
| Resultado | Receita, resultado bruto, EBITDA e lucro do período; cascata da DRE; margens por trimestre; para onde vai cada real de receita |
| Balanço | Ativo, PL e liquidez; composição do ativo; estrutura de capital (PC, PNC, PL); caixa, dívida bruta e PL por trimestre |
| Fluxo de caixa | Caixa das operações, investimentos e financiamentos; ponte do saldo inicial ao final; distribuição do valor adicionado (DVA); caixa por atividade em cada trimestre |
| Capital de giro | PMR, PME, PMP e ciclo financeiro com a variação sobre o trimestre anterior; evolução dos prazos; como o ciclo se forma |
| Demonstrações | Qualquer demonstração, linha a linha, com a coluna Período |
| Central de qualidade | Situação da publicação, as quatro conferências do painel e as 20 verificações |
| Baixar o ITR | O PDF e o Excel do 3T26 |

O visual (azul royal #20309A, branco e vermelho tomate #B8232B; menu escuro e cartões arredondados) está no CSS no começo de `app/painel.py`. Os
gráficos são feitos com Altair e todos os números vêm de `src/painel_dados.py`.

## Publicar na web (Streamlit Community Cloud, gratuito)

1. Confirme que o último commit está no GitHub, com `exemplos/exportacao/`.
2. Entre em **share.streamlit.io** com a conta do GitHub e clique em **Create app**.
3. Escolha **Deploy a public app from GitHub** e preencha:
   - Repository: `robsousax/sistema-itr`
   - Branch: `main`
   - Main file path: `app/painel.py`
   - App URL: `sistema-itr` (se estiver ocupado, escolha outro e corrija o link no README)
4. Em **Advanced settings**, escolha Python 3.12.
5. **Deploy**. A primeira instalação leva alguns minutos.

O plano gratuito põe o app para dormir depois de alguns dias sem acesso. Quem abrir o link nessa
situação vê um botão para acordá-lo, e ele volta em menos de um minuto.

## Manter o exemplo atualizado

Se a contabilidade mudar (roteiro, plano de contas, regras), atualize a cópia publicada:

```powershell
python src/importar_entrada.py
python src/exportar_parquet.py
Copy-Item exportacao\*.parquet exemplos\exportacao\
python src/gerar_itr.py
Copy-Item saidas\3T26\ITR_Orbe_3T26.pdf, saidas\3T26\ITR_Orbe_3T26.xlsx exemplos\
```

O teste `test_exemplo_publicado_esta_atualizado` falha se a cópia ficar diferente do motor.

## Testes (`testes/test_painel.py`, 22 testes)

- Os destaques do 3T26 são os números da DRE e do BP do motor.
- A coluna Período reproduz o 9M26 de DRE e DFC; no BP ela é o saldo do último trimestre.
- As quatro conferências dão zero em todos os trimestres e acusam diferença quando um número muda.
- A formatação dos indicadores segue o padrão brasileiro (29,7%; 2,19x; -13.086).
- A cópia em `exemplos/exportacao/` está igual ao motor.
- A cascata do resultado termina no lucro líquido, a ponte de caixa termina no saldo final e as composições somam 100%.
- O app Streamlit abre as oito páginas sem erro (`streamlit.testing`).

Teste de mutação: fazer o saldo inicial de caixa pegar o último trimestre derruba o teste da DFC.

## Limitações

- O painel é só de leitura: ele não importa dados nem roda a Central. Isso fica no Python local.
- A cópia publicada é do 3T26. Outros trimestres exigem rodar o sistema localmente.
