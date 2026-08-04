"""Testes da importação da B3. Os arquivos são sintéticos e escritos aqui —
extrato real jamais entra no repositório, nem como fixture."""
import sqlite3

import pytest

import esquema
import importar_b3 as b3
import razao

NEG_CABECALHO = ("Data do Negócio;Tipo de Movimentação;Mercado;Prazo/Vencimento;"
                 "Instituição;Código de Negociação;Quantidade;Preço;Valor")
MOV_CABECALHO = ("Entrada/Saída;Data;Movimentação;Produto;Instituição;Quantidade;"
                 "Preço unitário;Valor da Operação")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    esquema.aplicar(c)
    return c


def csv_negociacao(tmp_path, *linhas, nome="negociacao.csv"):
    alvo = tmp_path / nome
    alvo.write_text("\n".join([NEG_CABECALHO, *linhas]), encoding="utf-8-sig")
    return alvo


def csv_movimentacao(tmp_path, *linhas, nome="movimentacao.csv"):
    alvo = tmp_path / nome
    alvo.write_text("\n".join([MOV_CABECALHO, *linhas]), encoding="utf-8-sig")
    return alvo


# --------------------------------------------------------------- negociação

def test_le_compra_e_venda(tmp_path, conn):
    arq = csv_negociacao(
        tmp_path,
        "05/01/2026;Compra;Mercado à Vista;-;ALFA CTVM;PETR4;100;32,18;3.218,00",
        "10/03/2026;Venda;Mercado à Vista;-;ALFA CTVM;PETR4;40;38,00;1.520,00")
    conf = b3.ler(arq, conn)
    assert conf.relatorio == b3.NEGOCIACAO and conf.novas == 2
    compra, venda = conf.por_situacao(b3.NOVA)
    assert (compra.tipo, compra.data, compra.quantidade) == ("COMPRA", "2026-01-05", 100)
    assert compra.valor == pytest.approx(3218.0)
    assert venda.tipo == "VENDA" and venda.valor == pytest.approx(1520.0)


def test_avisa_que_o_relatorio_nao_traz_corretagem(tmp_path, conn):
    arq = csv_negociacao(
        tmp_path, "05/01/2026;Compra;Mercado à Vista;-;ALFA;PETR4;100;10,00;1.000,00")
    assert any("corretagem" in a for a in b3.ler(arq, conn).avisos)


def test_fracionario_e_o_mesmo_ativo(tmp_path, conn):
    """PETR4F e PETR4 são o mesmo papel: tratá-los como ativos diferentes
    quebraria o preço médio, que é global por ativo."""
    arq = csv_negociacao(
        tmp_path,
        "05/01/2026;Compra;Mercado à Vista;-;ALFA;PETR4;100;10,00;1.000,00",
        "06/01/2026;Compra;Mercado Fracionário;-;ALFA;PETR4F;7;10,00;70,00")
    conf = b3.ler(arq, conn)
    assert {l.ticker for l in conf.por_situacao(b3.NOVA)} == {"PETR4"}
    assert list(conf.ativos_novos) == ["PETR4"]


def test_numero_em_formato_brasileiro(tmp_path, conn):
    arq = csv_negociacao(
        tmp_path,
        "05/01/2026;Compra;Mercado à Vista;-;ALFA;BBAS3;1.500;R$ 1.234,56;1.851.840,00")
    (linha,) = b3.ler(arq, conn).por_situacao(b3.NOVA)
    assert linha.quantidade == 1500          # "1.500" é milhar, não um e meio
    assert linha.preco == pytest.approx(1234.56)
    assert linha.valor == pytest.approx(1_851_840.00)


# A conversão de número mora em textos.py e é testada lá — aqui só se garante
# que o importador continua ligado nela.
def test_usa_a_conversao_compartilhada():
    import textos
    assert b3._numero is textos.numero


