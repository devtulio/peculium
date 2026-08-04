"""Notas de renda fixa, um adaptador por corretora.

Os textos são sintéticos: reproduzem o **layout** medido nas notas reais — os
rótulos colados no valor da XP, a linha de valores mais curta que o cabeçalho da
Inter — com números e papéis fictícios.
"""
import sqlite3

import pytest

import esquema
import importar_nota_rf as rf
import razao
import renda_fixa

XP = """Nota de negociação de títulos TipoCOMPRA
Número119312735 Operação14/05/2026
CLIENTE
Nome N° conta CNPJ/CPF
CARACTERÍSTICAS DO TÍTULO
AtivoCDB BANCO TESTE S.A. - MAI/2028 Vencimento15/05/2028
EmissorBANCO TESTE S.A.    IndexadorCDI Carência15/05/2026
TítuloCDB FLU CDB5267UW6V CustódiaCETIP LiquidaçãoC/C Emissão14/05/2026
CARACTERÍSTICAS DA OPERAÇÃO
Quantidade1.000 Preço Unitário1,00 Valor Bruto1.000,00 IOF0,00 IR0,00 Valor líquido1.000,00
Taxa do Negócio100% CDI
CARACTERÍSTICAS DA COMPROMISSADA COM LIQUIDEZ DIÁRIA
Vencimento- Preço Unitário- Valor Bruto- IOF- IR- Valor líquido-
Taxa- Indexador- Valor Principal- Rendimento Bruto- Rendimento Líquido-
"""

INTER = """Notas de renda fixa
Notas de renda fixa do período de 06/06/2026 a 07/07/2026
Nota de Negociação: 636065055
Tipo de Operação: Aplicação
Data da Operação 18/06/2026
Dados Cliente
Características do Título
Ativo Emissão Vencimento Indexador Taxa Nominal Local de Custódia
CDB Porq Obj -CDB626BO9OA 18/06/2026 08/06/2028 CDI 100.00 CETIP
Emissor: BANCO INTER
Características de Operação
Quantidade/Valor Nominal PU da Operação Indexador/Taxa negociada Forma de Liquidação
450 R$ 0,01 CC
Valor Bruto I.R. Retido I.O.F. Retido Valor Líquido
R$ 4,50 R$ 0,00 R$ 0,00 R$ 4,50
Características do Compromisso
Taxa Prazo PU de Retorno Indexador Vencimento
Valor de Retorno Bruto IR Retido Valor Retorno Líquido
"""

# a nota real que trazia o código do papel como um byte de controle e um "3"
INTER_CODIGO_RUIM = INTER.replace(
    "CDB Porq Obj -CDB626BO9OA 18/06/2026 08/06/2028 CDI 100.00 CETIP",
    "CDB CREDITO -  \x003 16/07/2026 01/07/2029 CDI 80.00 CETIP")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    esquema.aplicar(c)
    return c


# --------------------------------------------------------------- XP

def test_xp(conn):
    (n,) = rf.parsear(XP)
    assert n.corretora == "XP INVESTIMENTOS" and n.numero == "119312735"
    assert n.tipo == rf.APLICACAO and n.data == "2026-05-14"
    assert n.ticker == "CDB5267UW6V"
    assert n.indexador == "CDI" and n.taxa == 100
    assert n.emissao == "2026-05-14" and n.vencimento == "2028-05-15"
    assert n.quantidade == 1000 and n.pu == 1.0 and n.valor_bruto == 1000
    assert n.pu_de_emissao == 1.0


def test_xp_ignora_o_bloco_da_compromissada():
    """O segundo bloco repete TODOS os rótulos com valores "-". Sem cortar o
    texto antes dele, o parser leria vencimento e preço do lugar errado."""
    (n,) = rf.parsear(XP)
    assert n.vencimento == "2028-05-15"      # e não o "-" do bloco de baixo
    assert n.pu == 1.0


def test_xp_sem_a_linha_de_valores_falha_alto():
    texto = XP.replace("Quantidade1.000", "Quantia1.000")
    with pytest.raises(rf.LayoutDesconhecido, match="quantidade e preço"):
        rf.parsear(texto)


# --------------------------------------------------------------- Inter

def test_inter(conn):
    (n,) = rf.parsear(INTER)
    assert n.corretora == "BANCO INTER" and n.numero == "636065055"
    assert n.ticker == "CDB626BO9OA" and n.codigo_ambiguo is False
    assert n.indexador == "CDI" and n.taxa == 100     # taxa vem com ponto decimal
    assert n.emissao == "2026-06-18" and n.vencimento == "2028-06-08"
    assert n.quantidade == 450 and n.pu == 0.01 and n.valor_bruto == 4.50
    assert n.pu_de_emissao == 0.01


