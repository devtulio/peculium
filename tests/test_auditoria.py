"""Os defeitos que a auditoria da v0.10.1 encontrou.

Um arquivo só, e de propósito: cada teste aqui nasceu de um achado reproduzido
rodando o código real, e ficam juntos para que quem mexer num deles veja de onde
os outros vieram. O que eles protegem é sempre a mesma coisa — um número que
saía errado **em silêncio**, ou um dado que sumia sem ninguém pedir.
"""
import sqlite3
import struct
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

import cofre
import cotacoes
import esquema
import fisco
import lancamentos as lanc
import obrigacoes
import peculium
import razao
import relatorios
import series

HOJE = "2026-12-31"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    esquema.aplicar(c)
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("INSERT INTO instituicoes (id, nome, chave) VALUES (1,'XP','xp')")
    c.executemany("INSERT INTO ativos (id, ticker, classe) VALUES (?,?,?)",
                  [(1, "PETR4", "ACAO"), (2, "VALE3", "ACAO"), (3, "MXRF11", "FII")])
    return c


def api_de(conn):
    """A `Api` sem cofre de verdade: o que interessa aqui é a validação."""
    api = peculium.Api.__new__(peculium.Api)
    api._aberto = type("Falso", (), {"conn": conn, "commit": lambda s: None,
                                     "aviso_esquema": ""})()
    api._conferencias = {}
    api._proximo_token = 0
    return api


# ------------------------------------------------------- § 1.2 foreign keys

def test_apagar_tudo_nao_desliga_as_foreign_keys(conn):
    """`PRAGMA foreign_keys` é no-op DENTRO de transação, e os DELETE abrem uma.

    O `finally` religava dentro da transação, ou seja: não religava. O cofre
    seguia sem integridade referencial até o programa ser reaberto, e nada
    dizia — um lançamento apontando para ativo inexistente entrava calado."""
    lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo=1, instituicao=1,
                quantidade=10, preco=30, hoje=HOJE)
    esquema.limpar(conn)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO lancamentos (data, tipo, ativo_id, criado_em)"
                     " VALUES ('2026-01-01','COMPRA',9999,'x')")


def test_apagar_tudo_continua_apagando(conn):
    lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo=1, instituicao=1,
                quantidade=10, preco=30, hoje=HOJE)
    apagados = esquema.limpar(conn)
    assert apagados["lancamentos"] == 1 and apagados["ativos"] == 3
    assert conn.execute("SELECT count(*) FROM config").fetchone()[0] > 0


# ------------------------------------------------------- § 1.3 buraco na série

def _serie(conn, indice="CDI", meses_fora=()):
    d, gravados = date(2026, 1, 1), 0
    while gravados < 150:
        if d.weekday() < 5:
            if d.month not in meses_fora:
                conn.execute("INSERT INTO series VALUES (?,?,0.05)",
                             (indice, d.isoformat()))
            gravados += 1
        d += timedelta(days=1)


def test_serie_com_buraco_recusa_calcular(conn):
    """Cobertura se lê de min/max, e nenhum dos dois enxerga buraco no meio.

    Com fevereiro faltando, `dias_uteis` contava 65 onde havia 85 e o fator do
    CDB saía 1,0330 em vez de 1,0430 — um ponto percentual a menos, sem aviso.
    Preferir o erro é a regra do módulo: nunca devolver número aproximado."""
    _serie(conn, meses_fora=(2,))
    assert series.buraco(conn, "CDI", "2026-01-01", "2026-04-30")
    with pytest.raises(series.SerieIndisponivel, match="vão de"):
        series.fator_cdi(conn, "2026-01-01", "2026-04-30")


def test_serie_contigua_nao_reclama(conn):
    """Feriado e fim de semana não podem virar falso alarme — o carnaval sozinho
    já emenda quatro dias sem pregão."""
    _serie(conn)
    assert series.buraco(conn, "CDI", "2026-01-01", "2026-04-30") is None
    assert series.fator_cdi(conn, "2026-01-01", "2026-04-30") > 1.0


