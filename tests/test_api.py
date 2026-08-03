"""Ponte Python↔UI sem pywebview.

O `peculium.py` importa `webview` **dentro** dos métodos que precisam dele, e é
de propósito: assim a ponte inteira é testável sem a janela, e um erro de import
no módulo de entrada não espera o primeiro duplo clique para aparecer.
"""
import pytest

import peculium


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(peculium, "PREFERENCIAS", tmp_path / "preferencias.json")
    return peculium.Api(tmp_path / "carteira.pec")


def dados(resposta):
    assert resposta["ok"] is True, resposta.get("erro")
    return resposta["dados"]


def test_cofre_fechado_so_responde_o_essencial(api):
    assert dados(api.estado())["existe"] is False
    for chamada in (api.painel, api.carteira, api.config):
        resposta = chamada()
        assert resposta["ok"] is False
        assert "cofre fechado" in resposta["erro"]


def test_senha_curta_e_recusada(api):
    resposta = api.criar_cofre("1234")
    assert resposta["ok"] is False and "8 caracteres" in resposta["erro"]


def test_ciclo_pela_ponte(api):
    chave = dados(api.criar_cofre("senha mestra boa"))["chave_recuperacao"]
    assert len(chave.replace("-", "")) >= 50

    dados(api.cadastrar_instituicao({"nome": "Corretora Teste"}))
    dados(api.cadastrar_ativo({"ticker": "petr4", "classe": "acao"}))
    cadastro = dados(api.cadastros())
    assert cadastro["ativos"][0]["ticker"] == "PETR4"      # normalizado

    dados(api.lancar({"data": "05/01/2026", "tipo": "COMPRA",
                      "ativo": cadastro["ativos"][0]["id"],
                      "instituicao": cadastro["instituicoes"][0]["id"],
                      "quantidade": 100, "preco": 10, "custos": 5}))
    (posicao,) = dados(api.carteira())
    assert posicao["ticker"] == "PETR4" and posicao["custo"] == pytest.approx(1005)

    painel = dados(api.painel())
    assert painel["ativos"] == 1 and painel["custo"] == pytest.approx(1005)

    (lancamento,) = dados(api.listar_lancamentos())
    assert lancamento["data_br"] == "05/01/2026"           # data em BR na tela
    dados(api.estornar(lancamento["id"], "engano"))
    assert dados(api.carteira()) == []


def test_erro_de_preenchimento_volta_como_mensagem(api):
    dados(api.criar_cofre("senha mestra boa"))
    resposta = api.lancar({"data": "05/01/2026", "tipo": "COMPRA",
                           "ativo": None, "quantidade": 1, "preco": 1})
    assert resposta["ok"] is False
    assert "ativo é obrigatório" in resposta["erro"]       # não vaza traceback


def test_config_persiste_o_tema_fora_do_cofre(api, tmp_path):
    """O tema precisa ser legível ANTES da senha, senão a tela de trava pisca
    branca — por isso ele também vai para um arquivo em claro, que não é dado
    sensível."""
    dados(api.criar_cofre("senha mestra boa"))
    dados(api.salvar_config({"tema": "aerarium"}))
    assert peculium.preferencias()["tema"] == "aerarium"
    assert dados(api.config())["tema"] == "aerarium"


def test_relatorio_pela_ponte(api):
    dados(api.criar_cofre("senha mestra boa"))
    disponiveis = dados(api.relatorios_disponiveis())
    assert {"posicao", "apuracao", "obrigacoes"} <= {r["chave"] for r in disponiveis}
    rel = dados(api.relatorio("posicao", {}))
    assert rel["colunas"][0] == "Ativo"
