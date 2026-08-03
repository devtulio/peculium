"""Testes da apuração de IR. Carteira sintética — extrato real nunca entra."""
import pytest

import fisco
import razao


def venda(data, *, classe="ACAO", bruto, custo_base, natureza=razao.SWING,
          custos=0.0, irrf=0.0, qtd=100):
    return razao.Venda(data, 1, "TICK4", classe, 1, qtd, bruto, custos, irrf,
                       custo_base, natureza)


def apurar(*vendas):
    return fisco.apurar(razao.Apuracao(vendas=list(vendas)))


# --------------------------------------------------------------- isenção

def test_isencao_ate_20_mil():
    f = apurar(venda("2026-03-10", bruto=19_000, custo_base=15_000))
    (isencao,) = f.isencoes
    assert isencao.aplicada and isencao.resultado_isento == pytest.approx(4_000)
    assert f.baldes == [] and f.darfs == []


def test_acima_de_20_mil_tributa_o_ganho_inteiro():
    """O limite não é faixa: passou de R$ 20 mil, tributa tudo, não só o excesso."""
    f = apurar(venda("2026-03-10", bruto=20_000.01, custo_base=15_000))
    (b,) = f.baldes
    assert b.balde == fisco.SWING
    assert b.base == pytest.approx(5_000.01)
    assert b.imposto == pytest.approx(750.0015)
    assert f.isencoes[0].aplicada is False


def test_limite_conta_o_bruto_e_nao_o_liquido():
    """Bruto 20.010 com 50 de custo dá líquido de 19.960 — dentro do limite se
    alguém olhar o líquido. A Receita olha o valor da alienação: estoura."""
    f = apurar(venda("2026-03-10", bruto=20_010, custos=50, custo_base=15_000))
    assert f.isencoes[0].aplicada is False
    assert f.baldes[0].imposto > 0
    # 20.000 exatos ainda estão dentro: o limite é "até", não "abaixo de"
    no_limite = apurar(venda("2026-03-10", bruto=20_000, custos=50, custo_base=15_000))
    assert no_limite.isencoes[0].aplicada is True


def test_limite_soma_as_vendas_do_mes():
    f = apurar(venda("2026-03-05", bruto=12_000, custo_base=10_000),
               venda("2026-03-20", bruto=9_000, custo_base=8_000))
    assert f.isencoes[0].aplicada is False
    assert f.baldes[0].resultado == pytest.approx(3_000)


def test_etf_nao_tem_isencao_mas_compensa_com_acoes():
    f = apurar(venda("2026-03-10", classe="ETF", bruto=5_000, custo_base=6_000),
               venda("2026-04-10", bruto=25_000, custo_base=20_000))
    marco, abril = f.baldes
    assert marco.resultado == pytest.approx(-1_000)     # prejuízo do ETF entra
    assert abril.compensado == pytest.approx(1_000)     # e abate o ganho da ação
    assert abril.base == pytest.approx(4_000)


def test_prejuizo_isento_nao_compensa_mas_fica_registrado():
    f = apurar(venda("2026-03-10", bruto=5_000, custo_base=8_000),
               venda("2026-04-10", bruto=25_000, custo_base=20_000))
    assert f.isencoes[0].prejuizo_descartado == pytest.approx(3_000)
    assert "entendimento da RFB" in f.avisos[0]
    (abril,) = f.baldes
    assert abril.compensado == 0 and abril.base == pytest.approx(5_000)


# --------------------------------------------------------------- baldes

def test_day_trade_nao_compensa_com_swing():
    f = apurar(venda("2026-03-10", bruto=30_000, custo_base=40_000,
                     natureza=razao.DAY_TRADE),
               venda("2026-04-10", bruto=30_000, custo_base=20_000))
    abril = [b for b in f.baldes if b.competencia == "2026-04"]
    (swing,) = [b for b in abril if b.balde == fisco.SWING]
    assert swing.compensado == 0                        # o prejuízo de DT não entra
    assert swing.base == pytest.approx(10_000)
    assert f.prejuizo[fisco.DAY_TRADE] == pytest.approx(10_000)


def test_day_trade_tem_aliquota_de_20():
    f = apurar(venda("2026-03-10", bruto=30_000, custo_base=20_000,
                     natureza=razao.DAY_TRADE))
    (b,) = f.baldes
    assert b.balde == fisco.DAY_TRADE and b.imposto == pytest.approx(2_000)


def test_renda_fixa_fica_fora_da_apuracao_mensal():
    """Resgate de CDB caindo no balde swing geraria DARF de 15% sobre rendimento
    que já foi tributado na fonte — imposto pago duas vezes."""
    f = apurar(venda("2026-03-10", classe="RF", bruto=11_000, custo_base=10_000),
               venda("2026-03-11", classe="TESOURO", bruto=5_000, custo_base=4_800))
    assert f.baldes == [] and f.darfs == []
    assert len(f.exclusiva) == 2
    assert any("retido na fonte" in a for a in f.avisos)


def test_renda_fixa_nao_contamina_o_prejuizo_das_acoes():
    f = apurar(venda("2026-03-10", classe="RF", bruto=5_000, custo_base=9_000),
               venda("2026-04-10", bruto=30_000, custo_base=20_000))
    (swing,) = f.baldes
    assert swing.compensado == 0            # prejuízo de RF não compensa ação
    assert swing.base == pytest.approx(10_000)


@pytest.mark.parametrize("dias, esperado", [
    (1, 0.225), (180, 0.225), (181, 0.20), (360, 0.20),
    (361, 0.175), (720, 0.175), (721, 0.15), (3000, 0.15),
])
def test_tabela_regressiva(dias, esperado):
    assert fisco.aliquota_regressiva(dias) == esperado