def test_download_com_buraco_refaz_a_faixa_inteira(conn):
    """Continuar do último dia nunca tapa um buraco anterior."""
    _serie(conn, meses_fora=(2,))
    conn.execute("INSERT OR REPLACE INTO config VALUES ('cotacao_online','1')")
    pedidos = []

    def buscador(codigo, inicio, fim):
        pedidos.append(inicio)
        return []

    series.baixar(conn, ["CDI"], buscador=buscador)
    assert pedidos[0] == "2026-01-01"        # o começo, não o fim da série


def test_valor_vazio_do_sgs_nao_derruba_o_download(conn):
    """O SGS devolve "" em algumas datas; fora do try, isso matava o download
    inteiro em vez de virar uma linha ignorada."""
    conn.execute("INSERT OR REPLACE INTO config VALUES ('cotacao_online','1')")
    r = series.baixar(conn, ["CDI"], inicio="2026-07-01", fim="2026-07-31",
                      buscador=lambda *_: [
                          {"data": "01/07/2026", "valor": "0.05"},
                          {"data": "02/07/2026", "valor": ""},
                          {"data": "03/07/2026", "valor": "0.05"}])
    assert r.gravados == 2 and not r.falhas


def test_serie_diaria_e_pedida_em_fatias(conn):
    """A API do SGS **recusa** pedido longo de série diária, e era assim que o
    programa pedia: sem intervalo nenhum.

    Medido contra a API de verdade: sem intervalo devolve `406 Not Acceptable`,
    11 anos idem, 10 anos estoura o tempo, 2 anos passa. Como `baixar()` pedia a
    série inteira de uma vez, CDI e Selic diária **nunca desciam** — e a curva de
    renda fixa ficava permanentemente sem calcular, dizendo "ligue a rede em
    Configurações" com a rede já ligada."""
    conn.execute("INSERT OR REPLACE INTO config VALUES ('cotacao_online','1')")
    pedidos = []

    def buscador(codigo, inicio, fim):
        pedidos.append((inicio, fim))
        return []

    series.baixar(conn, ["CDI"], buscador=buscador)
    assert len(pedidos) > 1, "a série diária tem de ser pedida em fatias"
    for inicio, fim in pedidos:
        anos = (date.fromisoformat(fim) - date.fromisoformat(inicio)).days / 365.25
        assert anos <= series.JANELA_ANOS + 0.1, f"fatia de {anos:.1f} anos"
    # as fatias se emendam: buraco entre elas seria o defeito do § 1.3 de volta
    for (_, fim), (inicio, _) in zip(pedidos, pedidos[1:]):
        assert inicio == fim


def test_serie_mensal_continua_vindo_inteira(conn):
    """Só a diária tem o limite. Fatiar a mensal seria pedido a mais sem ganho —
    e a Selic mensal precisa vir desde 1986 para os juros de mora de um DARF
    antigo fecharem."""
    conn.execute("INSERT OR REPLACE INTO config VALUES ('cotacao_online','1')")
    pedidos = []

    def buscador(codigo, inicio, fim):
        pedidos.append((inicio, fim))
        return []

    series.baixar(conn, ["SELIC_MENSAL"], buscador=buscador)
    assert pedidos == [(None, None)]


