"""Testes do parser de nota de corretagem.

Os textos são sintéticos: reproduzem o **layout** medido nas notas reais (ordem
das linhas do pypdf, rótulo depois do valor no resumo, coluna de observação
opcional) com valores e ativos fictícios. Documento real nunca entra no
repositório.
"""
import sqlite3

import pytest

import esquema
import importar_nota as nota
import razao

CABECALHO = ["Negociações", "Negócios realizados", "Q", "Negociação", "C/V",
             "Tipo mercado", "Prazo", "Especificação do título", "Obs. (*)",
             "Quantidade", "Preço / Ajuste", "Valor Operação / Ajuste", "D/C"]


def brl(valor: float) -> str:
    return f"{valor:,.2f}".translate(str.maketrans(",.", ".,"))


def negocio(especificacao, qtd, preco, *, sentido="C", mercado="VISTA",
            tags=(), obs="@"):
    valor = round(qtd * preco, 2)
    bloco = ["1-BOVESPA", sentido, mercado, especificacao, *tags]
    if obs:
        bloco.append(obs)
    bloco += [f"{qtd:g}", brl(preco), brl(valor), "D" if sentido == "C" else "C"]
    return bloco, valor * (1 if sentido == "C" else -1)


def montar(*blocos, numero="123456789", data="21/07/2026", rubricas=None,
           liquido=None, operacoes=None):
    """Monta o texto como o pypdf devolve: no resumo, valor ANTES do rótulo."""
    rubricas = rubricas or {}
    corpo = list(CABECALHO)
    soma = 0.0
    for bloco, assinado in blocos:
        corpo += bloco
        soma += assinado
    operacoes = soma if operacoes is None else operacoes
    custos = sum(v for k, v in rubricas.items() if k in nota.CUSTOS)
    irrf = rubricas.get(nota.IRRF, 0.0)
    liquido = (operacoes + custos + irrf) if liquido is None else liquido

    corpo += ["NOTA DE NEGOCIAÇÃO", "Nr. nota", numero, "Folha", "1",
              "Data pregão", data,
              "CORRETORA FICTICIA DE CÂMBIO, TÍTULOS E VALORES MOBILIÁRIOS S.A.",
              "C.N.P.J: 11.222.333/0001-44"]
    corpo += [brl(abs(operacoes)), "Valor líquido das operações",
              "D" if operacoes >= 0 else "C"]
    for rotulo, valor in rubricas.items():
        corpo += [brl(valor), rotulo, "D"]
    corpo += [brl(abs(liquido)), f"Líquido para 23/07/2026",
              "D" if liquido >= 0 else "C"]
    return "\n".join(corpo)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    esquema.aplicar(c)
    return c


# --------------------------------------------------------------- parsing

def test_nota_de_compra_com_tres_linhas():
    texto = montar(negocio("KLABIN S/A          PN", 200, 3.50, tags=["N2"]),
                   negocio("KLABIN S/A          PN", 54, 3.50, mercado="FRACIONARIO",
                           tags=["N2"], obs="#"),
                   negocio("KLABIN S/A          PN", 31, 3.50, mercado="FRACIONARIO",
                           tags=["N2"], obs=""),
                   rubricas={"Taxa de liquidação": 0.22, "Emolumentos": 0.04,
                             "Taxa de Transf. de Ativos": 0.02,
                             "Taxa Operacional": 9.80, "Impostos": 1.04,
                             "Outros": 0.59})
    n = nota.parsear(texto)
    assert n.numero == "123456789" and n.data_pregao == "2026-07-21"
    assert n.cnpj == "11222333000144"
    assert n.valor_operacoes == pytest.approx(997.50)
    assert n.total_custos == pytest.approx(11.71)
    assert n.liquido == pytest.approx(1009.21)
    assert [x.quantidade for x in n.negocios] == [200, 54, 31]
    assert all(x.sentido == "COMPRA" for x in n.negocios)


def test_rateio_pro_rata_fecha_no_centavo():
    """A última linha absorve o resíduo do arredondamento: sem isso a soma dos
    custos rateados não bate com o total da nota que os comprova."""
    n = nota.parsear(montar(
        negocio("ATIVO A", 200, 3.50), negocio("ATIVO B", 54, 3.50),
        negocio("ATIVO C", 31, 3.50),
        rubricas={"Taxa Operacional": 9.80, "Impostos": 1.04, "Outros": 0.59,
                  "Taxa de liquidação": 0.22, "Emolumentos": 0.04,
                  "Taxa de Transf. de Ativos": 0.02}))
    rateados = [x.custos for x in n.negocios]
    assert sum(rateados) == pytest.approx(11.71)
    assert rateados[0] == pytest.approx(8.22)      # 700,00 de 997,50
    assert rateados[2] == pytest.approx(1.27)


