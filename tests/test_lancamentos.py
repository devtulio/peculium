"""Testes da entrada manual — a porta que a UI vai usar."""
import sqlite3

import pytest

import esquema
import lancamentos as lanc
import razao

HOJE = "2026-08-03"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    esquema.aplicar(c)
    c.executemany("INSERT INTO instituicoes (id, nome) VALUES (?,?)",
                  [(1, "Alfa"), (2, "Beta")])
    c.executemany("INSERT INTO ativos (id, ticker, classe) VALUES (?,?,?)",
                  [(1, "PETR4", "ACAO"), (2, "PETR3", "ACAO")])
    return c


# --------------------------------------------------------------- caminho feliz

def test_compra_pelo_ticker_e_pelo_nome_da_instituicao(conn):
    identificador = lanc.lancar(conn, data="05/01/2026", tipo="compra",
                                ativo="petr4", instituicao="alfa",
                                quantidade=100, preco=10, custos=5, hoje=HOJE)
    linha = conn.execute("SELECT * FROM lancamentos WHERE id=?",
                         (identificador,)).fetchone()
    assert linha["data"] == "2026-01-05"        # aceita BR, guarda ISO
    assert linha["tipo"] == "COMPRA" and linha["origem"] == "MANUAL"
    assert linha["valor"] == pytest.approx(1000)   # calculado de qtd × preço
    (pos,) = razao.carteira(conn)
    assert pos.custo_total == pytest.approx(1005)


def test_provento_dispensa_instituicao(conn):
    lanc.lancar(conn, data="2026-03-01", tipo="DIVIDENDO", ativo="PETR4",
                valor=120, hoje=HOJE)
    (p,) = razao.apurar(conn).proventos
    assert p.tipo == "DIVIDENDO" and p.valor == 120


def test_transferencia_precisa_de_destino_diferente(conn):
    lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo="PETR4",
                instituicao="Alfa", quantidade=100, preco=10, hoje=HOJE)
    lanc.lancar(conn, data="2026-06-01", tipo="TRANSFERENCIA", ativo="PETR4",
                instituicao="Alfa", destino="Beta", quantidade=100, hoje=HOJE)
    ap = razao.apurar(conn)
    assert ap.vendas == [] and ap.por_instituicao == {(1, 2): 100}

    with pytest.raises(lanc.DadoInvalido, match="instituições diferentes"):
        lanc.lancar(conn, data="2026-06-02", tipo="TRANSFERENCIA", ativo="PETR4",
                    instituicao="Alfa", destino="Alfa", quantidade=1, hoje=HOJE)


def test_todo_tipo_aceito_aqui_e_entendido_pelo_razao(conn):
    """Guarda contra as duas listas divergirem: o que esta porta aceita, o motor
    tem de saber processar."""
    comuns = dict(instituicao="Alfa", hoje=HOJE)
    lanc.lancar(conn, data="2026-01-02", tipo="COMPRA", ativo="PETR4",
                quantidade=1000, preco=10, **comuns)
    for tipo in lanc.TIPOS:
        if tipo == "COMPRA":
            continue
        argumentos = dict(comuns, data="2026-02-02", tipo=tipo)
        if tipo in lanc.NEGOCIO:
            argumentos.update(ativo="PETR4", quantidade=1, preco=10)
        elif tipo == lanc.TRANSFERENCIA:
            argumentos.update(ativo="PETR4", quantidade=1, destino="Beta")
        elif tipo in lanc.POSICAO:
            argumentos.update(ativo="PETR4", quantidade=1, valor=10)
        elif tipo in lanc.PROVENTO:
            argumentos.update(ativo="PETR4", valor=10)
        else:
            argumentos.update(valor=10)
        lanc.lancar(conn, **argumentos)
    razao.apurar(conn)                          # não pode levantar ErroDeRazao


# --------------------------------------------------------------- validação

def test_recusa_data_no_futuro(conn):
    """Lançamento no futuro corrompe em silêncio toda pergunta sobre a posição
    de hoje."""
    with pytest.raises(lanc.DadoInvalido, match="futuro"):
        lanc.lancar(conn, data="2026-09-01", tipo="COMPRA", ativo="PETR4",
                    instituicao="Alfa", quantidade=1, preco=1, hoje=HOJE)


@pytest.mark.parametrize("campos, erro", [
    (dict(tipo="EMPRESTIMO"), "tipo desconhecido"),
    (dict(ativo="XXXX9"), "não cadastrado"),
    (dict(instituicao="Gama"), "não cadastrada"),
    (dict(quantidade=0), "quantidade"),
    (dict(preco=0), "preço"),
    (dict(quantidade=-5), "quantidade"),
    (dict(custos=-1), "negativos"),
    (dict(data="ontem"), "irreconhecível"),
])
def test_recusa_preenchimento_invalido(conn, campos, erro):
    base = dict(data="2026-01-05", tipo="COMPRA", ativo="PETR4",
                instituicao="Alfa", quantidade=10, preco=10, hoje=HOJE)
    with pytest.raises(lanc.DadoInvalido, match=erro):
        lanc.lancar(conn, **{**base, **campos})


def test_provento_sem_valor_e_recusado(conn):
    with pytest.raises(lanc.DadoInvalido, match="valor"):
        lanc.lancar(conn, data="2026-03-01", tipo="JCP", ativo="PETR4", hoje=HOJE)