def test_curva_calcula_ate_onde_a_serie_alcanca(conn):
    """O BCB publica o CDI com um dia útil de atraso: pedir a curva de HOJE
    falhava todo dia, com "atualize as séries" logo depois de atualizá-las.

    O PU fica gravado na data em que ele vale — adiantá-lo para hoje seria
    inventar um dia de rendimento. Quem cobre a diferença é `cotacoes.preco()`,
    que já procura a última cotação até a data pedida."""
    import cotacoes
    import renda_fixa as rf
    conn.execute("INSERT INTO ativos (id, ticker, classe) VALUES (9,'CDB1','RF')")
    _serie(conn)                                   # série vai até certo dia
    fim_da_serie = series.cobertura(conn, "CDI")[1]
    rf.cadastrar(conn, ativo_id=9, emissao="2026-01-02", indexador="CDI", taxa=100)

    depois = (date.fromisoformat(fim_da_serie) + timedelta(days=3)).isoformat()
    r = rf.atualizar_curvas(conn, depois)
    assert r.atualizados == 1 and not r.falhas
    assert r.ate == fim_da_serie
    # gravado na data em que vale, e a carteira o enxerga mesmo pedindo depois
    assert cotacoes.preco(conn, 9, fim_da_serie) > 1.0
    assert cotacoes.preco(conn, 9, depois) == cotacoes.preco(conn, 9, fim_da_serie)


def test_serie_que_comeca_tarde_demais_continua_falhando(conn):
    """O recorte é só no FIM. Série que começa depois da emissão é buraco de
    verdade, e continua recusando — senão a curva sairia contada pela metade."""
    import renda_fixa as rf
    conn.execute("INSERT INTO ativos (id, ticker, classe) VALUES (9,'CDB1','RF')")
    _serie(conn)
    rf.cadastrar(conn, ativo_id=9, emissao="2020-01-02", indexador="CDI", taxa=100)
    r = rf.atualizar_curvas(conn, "2026-04-30")
    assert r.atualizados == 0 and "CDB1" in r.falhas


def test_posicao_nao_avisa_do_que_ja_resolveu(conn):
    """A tabela mostrava o PU certo E o aviso "atualize as séries" na mesma
    linha: `posicao()` pedia a curva de hoje, o CDI de hoje ainda não saiu, e o
    valor vinha do fallback. Aviso que grita sem motivo é o que faz o usuário
    parar de ler avisos."""
    import renda_fixa as rf
    conn.execute("INSERT INTO ativos (id, ticker, classe) VALUES (9,'CDB1','RF')")
    _serie(conn)
    fim = series.cobertura(conn, "CDI")[1]
    rf.cadastrar(conn, ativo_id=9, emissao="2026-01-02", indexador="CDI", taxa=100)
    lanc.lancar(conn, data="2026-01-02", tipo="COMPRA", ativo=9, instituicao=1,
                quantidade=1000, preco=1, hoje=HOJE)

    depois = (date.fromisoformat(fim) + timedelta(days=3)).isoformat()
    (linha,) = rf.posicao(conn, depois)
    assert linha["erro"] is None
    assert linha["pu"] > 1.0 and linha["bruto"] > 1000


# ------------------------------------------------------- § 2.1 DARF parcial

def _darf(conn):
    lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo=2, instituicao=1,
                quantidade=1000, preco=50, hoje=HOJE)
    lanc.lancar(conn, data="2026-02-10", tipo="VENDA", ativo=2, instituicao=1,
                quantidade=1000, preco=75, hoje=HOJE)


def test_pagamento_parcial_nao_cobra_encargo_ja_pago(conn):
    """Em PARCIAL, `multa` e `juros` são os que o usuário JÁ PAGOU — somá-los ao
    que falta cobrava duas vezes o dinheiro que já saiu do bolso dele."""
    _darf(conn)
    obrigacoes.registrar(conn, "2026-02", 1000.0, "2026-04-20", multa=33.0, juros=12.0)
    o = [x for x in obrigacoes.listar(conn, hoje=HOJE) if x.competencia == "2026-02"][0]
    assert o.situacao == obrigacoes.PARCIAL
    assert o.total_a_pagar == pytest.approx(2750.0)      # não 2795,00


def test_vencido_continua_somando_multa_e_juros(conn):
    """O que mudou foi só o PARCIAL: no vencido não pago, os encargos são a
    calcular e entram no total."""
    _darf(conn)
    o = [x for x in obrigacoes.listar(conn, hoje=HOJE) if x.competencia == "2026-02"][0]
    assert o.situacao == obrigacoes.VENCIDO
    assert o.multa > 0 and o.total_a_pagar > o.valor_apurado