def test_data_invalida_vira_erro_e_nao_derruba_o_arquivo(tmp_path, conn):
    arq = csv_negociacao(
        tmp_path,
        "31/02/2026;Compra;Mercado à Vista;-;ALFA;PETR4;100;10,00;1.000,00",
        "05/01/2026;Compra;Mercado à Vista;-;ALFA;PETR4;100;10,00;1.000,00")
    conf = b3.ler(arq, conn)
    assert conf.erros == 1 and conf.novas == 1


# --------------------------------------------------------------- movimentação

def test_le_proventos(tmp_path, conn):
    arq = csv_movimentacao(
        tmp_path,
        "Credito;15/03/2026;Dividendo;PETR4 - PETROLEO BRASILEIRO SA;ALFA;100;1,20;120,00",
        "Credito;15/03/2026;Juros Sobre Capital Próprio;PETR4 - PETROLEO;ALFA;100;0,85;85,00",
        "Credito;20/03/2026;Rendimento;MXRF11 - MAXI RENDA;ALFA;200;0,10;20,00")
    conf = b3.ler(arq, conn)
    assert conf.relatorio == b3.MOVIMENTACAO
    assert [l.tipo for l in conf.por_situacao(b3.NOVA)] == ["DIVIDENDO", "JCP", "RENDIMENTO"]
    assert conf.ativos_novos["PETR4"]["nome"] == "PETROLEO BRASILEIRO SA"


def test_liquidacao_de_negocio_e_descartada(tmp_path, conn):
    """A armadilha do formato: sem descartar, importar os dois relatórios
    duplicaria a carteira inteira."""
    arq = csv_movimentacao(
        tmp_path,
        "Credito;05/01/2026;Transferência - Liquidação;PETR4 - PETROLEO;ALFA;100;10,00;1.000,00",
        "Credito;15/03/2026;Dividendo;PETR4 - PETROLEO;ALFA;100;1,20;120,00")
    conf = b3.ler(arq, conn)
    assert conf.novas == 1
    (ignorada,) = conf.por_situacao(b3.IGNORADA)
    assert "já vêm no relatório de Negociação" in ignorada.motivo


def test_portabilidade_com_as_duas_pontas_vira_um_lancamento(tmp_path, conn):
    """Débito na origem e crédito no destino: juntos dizem tudo que um
    lançamento de transferência precisa, e o par vira **um** lançamento.

    A outra linha some da lista de novas — se as duas virassem lançamento, a
    posição andaria duas vezes."""
    arq = csv_movimentacao(
        tmp_path,
        "Debito;01/06/2026;Transferência;PETR4 - PETROLEO;ALFA;100;10,00;1.000,00",
        "Credito;01/06/2026;Transferência;PETR4 - PETROLEO;BETA;100;10,00;1.000,00")
    conf = b3.ler(arq, conn)
    (nova,) = conf.por_situacao(b3.NOVA)
    assert (nova.tipo, nova.ticker, nova.quantidade) == ("TRANSFERENCIA", "PETR4", 100)
    assert (nova.instituicao, nova.destino) == ("ALFA", "BETA")
    assert conf.por_situacao(b3.PENDENTE) == []
    # o outro lado aparece como descartado COM MOTIVO: sumir em silêncio da
    # conferência esconderia uma linha que o arquivo tinha
    (ignorada,) = conf.por_situacao(b3.IGNORADA)
    assert "o outro lado da mesma portabilidade" in ignorada.motivo
    assert len(conf.linhas) == 2
    # as duas corretoras entram no cadastro, não só a de origem
    assert set(conf.instituicoes_novas) == {"ALFA", "BETA"}


def test_portabilidade_com_uma_ponta_so_fica_pendente(tmp_path, conn):
    """Metade da portabilidade não diz para onde o papel foi, e lançar assim
    moveria a posição para o nada."""
    arq = csv_movimentacao(
        tmp_path,
        "Debito;01/06/2026;Transferência;PETR4 - PETROLEO;ALFA;100;10,00;1.000,00")
    (pendente,) = b3.ler(arq, conn).por_situacao(b3.PENDENTE)
    assert (pendente.ticker, pendente.instituicao) == ("PETR4", "ALFA")
    assert "sem o outro lado" in pendente.motivo
    # o alerta que evita o erro de achar que transferência repõe a compra
    assert "não cria" in pendente.motivo


