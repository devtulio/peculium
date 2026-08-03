"""Testes do controle de contas a pagar dos DARF."""
import sqlite3

import pytest

import esquema
import obrigacoes
import relatorios


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    esquema.aplicar(c)
    c.execute("INSERT INTO instituicoes (id, nome) VALUES (1,'Alfa')")
    c.execute("INSERT INTO ativos (id, ticker, classe) VALUES (1,'PETR4','ACAO')")
    return c


def com_darf(conn, venda="2026-06-10"):
    """Venda que gera DARF de R$ 1.500. Por padrão na competência 06/2026,
    vencendo em 31/07; `venda` move a competência para testar atraso longo."""
    conn.executemany(
        "INSERT INTO lancamentos (data, tipo, ativo_id, instituicao_id, quantidade,"
        " preco, valor, criado_em) VALUES (?,?,1,1,?,?,?,'2026-01-01')",
        [("2026-01-05", "COMPRA", 1000, 20, 20_000),
         (venda, "VENDA", 1000, 30, 30_000)])
    return conn


# --------------------------------------------------------------- situações

def test_darf_apurado_e_nao_pago_fica_pendente(conn):
    com_darf(conn)
    (o,) = obrigacoes.listar(conn, hoje="2026-07-01")
    assert o.situacao == obrigacoes.PENDENTE
    assert o.competencia == "2026-06" and o.vencimento == "2026-07-31"
    assert o.valor_apurado == pytest.approx(1_500)
    assert o.total_a_pagar == pytest.approx(1_500)
    assert o.multa == 0


def test_pagamento_que_bate_fecha_a_obrigacao(conn):
    com_darf(conn)
    obrigacoes.registrar(conn, "2026-06", 1_500.0, "2026-07-30")
    (o,) = obrigacoes.listar(conn, hoje="2026-08-01")
    assert o.situacao == obrigacoes.PAGO
    assert o.total_a_pagar == 0 and o.data_pagamento == "2026-07-30"


def test_apuracao_que_sobe_depois_do_pagamento_vira_parcial(conn):
    """O caso que justifica o módulo: a nota de corretagem entra depois, o custo
    muda, e o que foi pago deixa de bater."""
    com_darf(conn)
    obrigacoes.registrar(conn, "2026-06", 1_500.0, "2026-07-30")
    assert obrigacoes.listar(conn, hoje="2026-08-01")[0].situacao == obrigacoes.PAGO

    # lançamento retroativo reduz o custo de aquisição e aumenta o ganho
    conn.execute("UPDATE lancamentos SET valor = 19000, preco = 19"
                 " WHERE tipo='COMPRA'")
    (o,) = obrigacoes.listar(conn, hoje="2026-08-01")
    assert o.situacao == obrigacoes.PARCIAL
    assert o.valor_apurado == pytest.approx(1_650)
    assert o.total_a_pagar == pytest.approx(150)
    assert any("apuração subiu depois de pago" in t for t in o.observacoes)


def test_apuracao_que_cai_depois_do_pagamento_vira_a_maior(conn):
    com_darf(conn)
    obrigacoes.registrar(conn, "2026-06", 1_500.0, "2026-07-30")
    conn.execute("UPDATE lancamentos SET valor = 21000, preco = 21"
                 " WHERE tipo='COMPRA'")
    (o,) = obrigacoes.listar(conn, hoje="2026-08-01")
    assert o.situacao == obrigacoes.A_MAIOR
    assert o.total_a_pagar == 0
    assert any("a maior" in t for t in o.observacoes)


def test_pagamento_orfao_aparece_em_vez_de_sumir(conn):
    """Se a apuração deixou de gerar DARF, o pagamento registrado não pode
    simplesmente desaparecer da tela."""
    obrigacoes.registrar(conn, "2026-06", 1_500.0, "2026-07-30")
    (o,) = obrigacoes.listar(conn, hoje="2026-08-01")
    assert o.situacao == obrigacoes.A_MAIOR and o.valor_apurado == 0
    assert any("não gera DARF" in t for t in o.observacoes)


