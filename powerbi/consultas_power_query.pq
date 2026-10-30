// Consultas do Power Query (linguagem M) para carregar a exportação do Sistema ITR.
// Passo a passo em docs/11_power_bi.md.
//
// 1. Crie o parâmetro PastaExportacao (Transformar dados > Gerenciar Parâmetros > Novo):
//      Nome: PastaExportacao   Tipo: Texto   Valor atual: C:\Portifolio\sistema-itr\exportacao\
//    (com a barra invertida no final)
//
// 2. Para cada tabela abaixo: Nova Fonte > Consulta Nula > Editor Avançado, cole o bloco
//    e renomeie a consulta com o nome indicado (exatamente igual).

// ---------- dim_calendario
let
    Fonte = Parquet.Document(File.Contents(PastaExportacao & "dim_calendario.parquet"))
in
    Fonte

// ---------- dim_conta
let
    Fonte = Parquet.Document(File.Contents(PastaExportacao & "dim_conta.parquet"))
in
    Fonte

// ---------- dim_evento
let
    Fonte = Parquet.Document(File.Contents(PastaExportacao & "dim_evento.parquet"))
in
    Fonte

// ---------- dim_linha
let
    Fonte = Parquet.Document(File.Contents(PastaExportacao & "dim_linha.parquet"))
in
    Fonte

// ---------- dim_indicador
let
    Fonte = Parquet.Document(File.Contents(PastaExportacao & "dim_indicador.parquet"))
in
    Fonte

// ---------- fato_lancamento
let
    Fonte = Parquet.Document(File.Contents(PastaExportacao & "fato_lancamento.parquet")),
    // Valores monetários como decimal fixo (4 casas): somas sem erro de ponto flutuante
    Tipos = Table.TransformColumnTypes(Fonte,
        {{"debito", Currency.Type}, {"credito", Currency.Type}, {"movimento", Currency.Type}})
in
    Tipos

// ---------- fato_demonstracao
let
    Fonte = Parquet.Document(File.Contents(PastaExportacao & "fato_demonstracao.parquet")),
    Tipos = Table.TransformColumnTypes(Fonte, {{"valor", Currency.Type}})
in
    Tipos

// ---------- fato_indicador
let
    Fonte = Parquet.Document(File.Contents(PastaExportacao & "fato_indicador.parquet"))
in
    Fonte

// ---------- fato_qualidade
let
    Fonte = Parquet.Document(File.Contents(PastaExportacao & "fato_qualidade.parquet"))
in
    Fonte
