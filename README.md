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
| 3 | Contrato de entrada e SQLite | Concluída: `entrada/modelo_entrada.xlsx`, `docs/03_contrato_de_entrada.md` |
| 4 | Gerador de eventos | Próxima |
| 5 | BP e DRE | — |
| 6 | DFC e DMPL | — |
| 7 | DRA, DVA e notas | — |
| 8 | Indicadores | — |
| 9 | Central de qualidade | — |
| 10 | Excel e PDF | — |
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
python src/importar_entrada.py     # valida entrada/entrada_itr.xlsx e grava base/itr.sqlite
pytest                             # roda todos os testes
```

## Documentação

- `docs/00_guia_instalacao_windows.md`: preparar o computador
- `docs/01_empresa_e_politicas.md`: a empresa, as políticas contábeis e as limitações
- `docs/02_plano_de_contas_e_regras.md`: plano de contas e como cada demonstração é montada
- `docs/03_contrato_de_entrada.md`: formato do Excel de entrada, validações e tabelas da base