def test_inter_linha_de_valores_menor_que_o_cabecalho():
    """`450 R$ 0,01 CC` são três valores para quatro colunas: a taxa negociada
    vem vazia. Ler por posição erraria a quantidade."""
    (n,) = rf.parsear(INTER)
    assert n.quantidade == 450 and n.pu == 0.01


def test_codigo_ambiguo_nao_vira_ticker():
    """Caso real: `CDB CREDITO -  \\x003`. Usar "3" como ticker faria qualquer
    outro papel também codificado "3" fundir-se com este, virando uma posição
    só, em silêncio."""
    (n,) = rf.parsear(INTER_CODIGO_RUIM)
    assert n.codigo_ambiguo is True
    assert n.ticker == "CDB-CREDITO-2029-07-01"
    assert "3" != n.ticker


def test_notas_diferentes_com_codigo_ruim_nao_se_fundem():
    outra = INTER_CODIGO_RUIM.replace("01/07/2029", "01/07/2031")
    (a,), (b,) = rf.parsear(INTER_CODIGO_RUIM), rf.parsear(outra)
    assert a.ticker != b.ticker


def test_varias_notas_no_mesmo_arquivo():
    """O arquivo da Inter é um extrato do período e o título diz 'Notas'."""
    duas = INTER + INTER.split("Notas de renda fixa do período")[1].replace(
        "636065055", "662299618")
    assert len(rf.parsear(duas)) == 2


# --------------------------------------------------------------- invariantes

def test_recusa_quando_quantidade_vezes_pu_nao_da_o_bruto():
    texto = XP.replace("Valor Bruto1.000,00", "Valor Bruto9.999,00")
    with pytest.raises(rf.NotaRFInconsistente, match="mas a nota diz bruto"):
        rf.parsear(texto)


def test_recusa_quando_o_liquido_nao_fecha():
    texto = XP.replace("Valor líquido1.000,00", "Valor líquido900,00")
    with pytest.raises(rf.NotaRFInconsistente, match="diz líquido"):
        rf.parsear(texto)


def test_arquivo_de_outra_corretora():
    with pytest.raises(rf.LayoutDesconhecido, match="cada corretora precisa"):
        rf.parsear("Nota de alguma outra corretora qualquer")


def test_reconhece_o_que_e_renda_fixa():
    assert rf.e_renda_fixa(XP) and rf.e_renda_fixa(INTER)
    assert not rf.e_renda_fixa("NOTA DE NEGOCIAÇÃO\n1-BOVESPA\nC\nVISTA")


# --------------------------------------------------------------- gravação

def test_gravar_cria_ativo_titulo_e_lancamento(conn):
    conf = rf.conferir(conn, rf.parsear(XP))
    assert conf.por_situacao(rf.CRIA)
    resumo = rf.gravar(conn, conf)
    assert resumo == {"lancamentos": 1, "titulos": 1, "ja_importadas": 0}

    t = renda_fixa.titulo(conn, 1)
    assert t.ticker == "CDB5267UW6V" and t.classe == "RF"
    assert t.indexador == "CDI" and t.taxa == 100 and t.pu_base == 1.0
    assert t.emissor == "BANCO TESTE S.A."
    (pos,) = razao.carteira(conn)
    assert pos.quantidade == 1000 and pos.custo_total == pytest.approx(1000)


def test_reimportar_a_mesma_nota_nao_duplica(conn):
    rf.gravar(conn, rf.conferir(conn, rf.parsear(XP)))
    conf = rf.conferir(conn, rf.parsear(XP))
    assert conf.por_situacao(rf.JA_IMPORTADA)
    assert rf.gravar(conn, conf)["lancamentos"] == 0
    assert razao.carteira(conn)[0].quantidade == 1000


def test_segunda_aplicacao_no_mesmo_papel_nao_recadastra(conn):
    rf.gravar(conn, rf.conferir(conn, rf.parsear(XP)))
    outra = XP.replace("Número119312735", "Número119312999").replace(
        "Operação14/05/2026", "Operação02/06/2026")
    resumo = rf.gravar(conn, rf.conferir(conn, rf.parsear(outra)))
    assert resumo["lancamentos"] == 1 and resumo["titulos"] == 0
    assert renda_fixa.titulo(conn, 1).emissao == "2026-05-14"   # não foi sobrescrito


def test_aplicacao_depois_da_emissao_avisa_sobre_o_pu(conn):
    """Sem o PU de emissão a posição sai errada, e ele não vem na nota quando a
    compra é de papel já emitido."""
    texto = XP.replace("Operação14/05/2026", "Operação02/06/2026")
    conf = rf.conferir(conn, rf.parsear(texto))
    assert conf.itens[0].nota.pu_de_emissao is None
    assert any("confirme-o depois" in a for a in conf.avisos)


