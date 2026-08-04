"""Apagar todos os dados (Zona de risco das Configurações).

Operação sem desfazer. O que estes testes protegem, em ordem de gravidade:

1. **não apaga sem a frase digitada** — um clique acidental não pode custar a
   carteira inteira;
2. **a cópia de antes existe e abre** — é a única volta atrás que existe;
3. **o dado apagado some do arquivo cifrado**, não só das consultas — `DELETE`
   sozinho deixa os bytes numa página livre, e o banco inteiro vai cifrado para
   o disco: sem `VACUUM`, quem tem a senha ainda leria o que foi apagado;
4. **a senha e a chave de recuperação continuam valendo** — o cofre é o mesmo,
   vazio.
"""
from __future__ import annotations

import sqlite3

import pytest

import cofre
import esquema
import peculium

SENHA = "senha mestra boa"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    esquema.aplicar(c)
    c.execute("INSERT INTO instituicoes (id, nome) VALUES (1,'XP')")
    c.execute("INSERT INTO ativos (id, ticker, classe) VALUES (1,'PETR4','ACAO')")
    c.execute("INSERT INTO lancamentos (data, tipo, ativo_id, instituicao_id,"
              " quantidade, preco, valor, criado_em)"
              " VALUES ('2026-01-05','COMPRA',1,1,100,10,1000,'2026-01-05')")
    c.execute("INSERT INTO config (chave,valor) VALUES ('tema','cera')")
    c.execute("INSERT INTO series (indice,data,valor) VALUES ('CDI','2026-01-02',0.05)")
    return c


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(peculium, "PREFERENCIAS", tmp_path / "preferencias.json")
    a = peculium.Api(tmp_path / "carteira.pec")
    assert a.criar_cofre(SENHA)["ok"]
    return a


def dados(resposta):
    assert resposta["ok"] is True, resposta.get("erro")
    return resposta["dados"]


def povoar(api) -> None:
    dados(api.cadastrar_instituicao({"nome": "Corretora Teste"}))
    dados(api.cadastrar_ativo({"ticker": "PETR4", "classe": "ACAO"}))
    dados(api.lancar({"data": "05/01/2026", "tipo": "COMPRA", "ativo": "PETR4",
                      "instituicao": "Corretora Teste", "quantidade": 100,
                      "preco": 10.0}))


# ------------------------------------------------------------------- esquema


def test_limpa_registro_e_poupa_preferencia(conn):
    apagados = esquema.limpar(conn)
    assert apagados == {"ativos": 1, "instituicoes": 1, "lancamentos": 1}
    assert conn.execute("SELECT count(*) FROM lancamentos").fetchone()[0] == 0
    # preferência e dado público do BCB não são registro do usuário
    assert conn.execute("SELECT valor FROM config WHERE chave='tema'").fetchone()[0] \
        == "cera"
    assert conn.execute("SELECT count(*) FROM series").fetchone()[0] == 1


def test_esquema_continua_utilizavel_depois(conn):
    """Esvaziar não é destruir: as tabelas e a versão do esquema ficam."""
    esquema.limpar(conn)
    assert esquema.versao_do_banco(conn) == esquema.VERSAO
    conn.execute("INSERT INTO ativos (ticker, classe) VALUES ('VALE3','ACAO')")
    assert conn.execute("SELECT count(*) FROM ativos").fetchone()[0] == 1


def test_tabela_nova_nao_fica_para_tras(conn):
    """As tabelas vêm do `sqlite_master`, não de uma lista escrita à mão.

    Uma lista fica desatualizada assim que alguém acrescenta uma tabela, e o
    resultado silencioso seria um "apagou tudo" que não apagou tudo."""
    conn.execute("CREATE TABLE inventada (id INTEGER PRIMARY KEY, x TEXT)")
    conn.execute("INSERT INTO inventada (x) VALUES ('sobra')")
    assert esquema.limpar(conn)["inventada"] == 1
    assert conn.execute("SELECT count(*) FROM inventada").fetchone()[0] == 0


def test_bytes_apagados_somem_do_banco(conn):
    """`DELETE` marca a página como livre; os bytes continuam lá.

    Como o banco inteiro é serializado e cifrado a cada gravação, sem o `VACUUM`
    o ticker apagado viajaria dentro do arquivo — recuperável por quem tem a
    senha, que é exatamente de quem o usuário quer apagar o dado."""
    conn.execute("INSERT INTO ativos (ticker, classe) VALUES ('SEGREDO1','ACAO')")
    conn.commit()
    assert b"SEGREDO1" in conn.serialize()          # controle: estava lá
    esquema.limpar(conn)
    assert b"SEGREDO1" not in conn.serialize()


