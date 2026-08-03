"""Esquema do banco do Peculium (DESIGN.md §4).

O banco vive dentro do cofre cifrado; este módulo só descreve a forma dele.
`aplicar()` é idempotente: cria o que falta e registra a versão em `config`.
"""
import sqlite3

VERSAO = 1

ESQUEMA = """
CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT
);

CREATE TABLE IF NOT EXISTS instituicoes (
    id     INTEGER PRIMARY KEY,
    nome   TEXT NOT NULL,
    cnpj   TEXT,
    ativo  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ativos (
    id       INTEGER PRIMARY KEY,
    ticker   TEXT NOT NULL UNIQUE,
    nome     TEXT,
    classe   TEXT NOT NULL,      -- ACAO | FII | ETF | BDR | UNIT | RF | TESOURO
    cnpj     TEXT,
    isin     TEXT,
    segmento TEXT,
    ativo    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS lancamentos (
    id                     INTEGER PRIMARY KEY,
    data                   TEXT NOT NULL,          -- ISO local, AAAA-MM-DD
    tipo                   TEXT NOT NULL,
    ativo_id               INTEGER REFERENCES ativos(id),
    instituicao_id         INTEGER REFERENCES instituicoes(id),
    instituicao_destino_id INTEGER REFERENCES instituicoes(id),
    quantidade             REAL NOT NULL DEFAULT 0,
    preco                  REAL NOT NULL DEFAULT 0,
    valor                  REAL NOT NULL DEFAULT 0,
    custos                 REAL NOT NULL DEFAULT 0,
    irrf                   REAL NOT NULL DEFAULT 0,
    origem                 TEXT NOT NULL DEFAULT 'MANUAL',
    hash_origem            TEXT UNIQUE,            -- idempotência da importação
    importacao_id          INTEGER REFERENCES importacoes(id),
    nota_id                INTEGER REFERENCES notas(id),
    estorna_id             INTEGER REFERENCES lancamentos(id),
    obs                    TEXT,
    criado_em              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eventos (
    id               INTEGER PRIMARY KEY,
    ativo_id         INTEGER NOT NULL REFERENCES ativos(id),
    data_ex          TEXT NOT NULL,
    tipo             TEXT NOT NULL,   -- DESDOBRAMENTO|GRUPAMENTO|CONVERSAO|INCORPORACAO
    fator            REAL NOT NULL,   -- multiplicador da QUANTIDADE (1:10 = 10; 10:1 = 0.1)
    ativo_destino_id INTEGER REFERENCES ativos(id),
    obs              TEXT
);

CREATE TABLE IF NOT EXISTS cotacoes (
    ativo_id   INTEGER NOT NULL REFERENCES ativos(id),
    data       TEXT NOT NULL,
    fechamento REAL NOT NULL,
    origem     TEXT NOT NULL DEFAULT 'MANUAL',
    PRIMARY KEY (ativo_id, data)
);

CREATE TABLE IF NOT EXISTS series (
    indice TEXT NOT NULL,
    data   TEXT NOT NULL,
    valor  REAL NOT NULL,
    PRIMARY KEY (indice, data)
);

CREATE TABLE IF NOT EXISTS rf_titulos (          -- v1.1
    lancamento_id INTEGER PRIMARY KEY REFERENCES lancamentos(id),
    indexador     TEXT,
    taxa          REAL,
    vencimento    TEXT,
    emissor       TEXT,
    isento        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS importacoes (
    id         INTEGER PRIMARY KEY,
    arquivo    TEXT NOT NULL,
    tipo       TEXT NOT NULL,
    em         TEXT NOT NULL,
    linhas     INTEGER NOT NULL DEFAULT 0,
    novas      INTEGER NOT NULL DEFAULT 0,
    duplicadas INTEGER NOT NULL DEFAULT 0,
    erros      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notas (
    id               INTEGER PRIMARY KEY,
    numero           TEXT NOT NULL,
    corretora        TEXT,
    cnpj             TEXT,
    data_pregao      TEXT NOT NULL,
    data_liquidacao  TEXT,
    valor_operacoes  REAL NOT NULL DEFAULT 0,
    total_custos     REAL NOT NULL DEFAULT 0,
    liquido          REAL NOT NULL DEFAULT 0,
    irrf             REAL NOT NULL DEFAULT 0,
    rubricas         TEXT,                  -- JSON com o resumo financeiro inteiro
    importada_em     TEXT NOT NULL,
    UNIQUE (numero, cnpj, data_pregao)
);

-- Especificação da nota -> ticker. A nota traz "KLABIN S/A PN", não KLBN4;
-- só os FII costumam trazer o código embutido. O mapa é aprendido uma vez.
CREATE TABLE IF NOT EXISTS apelidos (
    especificacao TEXT PRIMARY KEY,
    ativo_id      INTEGER NOT NULL REFERENCES ativos(id),
    criado_em     TEXT NOT NULL
);

-- Só o PAGAMENTO é fato e se guarda. O valor devido é sempre recalculado do
-- razão: gravá-lo criaria uma segunda verdade que uma nota retroativa desmente.
CREATE TABLE IF NOT EXISTS pagamentos (
    id          INTEGER PRIMARY KEY,
    competencia TEXT NOT NULL,          -- AAAA-MM da apuração
    codigo      TEXT NOT NULL,          -- 6015 para renda variável
    valor       REAL NOT NULL,          -- principal pago
    multa       REAL NOT NULL DEFAULT 0,
    juros       REAL NOT NULL DEFAULT 0,
    data        TEXT NOT NULL,          -- data do pagamento
    obs         TEXT,
    criado_em   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auditoria (
    id      INTEGER PRIMARY KEY,
    em      TEXT NOT NULL,
    acao    TEXT NOT NULL,
    detalhe TEXT
);

CREATE INDEX IF NOT EXISTS ix_lanc_data      ON lancamentos(data);
CREATE INDEX IF NOT EXISTS ix_lanc_ativo     ON lancamentos(ativo_id, data);
CREATE INDEX IF NOT EXISTS ix_lanc_estorna   ON lancamentos(estorna_id);
CREATE INDEX IF NOT EXISTS ix_eventos_ativo  ON eventos(ativo_id, data_ex);
CREATE INDEX IF NOT EXISTS ix_cotacoes_data  ON cotacoes(data);
CREATE INDEX IF NOT EXISTS ix_lanc_nota      ON lancamentos(nota_id);
CREATE INDEX IF NOT EXISTS ix_pag_comp       ON pagamentos(competencia, codigo);
"""


def aplicar(conn: sqlite3.Connection) -> None:
    conn.executescript(ESQUEMA)
    conn.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('esquema', ?)",
                 (str(VERSAO),))
