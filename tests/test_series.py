"""Séries do BCB e fatores de curva. Nenhum teste toca a rede."""
import sqlite3
from datetime import date, timedelta

import pytest

import esquema
import series


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    esquema.aplicar(c)
    c.execute("INSERT INTO config (chave, valor) VALUES ('cotacao_online','1')")
    return c


def semear_cdi(conn, inicio="2026-01-01", dias=60, taxa=0.052531):
    """Só dias úteis, como a série real — ela é o calendário do programa."""
    d = date.fromisoformat(inicio)
    gravados = 0
    while gravados < dias:
        if d.weekday() < 5:
            conn.execute("INSERT OR REPLACE INTO series VALUES ('CDI', ?, ?)",
                         (d.isoformat(), taxa))
            gravados += 1
        d += timedelta(days=1)
    return conn


# --------------------------------------------------------------- download

def test_desligada_nao_busca(conn):
    conn.execute("UPDATE config SET valor='0' WHERE chave='cotacao_online'")

    def nunca(*a):
        raise AssertionError("não pode tocar a rede com a rede desligada")

    assert series.baixar(conn, buscador=nunca).desligada is True


def test_grava_e_converte_a_data(conn):
    r = series.baixar(conn, ["CDI"], buscador=lambda *a: [
        {"data": "02/01/2026", "valor": "0.052531"},
        {"data": "05/01/2026", "valor": "0.052531"}])
    assert r.gravados == 2
    assert conn.execute("SELECT data FROM series ORDER BY data").fetchone()[0] \
        == "2026-01-02"                       # guarda ISO, a API devolve BR


def test_continua_de_onde_parou(conn):
    semear_cdi(conn, dias=5)
    pedidos = []

    def buscar(codigo, inicio, fim):
        pedidos.append(inicio)
        return []

    series.baixar(conn, ["CDI"], buscador=buscar)
    assert pedidos[0] == conn.execute("SELECT max(data) FROM series").fetchone()[0]


def test_falha_de_rede_nao_derruba(conn):
    def cai(*a):
        raise OSError("sem rede")

    r = series.baixar(conn, ["CDI"], buscador=cai)
    assert r.gravados == 0 and "CDI" in r.falhas


# --------------------------------------------------------------- dias úteis

def test_a_serie_e_o_calendario(conn):
    """Não existe tabela de feriados: a série do BCB só tem dia útil, então
    contar registros é contar dias úteis."""
    semear_cdi(conn, "2026-01-05", dias=10)     # 05/01 é segunda
    assert series.dias_uteis(conn, "2026-01-05", "2026-01-12") == 5
    conn.execute("DELETE FROM series WHERE data='2026-01-08'")   # feriado
    assert series.dias_uteis(conn, "2026-01-05", "2026-01-12") == 4


# --------------------------------------------------------------- fatores

def test_cdi_composto_dia_a_dia(conn):
    semear_cdi(conn, "2026-01-05", dias=10)
    fator = series.fator_cdi(conn, "2026-01-05", "2026-01-16", 100)
    assert fator == pytest.approx(1.00052531 ** 9, rel=1e-12)


def test_percentual_incide_sobre_a_taxa_e_nao_sobre_o_fator(conn):
    """110% do CDI é `1 + 0,10% × 1,10` ao dia, e não `(1 + 0,10%)^1,10`.

    As duas convenções ficam muito próximas — em 20 dias sobre R$ 1.000 a
    diferença é de um décimo de centavo. O teste não finge que a diferença é
    grande: prova que a implementação segue a fórmula do mercado, com tolerância
    apertada o bastante para a outra não passar."""
    semear_cdi(conn, "2026-01-05", dias=21, taxa=0.1)
    fim = conn.execute("SELECT max(data) FROM series").fetchone()[0]
    du = series.dias_uteis(conn, "2026-01-05", fim)
    fator = series.fator_cdi(conn, "2026-01-05", fim, 110)

    assert fator == pytest.approx((1 + 0.001 * 1.10) ** du, rel=1e-12)
    assert fator != pytest.approx((1.001 ** 1.10) ** du, rel=1e-9)


def test_rendimento_corre_do_dia_seguinte(conn):
    semear_cdi(conn, "2026-01-05", dias=10)
    assert series.fator_cdi(conn, "2026-01-05", "2026-01-05") == 1.0
    assert series.fator_cdi(conn, "2026-01-05", "2026-01-06") > 1.0


def test_prefixado_base_252(conn):
    semear_cdi(conn, "2026-01-05", dias=260)
    fator = series.fator_prefixado(conn, "2026-01-05", "2026-01-16", 12.0)
    du = series.dias_uteis(conn, "2026-01-05", "2026-01-16")
    assert fator == pytest.approx(1.12 ** (du / 252))


def test_recusa_calcular_fora_da_cobertura(conn):
    """Calcular além do que a série cobre devolveria um número menor que a
    verdade — e um patrimônio subavaliado é pior que um erro visível."""
    semear_cdi(conn, "2026-01-05", dias=10)
    with pytest.raises(series.SerieIndisponivel, match="atualize as séries"):
        series.fator_cdi(conn, "2026-01-05", "2026-06-01")
    with pytest.raises(series.SerieIndisponivel, match="começa em"):
        series.fator_cdi(conn, "2025-01-05", "2026-01-08")


def test_sem_serie_alguma_avisa_o_que_fazer(conn):
    with pytest.raises(series.SerieIndisponivel, match="ligue a rede"):
        series.fator_cdi(conn, "2026-01-05", "2026-01-08")


def test_ipca_mais_ainda_nao_tem_curva(conn):
    semear_cdi(conn, "2026-01-05", dias=10)
    with pytest.raises(series.SerieIndisponivel, match="preço unitário à mão"):
        series.fator(conn, "IPCA", "2026-01-05", "2026-01-08", 6.0)


@pytest.mark.parametrize("indexador", ["CDI", "cdi", "DI", "pós"])
def test_apelidos_do_indexador(conn, indexador):
    semear_cdi(conn, "2026-01-05", dias=10)
    assert series.fator(conn, indexador, "2026-01-05", "2026-01-08", 100) > 1
