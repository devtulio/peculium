"""Testes dos relatórios. Carteira sintética."""
import sqlite3
from datetime import date

import pytest

import cotacoes
import esquema
import relatorios


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    esquema.aplicar(c)
    c.execute("INSERT INTO instituicoes (id, nome) VALUES (1,'Alfa')")
    c.executemany("INSERT INTO ativos (id, ticker, classe) VALUES (?,?,?)",
                  [(1, "PETR4", "ACAO"), (2, "MXRF11", "FII")])
    return c


def lanc(conn, data, tipo, ativo=1, qtd=0, preco=0, valor=None, custos=0, irrf=0):
    conn.execute(
        "INSERT INTO lancamentos (data, tipo, ativo_id, instituicao_id, quantidade,"
        " preco, valor, custos, irrf, criado_em) VALUES (?,?,?,1,?,?,?,?,?,'2026-01-01')",
        (data, tipo, ativo, qtd, preco, qtd * preco if valor is None else valor,
         custos, irrf))


# --------------------------------------------------------------- posição

def test_posicao_marca_a_mercado(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10, custos=5)
    cotacoes.registrar(conn, 1, "2026-08-01", 15.0)
    rel = relatorios.posicao(conn)
    (linha,) = rel.linhas
    assert linha[0] == "PETR4"
    assert linha[4] == "1.005,00"                 # custo com a corretagem dentro
    assert linha[6] == "1.500,00"                 # valor de mercado
    assert linha[7].startswith("▲ +")             # sinal e seta, nunca só cor
    assert any("Resultado não realizado" in t for t in rel.rodape)


def test_posicao_sem_cotacao_usa_o_preco_medio_e_avisa(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10)
    rel = relatorios.posicao(conn)
    assert rel.linhas[0][5] == "—"
    assert rel.linhas[0][6] == "1.000,00"
    assert any("Sem cotação" in a for a in rel.avisos)


def test_posicao_respeita_a_data(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10)
    lanc(conn, "2026-06-05", "COMPRA", qtd=100, preco=20)
    assert relatorios.posicao(conn, "2026-03-01").linhas[0][2] == "100"
    assert relatorios.posicao(conn).linhas[0][2] == "200"


# --------------------------------------------------------------- proventos

def test_proventos_separam_tipo_e_irrf(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10)
    lanc(conn, "2026-03-01", "DIVIDENDO", valor=120)
    lanc(conn, "2026-03-01", "JCP", valor=100, irrf=15)
    rel = relatorios.proventos(conn, 2026)
    (linha,) = rel.linhas
    assert linha[1] == "120,00" and linha[2] == "100,00" and linha[4] == "15,00"
    assert linha[5] == "220,00"
    assert linha[6] == "22,00%"                   # yield sobre custo de 1.000
    assert any("custo da posição ATUAL" in a for a in rel.avisos)


# --------------------------------------------------------------- IR

def test_fluxo_de_proventos_preenche_o_mes_vazio(conn):
    """Mês sem provento tem que entrar como zero: listar só os meses que pagaram
    infla a média de quem recebe trimestralmente."""
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10)
    lanc(conn, "2026-01-20", "DIVIDENDO", valor=300)
    lanc(conn, "2026-03-20", "DIVIDENDO", valor=300)
    rel = relatorios.fluxo_proventos(conn, meses=12, ate="2026-03")
    assert [l[0] for l in rel.linhas] == ["01/2026", "02/2026", "03/2026"]
    assert rel.linhas[1][5] == "0,00"                 # fevereiro existe e é zero
    assert any("Média mensal: R$ 200,00" in t for t in rel.rodape)   # 600 / 3
    assert any("Projeção anualizada (média × 12): R$ 2.400,00" in t
               for t in rel.rodape)


def test_fluxo_de_proventos_media_movel_e_yield(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=1000, preco=10)   # custo 10.000
    for mes in ("01", "02", "03"):
        lanc(conn, f"2026-{mes}-20", "RENDIMENTO", valor=100)
    rel = relatorios.fluxo_proventos(conn, meses=12, ate="2026-03")
    assert [l[6] for l in rel.linhas] == ["100,00", "100,00", "100,00"]
    assert any("Yield anualizado" in t and "12,00%" in t for t in rel.rodape)
    assert any("não previsão" in a for a in rel.avisos)


def test_fluxo_de_proventos_sem_dados(conn):
    assert relatorios.fluxo_proventos(conn).linhas == []


def test_apuracao_traz_darf_e_prejuizo(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=1000, preco=20)
    lanc(conn, "2026-06-10", "VENDA", qtd=1000, preco=30)
    rel = relatorios.apuracao(conn, 2026)
    (linha,) = rel.linhas
    assert linha[0] == "06/2026"                  # competência em formato BR
    assert linha[1] == "SWING" and linha[8] == "1.500,00"
    assert any("DARF 06/2026" in t and "vence 31/07/2026" in t for t in rel.rodape)
    assert any("não transmite nada à Receita" in a for a in rel.avisos)