# ------------------------------------------------------- § 2.2 evento repetido

def test_evento_repetido_e_recusado(conn):
    """O razão aplica todos os eventos e nenhum tem estorno: dois desdobramentos
    1:2 iguais faziam 100 ações virarem 400."""
    lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo=1, instituicao=1,
                quantidade=100, preco=30, hoje=HOJE)
    lanc.registrar_evento(conn, ativo=1, data_ex="2026-03-01",
                          tipo="DESDOBRAMENTO", fator=2, hoje=HOJE)
    with pytest.raises(lanc.DadoInvalido, match="já está cadastrado"):
        lanc.registrar_evento(conn, ativo=1, data_ex="2026-03-01",
                              tipo="DESDOBRAMENTO", fator=2, hoje=HOJE)
    assert razao.carteira(conn, "2026-06-01")[0].quantidade == pytest.approx(200)


def test_eventos_diferentes_no_mesmo_dia_continuam_valendo(conn):
    """A trava é por (ativo, data, tipo): dois ativos desdobrando no mesmo dia é
    caso normal, e grupar um papel que desdobrou também."""
    lanc.registrar_evento(conn, ativo=1, data_ex="2026-03-01",
                          tipo="DESDOBRAMENTO", fator=2, hoje=HOJE)
    lanc.registrar_evento(conn, ativo=2, data_ex="2026-03-01",
                          tipo="DESDOBRAMENTO", fator=2, hoje=HOJE)
    lanc.registrar_evento(conn, ativo=1, data_ex="2026-03-01",
                          tipo="GRUPAMENTO", fator=0.5, hoje=HOJE)
    assert conn.execute("SELECT count(*) FROM eventos").fetchone()[0] == 3


# ------------------------------------------------------- § 2.3 migração parcial

def test_migracao_que_falha_nao_sobrevive_a_gravacao_seguinte(monkeypatch):
    """`commit()` serializa o banco INTEIRO. Sem rollback, o estado meio-migrado
    era persistido pela primeira gravação normal do usuário — um lançamento
    qualquer, minutos depois — apesar do aviso dizer que o cofre estava intacto."""
    alvo = Path(tempfile.mkdtemp()) / "t.pec"
    fracos = {"n": 2 ** 8, "r": 8, "p": 1}
    v, _ = cofre.criar(alvo, "senha-de-teste-1234", params=fracos)
    v.commit()
    v.fechar()

    def quebrada(conexao):
        conexao.execute("INSERT INTO auditoria (em, acao, detalhe)"
                        " VALUES ('x','MIGRACAO','meio')")
        raise RuntimeError("estourou no meio")

    monkeypatch.setattr(esquema, "aplicar", quebrada)
    v = cofre.abrir(alvo, "senha-de-teste-1234")
    assert "não pôde ser atualizado" in v.aviso_esquema
    v.conn.execute("INSERT INTO ativos (ticker, classe) VALUES ('PETR4','ACAO')")
    v.commit()                       # gravação normal, depois do aviso
    v.fechar()

    monkeypatch.undo()
    v = cofre.abrir(alvo, "senha-de-teste-1234")
    assert v.conn.execute("SELECT count(*) FROM auditoria"
                          " WHERE acao='MIGRACAO'").fetchone()[0] == 0
    v.fechar()


# ------------------------------------------------------- § 2.4 vínculo da nota

