# Etapa 10 — ITR em Excel e PDF

```bash
pip install -r requirements.txt
python -m playwright install chromium   # uma vez só: baixa o navegador que imprime o PDF
python src/gerar_itr.py                 # ITR do 3T26 em saidas/3T26/
python src/gerar_itr.py 2T26
pytest testes/test_exportacao.py
```

O comando gera três arquivos com o mesmo conteúdo:

| Arquivo | Para quê |
| --- | --- |
| `ITR_Orbe_3T26.xlsx` | Conferir e reaproveitar os números. Valores gravados em reais, exibidos em R$ mil |
| `ITR_Orbe_3T26.pdf` | Ler e enviar. A4, 19 páginas, com número de página |
| `ITR_Orbe_3T26.html` | O mesmo do PDF, para abrir no navegador |

A pasta `saidas/` não vai para o Git, porque é recriada a cada execução. Uma cópia do 3T26 fica em
`exemplos/`, para quem quiser ver o resultado sem instalar nada.

## A ordem de geração

```
coletar()  →  Central de qualidade (20 verificações)  →  com erro: para, nenhum arquivo é criado
           →  BP, DRE, DRA, DFC, DMPL, DVA, notas, indicadores, comentário
           →  exportar_excel()  e  exportar_pdf()
```

`src/relatorio.py` junta tudo num objeto só (`Relatorio`). Os dois exportadores só formatam: nenhum
deles calcula número. Assim o Excel e o PDF não têm como divergir entre si nem do motor.

## O Excel

Uma aba por peça: Capa (com índice clicável), Comentário, BP Ativo, BP Passivo, DRE, DRA, DFC,
DMPL 9M26, DMPL 9M25, DVA, Notas, Indicadores, EBITDA e Central de qualidade.

- **Valor exato, exibição em mil.** A célula guarda o valor em reais (ex.: 28194312,47) e o formato
  `#,##0,` mostra 28.194. Somar células no Excel dá o mesmo que o sistema, sem erro de arredondamento.
- **Conferências por fórmula, não por valor colado.** No pé de cada demonstração há uma linha que o
  próprio Excel calcula e que deve dar zero:

| Aba | Conferência |
| --- | --- |
| BP Passivo | Ativo total − Passivo total e PL |
| DFC | Saldo final de caixa − Caixa e equivalentes do BP |
| DMPL | PL final da DMPL − PL do BP |
| DVA | Valor adicionado a distribuir − Distribuição |
| EBITDA | EBITDA − (lucro + IR/CSLL + resultado financeiro + depreciação) |

  Se alguém alterar um número à mão, a conferência deixa de dar zero.
- Código CVM da linha na coluna A, como no formulário ITR. Cada aba já sai configurada para imprimir
  em uma página de largura.

## O PDF

O modelo fica em `modelos/itr.html` (estrutura) e `modelos/itr.css` (aparência). O Jinja2 preenche o
modelo e o Chromium, controlado pelo Playwright, imprime em A4. Escolhi esse caminho porque um
layout em HTML/CSS é fácil de ajustar e de revisar no navegador.

Ordem das páginas: capa com os destaques, índice, comentário de desempenho, as 9 demonstrações (BP em
duas páginas, DMPL dos dois períodos), notas explicativas, indicadores com a reconciliação do EBITDA e
a Central de qualidade (com o `run_id` e o SHA-256 do arquivo de origem).

O rodapé da capa traz o resultado da Central: 20 verificações, quantas aprovadas, alertas e erros.

## O comentário de desempenho

`src/comentario.py` escreve o texto por regras fixas, a partir dos números do sistema. Não há texto
livre: cada frase é um modelo com lacunas. Dois cuidados:

- **Só cita causa registrada.** O parágrafo "Fato do trimestre" vem do evento descrito no
  `config/roteiro.yaml`. O sistema não inventa explicação para uma variação.
- **Variação pequena é "estável".** Margem que mudou menos de 0,05 p.p. aparece como estável, para não
  destacar ruído.

Parágrafos: fato do trimestre, receita e margem, resultado operacional (EBITDA), capital de giro
(prazos médios e ciclo de caixa) e caixa e endividamento (DFC e dívida líquida).

## Testes (`testes/test_exportacao.py`, 15 testes)

- O Excel tem as 14 abas, grava o valor em reais e usa o formato em milhares.
- As conferências são fórmulas que apontam para as outras abas.
- As 10 notas e as 20 verificações estão no arquivo; os links do índice apontam para as abas.
- O HTML tem todas as seções; o PDF abre, tem número de página e traz o nome da empresa.
- **Bloqueio:** com um lançamento desbalanceado, `gerar()` levanta `PermissionError` e a pasta de
  saída nem chega a ser criada.
- Arquivo aberto no Excel gera uma mensagem própria ("feche e rode de novo"), diferente do bloqueio.
- O comentário usa a receita e o lucro calculados pelo motor e só cita o fato do roteiro.

Teste de mutação: retirei a chamada `exigir_liberacao()` de `coletar()` e o teste de bloqueio falhou,
como deveria.

## Problemas comuns

| Mensagem | O que fazer |
| --- | --- |
| `O Chromium do Playwright não está instalado` | `python -m playwright install chromium` |
| `Não foi possível gravar ... feche e rode de novo` | O ITR anterior está aberto no Excel ou no leitor de PDF. Feche e rode de novo |
| `Publicação bloqueada pela Central de qualidade` | Nenhum arquivo foi gerado. `python src/qualidade.py` mostra qual verificação falhou |
| `Base não encontrada` | `python src/importar_entrada.py` antes |

## Limitações

- O formulário ITR real é preenchido no Empresas.NET da CVM; aqui o layout é só inspirado nele.
- O comentário de desempenho é um texto por regras. Ele não substitui a análise da administração.
- As notas explicativas são as 10 selecionadas na Etapa 7, não o conjunto completo exigido.