# --------------------------------------------------------------------- cofre


def test_instantaneo_nao_gira_com_os_backups(tmp_path):
    """Os três backups automáticos giram a cada gravação: três commits depois de
    um apagamento, nenhum deles teria mais o dado antigo."""
    alvo = tmp_path / "carteira.pec"
    c, _ = cofre.criar(alvo, SENHA)
    c.conn.execute("INSERT INTO ativos (ticker, classe) VALUES ('PETR4','ACAO')")
    copia = c.instantaneo("antes-do-reset")

    esquema.limpar(c.conn)
    for _ in range(cofre.BACKUPS + 2):              # gira todos os automáticos
        c.commit()
    c.fechar()

    assert copia.exists()
    with cofre.abrir(copia, SENHA) as guardado:     # abre com a senha de agora
        assert guardado.conn.execute(
            "SELECT ticker FROM ativos").fetchone()[0] == "PETR4"
    with cofre.abrir(alvo, SENHA) as atual:
        assert atual.conn.execute("SELECT count(*) FROM ativos").fetchone()[0] == 0


# ---------------------------------------------------------------------- ponte


def test_sem_a_frase_nao_apaga_nada(api):
    povoar(api)
    for tentativa in ("", "apagar", "APAGAR TUDO!!", "sim"):
        resposta = api.resetar(tentativa)
        assert resposta["ok"] is False
        assert "APAGAR TUDO" in resposta["erro"]
    assert len(dados(api.carteira())) == 1          # a carteira segue de pé


def test_frase_certa_apaga_e_guarda_copia(api, tmp_path):
    povoar(api)
    resultado = dados(api.resetar("  apagar tudo  "))   # espaço e caixa não importam

    # três registros e as três linhas que a auditoria gravou ao criá-los
    assert resultado["apagados"] == {"ativos": 1, "auditoria": 3,
                                     "instituicoes": 1, "lancamentos": 1}
    assert resultado["total"] == 6
    assert dados(api.carteira()) == []
    assert dados(api.cadastros())["ativos"] == []

    copia = tmp_path / resultado["backup"]
    assert copia.exists() and "antes-do-reset" in copia.name
    with cofre.abrir(copia, SENHA) as guardado:
        assert guardado.conn.execute(
            "SELECT count(*) FROM lancamentos").fetchone()[0] == 1


def test_senha_e_chave_continuam_valendo(tmp_path, monkeypatch):
    """O cofre é o mesmo, vazio: reset não recria arquivo nem troca credencial."""
    monkeypatch.setattr(peculium, "PREFERENCIAS", tmp_path / "preferencias.json")
    api = peculium.Api(tmp_path / "carteira.pec")
    chave = dados(api.criar_cofre(SENHA))["chave_recuperacao"]
    povoar(api)
    dados(api.resetar("APAGAR TUDO"))

    dados(api.abrir_cofre(SENHA))
    dados(api.abrir_com_recuperacao(chave))


def test_preferencias_sobrevivem_ao_reset(api):
    dados(api.salvar_config({"tema": "aerarium", "cpf": "000.000.000-00"}))
    povoar(api)
    dados(api.resetar("APAGAR TUDO"))
    config = dados(api.config())
    assert (config["tema"], config["cpf"]) == ("aerarium", "000.000.000-00")


def test_o_reset_fica_registrado_na_auditoria(api):
    """A auditoria também é apagada — esta vira a primeira linha da nova, senão
    não sobraria nenhum vestígio de que a carteira já teve conteúdo."""
    povoar(api)
    dados(api.resetar("APAGAR TUDO"))
    linhas = list(api._conn.execute("SELECT acao, detalhe FROM auditoria"))
    assert len(linhas) == 1
    assert linhas[0]["acao"] == "RESET"
    assert "antes-do-reset" in linhas[0]["detalhe"]


def test_conferencia_pendente_nao_sobrevive(api, tmp_path):
    """Conferência pendente carrega dado da carteira em memória; deixá-la viva
    permitiria gravá-la de volta depois do apagamento."""
    povoar(api)
    api._conferencias["imp1"] = ("B3", object())
    dados(api.resetar("APAGAR TUDO"))
    assert api._conferencias == {}


# --------------------------------------------------- migração de cofre antigo

