"""Testes do motor de posição. Carteira sintética — extrato real nunca entra."""
import sqlite3

import pytest

import esquema
import razao


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    esquema.aplicar(c)
    c.executemany("INSERT INTO instituicoes (id, nome) VALUES (?, ?)",
                  [(1, "Alfa"), (2, "Beta")])
    c.executemany("INSERT INTO ativos (id, ticker, classe) VALUES (?, ?, ?)",
                  [(1, "PETR4", "ACAO"), (2, "MXRF11", "FII"), (3, "PETR3", "ACAO")])
    return c


def lanc(conn, data, tipo, *, ativo=1, inst=1, qtd=0, preco=0, valor=None,
         custos=0.0, irrf=0.0, destino=None, estorna=None):
    conn.execute(
        "INSERT INTO lancamentos (data, tipo, ativo_id, instituicao_id,"
        " instituicao_destino_id, quantidade, preco, valor, custos, irrf,"
        " estorna_id, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,'2026-01-01')",
        (data, tipo, ativo, inst, destino, qtd, preco,
         qtd * preco if valor is None else valor, custos, irrf, estorna))
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def evento(conn, data, tipo, fator, *, ativo=1, destino=None):
    conn.execute("INSERT INTO eventos (ativo_id, data_ex, tipo, fator,"
                 " ativo_destino_id) VALUES (?,?,?,?,?)",
                 (ativo, data, tipo, fator, destino))


# --------------------------------------------------------------- preço médio

def test_preco_medio_pondera_e_inclui_custos(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10, custos=5)
    lanc(conn, "2026-02-10", "COMPRA", qtd=100, preco=20, custos=5)
    pos = razao.apurar(conn).posicoes[1]
    assert pos.quantidade == 200
    assert pos.custo_total == pytest.approx(3010)
    assert pos.preco_medio == pytest.approx(15.05)


def test_venda_usa_preco_medio_da_data(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10)
    lanc(conn, "2026-03-01", "VENDA", qtd=40, preco=15, custos=2)
    ap = razao.apurar(conn)
    (venda,) = ap.vendas
    assert venda.natureza == razao.SWING
    assert venda.custo_base == pytest.approx(400)
    assert venda.resultado == pytest.approx(198)      # 600 - 2 de custo - 400
    assert ap.posicoes[1].quantidade == 60
    assert ap.posicoes[1].custo_total == pytest.approx(600)
    assert ap.posicoes[1].preco_medio == pytest.approx(10)   # venda não muda o médio


def test_venda_maior_que_a_posicao_e_ignorada_com_aviso(conn):
    """Importação incompleta é o caso comum: o extrato da B3 cobre uma janela e a
    compra pode ser anterior. Derrubar a apuração faria a carteira sumir da tela
    inteira por causa de uma linha — e apurar a venda com custo inventado
    produziria imposto errado. Some a venda, não o programa."""
    lanc(conn, "2026-01-05", "COMPRA", qtd=10, preco=10)
    lanc(conn, "2026-01-06", "VENDA", qtd=40, preco=12)
    ap = razao.apurar(conn)
    assert ap.vendas == []                       # fora do IR
    assert ap.posicoes[1].quantidade == 10       # e fora da posição
    assert "IGNORADA" in ap.avisos[0] and "falta o lançamento" in ap.avisos[0]


def test_uma_venda_orfa_nao_derruba_o_resto_da_carteira(conn):
    lanc(conn, "2026-01-05", "COMPRA", ativo=2, qtd=100, preco=10)
    lanc(conn, "2026-01-06", "VENDA", qtd=40, preco=12)     # ativo 1, sem compra
    carteira = {p.ticker: p for p in razao.apurar(conn).carteira()}
    assert carteira["MXRF11"].quantidade == 100


# --------------------------------------------------------------- day trade