def test_fii_e_balde_proprio_sem_isencao():
    f = apurar(venda("2026-03-10", classe="FII", bruto=5_000, custo_base=4_000))
    (b,) = f.baldes
    assert b.balde == fisco.FII
    assert b.imposto == pytest.approx(200)              # 20% de 1.000, sem isenção
    assert f.isencoes == []


def test_fii_em_day_trade_continua_no_balde_de_fii():
    f = apurar(venda("2026-03-10", classe="FII", bruto=5_000, custo_base=6_000,
                     natureza=razao.DAY_TRADE),
               venda("2026-04-10", classe="FII", bruto=9_000, custo_base=8_000))
    assert {b.balde for b in f.baldes} == {fisco.FII}
    assert f.baldes[1].compensado == pytest.approx(1_000)


def test_prejuizo_atravessa_meses_e_anos():
    f = apurar(venda("2026-11-10", bruto=25_000, custo_base=40_000),
               venda("2027-05-10", bruto=30_000, custo_base=20_000))
    seguinte = f.baldes[1]
    assert seguinte.prejuizo_anterior == pytest.approx(15_000)
    assert seguinte.compensado == pytest.approx(10_000)  # compensa até zerar o ganho
    assert seguinte.base == 0 and seguinte.imposto == 0
    assert f.prejuizo[fisco.SWING] == pytest.approx(5_000)


# --------------------------------------------------------------- IRRF e DARF

def test_irrf_deduz_e_o_excedente_atravessa_o_mes():
    f = apurar(venda("2026-03-10", bruto=30_000, custo_base=29_000, irrf=300,
                     natureza=razao.DAY_TRADE),
               venda("2026-04-10", bruto=30_000, custo_base=20_000,
                     natureza=razao.DAY_TRADE))
    marco, abril = f.baldes
    assert marco.imposto == pytest.approx(200) and marco.a_pagar == 0
    assert marco.irrf_acumulado == pytest.approx(100)   # sobrou e não se perde
    assert abril.irrf == pytest.approx(100)
    assert abril.a_pagar == pytest.approx(2_000 - 100)


def test_darf_abaixo_do_piso_acumula():
    f = apurar(venda("2026-03-10", bruto=25_000, custo_base=24_960))
    assert f.darfs == []
    assert f.acumulado_pendente == pytest.approx(6.0)   # 15% de 40
    assert "acumula para o mês seguinte" in f.avisos[0]


def test_acumulado_entra_no_darf_seguinte():
    f = apurar(venda("2026-03-10", bruto=25_000, custo_base=24_960),
               venda("2026-04-10", bruto=25_000, custo_base=24_900))
    (darf,) = f.darfs
    assert darf.competencia == "2026-04"
    assert darf.de_meses_anteriores == pytest.approx(6.0)
    assert darf.valor == pytest.approx(21.0)            # 6 de março + 15 de abril
    assert f.acumulado_pendente == 0


def test_mes_sem_imposto_novo_nao_repete_o_aviso():
    f = apurar(venda("2026-03-10", bruto=25_000, custo_base=24_960),
               venda("2026-04-10", bruto=25_000, custo_base=30_000))
    assert len(f.avisos) == 1
    assert f.acumulado_pendente == pytest.approx(6.0)   # segue pendente, intacto


def test_darf_soma_os_baldes_do_mes():
    f = apurar(venda("2026-03-10", bruto=30_000, custo_base=20_000),
               venda("2026-03-11", classe="FII", bruto=9_000, custo_base=4_000))
    (darf,) = f.darfs
    assert darf.composicao == {fisco.SWING: 1_500.0, fisco.FII: 1_000.0}
    assert darf.valor == pytest.approx(2_500)
    assert darf.codigo == "6015"


# --------------------------------------------------------------- vencimento

@pytest.mark.parametrize("competencia, esperado", [
    ("2026-03", "2026-04-30"),   # quinta-feira
    ("2026-04", "2026-05-29"),   # 31/05 é domingo, recua para sexta
    ("2026-12", "2027-01-29"),   # vira o ano; 31/01 é domingo
    ("2027-01", "2027-02-26"),   # 28/02 é domingo
])
def test_vencimento_e_o_ultimo_dia_util_do_mes_seguinte(competencia, esperado):
    assert fisco.vencimento(competencia) == esperado


def test_integracao_com_o_razao(tmp_path):
    """A ponte que importa: o que o razão produz precisa entrar no fisco sem
    tradução no meio."""
    import sqlite3

    import esquema
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    esquema.aplicar(conn)
    conn.execute("INSERT INTO instituicoes (id, nome) VALUES (1, 'Alfa')")
    conn.execute("INSERT INTO ativos (id, ticker, classe) VALUES (1, 'PETR4', 'ACAO')")
    conn.executemany(
        "INSERT INTO lancamentos (data, tipo, ativo_id, instituicao_id, quantidade,"
        " preco, valor, custos, criado_em) VALUES (?,?,1,1,?,?,?,?,'2026-01-01')",
        [("2026-01-05", "COMPRA", 1000, 20, 20_000, 10),
         ("2026-06-10", "VENDA", 1000, 30, 30_000, 10)])
    f = fisco.apurar(razao.apurar(conn))
    (b,) = f.baldes
    assert b.resultado == pytest.approx(9_980)          # 30.000 − 10 − 20.010
    assert f.darfs[0].valor == pytest.approx(1_497.0)