def test_portabilidades_de_papeis_diferentes_nao_se_cruzam(tmp_path, conn):
    """O par casa por data, papel e quantidade — casar só por data juntaria
    duas portabilidades do mesmo dia e trocaria as corretoras entre elas."""
    arq = csv_movimentacao(
        tmp_path,
        "Debito;01/06/2026;Transferência;PETR4 - PETROLEO;ALFA;100;10,00;1.000,00",
        "Credito;01/06/2026;Transferência;PETR4 - PETROLEO;BETA;100;10,00;1.000,00",
        "Debito;01/06/2026;Transferência;VALE3 - VALE;GAMA;50;60,00;3.000,00",
        "Credito;01/06/2026;Transferência;VALE3 - VALE;DELTA;50;60,00;3.000,00")
    novas = {l.ticker: l for l in b3.ler(arq, conn).por_situacao(b3.NOVA)}
    assert (novas["PETR4"].instituicao, novas["PETR4"].destino) == ("ALFA", "BETA")
    assert (novas["VALE3"].instituicao, novas["VALE3"].destino) == ("GAMA", "DELTA")


def test_transferencia_gravada_leva_a_corretora_de_destino(tmp_path, conn):
    arq = csv_movimentacao(
        tmp_path,
        "Debito;01/06/2026;Transferência;PETR4 - PETROLEO;ALFA;100;10,00;1.000,00",
        "Credito;01/06/2026;Transferência;PETR4 - PETROLEO;BETA;100;10,00;1.000,00")
    conf = b3.ler(arq, conn)
    assert b3.gravar(conn, conf, {"PETR4": "ACAO"}) == 1
    linha = conn.execute(
        "SELECT o.nome AS origem, d.nome AS destino FROM lancamentos l"
        " JOIN instituicoes o ON o.id = l.instituicao_id"
        " JOIN instituicoes d ON d.id = l.instituicao_destino_id"
        " WHERE l.tipo='TRANSFERENCIA'").fetchone()
    assert (linha["origem"], linha["destino"]) == ("ALFA", "BETA")


def test_movimentacao_desconhecida_vira_erro(tmp_path, conn):
    arq = csv_movimentacao(
        tmp_path, "Credito;01/06/2026;Coisa Nova da B3;PETR4 - X;ALFA;1;1,00;1,00")
    (erro,) = b3.ler(arq, conn).por_situacao(b3.ERRO)
    assert "desconhecida" in erro.motivo


# --------------------------------------------------------------- classes

@pytest.mark.parametrize("ticker, classe, confirmar", [
    ("PETR4", "ACAO", False),
    ("BBAS3", "ACAO", False),
    ("AAPL34", "BDR", False),
    ("MXRF11", "FII", True),      # 11 pode ser FII, ETF ou unit
    ("BOVA11", "FII", True),
])
def test_classe_provavel(ticker, classe, confirmar):
    assert b3.classe_provavel(ticker) == (classe, confirmar)


def test_avisa_quando_a_classe_precisa_de_confirmacao(tmp_path, conn):
    arq = csv_movimentacao(
        tmp_path, "Credito;20/03/2026;Rendimento;BOVA11 - ISHARES;ALFA;10;0,10;1,00")
    assert any("alíquota do IR" in a for a in b3.ler(arq, conn).avisos)


def test_gravar_exige_classe_quando_nao_ha_sugestao(tmp_path, conn):
    arq = csv_movimentacao(
        tmp_path, "Credito;20/03/2026;Rendimento;ESQUISITO - X;ALFA;10;0,10;1,00")
    conf = b3.ler(arq, conn)
    with pytest.raises(ValueError, match="ESQUISITO"):
        b3.gravar(conn, conf)
    assert b3.gravar(conn, conf, classes={"ESQUISITO": "FII"}) == 1


# --------------------------------------------------------------- idempotência