def test_parcelas_somam(conn):
    com_darf(conn)
    obrigacoes.registrar(conn, "2026-06", 1_000.0, "2026-07-30")
    obrigacoes.registrar(conn, "2026-06", 500.0, "2026-08-05")
    (o,) = obrigacoes.listar(conn, hoje="2026-08-10")
    assert o.situacao == obrigacoes.PAGO
    assert any("2 pagamentos somados" in t for t in o.observacoes)


def test_abaixo_do_piso_aparece_como_acumulando(conn):
    conn.executemany(
        "INSERT INTO lancamentos (data, tipo, ativo_id, instituicao_id, quantidade,"
        " preco, valor, criado_em) VALUES (?,?,1,1,?,?,?,'2026-01-01')",
        [("2026-01-05", "COMPRA", 1000, 24.96, 24_960),
         ("2026-06-10", "VENDA", 1000, 25, 25_000)])
    (o,) = obrigacoes.listar(conn, hoje="2026-08-01")
    assert o.situacao == obrigacoes.ACUMULANDO
    assert o.vencimento == "" and o.total_a_pagar == 0
    assert any("não vence e não some" in t for t in o.observacoes)


# --------------------------------------------------------------- mora

def test_vencido_calcula_multa_de_mora(conn):
    com_darf(conn)
    (o,) = obrigacoes.listar(conn, hoje="2026-08-10")
    assert o.situacao == obrigacoes.VENCIDO
    assert o.dias_atraso == 10
    assert o.multa == pytest.approx(1_500 * 0.033, abs=0.01)   # 0,33% × 10 dias
    # vencimento 31/07 e pagamento em 08: nenhum mês inteiro de atraso, então a
    # Selic não entra — só o 1% do mês do pagamento
    assert o.juros == pytest.approx(15.00)
    assert o.total_a_pagar == pytest.approx(1_500 + o.multa + 15.00)


@pytest.mark.parametrize("dias, esperado", [
    (0, 0.0), (1, 3.30), (10, 33.0), (60, 198.0),
    (61, 200.0),      # 0,33% × 61 = 20,13% — o teto de 20% corta
    (365, 200.0),
])
def test_multa_tem_teto_de_20_por_cento(dias, esperado):
    from datetime import date, timedelta
    vencimento = date(2026, 7, 31)
    pagamento = (vencimento + timedelta(days=dias)).isoformat()
    _, multa, _ = obrigacoes.encargos(1_000, vencimento.isoformat(), pagamento)
    assert multa == pytest.approx(esperado, abs=0.01)


# ------------------------------------------------------- juros de mora (§3)

def com_selic(conn, **taxas):
    """Selic acumulada no mês, em % ao mês, como o BCB publica na série 4390."""
    conn.executemany(
        "INSERT OR REPLACE INTO series (indice, data, valor) VALUES (?,?,?)",
        [(obrigacoes.SERIE_JUROS, f"{c}-01", v) for c, v in taxas.items()])


@pytest.mark.parametrize("vencimento, pagamento, esperado", [
    # pagar no próprio mês do vencimento: nem multa nem juros
    ("2026-07-31", "2026-07-31", []),
    # mês seguinte: nenhum mês inteiro de atraso — só o 1% do mês do pagamento
    ("2026-07-31", "2026-08-10", []),
    ("2026-03-31", "2026-08-10", ["2026-04", "2026-05", "2026-06", "2026-07"]),
    # virada de ano
    ("2025-11-28", "2026-02-05", ["2025-12", "2026-01"]),
])
def test_meses_que_entram_na_conta(vencimento, pagamento, esperado):
    """Do mês **seguinte** ao vencimento até o **anterior** ao do pagamento.

    Errar uma ponta cobra juros de um mês que a lei não cobra, ou deixa de
    cobrar um que ela cobra."""
    assert obrigacoes.meses_de_juros(vencimento, pagamento) == esperado


def test_juros_somam_selic_mensal_mais_um_por_cento(conn):
    """Somam-se as taxas mensais; não se capitaliza (art. 61 §3)."""
    com_selic(conn, **{"2026-04": 1.00, "2026-05": 1.10,
                       "2026-06": 1.05, "2026-07": 1.15})
    taxa, faltando = obrigacoes.taxa_de_juros(conn, "2026-03-31", "2026-08-10")
    assert faltando == []
    assert taxa == pytest.approx(0.0530)            # 4,30% + 1% do mês do pagamento
    assert obrigacoes.encargos(1_000, "2026-03-31", "2026-08-10", conn)[2] \
        == pytest.approx(53.00)


