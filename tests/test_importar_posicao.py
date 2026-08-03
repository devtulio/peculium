"""Leitor de posição da B3 (DESIGN.md §6.4).

A propriedade que estes testes protegem acima de todas: **retrato não vira
lançamento**. Se um dia alguém fizer o leitor criar posição a partir da
quantidade da B3, o preço médio passa a ser inventado e o imposto sai errado —
por isso a checagem de `lancamentos` vazio aparece em mais de um teste.

Nenhum arquivo aqui é real. As colunas e os nomes de aba foram medidos nos
relatórios do usuário, mas os valores são fictícios: extrato de verdade não
entra no repositório.
"""
from __future__ import annotations

import sqlite3

import pytest

import esquema

import cotacoes
import importar_posicao as ip
import lancamentos
import renda_fixa

openpyxl = pytest.importorskip("openpyxl")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    esquema.aplicar(c)
    c.execute("INSERT INTO instituicoes (id, nome) VALUES (1,'ALFA')")
    return c


def criar_ativo(conn, ticker, classe):
    return conn.execute("INSERT INTO ativos (ticker, nome, classe) VALUES (?,?,?)",
                        (ticker, ticker, classe)).lastrowid


def comprar(conn, ativo_id, data, quantidade, preco):
    return lancamentos.lancar(conn, data=data, tipo="COMPRA", ativo=ativo_id,
                              instituicao=1, quantidade=quantidade, preco=preco)

ACOES = ["Produto", "Instituição", "Conta", "Código de Negociação", "CNPJ da Empresa",
         "Tipo", "Escriturador", "Quantidade", "Quantidade Disponível",
         "Quantidade Indisponível", "Motivo", "Preço de Fechamento",
         "Valor Atualizado"]
FUNDOS = ["Produto", "Instituição", "Conta", "Código de Negociação", "CNPJ do Fundo",
          "Tipo", "Administrador", "Quantidade", "Quantidade Disponível",
          "Quantidade Indisponível", "Motivo", "Preço de Fechamento",
          "Valor Atualizado"]
RF = ["Produto", "Instituição", "Emissor", "Código", "Indexador", "Tipo de Regime",
      "Data de Emissão", "Vencimento", "Quantidade", "Quantidade Disponível",
      "Quantidade Indisponível", "Motivo", "Contraparte",
      "Preço Atualizado MTM", "Valor Atualizado MTM",
      "Preço Atualizado CURVA", "Valor Atualizado CURVA"]
TESOURO = ["Produto", "Instituição", "Código ISIN", "Indexador", "Vencimento",
           "Quantidade", "Quantidade Disponível", "Quantidade Indisponível",
           "Motivo", "Valor Aplicado", "Valor Bruto", "Valor Líquido",
           "Valor Atualizado"]