def test_reimportar_o_mesmo_arquivo_nao_duplica(tmp_path, conn):
    arq = csv_negociacao(
        tmp_path,
        "05/01/2026;Compra;Mercado à Vista;-;ALFA;PETR4;100;10,00;1.000,00")
    b3.gravar(conn, b3.ler(arq, conn))
    segunda = b3.ler(arq, conn)
    assert segunda.novas == 0 and segunda.duplicadas == 1
    assert b3.gravar(conn, segunda) == 0
    assert conn.execute("SELECT count(*) FROM lancamentos").fetchone()[0] == 1


def test_periodos_sobrepostos_so_trazem_o_que_falta(tmp_path, conn):
    """Reimportar com sobreposição é o caso normal: os extratos da B3 se
    sobrepõem no período."""
    primeiro = csv_negociacao(
        tmp_path,
        "05/01/2026;Compra;Mercado à Vista;-;ALFA;PETR4;100;10,00;1.000,00",
        nome="jan.csv")
    segundo = csv_negociacao(
        tmp_path,
        "05/01/2026;Compra;Mercado à Vista;-;ALFA;PETR4;100;10,00;1.000,00",
        "12/02/2026;Compra;Mercado à Vista;-;ALFA;PETR4;50;12,00;600,00",
        nome="jan-fev.csv")
    b3.gravar(conn, b3.ler(primeiro, conn))
    conf = b3.ler(segundo, conn)
    assert (conf.novas, conf.duplicadas) == (1, 1)
    b3.gravar(conn, conf)
    assert conn.execute("SELECT count(*) FROM lancamentos").fetchone()[0] == 2


def test_negocios_identicos_no_mesmo_dia_entram_os_dois(tmp_path, conn):
    """Duas ordens iguais no mesmo dia não são duplicata: hash sem número de
    ocorrência engoliria a segunda em silêncio."""
    linha = "05/01/2026;Compra;Mercado à Vista;-;ALFA;PETR4;100;10,00;1.000,00"
    arq = csv_negociacao(tmp_path, linha, linha)
    conf = b3.ler(arq, conn)
    assert conf.novas == 2
    assert b3.gravar(conn, conf) == 2
    # e reimportar o mesmo arquivo continua não duplicando
    assert b3.ler(arq, conn).duplicadas == 2


# --------------------------------------------------------------- ponta a ponta

def test_importado_alimenta_o_razao(tmp_path, conn):
    negocios = csv_negociacao(
        tmp_path,
        "05/01/2026;Compra;Mercado à Vista;-;ALFA CTVM;PETR4;100;10,00;1.000,00",
        "06/01/2026;Compra;Mercado Fracionário;-;ALFA CTVM;PETR4F;50;12,00;600,00",
        "10/03/2026;Venda;Mercado à Vista;-;ALFA CTVM;PETR4;50;20,00;1.000,00")
    proventos = csv_movimentacao(
        tmp_path,
        "Credito;15/03/2026;Dividendo;PETR4 - PETROLEO;ALFA CTVM;100;1,20;120,00")
    b3.gravar(conn, b3.ler(negocios, conn))
    b3.gravar(conn, b3.ler(proventos, conn))

    ap = razao.apurar(conn)
    (pos,) = ap.carteira()
    assert pos.ticker == "PETR4" and pos.quantidade == 100
    assert pos.custo_total == pytest.approx(1600 - 50 * (1600 / 150))
    (venda,) = ap.vendas
    assert venda.natureza == razao.SWING
    assert [p.tipo for p in ap.proventos] == ["DIVIDENDO"]
    # a instituição foi criada uma vez só, apesar dos dois arquivos
    assert conn.execute("SELECT count(*) FROM instituicoes").fetchone()[0] == 1


def test_xlsx_com_titulo_antes_do_cabecalho(tmp_path, conn):
    """A B3 põe título acima do cabeçalho em alguns exports."""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Relatório de Negociação"])
    ws.append([])
    ws.append(NEG_CABECALHO.split(";"))
    ws.append(["05/01/2026", "Compra", "Mercado à Vista", "-", "ALFA", "PETR4",
               100, 10.0, 1000.0])
    alvo = tmp_path / "negociacao.xlsx"
    wb.save(alvo)
    conf = b3.ler(alvo, conn)
    assert conf.novas == 1
    assert conf.por_situacao(b3.NOVA)[0].ticker == "PETR4"


