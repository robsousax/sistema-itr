# Sistema ITR — Simulador Acadêmico de Demonstrações Financeiras Intermediárias

Projeto de portfólio em contabilidade societária e controladoria. O sistema recebe os dados
contábeis de uma companhia aberta **fictícia**, a **Orbe Suprimentos S.A.**, e gera:

- o ITR em Excel (uma aba por demonstração);
- o ITR em PDF (DFs, notas explicativas e comentário de desempenho);
- um painel de indicadores (Power BI e versão web em Streamlit).

> **Aviso:** este é um projeto acadêmico. A estrutura é inspirada no formulário ITR da CVM, mas
> nada aqui é um ITR real: o ITR oficial é enviado pelo Empresas.NET e passa por revisão de
> auditor independente. Empresa, números e eventos são fictícios.

## Como o sistema funciona

```
Entrada (Excel)  →  Validação (integridade e coerência)  →  Base SQLite
                 →  Motor contábil (BP, DRE, DRA, DFC, DMPL, DVA, notas, indicadores)
                 →  Conciliação entre demonstrações  →  Excel · PDF · Power BI · Web
```

Nada é publicado se uma checagem de erro falhar.

## Situação do projeto

| Etapa | Entrega | Situação |
| --- | --- | --- |
| 0 | Ambiente e Git | Concluída: `docs/00_guia_instalacao_windows.md` |
| 1 | Empresa e políticas contábeis | Concluída: `docs/01_empresa_e_politicas.md`, `config/empresa.yaml` |
| 2 | Plano de contas e mapeamentos | Concluída: `config/*.csv`, `docs/02_plano_de_contas_e_regras.md` |
| 3 | Contrato de entrada e SQLite | Concluída e revisada: `entrada/modelo_entrada.xlsx`, `docs/03_contrato_de_entrada.md` |
| 4 | Gerador de eventos | Concluída: `config/roteiro.yaml`, `entrada/entrada_itr.xlsx`, `docs/04_gerador_de_dados.md` |
| 5 | BP e DRE | Concluída: `src/demonstracoes.py`, `docs/05_bp_e_dre.md` |
| 6 | DFC e DMPL | Concluída: `src/dfc_dmpl.py`, `docs/06_dfc_e_dmpl.md` |
| 7 | DRA, DVA e notas | Concluída: `src/dra_dva.py`, `src/notas.py`, `docs/07_dra_dva_e_notas.md` |
| 8 | Indicadores | Concluída: `src/indicadores.py`, `docs/08_indicadores.md` |
| 9 | Central de qualidade | Concluída: `src/qualidade.py`, `docs/09_central_de_qualidade.md` |
| 10 | Excel e PDF | Próxima |
| 11 | Power BI | — |
| 12 | Web e vitrine | — |

## Estrutura de pastas

```
sistema-itr/
├── entrada/      template de entrada e quadros auxiliares (etapa 3)
├── config/       empresa, plano de contas e mapeamentos (fonte da verdade: arquivos .csv)
├── base/         itr.sqlite (gerado, não vai para o Git)
├── src/          código Python
├── modelos/      modelo HTML/CSS do PDF
├── saidas/       ITRs gerados
├── exportacao/   arquivos Parquet para o Power BI
├── powerbi/      painel .pbix
├── testes/       testes automáticos (pytest)
└── docs/         decisões, regras contábeis, dicionário de dados, limitações
```

## Comandos úteis

```bash
python src/checar_config.py        # confere se toda conta e todo evento têm classificação
python src/config_para_excel.py    # gera config/plano_de_contas_e_mapeamentos.xlsx para consulta
python src/gerar_modelo_entrada.py # gera entrada/modelo_entrada.xlsx (Excel de entrada em branco)
python src/gerar_dados.py          # gera entrada/entrada_itr.xlsx com a contabilidade da Orbe (roteiro)
python src/importar_entrada.py     # valida entrada/entrada_itr.xlsx e grava base/itr.sqlite
python src/demonstracoes.py        # mostra o BP e a DRE do 3T26 em R$ mil (ou: ... 2T26)
python src/dfc_dmpl.py             # mostra a DFC e a DMPL do 3T26, com as conferências
python src/dra_dva.py              # mostra a DRA e a DVA do 3T26
python src/notas.py                # mostra as 10 notas explicativas e confere com as demonstrações
python src/indicadores.py          # indicadores trimestrais e reconciliação do EBITDA (Res. CVM 156)
python src/qualidade.py            # Central de qualidade: 20 verificações; libera ou bloqueia a publicação
pytest                             # roda todos os testes
```

## Documentação

- `docs/00_guia_instalacao_windows.md`: preparar o computador
- `docs/01_empresa_e_politicas.md`: a empresa, as políticas contábeis e as limitações
- `docs/02_plano_de_contas_e_regras.md`: plano de contas e como cada demonstração é montada
- `docs/03_contrato_de_entrada.md`: formato do Excel de entrada, validações e tabelas da base
- `docs/04_gerador_de_dados.md`: como o roteiro vira lançamentos, a história da Orbe e as simplificações
- `docs/05_bp_e_dre.md`: como o motor monta o BP e a DRE, períodos do CPC 21 e lucro por ação
- `docs/06_dfc_e_dmpl.md`: DFC indireta conferida pelo método direto, transações sem caixa e DMPL por coluna
- `docs/07_dra_dva_e_notas.md`: DRA, DVA com o ajuste do CPC 09 e as 10 notas explicativas
- `docs/08_indicadores.md`: fórmulas dos indicadores, convenções e EBITDA
- `docs/09_central_de_qualidade.md`: as 20 verificações, erro × alerta e o registro de cada execução
