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


# ------------------------------------------- editar: anotar vs corrigir

def test_anotar_muda_so_a_observacao(conn):
    """Observação é anotação, não fato: nada em posição, preço médio ou imposto
    depende dela, e por isso é o único campo que muda no lugar."""
    ident = lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo=1,
                        instituicao=1, quantidade=100, preco=10.0)
    antes = razao.carteira(conn)

    lanc.anotar(conn, ident, "  aporte do 13º  ")
    linha = conn.execute("SELECT * FROM lancamentos WHERE id=?", (ident,)).fetchone()
    assert linha["obs"] == "aporte do 13º"          # espaços das pontas somem
    # nenhum lançamento novo, nenhum estorno, posição idêntica
    assert conn.execute("SELECT count(*) FROM lancamentos").fetchone()[0] == 1
    assert [(p.ticker, p.quantidade, p.custo_total) for p in razao.carteira(conn)] \
        == [(p.ticker, p.quantidade, p.custo_total) for p in antes]
    assert conn.execute(
        "SELECT count(*) FROM auditoria WHERE acao='ANOTAR'").fetchone()[0] == 1


def test_anotar_vazio_limpa(conn):
    ident = lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo=1,
                        instituicao=1, quantidade=100, preco=10.0, obs="algo")
    lanc.anotar(conn, ident, "   ")
    assert conn.execute("SELECT obs FROM lancamentos WHERE id=?",
                        (ident,)).fetchone()[0] is None


def test_corrigir_estorna_e_relanca(conn):
    """Número é fato, e fato não se sobrescreve: o original continua no extrato,
    o estorno anula o efeito dele e o novo entra com o valor certo."""
    ident = lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo=1,
                        instituicao=1, quantidade=100, preco=10.0)
    r = lanc.corrigir(conn, ident, preco=10.5, custos=8.22,
                      motivo="faltavam os custos da nota")

    # as três linhas convivem: original, estorno e novo
    assert conn.execute("SELECT count(*) FROM lancamentos").fetchone()[0] == 3
    assert conn.execute("SELECT estorna_id FROM lancamentos WHERE id=?",
                        (r["estorno"],)).fetchone()[0] == ident
    (p,) = razao.carteira(conn)
    assert p.quantidade == 100
    assert p.custo_total == pytest.approx(1058.22)   # 100 × 10,50 + 8,22

    # o que não foi passado vem do original
    novo = conn.execute("SELECT * FROM lancamentos WHERE id=?", (r["novo"],)).fetchone()
    assert (novo["data"], novo["tipo"], novo["quantidade"]) == ("2026-01-05",
                                                                "COMPRA", 100)
    assert conn.execute(
        "SELECT count(*) FROM auditoria WHERE acao='CORRIGIR'").fetchone()[0] == 1


def test_corrigir_recusa_campo_que_nao_existe(conn):
    ident = lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo=1,
                        instituicao=1, quantidade=100, preco=10.0)
    with pytest.raises(lanc.DadoInvalido, match="não corrigível"):
        lanc.corrigir(conn, ident, hash_origem="x")


def test_corrigir_duas_vezes_usa_o_lancamento_novo(conn):
    """Corrigir o que já foi corrigido é corrigir o estornado — e isso o estorno
    já barra. A segunda correção tem de partir do lançamento novo."""
    ident = lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo=1,
                        instituicao=1, quantidade=100, preco=10.0)
    r = lanc.corrigir(conn, ident, preco=10.5)
    with pytest.raises(lanc.DadoInvalido, match="já foi estornado"):
        lanc.corrigir(conn, ident, preco=11.0)

    r2 = lanc.corrigir(conn, r["novo"], preco=11.0)
    (p,) = razao.carteira(conn)
    assert p.custo_total == pytest.approx(1100.0)
    assert r2["novo"] != r["novo"]


def test_a_origem_diz_que_o_lancamento_e_correcao(conn):
    ident = lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo=1,
                        instituicao=1, quantidade=100, preco=10.0)
    r = lanc.corrigir(conn, ident, preco=10.5)
    assert conn.execute("SELECT origem FROM lancamentos WHERE id=?",
                        (r["novo"],)).fetchone()[0] == f"CORRIGE_{ident}"


def test_corrigir_preserva_o_hash_no_original(conn):
    """O `hash_origem` fica com o original de propósito: assim reimportar o
    mesmo arquivo continua reconhecendo a linha como já vista, em vez de criar
    uma terceira cópia."""
    conn.execute(
        "INSERT INTO lancamentos (data, tipo, ativo_id, instituicao_id, quantidade,"
        " preco, valor, origem, hash_origem, criado_em)"
        " VALUES ('2026-01-05','COMPRA',1,1,100,10,1000,'B3_NEGOCIACAO','h1','x')")
    ident = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    r = lanc.corrigir(conn, ident, custos=8.22)
    assert conn.execute("SELECT hash_origem FROM lancamentos WHERE id=?",
                        (ident,)).fetchone()[0] == "h1"
    assert conn.execute("SELECT hash_origem FROM lancamentos WHERE id=?",
                        (r["novo"],)).fetchone()[0] is None


def test_corrigir_provento_nao_recalcula_o_valor(conn):
    """Em provento o valor é o dado principal e a quantidade é informativa:
    recalcular de quantidade × preço zeraria o lançamento."""
    ident = lanc.lancar(conn, data="2026-05-15", tipo="RENDIMENTO", ativo=1,
                        instituicao=1, valor=12.0)
    r = lanc.corrigir(conn, ident, quantidade=100)
    novo = conn.execute("SELECT quantidade, valor FROM lancamentos WHERE id=?",
                        (r["novo"],)).fetchone()
    assert (novo["quantidade"], novo["valor"]) == (100, 12.0)
