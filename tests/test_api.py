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


def test_trancar_e_reabrir(api):
    """Regressão: trancar só recarregava a tela, o cofre seguia aberto no Python
    e a reabertura esbarrava na própria trava — "já está aberto em outra janela",
    sem outra janela nenhuma."""
    dados(api.criar_cofre("senha mestra boa"))
    dados(api.cadastrar_instituicao({"nome": "Corretora Teste"}))

    assert dados(api.fechar_cofre())["fechado"] is True
    assert api.carteira()["ok"] is False          # trancado de verdade

    dados(api.abrir_cofre("senha mestra boa"))
    assert len(dados(api.cadastros())["instituicoes"]) == 1


def test_reabrir_sem_ter_trancado_se_recupera(api):
    """A janela pode ser recarregada sem passar pelo botão Trancar; abrir de novo
    não pode travar contra o cofre que este mesmo processo já segura."""
    dados(api.criar_cofre("senha mestra boa"))
    dados(api.abrir_cofre("senha mestra boa"))    # sem fechar antes
    dados(api.carteira())


def test_fechar_duas_vezes_nao_quebra(api):
    dados(api.criar_cofre("senha mestra boa"))
    assert dados(api.fechar_cofre())["fechado"] is True
    assert dados(api.fechar_cofre())["fechado"] is False


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


# ------------------------------------------------------- cadastros editáveis

def _cofre_com_cadastros(api):
    dados(api.criar_cofre("senha mestra boa"))
    inst = dados(api.cadastrar_instituicao({"nome": "Corretora Teste"}))["id"]
    ativo = dados(api.cadastrar_ativo({"ticker": "PETR4", "classe": "ACAO"}))["id"]
    return inst, ativo


def test_editar_ativo_preserva_os_lancamentos(api):
    """Renomear é seguro porque o lançamento aponta para o **id**, não o texto."""
    inst, ativo = _cofre_com_cadastros(api)
    dados(api.lancar({"data": "05/01/2026", "tipo": "COMPRA", "ativo": "PETR4",
                      "instituicao": "Corretora Teste", "quantidade": 100,
                      "preco": 30.0}))
    dados(api.editar_ativo(ativo, {"ticker": "petr3", "nome": "Petrobras ON",
                                   "classe": "ACAO"}))
    carteira = dados(api.carteira())
    assert len(carteira) == 1
    assert carteira[0]["ticker"] == "PETR3"          # normaliza a caixa
    assert carteira[0]["quantidade"] == 100          # o lançamento sobreviveu


def test_editar_ativo_registra_a_troca_de_classe(api):
    """A classe muda a alíquota do imposto: a auditoria guarda antes e depois."""
    _inst, ativo = _cofre_com_cadastros(api)
    dados(api.editar_ativo(ativo, {"ticker": "PETR4", "classe": "FII"}))
    detalhe = api._conn.execute(
        "SELECT detalhe FROM auditoria WHERE acao='ATIVO_EDITADO'").fetchone()[0]
    assert "PETR4/ACAO" in detalhe and "PETR4/FII" in detalhe


def test_editar_o_que_nao_existe_falha_com_explicacao(api):
    dados(api.criar_cofre("senha mestra boa"))
    for resposta in (api.editar_ativo(999, {"ticker": "X", "classe": "ACAO"}),
                     api.editar_instituicao(999, {"nome": "X"})):
        assert resposta["ok"] is False and "não existe" in resposta["erro"]


def test_editar_instituicao_normaliza_o_cnpj(api):
    inst, _ativo = _cofre_com_cadastros(api)
    dados(api.editar_instituicao(inst, {"nome": "XP INVESTIMENTOS",
                                        "cnpj": "02332886000104"}))
    guardada = dados(api.cadastros())["instituicoes"][0]
    assert (guardada["nome"], guardada["cnpj"]) == ("XP INVESTIMENTOS",
                                                    "02.332.886/0001-04")


def test_cnpj_errado_nao_entra_no_cadastro(api):
    """Um dígito trocado viveria no cadastro e voltaria como "não encontrado"
    toda vez que alguém tentasse usá-lo."""
    dados(api.criar_cofre("senha mestra boa"))
    resposta = api.cadastrar_instituicao({"nome": "Fantasma",
                                          "cnpj": "02332886000105"})
    assert resposta["ok"] is False and "CNPJ inválido" in resposta["erro"]
    assert dados(api.cadastros())["instituicoes"] == []