def test_xlsx_com_dimensao_mentirosa(tmp_path, conn):
    """A planilha da B3 declara `<dimension ref="A1:A1"/>`, o que é falso.

    O modo read_only do openpyxl acredita na declaração e devolve só a coluna A:
    o cabeçalho chegava com um campo e o arquivo real era recusado como "não é da
    B3". Reproduz o defeito reescrevendo a dimensão dentro do .xlsx."""
    import re as _re
    import shutil
    import zipfile

    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(NEG_CABECALHO.split(";"))
    ws.append(["05/01/2026", "Compra", "Mercado à Vista", "-", "ALFA", "PETR4",
               "100", "10.5", "1050"])
    bom = tmp_path / "bom.xlsx"
    wb.save(bom)

    ruim = tmp_path / "negociacao.xlsx"
    with zipfile.ZipFile(bom) as origem, zipfile.ZipFile(ruim, "w") as destino:
        for item in origem.infolist():
            dados = origem.read(item.filename)
            if item.filename.endswith("sheet1.xml"):
                dados = _re.sub(rb'<dimension ref="[^"]+"/>',
                                b'<dimension ref="A1:A1"/>', dados)
            destino.writestr(item, dados)
    shutil.rmtree(bom, ignore_errors=True)

    conf = b3.ler(ruim, conn)
    (linha,) = conf.por_situacao(b3.NOVA)
    assert linha.ticker == "PETR4" and linha.quantidade == 100
    assert linha.preco == pytest.approx(10.5)      # e o formato americano da B3


def test_formato_numerico_e_do_arquivo_inteiro(tmp_path, conn):
    """`9.919` é indecidível isoladamente — 9919 em pt-BR, 9,919 em en-US. A
    planilha real da B3 vem em americano, e a heurística por valor devolvia mil
    vezes o preço de um provento."""
    alvo = tmp_path / "negociacao.csv"
    alvo.write_text("\n".join([NEG_CABECALHO,
        "05/01/2026;Compra;Mercado à Vista;-;ALFA;PETR4;100;9.919;991.9"]),
        encoding="utf-8-sig")
    (linha,) = b3.ler(alvo, conn).por_situacao(b3.NOVA)
    assert linha.preco == pytest.approx(9.919)     # e não 9919
    assert linha.valor == pytest.approx(991.9)


def test_arquivo_que_nao_e_da_b3(tmp_path, conn):
    alvo = tmp_path / "lista.csv"
    alvo.write_text("nome;telefone\nfulano;123\n", encoding="utf-8")
    with pytest.raises(b3.ArquivoNaoReconhecido, match="Área do Investidor"):
        b3.ler(alvo, conn)


def test_coluna_essencial_faltando_falha_nomeando_a_coluna(tmp_path, conn):
    alvo = tmp_path / "negociacao.csv"
    alvo.write_text("Data do Negócio;Instituição;Código de Negociação;Quantidade\n"
                    "05/01/2026;ALFA;PETR4;100\n", encoding="utf-8")
    with pytest.raises(b3.ArquivoNaoReconhecido, match="tipo de movimentacao"):
        b3.ler(alvo, conn)


