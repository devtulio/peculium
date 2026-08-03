"""Renda fixa: curva, posição e estimativa de IR. Sem rede."""
import sqlite3
from datetime import date, timedelta

import pytest

import cotacoes
import esquema
import lancamentos as lanc
import razao
import renda_fixa as rf
import series

HOJE = "2026-12-31"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    esquema.aplicar(c)
    c.execute("INSERT INTO instituicoes (id, nome) VALUES (1,'XP')")
    c.executemany("INSERT INTO ativos (id, ticker, nome, classe) VALUES (?,?,?,?)", [
        (1, "CDB5267UW6V", "CDB Banco XP MAI/2028", "RF"),
        (2, "LCI-INTER-2027", "LCI Inter", "RF"),
        (3, "PETR4", "Petrobras", "ACAO"),
    ])
    # série só com dia útil, como a do BCB
    d, gravados = date(2026, 1, 1), 0
    while gravados < 300:
        if d.weekday() < 5:
            c.execute("INSERT INTO series VALUES ('CDI', ?, 0.052531)", (d.isoformat(),))
            gravados += 1
        d += timedelta(days=1)
    return c


def aplicar(conn, ativo=1, data="2026-05-14", qtd=1000, preco=1.0):
    return lanc.lancar(conn, data=data, tipo="COMPRA", ativo=ativo, instituicao=1,
                       quantidade=qtd, preco=preco, hoje=HOJE)


# --------------------------------------------------------------- cadastro

def test_cadastro_e_leitura(conn):
    rf.cadastrar(conn, ativo_id=1, emissao="14/05/2026", indexador="cdi", taxa=100,
                 vencimento="15/05/2028", emissor="BANCO XP S.A.")
    t = rf.titulo(conn, 1)
    assert t.emissao == "2026-05-14" and t.vencimento == "2028-05-15"
    assert t.indexador == "CDI" and t.descricao() == "100% do CDI"
    assert t.isento is False


def test_recusa_ativo_de_renda_variavel(conn):
    with pytest.raises(ValueError, match="classe ACAO"):
        rf.cadastrar(conn, ativo_id=3, emissao="2026-05-14", indexador="CDI", taxa=100)


@pytest.mark.parametrize("campos, erro", [
    (dict(indexador="POUPANCA"), "indexador deve ser"),
    (dict(pu_base=0), "maior que zero"),
    (dict(vencimento="2026-05-13"), "depois da emissão"),
    (dict(ativo_id=99), "não existe"),
])
def test_recusa_cadastro_invalido(conn, campos, erro):
    base = dict(ativo_id=1, emissao="2026-05-14", indexador="CDI", taxa=100)
    with pytest.raises(ValueError, match=erro):
        rf.cadastrar(conn, **{**base, **campos})


def test_pu_de_emissao_que_nao_bate_com_a_aplicacao_e_recusado(conn):
    """Caso real: nota da Inter com 450 unidades a R$ 0,01 — R$ 4,50 aplicados.
    Cadastrada com o pu_base padrão de R$ 1,00, a posição virava R$ 457, cem
    vezes o valor, e o custo continuava certo: nada denunciava o erro."""
    aplicar(conn, data="2026-06-18", qtd=450, preco=0.01)
    with pytest.raises(ValueError, match="ordem de grandeza"):
        rf.cadastrar(conn, ativo_id=1, emissao="2026-06-18", indexador="CDI",
                     taxa=100)                      # pu_base assume 1,00
    rf.cadastrar(conn, ativo_id=1, emissao="2026-06-18", indexador="CDI",
                 taxa=100, pu_base=0.01)
    (p,) = rf.posicao(conn, "2026-07-14")
    assert p["custo"] == pytest.approx(4.50)
    assert 4.50 < p["bruto"] < 4.60                 # rende, mas continua sendo 4,50


def test_aplicacao_depois_da_emissao_nao_dispara_a_checagem(conn):
    """Comprar um papel já emitido é normal: aí o PU da compra é maior que o de
    emissão porque o papel já rendeu."""
    aplicar(conn, data="2026-07-01", qtd=1000, preco=1.03)
    rf.cadastrar(conn, ativo_id=1, emissao="2026-01-05", indexador="CDI", taxa=100)
    assert rf.titulo(conn, 1).pu_base == 1.0