def test_day_trade_detectado_sem_ser_declarado(conn):
    lanc(conn, "2026-04-01", "COMPRA", qtd=100, preco=10)
    lanc(conn, "2026-04-01", "VENDA", qtd=100, preco=11)
    ap = razao.apurar(conn)
    (venda,) = ap.vendas
    assert venda.natureza == razao.DAY_TRADE
    assert venda.resultado == pytest.approx(100)
    assert 1 not in {p.ativo_id for p in ap.carteira()}   # nada sobrou em carteira


def test_day_trade_convive_com_posicao_anterior(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10)
    lanc(conn, "2026-04-01", "COMPRA", qtd=50, preco=12)
    lanc(conn, "2026-04-01", "VENDA", qtd=50, preco=15)
    ap = razao.apurar(conn)
    (venda,) = ap.vendas
    assert venda.natureza == razao.DAY_TRADE
    assert venda.resultado == pytest.approx(150)          # 50 × (15 − 12)
    assert ap.posicoes[1].quantidade == 100               # o estoque velho não é tocado
    assert ap.posicoes[1].preco_medio == pytest.approx(10)


def test_day_trade_e_por_instituicao(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10, inst=1)
    lanc(conn, "2026-04-01", "COMPRA", qtd=50, preco=12, inst=1)
    lanc(conn, "2026-04-01", "VENDA", qtd=50, preco=15, inst=2)
    naturezas = {v.natureza for v in razao.apurar(conn).vendas}
    assert naturezas == {razao.SWING}   # corretoras diferentes não fecham day trade


def test_day_trade_parcial_sobra_como_swing(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10)
    lanc(conn, "2026-04-01", "COMPRA", qtd=30, preco=12)
    lanc(conn, "2026-04-01", "VENDA", qtd=50, preco=15)
    ap = razao.apurar(conn)
    dt = [v for v in ap.vendas if v.natureza == razao.DAY_TRADE]
    sw = [v for v in ap.vendas if v.natureza == razao.SWING]
    assert dt[0].quantidade == 30 and dt[0].resultado == pytest.approx(90)
    assert sw[0].quantidade == 20
    assert sw[0].resultado == pytest.approx(100)          # 20 × (15 − 10)
    assert ap.posicoes[1].quantidade == 80


# --------------------------------------------------------------- eventos

def test_desdobramento_retroativo_reescreve_o_preco_medio(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10)
    evento(conn, "2026-02-01", "DESDOBRAMENTO", 10)
    lanc(conn, "2026-03-01", "VENDA", qtd=500, preco=2)
    ap = razao.apurar(conn)
    (venda,) = ap.vendas
    assert venda.custo_base == pytest.approx(500)          # 500 × 1,00
    assert venda.resultado == pytest.approx(500)
    assert ap.posicoes[1].quantidade == 500
    assert ap.posicoes[1].preco_medio == pytest.approx(1)  # custo total intacto


def test_grupamento(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=1000, preco=1)
    evento(conn, "2026-02-01", "GRUPAMENTO", 0.1)
    pos = razao.apurar(conn).posicoes[1]
    assert pos.quantidade == 100
    assert pos.custo_total == pytest.approx(1000)
    assert pos.preco_medio == pytest.approx(10)


def test_conversao_migra_custo_e_saldo_da_instituicao(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10, ativo=1, inst=2)
    evento(conn, "2026-02-01", "CONVERSAO", 1, ativo=1, destino=3)
    ap = razao.apurar(conn)
    assert ap.posicoes[1].quantidade == 0
    assert ap.posicoes[3].quantidade == 100
    assert ap.posicoes[3].custo_total == pytest.approx(1000)
    assert ap.por_instituicao == {(3, 2): 100}


def test_evento_antes_da_compra_nao_afeta_quem_nao_tinha(conn):
    evento(conn, "2026-01-01", "DESDOBRAMENTO", 10)
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10)
    assert razao.apurar(conn).posicoes[1].quantidade == 100


# --------------------------------------------------------------- portabilidade