def test_corrigir_leva_a_nota_junto(conn):
    """O `hash_origem` fica com o original de propósito — é ele que faz
    reimportar o arquivo reconhecer a linha. O vínculo com a NOTA é do negócio:
    sem ele, corrigir o preço fazia o negócio sumir da nota e o extrato passar a
    dizer MANUAL num lançamento que veio de documento."""
    conn.execute("INSERT INTO notas (id, numero, data_pregao, importada_em)"
                 " VALUES (7,'140560283','2026-05-27','x')")
    conn.execute("INSERT INTO importacoes (id, arquivo, tipo, em)"
                 " VALUES (4,'nota.pdf','NOTA','x')")
    original = lanc.lancar(conn, data="2026-05-27", tipo="COMPRA", ativo=1,
                           instituicao=1, quantidade=10, preco=30, hoje=HOJE)
    conn.execute("UPDATE lancamentos SET nota_id=7, importacao_id=4,"
                 " hash_origem='h1' WHERE id=?", (original,))
    novo = lanc.corrigir(conn, original, preco=31)["novo"]
    linha = conn.execute("SELECT * FROM lancamentos WHERE id=?", (novo,)).fetchone()
    assert linha["nota_id"] == 7 and linha["importacao_id"] == 4
    assert linha["hash_origem"] is None          # esse fica, e é decisão


# ------------------------------------------------------- § 2.5 estorno no custo

def test_relatorio_de_custos_ignora_o_estornado(conn):
    """Faltava a exclusão do lançamento estornado que as outras consultas têm: o
    razão já tinha tirado o negócio da carteira e o custo dele seguia somando."""
    identificador = lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo=1,
                                instituicao=1, quantidade=100, preco=30,
                                custos=25.50, hoje=HOJE)
    assert relatorios.custos(conn).linhas
    lanc.estornar(conn, identificador, "duplicado")
    assert relatorios.custos(conn).linhas == []


def test_painel_nao_conta_mes_cujo_aporte_foi_estornado(conn):
    """Os três números saem da mesma tela e só um tinha o filtro: o painel dizia
    "aportado em 1 mês" ao lado de aportes do ano zerados."""
    identificador = lanc.lancar(conn, data="2026-03-05", tipo="COMPRA", ativo=1,
                                instituicao=1, quantidade=100, preco=30, hoje=HOJE)
    lanc.estornar(conn, identificador, "duplicado")
    d = peculium.Api.painel(api_de(conn))["dados"]
    assert d["meses_de_aporte"] == 0
    assert d["aportes_ano"] == 0 and d["patrimonio"] == 0


# ------------------------------------------------------- § 2.6 token

def test_token_de_importacao_nao_reaproveita_numero(conn):
    """Com `len(self._conferencias)`, confirmar a primeira de duas prévias fazia
    a terceira nascer com o token da segunda e SUBSTITUIR a que ainda estava
    aberta — confirmar aquela tela gravava o arquivo errado."""
    api = api_de(conn)
    primeiro, segundo = api._novo_token(), api._novo_token()
    api._conferencias[primeiro] = "arquivo A"
    api._conferencias[segundo] = "arquivo B"
    api._conferencias.pop(primeiro)                 # o usuário confirmou o A
    terceiro = api._novo_token()                    # e abriu uma prévia nova
    assert terceiro not in (primeiro, segundo)
    api._conferencias[terceiro] = "arquivo C"
    assert api._conferencias[segundo] == "arquivo B"    # a pendente sobreviveu


def test_confirmar_token_desconhecido_explica(conn):
    r = peculium.Api.confirmar_importacao(api_de(conn), "imp99")
    assert r["ok"] is False and "não está mais aberta" in r["erro"]


# ------------------------------------------------------- § 2.7 classe do ativo

@pytest.mark.parametrize("classe", ["CRIPTO", "", "acao "])
def test_classe_fora_das_sete_e_recusada(conn, classe):
    """A única lista das sete vivia no JavaScript, e foi uma cópia incompleta
    dela que, na v0.9.3, fez todo CDB entrar como AÇÃO. Defesa de tela não
    defende o razão."""
    r = peculium.Api.cadastrar_ativo(api_de(conn), {"ticker": "XPTO9", "classe": classe})
    if classe.strip().upper() in peculium.Api.CLASSES:
        assert r["ok"] is True
    else:
        assert r["ok"] is False and "classe inválida" in r["erro"]