def test_apuracao_registra_a_isencao(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10)
    lanc(conn, "2026-06-10", "VENDA", qtd=100, preco=15)
    rel = relatorios.apuracao(conn, 2026)
    assert rel.linhas == []                       # nada tributável
    assert any("dentro do limite" in a for a in rel.avisos)


# --------------------------------------------------------------- declaração

def test_bens_e_direitos_usa_a_posicao_de_31_12(conn):
    """A compra de janeiro do ano seguinte não pode entrar na declaração do ano
    anterior — e o valor declarado é o custo, nunca o de mercado."""
    lanc(conn, "2026-11-05", "COMPRA", qtd=100, preco=10)
    lanc(conn, "2027-01-15", "COMPRA", qtd=900, preco=10)
    cotacoes.registrar(conn, 1, "2026-12-31", 99.0)
    rel = relatorios.bens_direitos(conn, 2026)
    (linha,) = rel.linhas
    assert linha[2] == "100" and linha[4] == "1.000,00"
    assert rel.titulo == "Bens e direitos em 31/12/2026"
    assert any("CUSTO de aquisição" in a for a in rel.avisos)


def test_operacoes_mostram_data_em_formato_brasileiro(conn):
    """O banco guarda ISO para ordenar; a tela e o papel mostram dd/mm/aaaa."""
    lanc(conn, "2026-04-23", "COMPRA", qtd=10, preco=10.70)
    (linha,) = relatorios.operacoes(conn).linhas
    assert linha[0] == "23/04/2026"
    assert conn.execute("SELECT data FROM lancamentos").fetchone()[0] == "2026-04-23"


# --------------------------------------------------------------- custos

def test_custos_denunciam_negocios_sem_nota(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10, custos=11.71)
    lanc(conn, "2026-02-05", "COMPRA", qtd=100, preco=10)
    rel = relatorios.custos(conn)
    assert ["01/2026", "Alfa", "1", "11,71"] in rel.linhas
    assert any("não estima custo" in a for a in rel.avisos)


def test_custo_zero_com_nota_nao_e_denunciado(conn):
    """Numa nota grande, o rateio de uma linha pequena arredonda para zero de
    forma legítima. O que denuncia negócio sem custo é não ter nota."""
    conn.execute("INSERT INTO notas (id, numero, data_pregao, importada_em)"
                 " VALUES (1,'999','2026-01-05','2026-01-05')")
    lanc(conn, "2026-01-05", "COMPRA", qtd=1, preco=9.91, custos=0)
    conn.execute("UPDATE lancamentos SET nota_id = 1")
    assert relatorios.custos(conn).avisos == []


# --------------------------------------------------------------- retorno

def test_xirr_de_um_ano_cheio():
    assert relatorios.xirr([(date(2026, 1, 1), -1000),
                            (date(2027, 1, 1), 1100)]) == pytest.approx(0.10, abs=1e-4)


def test_xirr_com_aportes_irregulares():
    taxa = relatorios.xirr([(date(2026, 1, 1), -1000),
                            (date(2026, 7, 1), -500),
                            (date(2027, 1, 1), 1600)])
    assert taxa is not None and 0.03 < taxa < 0.15


def test_xirr_sem_solucao():
    assert relatorios.xirr([(date(2026, 1, 1), -100)]) is None
    assert relatorios.xirr([(date(2026, 1, 1), -100),
                            (date(2027, 1, 1), -100)]) is None


def test_rentabilidade_conta_custos_como_aporte(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10, custos=5)
    lanc(conn, "2026-03-01", "DIVIDENDO", valor=120)
    cotacoes.registrar(conn, 1, "2026-08-01", 12.0)
    rel = relatorios.rentabilidade(conn, "2026-08-01")
    assert rel.linhas[0][1] == "R$ 1.005,00"      # 1.000 do papel + 5 de custo
    assert rel.linhas[1][1] == "R$ 1.320,00"      # 120 de provento + 1.200 na mão
    assert any("Não é comparável" in a for a in rel.avisos)


# --------------------------------------------------------------- saída

def test_csv_leva_rodape_e_avisos(conn):
    lanc(conn, "2026-01-05", "COMPRA", qtd=100, preco=10)
    texto = relatorios.csv_texto(relatorios.posicao(conn))
    linhas = texto.splitlines()
    assert linhas[0].startswith("Ativo;Classe")
    assert "PETR4" in linhas[1]
    assert any("Custo total" in l for l in linhas)


def test_html_escapa_e_marca_colunas_numericas(conn):
    conn.execute("INSERT INTO ativos (id, ticker, classe) VALUES (3,'<script>','ACAO')")
    lanc(conn, "2026-01-05", "COMPRA", ativo=3, qtd=100, preco=10)
    saida = relatorios.documento(relatorios.posicao(conn))
    assert "<script>" not in saida and "&lt;script&gt;" in saida
    assert 'class="n"' in saida
    assert "tabular-nums" in saida
    assert "PEC" in saida                          # wordmark no timbre


def test_html_vazio_nao_quebra(conn):
    saida = relatorios.documento(relatorios.posicao(conn))
    assert "Nada a exibir" in saida