# --------------------------------------------------------------- curva

def test_pu_acompanha_a_curva(conn):
    rf.cadastrar(conn, ativo_id=1, emissao="2026-05-14", indexador="CDI", taxa=100)
    du = series.dias_uteis(conn, "2026-05-14", "2026-07-14")
    assert rf.pu(conn, 1, "2026-07-14") == pytest.approx(1.00052531 ** du, rel=1e-12)


def test_pu_base_diferente_de_um(conn):
    """Tesouro não vale R$ 1,00 na emissão: o PU inicial é parâmetro."""
    rf.cadastrar(conn, ativo_id=1, emissao="2026-05-14", indexador="PRE", taxa=12,
                 pu_base=2_079.12)
    assert rf.pu(conn, 1, "2026-05-14") == pytest.approx(2_079.12)
    assert rf.pu(conn, 1, "2026-07-14") > 2_079.12


def test_papel_para_de_render_no_vencimento(conn):
    rf.cadastrar(conn, ativo_id=1, emissao="2026-01-05", indexador="CDI", taxa=100,
                 vencimento="2026-06-30")
    no_vencimento = rf.pu(conn, 1, "2026-06-30")
    assert rf.pu(conn, 1, "2026-12-01") == pytest.approx(no_vencimento)


def test_ipca_nao_tem_curva_e_diz_o_que_fazer(conn):
    rf.cadastrar(conn, ativo_id=1, emissao="2026-05-14", indexador="IPCA", taxa=6)
    with pytest.raises(series.SerieIndisponivel, match="preço unitário à mão"):
        rf.pu(conn, 1, "2026-07-14")


# --------------------------------------------------------------- atualização

def test_curva_vira_cotacao(conn):
    """Depois disto, carteira, painel e relatórios enxergam renda fixa sem saber
    que ela é diferente."""
    rf.cadastrar(conn, ativo_id=1, emissao="2026-05-14", indexador="CDI", taxa=100)
    aplicar(conn)
    r = rf.atualizar_curvas(conn, "2026-07-14")
    assert r.atualizados == 1 and not r.falhas
    assert cotacoes.preco(conn, 1, "2026-07-14") == pytest.approx(rf.pu(conn, 1, "2026-07-14"))

    (pos,) = razao.carteira(conn, "2026-07-14")
    assert pos.ticker == "CDB5267UW6V"
    assert cotacoes.preco(conn, 1, "2026-07-14") > 1.0


def test_preco_digitado_a_mao_vence_a_curva(conn):
    """É assim que o Tesouro IPCA+, sem curva reconstruível, entra no sistema."""
    rf.cadastrar(conn, ativo_id=1, emissao="2026-05-14", indexador="CDI", taxa=100)
    cotacoes.registrar(conn, 1, "2026-07-14", 1.5, cotacoes.MANUAL)
    r = rf.atualizar_curvas(conn, "2026-07-14")
    assert r.ignorados == 1 and r.atualizados == 0
    assert cotacoes.preco(conn, 1, "2026-07-14") == pytest.approx(1.5)


def test_titulo_sem_curva_nao_derruba_os_outros(conn):
    rf.cadastrar(conn, ativo_id=1, emissao="2026-05-14", indexador="CDI", taxa=100)
    rf.cadastrar(conn, ativo_id=2, emissao="2026-05-14", indexador="IPCA", taxa=6)
    r = rf.atualizar_curvas(conn, "2026-07-14")
    assert r.atualizados == 1
    assert "LCI-INTER-2027" in r.falhas


# --------------------------------------------------------------- posição