def test_mes_do_pagamento_entra_com_um_por_cento_fixo(conn):
    """O 1% é do mês do pagamento e não depende de série nenhuma."""
    taxa, faltando = obrigacoes.taxa_de_juros(conn, "2026-07-31", "2026-08-10")
    assert (taxa, faltando) == (0.01, [])


def test_mes_faltando_na_serie_recusa_calcular(conn):
    """Juros a menos numa guia é diferença que a Receita cobra depois: melhor
    dizer que não sabe do que devolver um número menor que a verdade."""
    com_selic(conn, **{"2026-04": 1.00, "2026-06": 1.05, "2026-07": 1.15})
    taxa, faltando = obrigacoes.taxa_de_juros(conn, "2026-03-31", "2026-08-10")
    assert (taxa, faltando) == (0.0, ["2026-05"])
    assert obrigacoes.encargos(1_000, "2026-03-31", "2026-08-10", conn)[2] is None


def test_sem_conexao_os_juros_ficam_em_aberto():
    """`encargos` sem banco continua servindo para quem só quer a multa."""
    assert obrigacoes.encargos(1_000, "2026-03-31", "2026-08-10")[2] is None


def test_a_tela_diz_qual_mes_falta(conn):
    com_darf(conn, venda="2026-02-10")      # DARF de 02/2026, vence 31/03
    com_selic(conn, **{"2026-04": 1.00, "2026-06": 1.05})
    (o,) = obrigacoes.listar(conn, hoje="2026-08-10")
    assert o.juros is None
    assert any("05/2026" in obs and "07/2026" in obs for obs in o.observacoes)


def test_pagar_no_vencimento_nao_gera_multa():
    assert obrigacoes.encargos(1_000, "2026-07-31", "2026-07-31") == (0, 0.0, 0.0)


# --------------------------------------------------------------- painel

def test_a_vencer_pega_janela_e_vencido(conn):
    com_darf(conn)
    assert obrigacoes.a_vencer(conn, dias=15, hoje="2026-07-01") == []
    assert len(obrigacoes.a_vencer(conn, dias=15, hoje="2026-07-20")) == 1
    assert len(obrigacoes.a_vencer(conn, dias=15, hoje="2026-09-01")) == 1  # vencido


def test_a_vencer_ignora_o_que_ja_foi_pago(conn):
    com_darf(conn)
    obrigacoes.registrar(conn, "2026-06", 1_500.0, "2026-07-20")
    assert obrigacoes.a_vencer(conn, dias=15, hoje="2026-07-25") == []


# --------------------------------------------------------------- registro

def test_registrar_recusa_valor_invalido(conn):
    with pytest.raises(ValueError, match="valor positivo"):
        obrigacoes.registrar(conn, "2026-06", 0, "2026-07-30")
    with pytest.raises(ValueError):
        obrigacoes.registrar(conn, "2026-06", 10, "30/07/2026")   # data é ISO


def test_cancelar_pagamento(conn):
    com_darf(conn)
    identificador = obrigacoes.registrar(conn, "2026-06", 1_500.0, "2026-07-30")
    assert obrigacoes.cancelar(conn, identificador) is True
    assert obrigacoes.listar(conn, hoje="2026-08-01")[0].situacao == obrigacoes.VENCIDO
    assert obrigacoes.cancelar(conn, 9999) is False


# --------------------------------------------------------------- relatório

def test_relatorio_em_formato_brasileiro(conn):
    com_darf(conn)
    rel = relatorios.obrigacoes(conn, hoje="2026-08-10")
    (linha,) = rel.linhas
    assert linha[0] == "06/2026" and linha[2] == "31/07/2026"
    assert linha[6] == obrigacoes.VENCIDO
    assert any("Total em aberto" in t for t in rel.rodape)
    assert any("vencida" in t for t in rel.rodape)