def planilha(caminho, abas: dict[str, tuple[list, list[list]]]):
    """Monta um .xlsx com as abas e colunas medidas nos relatórios reais."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nome, (cabecalho, linhas) in abas.items():
        ws = wb.create_sheet(nome[:31])
        ws.append(cabecalho)
        for linha in linhas:
            ws.append(linha)
    wb.save(caminho)
    return caminho


def posicao_simples(tmp_path, nome="posicao-2026-08-03-12-34-36.xlsx"):
    return planilha(tmp_path / nome, {
        "Acoes": (ACOES, [
            ["PETROBRAS PN", "ALFA", "1", "PETR4", "33.000.167/0001-01", "PN",
             "ITAU", 100, 100, 0, "-", 38.5, 3850.0],
        ]),
        "Fundo de Investimento": (FUNDOS, [
            ["FUNDO XYZ", "ALFA", "1", "XPTO11", "12.345.678/0001-99", "FII",
             "XP", 50, 50, 0, "-", 9.6, 480.0],
        ]),
    })


# ------------------------------------------------------------------- data


@pytest.mark.parametrize("nome, esperada", [
    ("posicao-2026-08-03-12-34-36.xlsx", "2026-08-03"),
    ("relatorio-consolidado-anual-2025.xlsx", "2025-12-31"),
    ("relatorio-consolidado-mensal-2026-junho.xlsx", "2026-06-30"),
    ("relatorio-consolidado-mensal-2026-fevereiro.xlsx", "2026-02-28"),
    ("relatorio-consolidado-mensal-2024-fevereiro.xlsx", "2024-02-29"),   # bissexto
])
def test_data_vem_do_nome_do_arquivo(tmp_path, nome, esperada):
    """Errar a data do retrato grava o preço na data errada — e o consolidado de
    2025 reescreveria a cotação de hoje com um preço de um ano atrás."""
    assert ip.data_de_referencia(tmp_path / nome)[0] == esperada


def test_data_desconhecida_avisa(tmp_path):
    data, aviso = ip.data_de_referencia(tmp_path / "minha-carteira.xlsx")
    assert data and "não diz a data" in aviso


def test_arquivo_sem_aba_de_posicao_e_recusado(tmp_path):
    alvo = planilha(tmp_path / "negociacao.xlsx",
                    {"Negociação": (["Data", "Código"], [["05/01/2026", "PETR4"]])})
    with pytest.raises(ip.ArquivoNaoReconhecido):
        ip.ler(alvo)


# ------------------------------------------------------------------- leitura


def test_le_acoes_e_fundos(tmp_path):
    conf = ip.ler(posicao_simples(tmp_path))
    assert conf.data == "2026-08-03"
    por_ticker = {i.ticker: i for i in conf.itens}
    assert por_ticker["PETR4"].classe == "ACAO"
    assert por_ticker["PETR4"].quantidade == 100
    assert por_ticker["PETR4"].preco == 38.5
    assert por_ticker["PETR4"].cnpj == "33000167000101"
    assert por_ticker["XPTO11"].classe == "FII"


def test_abas_do_consolidado_tem_outro_nome(tmp_path):
    """O consolidado prefixa as abas com "Posição - "; o conteúdo é o mesmo."""
    alvo = planilha(tmp_path / "relatorio-consolidado-anual-2025.xlsx",
                    {"Posição - Acoes": (ACOES, [
                        ["PETROBRAS PN", "ALFA", "1", "PETR4", "-", "PN", "ITAU",
                         100, 100, 0, "-", 30.0, 3000.0]])})
    conf = ip.ler(alvo)
    assert conf.data == "2025-12-31"
    assert [i.ticker for i in conf.itens] == ["PETR4"]


def test_linha_zerada_e_ignorada(tmp_path):
    alvo = planilha(tmp_path / "posicao-2026-08-03.xlsx", {"Acoes": (ACOES, [
        ["PETROBRAS PN", "ALFA", "1", "PETR4", "-", "PN", "ITAU", 0, 0, 0, "-", 38.5, 0.0],
        ["VALE ON", "ALFA", "1", "VALE3", "-", "ON", "ITAU", 10, 10, 0, "-", 60.0, 600.0],
    ])})
    assert [i.ticker for i in ip.ler(alvo).itens] == ["VALE3"]


def test_numero_da_b3_e_americano(tmp_path):
    """A planilha da B3 escreve `1234.56`, não `1.234,56`. Lida como pt-BR, a
    quantidade 1.500 viraria mil e quinhentos — e a posição, mil vezes maior."""
    alvo = planilha(tmp_path / "posicao-2026-08-03.xlsx", {"Acoes": (ACOES, [
        ["PETROBRAS PN", "ALFA", "1", "PETR4", "-", "PN", "ITAU",
         "1500", "1500", "0", "-", "9.919", "14878.5"],
    ])})
    item = ip.ler(alvo).itens[0]
    assert item.quantidade == 1500
    assert item.preco == pytest.approx(9.919)


def test_quantidade_fracionaria_do_tesouro(tmp_path):
    """`1.500` é um título e meio, não mil e quinhentos.

    É o caso que separa o formato americano do brasileiro na **quantidade**: o
    Tesouro é o único papel que vem fracionado, e ler `1.500` como milhar
    multiplicaria a posição por mil."""
    alvo = planilha(tmp_path / "posicao-2026-08-03.xlsx", {"Tesouro Direto": (TESOURO, [
        ["Tesouro Selic 2029", "ALFA", "BRSTNCLF1RA0", "SELIC", "01/03/2029",
         "1.500", "1.500", "0", "-", "15000.0", "16500.0", "16000.0", "16500.0"],
    ])})
    item = ip.ler(alvo).itens[0]
    assert item.quantidade == pytest.approx(1.5)
    assert item.preco == pytest.approx(11000.0)      # 16.500 / 1,5


def test_tesouro_ganha_ticker_derivado(tmp_path):
    """O Tesouro não tem código de negociação. Sem um ticker estável, cada
    importação criaria outro ativo para o mesmo papel."""
    alvo = planilha(tmp_path / "posicao-2026-08-03.xlsx", {"Tesouro Direto": (TESOURO, [
        ["Tesouro IPCA+ com Juros Semestrais 2037", "ALFA", "BRSTNCNTF1R5",
         "IPCA", "15/05/2037", 0.5, 0.5, 0, "-", 1800.0, 2060.18, 2000.0, 2060.18],
        ["Tesouro Selic 2029", "ALFA", "BRSTNCLF1RA0", "SELIC", "01/03/2029",
         2, 2, 0, "-", 20000.0, 22000.0, 21000.0, 22000.0],
    ])})
    itens = {i.ticker: i for i in ip.ler(alvo).itens}
    assert set(itens) == {"TESOURO-IPCA-JUROS-2037", "TESOURO-SELIC-2029"}
    ipca = itens["TESOURO-IPCA-JUROS-2037"]
    assert ipca.quantidade == 0.5
    assert ipca.preco == pytest.approx(4120.36)      # 2060,18 / 0,5
    assert ipca.vencimento == "2037-05-15"


def test_renda_fixa_traz_cadastro_e_preco_na_curva(tmp_path):
    alvo = planilha(tmp_path / "posicao-2026-08-03.xlsx", {"Renda Fixa": (RF, [
        ["CDB BANCO ALFA", "ALFA", "BANCO ALFA S/A", "CDB123ABC", "CDI", "-",
         "14/05/2026", "15/05/2028", 1000, 1000, 0, "-", "-",
         1.03, 1030.0, 1.0295, 1029.5],
    ])})
    item = ip.ler(alvo).itens[0]
    assert item.ticker == "CDB123ABC"
    assert item.emissor == "BANCO ALFA S/A"
    assert item.emissao == "2026-05-14"
    assert item.vencimento == "2028-05-15"
    # curva antes de MtM: num papel carregado até o vencimento é a curva que vale
    assert item.preco == pytest.approx(1.0295)


def test_dimensao_mentirosa_da_b3(tmp_path):
    """A B3 declara `<dimension ref="A1:A1"/>`, o que é falso: em read_only o
    openpyxl acredita e devolve só a coluna A. Sem `reset_dimensions()` o
    cabeçalho chega com um campo só e o arquivo é recusado."""
    import re
    import zipfile

    bom = posicao_simples(tmp_path, "bom.xlsx")
    ruim = tmp_path / "posicao-2026-08-03.xlsx"
    with zipfile.ZipFile(bom) as origem, zipfile.ZipFile(ruim, "w") as destino:
        for item in origem.infolist():
            dados = origem.read(item.filename)
            if item.filename.endswith(".xml") and b"<dimension" in dados:
                dados = re.sub(rb'<dimension ref="[^"]+"/>',
                               b'<dimension ref="A1:A1"/>', dados)
            destino.writestr(item, dados)
    assert {i.ticker for i in ip.ler(ruim).itens} == {"PETR4", "XPTO11"}


# ------------------------------------------------------------------- conferência


def test_conferencia_aponta_os_tres_casos(tmp_path, conn):
    ativo = criar_ativo(conn, "PETR4", "ACAO")
    comprar(conn, ativo, "2026-01-05", 100, 30.0)
    sumido = criar_ativo(conn, "VALE3", "ACAO")
    comprar(conn, sumido, "2026-01-05", 10, 60.0)
    parcial = criar_ativo(conn, "XPTO11", "FII")
    comprar(conn, parcial, "2026-01-05", 20, 9.0)

    conf = ip.conferir(conn, ip.ler(posicao_simples(tmp_path)))
    situacoes = {d.ticker: d.situacao for d in conf.divergencias}
    assert situacoes["PETR4"] == ip.CONFERE
    assert situacoes["VALE3"] == ip.SO_NO_PECULIUM      # vendi e não lancei
    assert situacoes["XPTO11"] == ip.QUANTIDADE_DIFERE  # 20 aqui, 50 na B3
    assert conf.confere == 1
    assert {d.ticker for d in conf.problemas} == {"VALE3", "XPTO11"}


def test_conferencia_acha_o_que_so_existe_na_b3(tmp_path, conn):
    conf = ip.conferir(conn, ip.ler(posicao_simples(tmp_path)))
    assert {d.situacao for d in conf.divergencias} == {ip.SO_NA_B3}
    assert conf.confere == 0


def test_conferencia_e_na_data_do_retrato(tmp_path, conn):
    """Compra posterior ao retrato não pode aparecer como divergência: senão o
    consolidado de 2025 acusaria tudo que foi comprado em 2026."""
    ativo = criar_ativo(conn, "PETR4", "ACAO")
    comprar(conn, ativo, "2025-11-03", 100, 30.0)
    comprar(conn, ativo, "2026-03-10", 900, 40.0)      # depois do retrato
    conf = ip.conferir(conn, ip.ler(posicao_simples(
        tmp_path, "relatorio-consolidado-anual-2025.xlsx")))       # retrato de 31/12/2025
    assert {d.ticker: d.situacao for d in conf.divergencias}["PETR4"] == ip.CONFERE


# ------------------------------------------------------------------- gravação


def test_gravar_nunca_cria_lancamento(tmp_path, conn):
    """A regra que sustenta o módulo inteiro. Retrato traz quantidade e valor de
    mercado, nunca o custo de aquisição: virar lançamento inventaria o preço
    médio e contaminaria o imposto."""
    conf = ip.conferir(conn, ip.ler(posicao_simples(tmp_path)))
    resumo = ip.gravar(conn, conf)
    assert resumo["ativos_novos"] == 2
    assert conn.execute("SELECT count(*) FROM lancamentos").fetchone()[0] == 0
    assert razao_vazio(conn)


def razao_vazio(conn) -> bool:
    import razao
    return razao.carteira(conn) == []


def test_gravar_registra_cotacao_na_data_do_retrato(tmp_path, conn):
    conf = ip.conferir(conn, ip.ler(posicao_simples(tmp_path)))
    assert ip.gravar(conn, conf)["cotacoes"] == 2
    linha = conn.execute(
        "SELECT c.data, c.fechamento, c.origem FROM cotacoes c JOIN ativos a"
        " ON a.id=c.ativo_id WHERE a.ticker='PETR4'").fetchone()
    assert (linha["data"], linha["fechamento"], linha["origem"]) == \
        ("2026-08-03", 38.5, "B3")


def test_preco_digitado_a_mao_vence_o_da_b3(tmp_path, conn):
    ativo = criar_ativo(conn, "PETR4", "ACAO")
    cotacoes.registrar(conn, ativo, "2026-08-03", 99.0, cotacoes.MANUAL)
    ip.gravar(conn, ip.ler(posicao_simples(tmp_path)))
    assert cotacoes.preco(conn, ativo, "2026-08-03") == 99.0


def test_preco_da_b3_vence_a_curva_calculada(conn):
    """A B3 informa o preço oficial; a curva é estimativa nossa. Sem a
    precedência, `atualizar_curvas()` apagaria o bom com o estimado."""
    ativo = criar_ativo(conn, "CDB123ABC", "RF")
    cotacoes.registrar(conn, ativo, "2026-08-03", 1.0295, ip.ORIGEM)
    assert cotacoes.registrar(conn, ativo, "2026-08-03", 1.01, renda_fixa.CURVA) is False
    assert cotacoes.preco(conn, ativo, "2026-08-03") == 1.0295


def test_titulo_sem_indexador_nao_e_cadastrado_mas_avisa(tmp_path, conn):
    """Caso real: a B3 deixa o indexador em branco em boa parte dos CDBs."""
    alvo = planilha(tmp_path / "posicao-2026-08-03.xlsx", {"Renda Fixa": (RF, [
        ["CDB BANCO ALFA", "ALFA", "BANCO ALFA S/A", "CDB123ABC", "", "-",
         "14/05/2026", "15/05/2028", 1000, 1000, 0, "-", "-",
         1.03, 1030.0, 1.0295, 1029.5],
    ])})
    conf = ip.ler(alvo)
    assert ip.gravar(conn, conf)["titulos"] == 0
    assert any("não informou o indexador" in a for a in conf.avisos)
    ativo = conn.execute("SELECT id FROM ativos WHERE ticker='CDB123ABC'").fetchone()[0]
    assert cotacoes.preco(conn, ativo, "2026-08-03") == 1.0295   # preço entrou


def test_titulo_cadastrado_usa_o_pu_da_aplicacao(tmp_path, conn):
    """O retrato traz o preço de **hoje**. Usá-lo como PU de emissão poria a base
    3% alta e levantaria a curva inteira junto."""
    ativo = criar_ativo(conn, "CDB123ABC", "RF")
    comprar(conn, ativo, "2026-05-14", 1000, 1.0)
    alvo = planilha(tmp_path / "posicao-2026-08-03.xlsx", {"Renda Fixa": (RF, [
        ["CDB BANCO ALFA", "ALFA", "BANCO ALFA S/A", "CDB123ABC", "CDI", "-",
         "14/05/2026", "15/05/2028", 1000, 1000, 0, "-", "-",
         1.03, 1030.0, 1.0295, 1029.5],
    ])})
    assert ip.gravar(conn, ip.ler(alvo))["titulos"] == 1
    titulo = renda_fixa.titulo(conn, ativo)
    assert titulo.pu_base == 1.0
    assert titulo.indexador == "CDI"
    assert titulo.emissor == "BANCO ALFA S/A"


def test_titulo_sem_taxa_nao_inventa_curva(tmp_path, conn):
    """A posição não traz a taxa. Com taxa 0 a curva sairia plana e — pior —
    sobrescreveria o preço oficial que a própria B3 informou."""
    import series

    ativo = criar_ativo(conn, "CDB123ABC", "RF")
    comprar(conn, ativo, "2026-05-14", 1000, 1.0)
    alvo = planilha(tmp_path / "posicao-2026-08-03.xlsx", {"Renda Fixa": (RF, [
        ["CDB BANCO ALFA", "ALFA", "BANCO ALFA S/A", "CDB123ABC", "CDI", "-",
         "14/05/2026", "15/05/2028", 1000, 1000, 0, "-", "-",
         1.03, 1030.0, 1.0295, 1029.5],
    ])})
    ip.gravar(conn, ip.ler(alvo))
    with pytest.raises(series.SerieIndisponivel, match="taxa"):
        renda_fixa.pu(conn, ativo, "2026-08-03")
    assert renda_fixa.atualizar_curvas(conn, "2026-08-03").atualizados == 0
    assert cotacoes.preco(conn, ativo, "2026-08-03") == 1.0295