def test_rateio_absorve_residuo_que_nao_fecha_sozinho():
    """Três valores iguais e um total que não divide por três: o arredondamento
    ingênuo dá 3,33 × 3 = 9,99 e perde um centavo do custo de aquisição."""
    n = nota.parsear(montar(
        negocio("ATIVO A", 10, 10.0), negocio("ATIVO B", 10, 10.0),
        negocio("ATIVO C", 10, 10.0),
        rubricas={"Taxa Operacional": 10.00}))
    rateados = [x.custos for x in n.negocios]
    assert rateados == [pytest.approx(3.33), pytest.approx(3.33), pytest.approx(3.34)]
    assert sum(rateados) == pytest.approx(10.00)


def test_nota_de_venda_tem_liquido_a_credito():
    n = nota.parsear(montar(
        negocio("ATIVO A", 100, 10.0, sentido="V"),
        rubricas={"Taxa de liquidação": 5.00, nota.IRRF: 0.05}))
    assert n.negocios[0].sentido == "VENDA"
    assert n.valor_operacoes == pytest.approx(-1000)
    assert n.liquido == pytest.approx(-994.95)     # dinheiro entra
    assert n.negocios[0].irrf == pytest.approx(0.05)


def test_nota_mista_compra_e_venda():
    n = nota.parsear(montar(
        negocio("ATIVO A", 50, 10.0),
        negocio("ATIVO B", 30, 10.0, sentido="V"),
        rubricas={"Taxa de liquidação": 3.00}))
    assert n.valor_operacoes == pytest.approx(200)   # 500 de compra − 300 de venda
    assert n.liquido == pytest.approx(203)


def test_irrf_so_rateia_entre_vendas():
    n = nota.parsear(montar(
        negocio("ATIVO A", 50, 10.0),
        negocio("ATIVO B", 30, 10.0, sentido="V"),
        rubricas={"Taxa de liquidação": 3.00, nota.IRRF: 0.02}))
    compra, venda = n.negocios
    assert compra.irrf == 0 and venda.irrf == pytest.approx(0.02)
    assert compra.custos > 0 and venda.custos > 0    # custo rateia entre as duas


def test_nota_que_nao_fecha_e_recusada():
    texto = montar(negocio("ATIVO A", 100, 10.0),
                   rubricas={"Taxa de liquidação": 5.00}, liquido=9999.99)
    with pytest.raises(nota.NotaInconsistente, match="líquido não confere"):
        nota.parsear(texto)


def test_soma_das_linhas_que_nao_bate_e_recusada():
    texto = montar(negocio("ATIVO A", 100, 10.0),
                   rubricas={"Taxa de liquidação": 5.00}, operacoes=777.00)
    with pytest.raises(nota.NotaInconsistente, match="soma dos negócios"):
        nota.parsear(texto)


def test_diagnostico_quando_o_irrf_estaria_dobrado():
    """Se a nota já contar o IRRF dentro das rubricas de custo, o erro diz isso
    em vez de só recusar — é o caso que só uma nota de venda real vai decidir."""
    texto = montar(negocio("ATIVO A", 100, 10.0, sentido="V"),
                   rubricas={"Taxa de liquidação": 5.00, nota.IRRF: 0.05},
                   liquido=-995.00)
    with pytest.raises(nota.NotaInconsistente, match="IRRF já estivesse dentro"):
        nota.parsear(texto)


# --------------------------------------------------------------- layout

def test_etiquetas_de_governanca_ficam_na_especificacao():
    """ER, ED, EJ, NM e N2 são etiquetas do papel, não observação — confundi-las
    com a coluna Obs. comeria parte do nome do ativo."""
    n = nota.parsear(montar(
        negocio("CAIXA SEGURI          ON", 10, 17.58, tags=["ED", "NM"], obs="@#"),
        rubricas={"Taxa de liquidação": 0.01}))
    (x,) = n.negocios
    assert x.especificacao == "CAIXA SEGURI ON ED NM"
    assert x.obs == "@#"