def test_portabilidade_nao_e_venda(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10, inst=1)
    lanc(conn, "2026-06-01", "TRANSFERENCIA", qtd=100, inst=1, destino=2)
    ap = razao.apurar(conn)
    assert ap.vendas == []                                  # nenhum lucro inventado
    assert ap.posicoes[1].custo_total == pytest.approx(1000)
    assert ap.por_instituicao == {(1, 2): 100}


def test_venda_em_corretora_sem_saldo_avisa(conn):
    """A transferência que faltou na importação: a posição global fecha, e só o
    saldo por instituição denuncia o furo."""
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10, inst=1)
    lanc(conn, "2026-07-01", "VENDA", qtd=100, preco=15, inst=2)
    ap = razao.apurar(conn)
    assert ap.vendas[0].resultado == pytest.approx(500)   # a apuração não trava
    assert "falta a transferência" in ap.avisos[0]


def test_venda_apos_portabilidade_mantem_o_custo_de_origem(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10, inst=1)
    lanc(conn, "2026-06-01", "TRANSFERENCIA", qtd=100, inst=1, destino=2)
    lanc(conn, "2026-07-01", "VENDA", qtd=100, preco=15, inst=2)
    (venda,) = razao.apurar(conn).vendas
    assert venda.custo_base == pytest.approx(1000)
    assert venda.resultado == pytest.approx(500)


# --------------------------------------------------------------- proventos

def test_bonificacao_entra_com_custo_declarado(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10)
    lanc(conn, "2026-02-01", "BONIFICACAO", qtd=10, valor=80)
    pos = razao.apurar(conn).posicoes[1]
    assert pos.quantidade == 110
    assert pos.custo_total == pytest.approx(1080)


def test_amortizacao_reduz_o_custo(conn):
    lanc(conn, "2026-01-05", "COMPRA", ativo=2, qtd=100, preco=10)
    lanc(conn, "2026-02-01", "AMORTIZACAO", ativo=2, valor=200)
    ap = razao.apurar(conn)
    assert ap.posicoes[2].custo_total == pytest.approx(800)
    assert ap.avisos == []


def test_amortizacao_acima_do_custo_avisa(conn):
    lanc(conn, "2026-01-05", "COMPRA", ativo=2, qtd=100, preco=1)
    lanc(conn, "2026-02-01", "AMORTIZACAO", ativo=2, valor=500)
    ap = razao.apurar(conn)
    assert ap.posicoes[2].custo_total == 0
    assert "excedente é ganho" in ap.avisos[0]


def test_proventos_separam_irrf(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10)
    lanc(conn, "2026-03-01", "DIVIDENDO", valor=120)
    lanc(conn, "2026-03-01", "JCP", valor=100, irrf=15)
    ap = razao.apurar(conn)
    assert {p.tipo for p in ap.proventos} == {"DIVIDENDO", "JCP"}
    assert sum(p.irrf for p in ap.proventos) == pytest.approx(15)
    assert ap.posicoes[1].custo_total == pytest.approx(1000)   # provento não mexe no custo


# --------------------------------------------------------------- estorno

def test_estorno_apaga_o_efeito_e_nao_o_registro(conn):
    id_errado = lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10)
    lanc(conn, "2026-01-05", "COMPRA", qtd=1000, preco=10)
    lanc(conn, "2026-01-06", "COMPRA", qtd=100, preco=10, estorna=id_errado)
    ap = razao.apurar(conn)
    assert ap.posicoes[1].quantidade == 1000          # sobrou só o lançamento bom
    assert conn.execute("SELECT count(*) FROM lancamentos").fetchone()[0] == 3


def test_tipo_desconhecido_falha_alto(conn):
    lanc(conn, "2026-01-05", "CHUTE", qtd=1, preco=1)
    with pytest.raises(razao.ErroDeRazao, match="desconhecido"):
        razao.apurar(conn)