ESQUEMA_V3 = """
CREATE TABLE config (chave TEXT PRIMARY KEY, valor TEXT);
INSERT INTO config VALUES ('esquema','3');
CREATE TABLE instituicoes (id INTEGER PRIMARY KEY, nome TEXT NOT NULL,
                           cnpj TEXT, ativo INTEGER NOT NULL DEFAULT 1);
CREATE TABLE ativos (id INTEGER PRIMARY KEY, ticker TEXT NOT NULL UNIQUE,
                     nome TEXT, classe TEXT NOT NULL, cnpj TEXT,
                     ativo INTEGER NOT NULL DEFAULT 1);
CREATE TABLE lancamentos (id INTEGER PRIMARY KEY, data TEXT NOT NULL,
  tipo TEXT NOT NULL, ativo_id INTEGER, instituicao_id INTEGER,
  instituicao_destino_id INTEGER, quantidade REAL NOT NULL DEFAULT 0,
  preco REAL NOT NULL DEFAULT 0, valor REAL NOT NULL DEFAULT 0,
  custos REAL NOT NULL DEFAULT 0, irrf REAL NOT NULL DEFAULT 0, origem TEXT,
  hash_origem TEXT UNIQUE, importacao_id INTEGER, nota_id INTEGER,
  estorna_id INTEGER, obs TEXT, criado_em TEXT NOT NULL);
INSERT INTO instituicoes (id,nome) VALUES (1,'XP INVESTIMENTOS CCTVM S/A');
INSERT INTO instituicoes (id,nome) VALUES (2,'XP INVESTIMENTOS CCTVM S/A.');
INSERT INTO instituicoes (id,nome,cnpj) VALUES (3,'XP INVESTIMENTOS','02332886000104');
INSERT INTO instituicoes (id,nome) VALUES (4,'BANCO INTER S/A');
INSERT INTO ativos (id,ticker,classe) VALUES (1,'PETR4','ACAO');
INSERT INTO lancamentos (data,tipo,ativo_id,instituicao_id,quantidade,preco,valor,
  criado_em) VALUES ('2026-01-05','COMPRA',1,2,100,10,1000,'x');
INSERT INTO lancamentos (data,tipo,ativo_id,instituicao_id,quantidade,preco,valor,
  criado_em) VALUES ('2026-02-05','COMPRA',1,3,50,10,500,'x');
"""


def _v3():
    """Cofre da versão anterior: as tabelas JÁ existem, sem a coluna nova."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(ESQUEMA_V3)
    return c


def test_cofre_que_ja_tem_a_tabela_ganha_a_coluna_nova():
    """A regressão que derrubou a importação de um usuário real.

    `aplicar()` rodava o script do esquema ANTES da migração. `CREATE TABLE IF
    NOT EXISTS` não altera tabela que já existe, então a coluna `chave` não
    nascia — e a linha seguinte do script, que cria o índice sobre ela, estourava
    com `no such column`. A migração que acrescentaria a coluna nunca chegava a
    rodar, e o cofre abria quebrado.

    O teste antigo não pegava porque montava um cofre **sem** a tabela
    `instituicoes`: ali o `CREATE TABLE` rodava de verdade e a coluna vinha
    junto."""
    c = _v3()
    esquema.aplicar(c)
    assert "chave" in {x[1] for x in c.execute("PRAGMA table_info(instituicoes)")}
    assert esquema.versao_do_banco(c) == esquema.VERSAO


def test_migracao_funde_as_instituicoes_repetidas():
    c = _v3()
    esquema.aplicar(c)
    linhas = list(c.execute("SELECT id, nome, chave, cnpj FROM instituicoes ORDER BY id"))
    assert len(linhas) == 2                       # três grafias da XP viram uma
    assert linhas[0]["chave"] == "xp investimentos"
    # o CNPJ só existia na cópia que sumiu, e não pode sumir com ela
    assert linhas[0]["cnpj"] == "02332886000104"
    # e nenhum lançamento fica órfão
    assert {r[0] for r in c.execute(
        "SELECT DISTINCT instituicao_id FROM lancamentos")} == {linhas[0]["id"]}


def test_migracao_e_idempotente():
    """Abrir duas vezes não pode fundir de novo nem duplicar."""
    c = _v3()
    esquema.aplicar(c)
    antes = [dict(r) for r in c.execute("SELECT * FROM instituicoes ORDER BY id")]
    esquema.aplicar(c)
    assert [dict(r) for r in c.execute("SELECT * FROM instituicoes ORDER BY id")] == antes
