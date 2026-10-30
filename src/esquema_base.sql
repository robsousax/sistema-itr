-- Estrutura da base base/itr.sqlite (Etapa 3).
-- Valores monetários: INTEGER em centavos (colunas *_centavos). Datas: texto 'AAAA-MM-DD'.
-- As regras CHECK e REFERENCES repetem, dentro do banco, parte das validações do Python.

PRAGMA foreign_keys = ON;

-- Rastreabilidade: de qual arquivo a base foi gerada
CREATE TABLE importacao (
    arquivo        TEXT NOT NULL,
    sha256         TEXT NOT NULL,   -- "impressão digital" do arquivo importado
    importado_em   TEXT NOT NULL
);

-- Cópias da configuração (fonte da verdade: config/*.csv)
CREATE TABLE plano_de_contas (
    codigo      TEXT PRIMARY KEY,
    descricao   TEXT NOT NULL,
    tipo        TEXT NOT NULL CHECK (tipo IN ('A', 'S')),
    natureza    TEXT NOT NULL CHECK (natureza IN ('D', 'C')),
    nivel       INTEGER NOT NULL,
    codigo_pai  TEXT,
    grupo       TEXT NOT NULL,
    redutora    TEXT NOT NULL CHECK (redutora IN ('S', 'N'))
);

CREATE TABLE dim_evento (
    codigo          TEXT PRIMARY KEY,
    nome            TEXT NOT NULL,
    grupo           TEXT NOT NULL,
    contas_debito   TEXT,
    contas_credito  TEXT,
    descricao       TEXT
);

-- Balancete de abertura (31/12/2024). Só contas com saldo.
CREATE TABLE saldo_abertura (
    codigo_conta      TEXT PRIMARY KEY REFERENCES plano_de_contas (codigo),
    data              TEXT NOT NULL,
    debito_centavos   INTEGER NOT NULL CHECK (debito_centavos >= 0),
    credito_centavos  INTEGER NOT NULL CHECK (credito_centavos >= 0),
    CHECK (debito_centavos = 0 OR credito_centavos = 0)
);

-- Uma linha por partida. Partidas com o mesmo id_lancamento formam um lançamento.
CREATE TABLE lancamento (
    id                INTEGER PRIMARY KEY,
    id_lancamento     TEXT NOT NULL,
    data              TEXT NOT NULL,
    codigo_evento     TEXT NOT NULL REFERENCES dim_evento (codigo),
    codigo_conta      TEXT NOT NULL REFERENCES plano_de_contas (codigo),
    debito_centavos   INTEGER NOT NULL CHECK (debito_centavos >= 0),
    credito_centavos  INTEGER NOT NULL CHECK (credito_centavos >= 0),
    historico         TEXT,
    linha_excel       INTEGER NOT NULL,
    CHECK ((debito_centavos > 0) <> (credito_centavos > 0))
);
CREATE INDEX ix_lancamento_data ON lancamento (data);
CREATE INDEX ix_lancamento_conta ON lancamento (codigo_conta);

-- Quadros auxiliares
CREATE TABLE imobilizado (
    id_bem                                   TEXT PRIMARY KEY,
    descricao                                TEXT NOT NULL,
    classe                                   TEXT NOT NULL,
    conta_custo                              TEXT NOT NULL REFERENCES plano_de_contas (codigo),
    conta_depreciacao                        TEXT REFERENCES plano_de_contas (codigo),
    vida_util_anos                           INTEGER,   -- vazio: terrenos e obras em andamento
    data_aquisicao                           TEXT NOT NULL,
    custo_centavos                           INTEGER NOT NULL CHECK (custo_centavos > 0),
    depreciacao_acumulada_abertura_centavos  INTEGER NOT NULL
        CHECK (depreciacao_acumulada_abertura_centavos BETWEEN 0 AND custo_centavos),
    data_baixa                               TEXT,
    valor_venda_centavos                     INTEGER NOT NULL CHECK (valor_venda_centavos >= 0),
    linha_excel                              INTEGER NOT NULL
);

CREATE TABLE emprestimo (
    id_contrato                 TEXT PRIMARY KEY,
    modalidade                  TEXT NOT NULL CHECK (modalidade IN ('FINAME', 'CCB')),
    credor                      TEXT,
    data_contratacao            TEXT NOT NULL,
    valor_contratado_centavos   INTEGER NOT NULL CHECK (valor_contratado_centavos > 0),
    taxa_juros_aa               REAL NOT NULL CHECK (taxa_juros_aa > 0 AND taxa_juros_aa < 1),
    prazo_meses                 INTEGER NOT NULL CHECK (prazo_meses > 0),
    carencia_meses              INTEGER NOT NULL CHECK (carencia_meses >= 0),
    sistema_amortizacao         TEXT NOT NULL CHECK (sistema_amortizacao IN ('SAC', 'PRICE')),
    saldo_cp_abertura_centavos  INTEGER NOT NULL CHECK (saldo_cp_abertura_centavos >= 0),
    saldo_lp_abertura_centavos  INTEGER NOT NULL CHECK (saldo_lp_abertura_centavos >= 0),
    linha_excel                 INTEGER NOT NULL
);

CREATE TABLE ato_pl (
    id                INTEGER PRIMARY KEY,
    data              TEXT NOT NULL,
    tipo_ato          TEXT NOT NULL,
    valor_centavos    INTEGER NOT NULL CHECK (valor_centavos >= 0),
    quantidade_acoes  INTEGER NOT NULL CHECK (quantidade_acoes >= 0),
    descricao         TEXT,
    linha_excel       INTEGER NOT NULL
);

CREATE TABLE diferenca_temporaria (
    data_base            TEXT NOT NULL,
    tipo                 TEXT NOT NULL,
    conta_origem         TEXT NOT NULL REFERENCES plano_de_contas (codigo),
    valor_base_centavos  INTEGER NOT NULL CHECK (valor_base_centavos >= 0),
    descricao            TEXT,
    linha_excel          INTEGER NOT NULL,
    PRIMARY KEY (data_base, tipo)
);