def test_posicao_traz_rendimento_e_metadados(conn):
    rf.cadastrar(conn, ativo_id=1, emissao="2026-05-14", indexador="CDI", taxa=110,
                 vencimento="2028-05-15", emissor="BANCO XP S.A.")
    aplicar(conn, qtd=1000, preco=1.0)
    (p,) = rf.posicao(conn, "2026-07-14")
    assert p["ticker"] == "CDB5267UW6V" and p["indexador"] == "110% do CDI"
    assert p["custo"] == pytest.approx(1000)
    assert p["bruto"] > 1000 and p["rendimento"] > 0
    assert p["emissor"] == "BANCO XP S.A." and p["vencido"] is False


def test_posicao_ignora_titulo_ja_resgatado(conn):
    rf.cadastrar(conn, ativo_id=1, emissao="2026-05-14", indexador="CDI", taxa=100)
    aplicar(conn, qtd=1000)
    lanc.lancar(conn, data="2026-07-14", tipo="VENDA", ativo=1, instituicao=1,
                quantidade=1000, preco=1.05, hoje=HOJE)
    assert rf.posicao(conn, "2026-07-14") == []


# --------------------------------------------------------------- IR

@pytest.mark.parametrize("resgate, aliquota", [
    ("2026-08-01", 0.225),    # 79 dias
    ("2026-12-01", 0.20),     # 201 dias
    ("2027-08-01", 0.175),    # 444 dias
    ("2028-08-01", 0.15),     # 810 dias
])
def test_ir_segue_a_tabela_regressiva(conn, resgate, aliquota):
    rf.cadastrar(conn, ativo_id=1, emissao="2026-05-14", indexador="CDI", taxa=100)
    r = rf.ir_estimado(conn, 1, resgate, ganho=1_000)
    assert r["aliquota"] == aliquota
    assert r["imposto"] == pytest.approx(1_000 * aliquota)


def test_papel_isento_nao_paga(conn):
    rf.cadastrar(conn, ativo_id=2, emissao="2026-05-14", indexador="CDI", taxa=95,
                 isento=True)
    r = rf.ir_estimado(conn, 2, "2026-08-01", ganho=1_000)
    assert r["imposto"] == 0 and r["isento"] is True


def test_a_estimativa_se_declara_estimativa(conn):
    """O valor retido de verdade vem do extrato da corretora: este número é para
    conferir ordem de grandeza, nunca para virar guia."""
    rf.cadastrar(conn, ativo_id=1, emissao="2026-05-14", indexador="CDI", taxa=100)
    r = rf.ir_estimado(conn, 1, "2026-08-01", ganho=1_000)
    assert "extrato da corretora" in r["observacao"]


def test_prejuizo_nao_gera_imposto(conn):
    rf.cadastrar(conn, ativo_id=1, emissao="2026-05-14", indexador="CDI", taxa=100)
    assert rf.ir_estimado(conn, 1, "2026-08-01", ganho=-50)["imposto"] == 0


# --------------------------------------------------------------- migração

def test_migracao_do_esquema_antigo():
    """A `rf_titulos` da v0.1.x era chaveada pelo lançamento e nunca foi escrita."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE config (chave TEXT PRIMARY KEY, valor TEXT);
        INSERT INTO config VALUES ('esquema', '1');
        CREATE TABLE rf_titulos (lancamento_id INTEGER PRIMARY KEY, indexador TEXT,
                                 taxa REAL, vencimento TEXT, emissor TEXT,
                                 isento INTEGER NOT NULL DEFAULT 0);
    """)
    esquema.aplicar(c)
    colunas = {x[1] for x in c.execute("PRAGMA table_info(rf_titulos)")}
    assert "ativo_id" in colunas and "lancamento_id" not in colunas
    assert esquema.versao_do_banco(c) == 2


def test_migracao_recusa_descartar_dado():
    c = sqlite3.connect(":memory:")
    c.executescript("""
        CREATE TABLE config (chave TEXT PRIMARY KEY, valor TEXT);
        INSERT INTO config VALUES ('esquema', '1');
        CREATE TABLE rf_titulos (lancamento_id INTEGER PRIMARY KEY, indexador TEXT);
        INSERT INTO rf_titulos VALUES (1, 'CDI');
    """)
    with pytest.raises(RuntimeError, match="recusada para não descartar dado"):
        esquema.aplicar(c)