def test_obs_ausente():
    n = nota.parsear(montar(negocio("ATIVO A", 31, 3.50, tags=["N2"], obs=""),
                            rubricas={"Taxa de liquidação": 0.01}))
    assert n.negocios[0].obs == "" and n.negocios[0].especificacao == "ATIVO A N2"


def test_marcacao_de_day_trade():
    n = nota.parsear(montar(negocio("ATIVO A", 10, 5.0, obs="D"),
                            rubricas={"Taxa de liquidação": 0.01}))
    assert n.negocios[0].day_trade is True


def test_ticker_embutido_dos_fii():
    """Os FII trazem o código na especificação; ações e Fiagros não."""
    n = nota.parsear(montar(
        negocio("FII MAXI REN          MXRF11          CI", 10, 9.87),
        negocio("FIAGRO SUNO          CI", 10, 10.43, tags=["ER"]),
        rubricas={"Taxa de liquidação": 0.05}))
    assert n.negocios[0].ticker == "MXRF11"
    assert n.negocios[1].ticker == ""


def test_senhas_candidatas():
    """Os três recortes do fim do CPF são DIFERENTES e todos ocorrem na prática:
    em 123.456.789-09, os 3 últimos são '909', os 3 últimos do corpo são '789'
    e os verificadores são '09'."""
    candidatas = nota.senhas_candidatas("123.456.789-09")
    assert candidatas[0] == ""                    # boa parte das notas não é protegida
    assert "909" in candidatas                    # 3 últimos do CPF inteiro
    assert "789" in candidatas                    # 3 últimos do corpo
    assert "09" in candidatas                     # dígitos verificadores
    assert "123456" in candidatas                 # regra que abriu a nota da Inter
    assert "123" in candidatas and "12345678909" in candidatas
    assert nota.senhas_candidatas(None) == [""]


def test_senha_cadastrada_vem_antes_dos_candidatos():
    """Medido no acervo real: parte das notas usa senha que NÃO deriva do CPF.
    A cadastrada por corretora é o único caminho garantido."""
    candidatas = nota.senhas_candidatas("123.456.789-09", ("132",))
    assert candidatas[0] == "132"
    assert candidatas[1] == ""


# --------------------------------------------------------------- conferência

def _b3(conn, data, tipo, ativo_id, qtd, preco):
    conn.execute(
        "INSERT INTO lancamentos (data, tipo, ativo_id, instituicao_id, quantidade,"
        " preco, valor, origem, hash_origem, criado_em)"
        " VALUES (?,?,?,1,?,?,?,'B3_NEGOCIACAO',?,'2026-01-01')",
        (data, tipo, ativo_id, qtd, preco, qtd * preco, f"h{data}{ativo_id}{qtd}"))
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _semear(conn):
    conn.execute("INSERT INTO instituicoes (id, nome) VALUES (1, 'CORRETORA FICTICIA')")
    conn.execute("INSERT INTO ativos (id, ticker, classe) VALUES (1, 'MXRF11', 'FII')")


def test_negocio_da_b3_e_enriquecido_com_os_custos(conn):
    _semear(conn)
    _b3(conn, "2026-07-21", "COMPRA", 1, 10, 9.87)
    n = nota.parsear(montar(
        negocio("FII MAXI REN          MXRF11          CI", 10, 9.87),
        rubricas={"Taxa de liquidação": 0.30}))
    conf = nota.conferir(conn, n)
    (item,) = conf.itens
    assert item.situacao == nota.ENRIQUECE and item.lancamento_id is not None

    resumo = nota.gravar(conn, conf)
    assert resumo["enriquecidos"] == 1 and resumo["criados"] == 0
    ap = razao.apurar(conn)
    (pos,) = ap.carteira()
    assert pos.quantidade == 10
    assert pos.custo_total == pytest.approx(98.70 + 0.30)   # custo entrou no preço médio
    # o estorno fica visível: três lançamentos, um efeito
    assert conn.execute("SELECT count(*) FROM lancamentos").fetchone()[0] == 3


def test_negocio_sem_contraparte_e_criado(conn):
    _semear(conn)
    n = nota.parsear(montar(
        negocio("FII MAXI REN          MXRF11          CI", 10, 9.87),
        rubricas={"Taxa de liquidação": 0.30}))
    conf = nota.conferir(conn, n)
    assert conf.por_situacao(nota.CRIA)
    nota.gravar(conn, conf)
    (pos,) = razao.carteira(conn)
    assert pos.custo_total == pytest.approx(99.00)


