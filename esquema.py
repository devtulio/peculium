"""Esquema do banco do Peculium (DESIGN.md §4).

O banco vive dentro do cofre cifrado; este módulo só descreve a forma dele.
`aplicar()` é idempotente: cria o que falta e registra a versão em `config`.
"""
import sqlite3

VERSAO = 4

ESQUEMA = """
CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT
);

-- `chave` é o nome sem acento, pontuação nem forma societária: é o que impede a
-- mesma corretora de virar quatro cadastros porque cada documento a escreve de
-- um jeito. Ela é UNIQUE; o `nome` continua sendo o que se mostra na tela.
CREATE TABLE IF NOT EXISTS instituicoes (
    id     INTEGER PRIMARY KEY,
    nome   TEXT NOT NULL,
    chave  TEXT,
    cnpj   TEXT,
    ativo  INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_inst_chave ON instituicoes(chave)
    WHERE chave IS NOT NULL;

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

-- A curva pertence ao PAPEL, não à compra: dois aportes no mesmo CDB são o mesmo
-- título com o mesmo preço unitário, e o que muda é a quantidade. Por isso a
-- chave é o ativo — como no Tesouro, onde o PU do dia vale para quem tem 1 ou
-- 100 títulos.
CREATE TABLE IF NOT EXISTS rf_titulos (
    ativo_id   INTEGER PRIMARY KEY REFERENCES ativos(id),
    emissao    TEXT NOT NULL,          -- início da curva
    indexador  TEXT NOT NULL,          -- CDI | PRE | IPCA
    taxa       REAL NOT NULL,          -- % do CDI, ou taxa anual no prefixado
    pu_base    REAL NOT NULL DEFAULT 1.0,
    vencimento TEXT,
    emissor    TEXT,
    isento     INTEGER NOT NULL DEFAULT 0,   -- LCI/LCA e poupança
    obs        TEXT
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

-- Último retrato da B3, para o painel poder acusar a divergência depois que a
-- tela de importação fechou. Guarda o que a B3 disse, nunca o que se conclui
-- dela: a divergência é recalculada contra a carteira a cada abertura, senão
-- lançar a compra que faltava não apagaria o aviso.
CREATE TABLE IF NOT EXISTS posicao_b3 (
    data        TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    classe      TEXT NOT NULL,
    quantidade  REAL NOT NULL,
    valor       REAL,
    PRIMARY KEY (data, ticker)
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


def versao_do_banco(conn: sqlite3.Connection) -> int:
    try:
        linha = conn.execute("SELECT valor FROM config WHERE chave='esquema'").fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(linha[0]) if linha else 0


def _migrar_2(conn: sqlite3.Connection) -> None:
    """`rf_titulos` era chaveada pelo lançamento; a curva pertence ao papel.

    A tabela nunca chegou a ser escrita — nenhuma versão publicada tinha caminho
    para preenchê-la —, então recriar é seguro. Ainda assim, confere que está
    vazia antes: apagar dado do usuário para arrumar o formato seria pior que o
    formato errado."""
    colunas = {c[1] for c in conn.execute("PRAGMA table_info(rf_titulos)")}
    if "lancamento_id" not in colunas:
        return
    linhas = conn.execute("SELECT count(*) FROM rf_titulos").fetchone()[0]
    if linhas:
        raise RuntimeError(
            f"rf_titulos tem {linhas} linha(s) no formato antigo — migração "
            f"automática recusada para não descartar dado")
    conn.execute("DROP TABLE rf_titulos")
    conn.executescript(ESQUEMA)


def _migrar_4(conn: sqlite3.Connection) -> None:
    """Preenche a chave das instituições e FUNDE as duplicadas.

    Cofre feito antes desta versão tem a mesma corretora repetida — quatro
    grafias da XP num acervo real. Funde-se para a de menor id (a primeira
    vista), e os lançamentos das outras são repontados antes de elas sumirem:
    apagar primeiro deixaria lançamento órfão."""
    import textos

    if "chave" not in {c[1] for c in conn.execute("PRAGMA table_info(instituicoes)")}:
        conn.execute("ALTER TABLE instituicoes ADD COLUMN chave TEXT")

    por_chave: dict[str, int] = {}
    for linha in conn.execute("SELECT id, nome FROM instituicoes ORDER BY id"):
        chave = textos.nome_instituicao(linha["nome"])
        if not chave:
            continue
        if chave in por_chave:
            manter = por_chave[chave]
            conn.execute("UPDATE lancamentos SET instituicao_id=? WHERE instituicao_id=?",
                         (manter, linha["id"]))
            conn.execute("UPDATE lancamentos SET instituicao_destino_id=?"
                         " WHERE instituicao_destino_id=?", (manter, linha["id"]))
            # o CNPJ pode ter vindo só na cópia que vai sumir
            conn.execute(
                "UPDATE instituicoes SET cnpj=coalesce(cnpj,"
                " (SELECT cnpj FROM instituicoes WHERE id=?)) WHERE id=?",
                (linha["id"], manter))
            conn.execute("DELETE FROM instituicoes WHERE id=?", (linha["id"],))
        else:
            por_chave[chave] = linha["id"]
            conn.execute("UPDATE instituicoes SET chave=? WHERE id=?",
                         (chave, linha["id"]))
    conn.executescript(ESQUEMA)          # o índice único só entra depois da fusão


def aplicar(conn: sqlite3.Connection) -> None:
    atual = versao_do_banco(conn)
    conn.executescript(ESQUEMA)
    if atual and atual < 2:
        _migrar_2(conn)
    if atual and atual < 4:
        _migrar_4(conn)
    conn.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('esquema', ?)",
                 (str(VERSAO),))


# Sobrevivem ao apagamento geral. `config` é preferência, não registro — apagá-la
# só faria o usuário reconfigurar tema e senha de PDF. `series` é dado público do
# Banco Central, em cache: apagá-la não protege nada e obriga a baixar tudo de
# novo para a curva voltar a ser calculável.
PRESERVADAS = ("config", "series")


def limpar(conn: sqlite3.Connection,
           preservar: tuple[str, ...] = PRESERVADAS) -> dict[str, int]:
    """Apaga o conteúdo do cofre e devolve quantas linhas saíram de cada tabela.

    A senha mestra, a chave de recuperação e o próprio arquivo continuam os
    mesmos: isto esvazia o banco, não recria o cofre.

    As tabelas vêm do `sqlite_master`, nunca de uma lista escrita à mão — uma
    lista fica para trás quando alguém acrescenta uma tabela, e o resultado
    silencioso seria um "apagou tudo" que não apagou tudo."""
    tabelas = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
        " AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    apagados: dict[str, int] = {}
    # sem isto a ordem do apagamento importaria, e ela viria da mesma lista à mão
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        for tabela in tabelas:
            if tabela in preservar:
                continue
            linhas = conn.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]
            conn.execute(f"DELETE FROM {tabela}")
            if linhas:
                apagados[tabela] = linhas
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
    # DELETE só marca a página como livre: os bytes apagados continuariam dentro
    # do banco, e o banco inteiro vai cifrado para o arquivo. Sem o VACUUM, quem
    # tem a senha ainda leria o que o usuário mandou apagar.
    conn.commit()                            # VACUUM não roda dentro de transação
    conn.execute("VACUUM")
    return apagados