def test_editar_ativo_tambem_valida(conn):
    r = peculium.Api.editar_ativo(api_de(conn), 1, {"classe": "CRIPTO"})
    assert r["ok"] is False and "classe inválida" in r["erro"]


def test_ticker_repetido_fala_portugues(conn):
    """Antes: "UNIQUE constraint failed: ativos.ticker"."""
    r = peculium.Api.cadastrar_ativo(api_de(conn), {"ticker": "PETR4", "classe": "ACAO"})
    assert r["ok"] is False and r["erro"] == "PETR4 já está cadastrado"


# ------------------------------------------------------- § 2.8 IRRF anual

def test_irrf_excedente_nao_atravessa_o_ano(conn):
    """IN RFB 1585 art. 63 §5: o IRRF abate o imposto dos meses seguintes **do
    mesmo ano-calendário**. O que sobra em 31/12 vai para o ajuste anual, não
    para janeiro — o programa abatia R$ 3.500 de 2026 no imposto de 2027."""
    lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo=2, instituicao=1,
                quantidade=2000, preco=10, hoje="2027-12-31")
    lanc.lancar(conn, data="2026-12-10", tipo="VENDA", ativo=2, instituicao=1,
                quantidade=2000, preco=15, irrf=5000, hoje="2027-12-31")
    lanc.lancar(conn, data="2027-03-10", tipo="COMPRA", ativo=2, instituicao=1,
                quantidade=2000, preco=10, hoje="2027-12-31")
    lanc.lancar(conn, data="2027-04-10", tipo="VENDA", ativo=2, instituicao=1,
                quantidade=2000, preco=30, irrf=0, hoje="2027-12-31")
    f = fisco.apurar(razao.apurar(conn))
    de_2027 = [b for b in f.baldes if b.competencia.startswith("2027")][0]
    assert de_2027.irrf == 0.0
    assert de_2027.a_pagar == pytest.approx(6000.0)      # não 2500,00
    assert any("não passa para o ano seguinte" in a for a in f.avisos)


def test_irrf_compensa_dentro_do_mesmo_ano(conn):
    """O que continua valendo: dentro do ano, o excedente abate os meses
    seguintes — é o caso comum de quem vende todo mês."""
    lanc.lancar(conn, data="2026-01-05", tipo="COMPRA", ativo=2, instituicao=1,
                quantidade=2000, preco=10, hoje=HOJE)
    lanc.lancar(conn, data="2026-03-10", tipo="VENDA", ativo=2, instituicao=1,
                quantidade=2000, preco=15, irrf=5000, hoje=HOJE)
    lanc.lancar(conn, data="2026-06-10", tipo="COMPRA", ativo=2, instituicao=1,
                quantidade=2000, preco=10, hoje=HOJE)
    lanc.lancar(conn, data="2026-09-10", tipo="VENDA", ativo=2, instituicao=1,
                quantidade=2000, preco=30, hoje=HOJE)
    setembro = [b for b in fisco.apurar(razao.apurar(conn)).baldes
                if b.competencia == "2026-09"][0]
    assert setembro.irrf == pytest.approx(3500.0)


# ------------------------------------------------------- § 3 arestas

def test_cotar_com_ticker_fora_do_cadastro_vira_falha(conn):
    """`ids[alvo]` ficava FORA do try e escapava como KeyError cru, contra a
    docstring que promete que nenhuma exceção escapa."""
    conn.execute("INSERT OR REPLACE INTO config VALUES ('cotacao_online','1')")
    r = cotacoes.cotar(conn, "2026-01-05", ["ITUB4"], buscador=lambda t: 30.0)
    assert r.falhas == {"ITUB4": "ativo não cadastrado"}


