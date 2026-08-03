"""Testes da cotação. Nenhum teste toca a rede: o buscador é injetado."""
import sqlite3

import pytest

import cotacoes
import esquema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    esquema.aplicar(c)
    c.execute("INSERT INTO ativos (id, ticker, classe) VALUES (1,'PETR4','ACAO')")
    c.execute("INSERT INTO instituicoes (id, nome) VALUES (1,'Alfa')")
    c.execute("INSERT INTO lancamentos (data, tipo, ativo_id, instituicao_id,"
              " quantidade, preco, valor, criado_em)"
              " VALUES ('2026-01-05','COMPRA',1,1,100,10,1000,'2026-01-05')")
    return c


def ligar(conn):
    conn.execute("INSERT OR REPLACE INTO config (chave, valor) VALUES ('cotacao_online','1')")


def test_desligada_por_padrao_nao_busca(conn):
    def nunca(_):
        raise AssertionError("não pode tocar a rede com a cotação desligada")

    resultado = cotacoes.cotar(conn, "2026-08-01", buscador=nunca)
    assert resultado.desligada is True and resultado.atualizadas == 0


def test_busca_so_o_que_esta_em_carteira(conn):
    ligar(conn)
    conn.execute("INSERT INTO ativos (id, ticker, classe) VALUES (2,'VALE3','ACAO')")
    pedidos = []

    def buscar(ticker):
        pedidos.append(ticker)
        return 38.04

    cotacoes.cotar(conn, "2026-08-01", buscador=buscar)
    assert pedidos == ["PETR4"]        # VALE3 não tem lançamento nenhum
    assert cotacoes.preco(conn, 1) == pytest.approx(38.04)


def test_preco_manual_vence_o_baixado(conn):
    ligar(conn)
    cotacoes.registrar(conn, 1, "2026-08-01", 40.00, cotacoes.MANUAL)
    resultado = cotacoes.cotar(conn, "2026-08-01", buscador=lambda t: 38.04)
    assert resultado.ignoradas == 1 and resultado.atualizadas == 0
    assert cotacoes.preco(conn, 1) == pytest.approx(40.00)


def test_online_sobrescreve_online(conn):
    ligar(conn)
    cotacoes.cotar(conn, "2026-08-01", buscador=lambda t: 38.04)
    cotacoes.cotar(conn, "2026-08-01", buscador=lambda t: 39.10)
    assert cotacoes.preco(conn, 1) == pytest.approx(39.10)


def test_falha_de_rede_nao_derruba(conn):
    ligar(conn)

    def cai(_):
        raise OSError("sem rede")

    resultado = cotacoes.cotar(conn, "2026-08-01", buscador=cai)
    assert resultado.atualizadas == 0
    assert "PETR4" in resultado.falhas
    assert cotacoes.preco(conn, 1) is None       # e a carteira segue aberta


def test_ticker_estranho_nao_vira_requisicao(conn):
    """O ticker entra numa URL: validar o formato é o que impede um 'ativo'
    com barra no nome de virar outra requisição."""
    ligar(conn)
    pedidos = []
    resultado = cotacoes.cotar(conn, "2026-08-01", tickers=["../../etc/passwd"],
                               buscador=lambda t: pedidos.append(t))
    assert pedidos == []
    assert "formato de ticker não reconhecido" in next(iter(resultado.falhas.values()))


def test_preco_nunca_extrapola_para_frente(conn):
    cotacoes.registrar(conn, 1, "2026-07-01", 30.0)
    cotacoes.registrar(conn, 1, "2026-08-01", 38.0)
    assert cotacoes.preco(conn, 1, "2026-07-15") == pytest.approx(30.0)
    assert cotacoes.preco(conn, 1, "2026-06-01") is None
    assert cotacoes.preco(conn, 1) == pytest.approx(38.0)


def test_whitelist_de_host_esta_no_codigo():
    assert cotacoes.HOSTS and all(h and "/" not in h for h in cotacoes.HOSTS)