def test_subscricao_exige_o_valor_pago(conn):
    with pytest.raises(lanc.DadoInvalido, match="valor pago"):
        lanc.lancar(conn, data="2026-03-01", tipo="SUBSCRICAO", ativo="PETR4",
                    quantidade=10, hoje=HOJE)


# --------------------------------------------------------------- estorno

def test_estorno_anula_o_efeito_e_preserva_o_registro(conn):
    errado = lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo="PETR4",
                         instituicao="Alfa", quantidade=1000, preco=10, hoje=HOJE)
    lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo="PETR4",
                instituicao="Alfa", quantidade=100, preco=10, hoje=HOJE)
    lanc.estornar(conn, errado, motivo="quantidade digitada errada")
    (pos,) = razao.carteira(conn)
    assert pos.quantidade == 100
    assert conn.execute("SELECT count(*) FROM lancamentos").fetchone()[0] == 3


def test_nao_estorna_duas_vezes_nem_estorna_estorno(conn):
    identificador = lanc.lancar(conn, data="2026-01-05", tipo="COMPRA",
                                ativo="PETR4", instituicao="Alfa",
                                quantidade=10, preco=10, hoje=HOJE)
    espelho = lanc.estornar(conn, identificador)
    with pytest.raises(lanc.DadoInvalido, match="já foi estornado"):
        lanc.estornar(conn, identificador)
    with pytest.raises(lanc.DadoInvalido, match="já é um estorno"):
        lanc.estornar(conn, espelho)
    with pytest.raises(lanc.DadoInvalido, match="não existe"):
        lanc.estornar(conn, 9999)


# --------------------------------------------------------------- eventos

def test_desdobramento_cadastrado_reescreve_o_preco_medio(conn):
    """O evento estava implementado no razão e era inalcançável: não havia como
    cadastrar um."""
    lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo="PETR4",
                instituicao="Alfa", quantidade=100, preco=10, hoje=HOJE)
    lanc.registrar_evento(conn, ativo="PETR4", data_ex="01/02/2026",
                          tipo="desdobramento", fator=10, hoje=HOJE)
    (pos,) = razao.carteira(conn)
    assert pos.quantidade == 1000
    assert pos.preco_medio == pytest.approx(1.0)
    assert pos.custo_total == pytest.approx(1000)


def test_conversao_exige_destino_diferente(conn):
    with pytest.raises(lanc.DadoInvalido, match="precisa do ativo de destino"):
        lanc.registrar_evento(conn, ativo="PETR4", data_ex="2026-02-01",
                              tipo="CONVERSAO", fator=1, hoje=HOJE)
    with pytest.raises(lanc.DadoInvalido, match="destino diferente"):
        lanc.registrar_evento(conn, ativo="PETR4", data_ex="2026-02-01",
                              tipo="CONVERSAO", fator=1, destino="PETR4", hoje=HOJE)


def test_fator_precisa_ser_positivo(conn):
    with pytest.raises(lanc.DadoInvalido, match="fator"):
        lanc.registrar_evento(conn, ativo="PETR4", data_ex="2026-02-01",
                              tipo="GRUPAMENTO", fator=0, hoje=HOJE)


def test_remover_evento(conn):
    lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo="PETR4",
                instituicao="Alfa", quantidade=100, preco=10, hoje=HOJE)
    evento = lanc.registrar_evento(conn, ativo="PETR4", data_ex="2026-02-01",
                                   tipo="DESDOBRAMENTO", fator=10, hoje=HOJE)
    assert lanc.remover_evento(conn, evento) is True
    assert razao.carteira(conn)[0].quantidade == 100
    assert lanc.remover_evento(conn, evento) is False


# --------------------------------------------------------------- auditoria

def test_toda_gravacao_deixa_rastro(conn):
    identificador = lanc.lancar(conn, data="2026-01-05", tipo="COMPRA",
                                ativo="PETR4", instituicao="Alfa",
                                quantidade=100, preco=10, hoje=HOJE)
    lanc.estornar(conn, identificador, motivo="engano")
    lanc.registrar_evento(conn, ativo="PETR4", data_ex="2026-02-01",
                          tipo="GRUPAMENTO", fator=0.1, hoje=HOJE)
    acoes = [r["acao"] for r in lanc.historico(conn)]
    assert acoes == ["EVENTO", "ESTORNAR", "LANCAR"]     # mais recente primeiro
    assert "engano" in lanc.historico(conn)[1]["detalhe"]
    assert "05/01/2026" in lanc.historico(conn)[2]["detalhe"]   # data em BR


def test_aquisicao_sem_custo_entra_como_bonificacao(conn):
    """Papel recebido de presente existe: um BDR que o banco deu de brinde.

    COMPRA recusa preço zero — e recusa com razão, porque compra a zero quase
    sempre é dedo errado. O caminho é BONIFICAÇÃO, e é o que os avisos apontam."""
    with pytest.raises(lanc.DadoInvalido, match="maior que zero"):
        lanc.lancar(conn, data="2026-05-27", tipo="COMPRA", ativo=1,
                    instituicao=1, quantidade=1, preco=0)

    lanc.lancar(conn, data="2026-05-27", tipo="BONIFICACAO", ativo=1,
                instituicao=1, quantidade=1, valor=0)
    (p,) = razao.carteira(conn)
    assert (p.quantidade, p.custo_total, p.preco_medio) == (1, 0.0, 0.0)