def test_preco_diferente_nao_casa_com_a_b3(conn):
    """Casar por data e ativo, ignorando preço, colaria a nota no negócio errado
    quando há mais de uma ordem do mesmo papel no dia."""
    _semear(conn)
    _b3(conn, "2026-07-21", "COMPRA", 1, 10, 9.87)
    n = nota.parsear(montar(
        negocio("FII MAXI REN          MXRF11          CI", 10, 12.00),
        rubricas={"Taxa de liquidação": 0.30}))
    assert nota.conferir(conn, n).itens[0].situacao == nota.CRIA


def test_ativo_sem_ticker_exige_o_mapa_uma_vez(conn):
    _semear(conn)
    n = nota.parsear(montar(negocio("KLABIN S/A          PN", 200, 3.50, tags=["N2"]),
                            rubricas={"Taxa de liquidação": 0.20}))
    conf = nota.conferir(conn, n)
    (item,) = conf.itens
    assert item.situacao == nota.SEM_ATIVO
    with pytest.raises(ValueError, match="KLABIN"):
        nota.gravar(conn, conf)

    nota.gravar(conn, conf, tickers={"KLABIN S/A PN N2": "KLBN4"},
                classes={"KLBN4": "ACAO"})
    assert conn.execute("SELECT ativo_id FROM apelidos WHERE especificacao=?",
                        ("KLABIN S/A PN N2",)).fetchone() is not None
    # aprendido: a próxima nota do mesmo papel já casa sozinha
    outra = nota.parsear(montar(negocio("KLABIN S/A          PN", 50, 3.60, tags=["N2"]),
                                numero="999", rubricas={"Taxa de liquidação": 0.05}))
    assert nota.conferir(conn, outra).itens[0].situacao == nota.CRIA


def test_fii_novo_com_ticker_embutido_exige_a_classe(conn):
    """O FII traz o código na nota, mas o ativo pode não existir ainda. Deixar
    passar gravava lançamento com ativo nulo — e o razão quebra no dia seguinte."""
    conn.execute("INSERT INTO instituicoes (id, nome) VALUES (1, 'CORRETORA FICTICIA')")
    n = nota.parsear(montar(
        negocio("FII CAPI SEC          CPTS11          CI", 100, 7.66),
        rubricas={"Taxa de liquidação": 0.20}))
    conf = nota.conferir(conn, n)
    (item,) = conf.itens
    assert item.situacao == nota.SEM_ATIVO and "confirme a classe" in item.motivo

    with pytest.raises(ValueError, match="classe não definida"):
        nota.gravar(conn, conf)                    # sufixo 11 nunca é decidido sozinho
    # a recusa não pode deixar rastro: a segunda tentativa tem de funcionar
    assert conn.execute("SELECT count(*) FROM notas").fetchone()[0] == 0
    nota.gravar(conn, conf, classes={"CPTS11": "FII"})
    (pos,) = razao.carteira(conn)
    assert pos.ticker == "CPTS11" and pos.classe == "FII"
    assert conn.execute("SELECT count(*) FROM lancamentos WHERE ativo_id IS NULL"
                        ).fetchone()[0] == 0


def test_reimportar_a_mesma_nota_nao_duplica(conn):
    _semear(conn)
    n = nota.parsear(montar(
        negocio("FII MAXI REN          MXRF11          CI", 10, 9.87),
        rubricas={"Taxa de liquidação": 0.30}))
    nota.gravar(conn, nota.conferir(conn, n))
    conf = nota.conferir(conn, n)
    assert conf.ja_importada is True
    assert nota.gravar(conn, conf)["ja_importada"] is True
    assert conn.execute("SELECT count(*) FROM notas").fetchone()[0] == 1
    assert razao.carteira(conn)[0].quantidade == 10


def test_corretora_vira_instituicao_uma_vez(conn):
    conn.execute("INSERT INTO ativos (id, ticker, classe) VALUES (1, 'MXRF11', 'FII')")
    for numero in ("111", "222"):
        n = nota.parsear(montar(
            negocio("FII MAXI REN          MXRF11          CI", 10, 9.87),
            numero=numero, rubricas={"Taxa de liquidação": 0.30}))
        nota.gravar(conn, nota.conferir(conn, n))
    assert conn.execute("SELECT count(*) FROM instituicoes").fetchone()[0] == 1
    assert conn.execute("SELECT cnpj FROM instituicoes").fetchone()[0] == "11222333000144"