@pytest.mark.parametrize("dados, erro", [
    (cofre.MAGIC, "truncado"),
    (cofre.MAGIC + struct.pack(">BH", 1, 4) + b"zzzz" + b"0" * 32, "ilegível"),
    (cofre.MAGIC + struct.pack(">BH", 1, 2) + b"{}" + b"0" * 32, "campos esperados"),
    (cofre.MAGIC + struct.pack(">BH", 1, 2) + b"{}", "acaba antes"),
])
def test_arquivo_corrompido_da_erro_do_dominio(dados, erro):
    """O módulo traduzia com cuidado o erro do SQLite e deixava escapar
    `struct.error: unpack requires a buffer of 3 bytes` — que na tela não diz
    nada a quem só quer saber que o arquivo não serve."""
    with pytest.raises(cofre.ArquivoInvalido, match=erro):
        cofre._partir(dados)


def test_cabecalho_nao_pode_pedir_memoria_absurda():
    """O header não é autenticado: `n = 2**30` faria o scrypt tentar alocar cerca
    de um terabyte antes de descobrir que a senha nem era daquele embrulho."""
    with pytest.raises(cofre.ArquivoInvalido, match="acima do teto"):
        cofre._derivar("senha", b"0" * 16, {"n": 2 ** 30, "r": 8, "p": 1})
    assert len(cofre._derivar("senha", b"0" * 16, {"n": 2 ** 8, "r": 8, "p": 1})) == 32


def test_prejuizo_mostrado_e_o_do_ano_escolhido(conn):
    """`f.prejuizo` é o saldo final de tudo: abrir a tela de 2025 mostrando o
    acumulado de hoje dizia um número que nunca existiu naquele dezembro."""
    for ano, preco in (("2025", 8), ("2026", 9)):
        lanc.lancar(conn, data=f"{ano}-01-05", tipo="COMPRA", ativo=3,
                    instituicao=1, quantidade=1000, preco=10, hoje=HOJE)
        lanc.lancar(conn, data=f"{ano}-06-05", tipo="VENDA", ativo=3,
                    instituicao=1, quantidade=1000, preco=preco, hoje=HOJE)
    api = api_de(conn)
    assert peculium.Api.impostos(api, 2025)["dados"]["prejuizo"]["FII"] == pytest.approx(2000)
    assert peculium.Api.impostos(api, 2026)["dados"]["prejuizo"]["FII"] == pytest.approx(3000)


def test_vencido_e_relativo_a_data_consultada(conn):
    """`date.today()` fazia a posição de 31/12 do ano passado marcar como vencido
    o papel que só venceu depois dela."""
    import renda_fixa as rf
    conn.execute("INSERT INTO ativos (id, ticker, classe) VALUES (9,'CDB1','RF')")
    rf.cadastrar(conn, ativo_id=9, emissao="2025-01-05", indexador="CDI", taxa=100,
                 vencimento="2026-06-30")
    assert rf.titulo(conn, 9).venceu_ate("2026-12-31") is True
    assert rf.titulo(conn, 9).venceu_ate("2026-01-31") is False
    # e pela porta que a tela usa, que é onde o defeito aparecia
    lanc.lancar(conn, data="2025-01-05", tipo="COMPRA", ativo=9, instituicao=1,
                quantidade=1000, preco=1, hoje=HOJE)
    assert rf.posicao(conn, "2026-01-31")[0]["vencido"] is False
    assert rf.posicao(conn, "2026-12-31")[0]["vencido"] is True


def test_pagamentos_chegam_a_tela_para_poder_cancelar(conn):
    """`cancelar_pagamento` existia sem nenhuma chamada na interface, e um DARF
    digitado com o valor trocado ficava lá para sempre."""
    _darf(conn)
    identificador = obrigacoes.registrar(conn, "2026-02", 100.0, "2026-04-20")
    d = peculium.Api.impostos(api_de(conn), 2026)["dados"]
    assert [p["id"] for p in d["pagamentos"]] == [identificador]
    assert d["pagamentos"][0]["data_br"] == "20/04/2026"
    peculium.Api.cancelar_pagamento(api_de(conn), identificador)
    assert peculium.Api.impostos(api_de(conn), 2026)["dados"]["pagamentos"] == []