def test_subscricao_orienta_por_subtipo(tmp_path, conn):
    """Os seis subtipos exigem coisas diferentes do usuário, e só um deles vira
    posição. Dizer "lance à mão" para todos era mandar ele descobrir qual."""
    arq = csv_movimentacao(
        tmp_path,
        "Credito;26/06/2026;Direito de Subscrição;MXRF12 - MAXI RENDA;ALFA;4;-;-",
        "Debito;08/07/2026;Solicitação de Subscrição;MXRF12 - MAXI RENDA;ALFA;4;-;-",
        "Credito;08/07/2026;Direitos de Subscrição - Exercido;MXRF12 - MAXI;ALFA;4;-;-",
        "Credito;09/07/2026;Recibo de Subscrição;MXRF13 - MAXI RENDA;ALFA;4;-;-",
        "Credito;14/07/2026;Direito Sobras de Subscrição;MXRF12 - MAXI;ALFA;54;-;-")
    # sem preço em nenhuma linha: o exercício deste arquivo não traz PU
    conf = b3.ler(arq, conn)
    # duas linhas caem no mesmo dia e no mesmo papel: a chave é o nº da linha
    linhas = {l.n: l for l in conf.linhas}

    # o recibo é o único que pede algo — e aqui não há linha de exercício com
    # preço, então ele fica pendente em vez de virar lançamento
    (recibo,) = conf.por_situacao(b3.PENDENTE)
    assert (recibo.ticker, recibo.quantidade) == ("MXRF13", 4)
    assert "É ESTA a linha que vira posição" in recibo.motivo
    assert "CONVERSÃO" in recibo.motivo  # o passo seguinte, quando o recibo virar cota

    # as demais são informativas: aparecem com o motivo, sem pedir nada
    assert "nada a lançar" in linhas[2].motivo      # direito
    assert "nada a lançar" in linhas[3].motivo      # solicitação
    assert "linha de recibo" in linhas[4].motivo    # exercido aponta para o recibo
    assert "sobras" in linhas[6].motivo
    assert {linhas[n].situacao for n in (2, 3, 4, 6)} == {b3.IGNORADA}


def test_subscricao_nunca_vira_lancamento(tmp_path, conn):
    """A regra que sustenta o tratamento: as linhas nomeiam o papel
    intermediário, não o que entra na carteira. Importar como está enche a
    posição de fantasma — aconteceu numa importação real."""
    arq = csv_movimentacao(
        tmp_path,
        "Credito;09/07/2026;Recibo de Subscrição;MXRF13 - MAXI RENDA;ALFA;4;-;-")
    conf = b3.ler(arq, conn)
    assert conf.novas == 0
    assert b3.gravar(conn, conf) == 0
    assert conn.execute("SELECT count(*) FROM lancamentos").fetchone()[0] == 0


# ------------------------------------------------------------------- Tesouro

def test_compra_de_tesouro_nao_e_descartada(tmp_path, conn):
    """Compra e venda na Movimentação são o outro lado do que vem na Negociação
    — menos no Tesouro Direto, que não passa pela bolsa e não aparece lá.

    Descartar junto fazia a compra sumir sem aviso: numa carteira real eram
    R$ 2.079,13 de patrimônio evaporando em silêncio."""
    arq = csv_movimentacao(
        tmp_path,
        "Credito;09/07/2026;Compra;Tesouro IPCA+ com Juros Semestrais 2037;"
        "ALFA;0,5;4.158,25;2.079,13",
        "Credito;05/01/2026;Compra;PETR4 - PETROLEO;ALFA;100;10,00;1.000,00")
    conf = b3.ler(arq, conn)
    (nova,) = conf.por_situacao(b3.NOVA)
    assert nova.tipo == "COMPRA"
    assert nova.quantidade == pytest.approx(0.5)
    assert nova.valor == pytest.approx(2079.13)
    # a ação continua sendo descartada: essa vem mesmo na Negociação
    (ignorada,) = conf.por_situacao(b3.IGNORADA)
    assert "já vem no relatório de Negociação" in ignorada.motivo


def test_tesouro_usa_o_mesmo_codigo_do_leitor_de_posicao(tmp_path, conn):
    """Sem o código derivado, o papel comprado e o papel do retrato da B3 seriam
    dois ativos diferentes, e a conferência acusaria divergência nos dois."""
    import importar_posicao

    arq = csv_movimentacao(
        tmp_path,
        "Credito;09/07/2026;Compra;Tesouro IPCA+ com Juros Semestrais 2037;"
        "ALFA;0,5;4.158,25;2.079,13")
    (nova,) = b3.ler(arq, conn).por_situacao(b3.NOVA)
    assert nova.ticker == importar_posicao._ticker_tesouro(
        "Tesouro IPCA+ com Juros Semestrais 2037")
    # e a classe sai sozinha: papel do Tesouro não é ambíguo
    assert b3.classe_provavel(nova.ticker) == ("TESOURO", False)