def test_ipca_avisa_que_precisa_de_preco_a_mao(conn):
    texto = XP.replace("IndexadorCDI", "IndexadorIPCA").replace(
        "Taxa do Negócio100% CDI", "Taxa do NegócioIPCA + 6,00%")
    conf = rf.conferir(conn, rf.parsear(texto))
    assert any("à mão" in a for a in conf.avisos)


def test_a_corretora_vira_instituicao_uma_vez(conn):
    rf.gravar(conn, rf.conferir(conn, rf.parsear(XP)))
    rf.gravar(conn, rf.conferir(conn, rf.parsear(INTER)))
    assert conn.execute("SELECT count(*) FROM instituicoes").fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM rf_titulos").fetchone()[0] == 2


# ------------------- casamento com a Movimentação da B3: os dois que dobravam

def _aplicacao_b3(conn, ticker, data, quantidade, pu, emissor=None):
    """A mesma aplicação como ela chega pelo extrato da B3: com o código oficial
    do papel, e na data da LIQUIDAÇÃO."""
    ativo_id = conn.execute(
        "INSERT INTO ativos (ticker, classe) VALUES (?,'RF')", (ticker,)).lastrowid
    if emissor:
        conn.execute("INSERT INTO rf_titulos (ativo_id, emissao, indexador, taxa,"
                     " pu_base, emissor) VALUES (?,?,'CDI',100,?,?)",
                     (ativo_id, data, pu, emissor))
    conn.execute(
        "INSERT INTO lancamentos (data, tipo, ativo_id, instituicao_id, quantidade,"
        " preco, valor, origem, criado_em) VALUES (?,'COMPRA',?,1,?,?,?,"
        "'B3_MOVIMENTACAO','2026-01-01')",
        (data, ativo_id, quantidade, pu, round(quantidade * pu, 2)))
    return ativo_id


def test_nota_e_extrato_com_dias_diferentes_nao_duplicam(conn):
    """A nota é do dia da negociação; a B3 registra a liquidação, dias depois.

    Num caso real foram 18/06 na nota e 22/06 no extrato. Exigir data exata
    fazia o mesmo aporte entrar duas vezes — 900 unidades onde havia 450."""
    _aplicacao_b3(conn, "CDB626BO9OA", "2026-06-22", 450, 0.01)
    conf = rf.conferir(conn, rf.parsear(INTER))
    (item,) = conf.itens
    assert item.situacao == rf.SO_CADASTRO
    rf.gravar(conn, conf)
    (pos,) = razao.carteira(conn)
    assert (pos.ticker, pos.quantidade) == ("CDB626BO9OA", 450)


def test_papel_com_codigo_diferente_dos_dois_lados_e_o_mesmo(conn):
    """A nota da Inter que não traz código utilizável gera um ticker derivado; a
    B3 chama o mesmo CDB pelo código dela. Sem casar os dois, são dois ativos
    para um papel só, cada um com metade da posição."""
    # a nota é de 18/06; a B3 registra a liquidação em 22/06
    ativo_id = _aplicacao_b3(conn, "CDB726AM6KA", "2026-06-22", 450, 0.01)
    conf = rf.conferir(conn, rf.parsear(INTER_CODIGO_RUIM))
    (item,) = conf.itens
    assert item.situacao == rf.SO_CADASTRO
    assert item.ativo_id == ativo_id            # aponta para o ativo da B3
    rf.gravar(conn, conf)
    assert conn.execute("SELECT count(*) FROM ativos").fetchone()[0] == 1
    (pos,) = razao.carteira(conn)
    assert (pos.ticker, pos.quantidade) == ("CDB726AM6KA", 450)


def test_fora_da_janela_de_liquidacao_nao_casa(conn):
    """Um mês de diferença não é atraso de liquidação: é outra aplicação."""
    _aplicacao_b3(conn, "CDB726AM6KA", "2026-08-20", 450, 0.01)
    (item,) = rf.conferir(conn, rf.parsear(INTER_CODIGO_RUIM)).itens
    assert item.situacao == rf.CRIA


def test_emissor_diferente_nao_casa(conn):
    """Dois CDBs de bancos diferentes, mesmo valor e mesmo dia, não podem ser
    confundidos só porque a quantidade e o PU batem."""
    _aplicacao_b3(conn, "CDB999XYZ", "2026-06-22", 450, 0.01,
                  emissor="BANCO OUTRO S.A.")
    (item,) = rf.conferir(conn, rf.parsear(INTER_CODIGO_RUIM)).itens
    assert item.situacao == rf.CRIA