def test_instituicao_sem_cnpj_continua_valendo(api):
    """O campo é opcional: exigir CNPJ para lançar uma compra seria atrito à toa."""
    dados(api.criar_cofre("senha mestra boa"))
    inst = dados(api.cadastrar_instituicao({"nome": "Corretora Teste"}))["id"]
    dados(api.editar_instituicao(inst, {"nome": "Corretora Teste", "cnpj": ""}))
    assert dados(api.cadastros())["instituicoes"][0]["cnpj"] is None


def test_arquivar_nao_apaga_lancamento(api):
    inst, ativo = _cofre_com_cadastros(api)
    dados(api.lancar({"data": "05/01/2026", "tipo": "COMPRA", "ativo": "PETR4",
                      "instituicao": "Corretora Teste", "quantidade": 100,
                      "preco": 30.0}))
    dados(api.editar_ativo(ativo, {"ativo": 0}))
    assert dados(api.cadastros())["ativos"][0]["ativo"] == 0
    assert len(dados(api.carteira())) == 1
    assert len(dados(api.listar_lancamentos())) == 1


def test_cnpj_da_importacao_ganha_mascara_na_leitura(api):
    """A importação da B3 grava só os dígitos; a máscara é da leitura, senão
    cada tela repetiria a regra de formatação."""
    dados(api.criar_cofre("senha mestra boa"))
    api._conn.execute("INSERT INTO instituicoes (nome, cnpj) VALUES (?,?)",
                      ("XP INVESTIMENTOS", "02332886000104"))
    assert dados(api.cadastros())["instituicoes"][0]["cnpj"] == "02.332.886/0001-04"


# ------------------------------------------------------------------- painel

def test_media_de_proventos_divide_pelos_meses_que_tiveram(api):
    """Dividir pelo ano em agosto diria metade do que o usuário recebe por mês."""
    inst, ativo = _cofre_com_cadastros(api)
    for data, valor in (("15/05/2026", 10.0), ("15/06/2026", 20.0)):
        dados(api.lancar({"data": data, "tipo": "RENDIMENTO", "ativo": "PETR4",
                          "instituicao": "Corretora Teste", "valor": valor}))
    d = dados(api.painel())
    assert d["proventos_ano"] == pytest.approx(30.0)
    assert d["meses_com_provento"] == 2          # não 12, nem os meses corridos


def test_painel_acusa_a_divergencia_da_ultima_posicao(api):
    """O retrato fica guardado para o painel poder acusar depois que a tela de
    importação fechou — e a conferência é REFEITA, não lida de um resultado."""
    inst, ativo = _cofre_com_cadastros(api)
    api._conn.execute(
        "INSERT INTO posicao_b3 (data, ticker, classe, quantidade, valor)"
        " VALUES ('2026-08-03','PETR4','ACAO',100,3850.0)")
    d = dados(api.painel())
    assert d["divergencia"]["data"] == "03/08/2026"
    assert d["divergencia"]["a_mais"] == pytest.approx(3850.0)
    assert [i["ticker"] for i in d["divergencia"]["itens"]] == ["PETR4"]

    # lançar a compra que faltava apaga o aviso, sem tocar no retrato guardado
    dados(api.lancar({"data": "05/01/2026", "tipo": "COMPRA", "ativo": "PETR4",
                      "instituicao": "Corretora Teste", "quantidade": 100,
                      "preco": 30.0}))
    assert dados(api.painel())["divergencia"] is None


def test_sem_retrato_importado_nao_ha_divergencia(api):
    _cofre_com_cadastros(api)
    assert dados(api.painel())["divergencia"] is None


def test_series_dos_graficos_do_painel(api):
    inst, ativo = _cofre_com_cadastros(api)
    dados(api.lancar({"data": "05/01/2026", "tipo": "COMPRA", "ativo": "PETR4",
                      "instituicao": "Corretora Teste", "quantidade": 100,
                      "preco": 30.0, "custos": 5.0}))
    dados(api.lancar({"data": "10/03/2026", "tipo": "COMPRA", "ativo": "PETR4",
                      "instituicao": "Corretora Teste", "quantidade": 50,
                      "preco": 32.0}))
    d = dados(api.painel())
    assert [a["competencia"] for a in d["aportes_mes"]] == ["JAN/26", "MAR/26"]
    # acumulado, não o do mês: o gráfico é de patrimônio investido
    assert [a["acumulado"] for a in d["aportes_mes"]] == [3005.0, 4605.0]
