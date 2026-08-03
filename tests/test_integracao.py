"""A pilha inteira dentro do cofre cifrado.

Cada módulo é testado com uma conexão solta; aqui se prova que eles funcionam
juntos sobre o banco que veio do `deserialize`, e que tudo sobrevive a fechar e
reabrir o arquivo.
"""
import pytest

import cofre
import fisco
import importar_b3 as b3
import lancamentos as lanc
import obrigacoes
import razao
import relatorios

LEVE = {"n": 2 ** 12, "r": 8, "p": 1}
HOJE = "2026-08-03"

NEGOCIACAO = "\n".join([
    "Data do Negócio;Tipo de Movimentação;Mercado;Prazo/Vencimento;Instituição;"
    "Código de Negociação;Quantidade;Preço;Valor",
    "05/01/2026;Compra;Mercado à Vista;-;CORRETORA TESTE;PETR4;1000;20,00;20.000,00",
    "10/06/2026;Venda;Mercado à Vista;-;CORRETORA TESTE;PETR4;1000;30,00;30.000,00",
])


def test_ciclo_completo_dentro_do_cofre(tmp_path):
    alvo = tmp_path / "carteira.pec"
    arquivo = tmp_path / "negociacao.csv"
    arquivo.write_text(NEGOCIACAO, encoding="utf-8-sig")

    with cofre.criar(alvo, "senha mestra boa", params=LEVE)[0] as c:
        # 1. importa negócios da B3
        conferencia = b3.ler(arquivo, c.conn)
        assert conferencia.novas == 2
        assert b3.gravar(c.conn, conferencia, classes={"PETR4": "ACAO"}) == 2

        # 2. lança um provento à mão e um evento corporativo
        lanc.lancar(c.conn, data="20/03/2026", tipo="DIVIDENDO", ativo="PETR4",
                    valor=500, hoje=HOJE)
        lanc.registrar_evento(c.conn, ativo="PETR4", data_ex="2026-02-01",
                              tipo="DESDOBRAMENTO", fator=2, hoje=HOJE)
        c.commit()

        # 3. o razão vê tudo junto: o desdobramento entra entre a compra e a venda
        ap = razao.apurar(c.conn)
        (venda,) = ap.vendas
        assert venda.quantidade == 1000
        assert venda.custo_base == pytest.approx(10_000)   # metade do custo
        assert ap.carteira()[0].quantidade == 1000         # 2000 − 1000 vendidas

        # 4. o fisco apura sobre o que o razão produziu
        f = fisco.apurar(ap)
        (darf,) = f.darfs
        assert darf.competencia == "2026-06" and darf.valor == pytest.approx(3_000)

        # 5. a obrigação nasce vencida e ganha multa
        (obrigacao,) = obrigacoes.listar(c.conn, hoje="2026-08-10")
        assert obrigacao.situacao == obrigacoes.VENCIDO and obrigacao.multa > 0
        obrigacoes.registrar(c.conn, "2026-06", 3_000.0, "2026-08-10",
                             multa=obrigacao.multa)
        c.commit()
        assert obrigacoes.listar(c.conn, hoje="2026-08-11")[0].situacao == \
            obrigacoes.PAGO

        # 6. relatório sai com data brasileira
        rel = relatorios.operacoes(c.conn)
        assert rel.linhas[0][0] == "05/01/2026"
        assert "&lt;" not in relatorios.documento(rel)

    # 7. tudo isso sobrevive a fechar e reabrir o arquivo cifrado
    with cofre.abrir(alvo, "senha mestra boa") as c:
        assert razao.carteira(c.conn)[0].quantidade == 1000
        assert obrigacoes.listar(c.conn, hoje="2026-08-11")[0].situacao == \
            obrigacoes.PAGO
        assert [r["acao"] for r in lanc.historico(c.conn)] == ["EVENTO", "LANCAR"]


def test_cofre_antigo_migra_ao_abrir(tmp_path):
    """Regressão: `esquema.aplicar` só rodava na CRIAÇÃO do cofre.

    Um cofre gravado por versão anterior nunca migrava, e a primeira tela que
    tocasse a tabela nova morria com o erro cru do SQLite — foi o que aconteceu
    na Carteira com "no such column: t.ativo_id"."""
    import esquema
    import renda_fixa

    alvo = tmp_path / "antigo.pec"
    with cofre.criar(alvo, "senha mestra boa", params=LEVE)[0] as c:
        # rebaixa o cofre para o formato da v0.1.x
        c.conn.execute("DROP TABLE rf_titulos")
        c.conn.execute("CREATE TABLE rf_titulos (lancamento_id INTEGER PRIMARY KEY,"
                       " indexador TEXT, taxa REAL, vencimento TEXT, emissor TEXT,"
                       " isento INTEGER NOT NULL DEFAULT 0)")
        c.conn.execute("UPDATE config SET valor='1' WHERE chave='esquema'")
        c.commit()

    with cofre.abrir(alvo, "senha mestra boa") as c:
        assert esquema.versao_do_banco(c.conn) == esquema.VERSAO
        assert renda_fixa.listar(c.conn) == []          # a consulta nova funciona

    # e a migração ficou gravada, não só em memória
    with cofre.abrir(alvo, "senha mestra boa") as c:
        colunas = {x[1] for x in c.conn.execute("PRAGMA table_info(rf_titulos)")}
        assert "ativo_id" in colunas and "lancamento_id" not in colunas


def test_migracao_que_falha_nao_impede_abrir(tmp_path):
    """Um cofre que não abre é muito pior que uma tela quebrada.

    A migração se recusa a rodar quando há dado no formato antigo; nesse caso o
    cofre tem de abrir mesmo assim, avisando."""
    alvo = tmp_path / "trancado.pec"
    with cofre.criar(alvo, "senha mestra boa", params=LEVE)[0] as c:
        c.conn.execute("DROP TABLE rf_titulos")
        c.conn.execute("CREATE TABLE rf_titulos (lancamento_id INTEGER PRIMARY KEY,"
                       " indexador TEXT)")
        c.conn.execute("INSERT INTO rf_titulos VALUES (1, 'CDI')")   # dado antigo
        c.conn.execute("UPDATE config SET valor='1' WHERE chave='esquema'")
        c.commit()

    with cofre.abrir(alvo, "senha mestra boa") as c:
        assert c.aviso_esquema and "não pôde ser atualizado" in c.aviso_esquema
        # o resto do programa continua funcionando
        assert c.conn.execute("SELECT count(*) FROM lancamentos").fetchone()[0] == 0


def test_cofre_recusa_banco_corrompido(tmp_path):
    """O GCM prova que os bytes são os que gravamos; não prova que o que
    gravamos era um banco são."""
    alvo = tmp_path / "carteira.pec"
    c, _ = cofre.criar(alvo, "senha", params=LEVE)
    c.fechar()

    # reescreve o cofre com um "banco" que decifra mas não é SQLite válido
    header, nonce, _ = cofre._partir(alvo.read_bytes())
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    dek = cofre._desembrulhar(
        cofre._derivar("senha", __import__("base64").b64decode(header["salt"]),
                       header["kdf"]), header["senha"])
    lixo = b"SQLite format 3\x00" + b"\x00" * 4096
    alvo.write_bytes(cofre._montar(header, nonce, AESGCM(dek).encrypt(nonce, lixo, None)))

    with pytest.raises(cofre.ArquivoInvalido):
        cofre.abrir(alvo, "senha")
