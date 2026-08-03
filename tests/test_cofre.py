"""Testes do cofre. Nenhum extrato real entra aqui — carteira sintética."""
import pytest

import cofre

# scrypt de verdade custa ~0,5 s por abertura de propósito; nos testes o custo
# vira parâmetro do cabeçalho e o arquivo continua sendo lido pelo mesmo caminho
LEVE = {"n": 2 ** 12, "r": 8, "p": 1}


@pytest.fixture
def alvo(tmp_path):
    return tmp_path / "carteira.pec"


def _semear(c):
    c.conn.execute("INSERT INTO instituicoes (nome) VALUES ('Corretora Alfa')")
    c.conn.execute("INSERT INTO ativos (ticker, classe) VALUES ('PETR4', 'ACAO')")
    c.commit()


def test_round_trip(alvo):
    with cofre.criar(alvo, "senha longa e boa", params=LEVE)[0] as c:
        _semear(c)
    with cofre.abrir(alvo, "senha longa e boa") as c:
        assert c.conn.execute("SELECT ticker FROM ativos").fetchone()[0] == "PETR4"


def test_parametros_de_producao(alvo):
    """Todo o resto da suíte usa scrypt barato; este exercita o PARAMS real —
    senão o caminho que o usuário roda nunca seria testado."""
    assert cofre.PARAMS["n"] >= 2 ** 16     # pega quem baixar o custo sem querer
    with cofre.criar(alvo, "senha de verdade")[0] as c:
        _semear(c)
    with cofre.abrir(alvo, "senha de verdade") as c:
        assert c.conn.execute("SELECT count(*) FROM ativos").fetchone()[0] == 1


def test_senha_errada(alvo):
    cofre.criar(alvo, "certa", params=LEVE)[0].fechar()
    with pytest.raises(cofre.SenhaIncorreta):
        cofre.abrir(alvo, "errada")


def test_nada_em_claro_no_arquivo(alvo):
    with cofre.criar(alvo, "senha", params=LEVE)[0] as c:
        c.conn.execute("INSERT INTO ativos (ticker, classe) VALUES ('SEGREDO11','FII')")
        c.commit()
    bruto = alvo.read_bytes()
    assert b"SEGREDO11" not in bruto
    assert b"CREATE TABLE" not in bruto   # nem o esquema vaza


def test_chave_de_recuperacao_abre(alvo):
    c, chave = cofre.criar(alvo, "esquecida", params=LEVE)
    _semear(c)
    c.fechar()
    with cofre.abrir_com_recuperacao(alvo, chave) as r:
        assert r.conn.execute("SELECT count(*) FROM ativos").fetchone()[0] == 1
    # tolera o jeito como o usuário digita o que imprimiu
    with cofre.abrir_com_recuperacao(alvo, chave.lower().replace("-", " ")) as r:
        assert r.conn.execute("SELECT count(*) FROM ativos").fetchone()[0] == 1


def test_chave_de_recuperacao_errada(alvo):
    cofre.criar(alvo, "x", params=LEVE)[0].fechar()
    with pytest.raises(cofre.SenhaIncorreta):
        cofre.abrir_com_recuperacao(alvo, cofre.gerar_chave_recuperacao())


def test_trocar_senha(alvo):
    c, chave = cofre.criar(alvo, "antiga", params=LEVE)
    _semear(c)
    c.trocar_senha("antiga", "nova")
    c.fechar()

    with pytest.raises(cofre.SenhaIncorreta):
        cofre.abrir(alvo, "antiga")
    with cofre.abrir(alvo, "nova") as r:
        assert r.conn.execute("SELECT count(*) FROM ativos").fetchone()[0] == 1
    # a DEK não mudou, então a chave de recuperação impressa continua valendo
    cofre.abrir_com_recuperacao(alvo, chave).fechar()


def test_trocar_senha_exige_a_atual(alvo):
    c = cofre.criar(alvo, "antiga", params=LEVE)[0]
    with pytest.raises(cofre.SenhaIncorreta):
        c.trocar_senha("chute", "nova")
    c.fechar()


def test_arquivo_adulterado(alvo):
    cofre.criar(alvo, "senha", params=LEVE)[0].fechar()
    bruto = bytearray(alvo.read_bytes())
    bruto[-1] ^= 0xFF          # um bit no corpo cifrado
    alvo.write_bytes(bruto)
    with pytest.raises(cofre.ArquivoInvalido):
        cofre.abrir(alvo, "senha")


def test_arquivo_alheio(alvo):
    alvo.write_bytes(b"isto nao e um cofre" * 10)
    with pytest.raises(cofre.ArquivoInvalido):
        cofre.abrir(alvo, "senha")


def test_backups_rotacionam(alvo):
    with cofre.criar(alvo, "senha", params=LEVE)[0] as c:
        for i in range(5):
            c.conn.execute("INSERT INTO ativos (ticker, classe) VALUES (?, 'ACAO')",
                           (f"TICK{i}",))
            c.commit()
    for i in (1, 2, 3):
        assert alvo.with_suffix(f".pec.{i}").exists()
    assert not alvo.with_suffix(".pec.4").exists()
    # o backup mais recente abre e está uma gravação atrás
    with cofre.abrir(alvo.with_suffix(".pec.1"), "senha") as r:
        assert r.conn.execute("SELECT count(*) FROM ativos").fetchone()[0] == 4


def test_uma_janela_por_cofre(alvo):
    c = cofre.criar(alvo, "senha", params=LEVE)[0]
    with pytest.raises(cofre.CofreEmUso):
        cofre.abrir(alvo, "senha")
    c.fechar()
    cofre.abrir(alvo, "senha").fechar()   # solta ao fechar


def test_razao_roda_sobre_o_banco_desserializado(alvo):
    """O motor precisa funcionar sobre a conexão que veio do cofre, não só sobre
    um :memory: recém-criado."""
    import razao

    with cofre.criar(alvo, "senha", params=LEVE)[0] as c:
        _semear(c)
        c.conn.execute(
            "INSERT INTO lancamentos (data, tipo, ativo_id, instituicao_id,"
            " quantidade, preco, valor, criado_em)"
            " VALUES ('2026-01-05','COMPRA',1,1,100,10,1000,'2026-01-05')")
        c.commit()
    with cofre.abrir(alvo, "senha") as c:
        (pos,) = razao.carteira(c.conn)
        assert pos.ticker == "PETR4" and pos.preco_medio == 10


def test_nao_sobrescreve_cofre_existente(alvo):
    cofre.criar(alvo, "senha", params=LEVE)[0].fechar()
    with pytest.raises(cofre.CofreError):
        cofre.criar(alvo, "outra", params=LEVE)