def test_venda_de_tesouro_tambem_entra(tmp_path, conn):
    arq = csv_movimentacao(
        tmp_path,
        "Debito;20/07/2026;Venda;Tesouro Selic 2029;ALFA;1;15.000,00;15.000,00")
    (nova,) = b3.ler(arq, conn).por_situacao(b3.NOVA)
    assert (nova.tipo, nova.ticker) == ("VENDA", "TESOURO-SELIC-2029")


# ---------------------------------------------------------------- subscrição

SUB_EXERCIDO = ("Debito;08/07/2026;Direitos de Subscrição - Exercido;"
                "MXRF12 - MAXI RENDA;ALFA;4;9,64;38,56")
SUB_RECIBO = ("Credito;09/07/2026;Recibo de Subscrição;"
              "MXRF13 - MAXI RENDA;ALFA;4;-;-")


def test_subscricao_exercida_vira_lancamento_com_o_preco_da_b3(tmp_path, conn):
    """O preço ESTÁ no arquivo: a linha "Exercido" traz PU e valor da operação.

    O programa mandava lançar à mão dizendo que a B3 não informava o preço —
    não era verdade, e o custo do papel ficava de fora da carteira."""
    arq = csv_movimentacao(
        tmp_path,
        "Credito;26/06/2026;Direito de Subscrição;MXRF12 - MAXI RENDA;ALFA;4;-;-",
        "Debito;08/07/2026;Solicitação de Subscrição;MXRF12 - MAXI RENDA;ALFA;4;-;-",
        SUB_EXERCIDO, SUB_RECIBO)
    conf = b3.ler(arq, conn)
    (nova,) = conf.por_situacao(b3.NOVA)
    assert (nova.tipo, nova.ticker, nova.data) == ("SUBSCRICAO", "MXRF13", "2026-07-09")
    assert (nova.quantidade, nova.preco, nova.valor) == (4, pytest.approx(9.64),
                                                         pytest.approx(38.56))
    # as outras quatro são informativas: não pedem nada do usuário
    assert conf.por_situacao(b3.PENDENTE) == []
    assert len(conf.por_situacao(b3.IGNORADA)) == 3


def test_recibo_sem_o_exercicio_fica_pendente(tmp_path, conn):
    """Sem a linha que traz o preço não dá para lançar: inventar o custo de uma
    subscrição é inventar preço médio."""
    (pendente,) = b3.ler(csv_movimentacao(tmp_path, SUB_RECIBO),
                         conn).por_situacao(b3.PENDENTE)
    assert pendente.ticker == "MXRF13"
    assert "É ESTA a linha que vira posição" in pendente.motivo


def test_exercicio_de_outra_quantidade_nao_serve_de_preco(tmp_path, conn):
    """Duas subscrições no mesmo período: casar pela quantidade evita usar o
    preço de uma no recibo da outra."""
    arq = csv_movimentacao(
        tmp_path,
        "Debito;08/07/2026;Direitos de Subscrição - Exercido;XPTO12 - X;ALFA;9;5,00;45,00",
        SUB_RECIBO)
    conf = b3.ler(arq, conn)
    assert conf.por_situacao(b3.NOVA) == []
    assert [l.ticker for l in conf.por_situacao(b3.PENDENTE)] == ["MXRF13"]


def test_subscricao_entra_na_posicao_pelo_valor_pago(tmp_path, conn):
    arq = csv_movimentacao(tmp_path, SUB_EXERCIDO, SUB_RECIBO)
    conf = b3.ler(arq, conn)
    assert b3.gravar(conn, conf, {"MXRF13": "FII"}) == 1
    (p,) = razao.carteira(conn)
    assert (p.ticker, p.quantidade) == ("MXRF13", 4)
    assert p.custo_total == pytest.approx(38.56)   # não entra a custo zero
