"""Consulta de CNPJ. Nenhum teste toca a rede: as fontes são injetadas.

Os CNPJ usados aqui são de empresas públicas e constam de documento público
(a XP e a Petrobras aparecem nos próprios relatórios da B3). Nada aqui é dado
pessoal do usuário.
"""
from __future__ import annotations

import pytest

import cnpj

XP = "02332886000104"
PETROBRAS = "33000167000101"


@pytest.mark.parametrize("valor", [
    XP, PETROBRAS, "02.332.886/0001-04", "00416968000101", "06990590000123",
])
def test_aceita_cnpj_valido(valor):
    assert cnpj.valido(valor) is True


@pytest.mark.parametrize("valor", [
    "02332886000105",      # último dígito trocado
    "33000167000102",
    "00000000000000",      # todos iguais passam na conta, mas não existem
    "123", "", None,
])
def test_recusa_cnpj_invalido(valor):
    assert cnpj.valido(valor) is False


def test_formata_e_extrai_digitos():
    assert cnpj.formatar(XP) == "02.332.886/0001-04"
    assert cnpj.digitos("02.332.886/0001-04") == XP
    assert cnpj.formatar("abc") == "abc"        # sem 14 dígitos, devolve como veio


def test_digito_verificador_barra_antes_da_rede():
    """Conferir aqui evita gastar uma das três consultas por minuto que a
    ReceitaWS concede, e devolve o erro certo em vez de "não encontrado"."""
    def nunca(_):
        raise AssertionError("não podia ter ido à rede")

    with pytest.raises(cnpj.CnpjInvalido, match="14 dígitos"):
        cnpj.consultar("123", fontes=(nunca,))
    with pytest.raises(cnpj.CnpjInvalido, match="confira"):
        cnpj.consultar("02332886000105", fontes=(nunca,))


def test_usa_a_primeira_fonte_que_responde():
    def _primeira(d):
        return {"cnpj": cnpj.formatar(d), "nome": "XP INVESTIMENTOS CCTVM S/A",
                "fantasia": "", "situacao": "ATIVA", "fonte": "ReceitaWS"}

    def _segunda(_):
        raise AssertionError("a reserva não devia ter sido chamada")

    assert cnpj.consultar(XP, fontes=(_primeira, _segunda))["fonte"] == "ReceitaWS"


def test_cai_para_a_reserva_quando_a_primeira_falha():
    """A ReceitaWS limita a três consultas por minuto: a reserva não é enfeite."""
    def _primeira(_):
        raise cnpj.ConsultaFalhou("Too many requests")

    def _segunda(d):
        return {"cnpj": cnpj.formatar(d), "nome": "PETROLEO BRASILEIRO S A",
                "fantasia": "", "situacao": "ATIVA", "fonte": "BrasilAPI"}

    assert cnpj.consultar(PETROBRAS, fontes=(_primeira, _segunda))["fonte"] == "BrasilAPI"


def test_resposta_sem_razao_social_nao_conta_como_sucesso():
    """Preencher o cadastro com nome vazio seria pior que não preencher."""
    def _vazia(d):
        return {"cnpj": cnpj.formatar(d), "nome": "", "fantasia": "",
                "situacao": "", "fonte": "ReceitaWS"}

    with pytest.raises(cnpj.ConsultaFalhou, match="sem razão social"):
        cnpj.consultar(XP, fontes=(_vazia,))


def test_falha_de_todas_explica_o_que_houve():
    def _uma(_):
        raise cnpj.ConsultaFalhou("Too many requests")

    def _outra(_):
        raise OSError("sem rede")

    with pytest.raises(cnpj.ConsultaFalhou) as erro:
        cnpj.consultar(XP, fontes=(_uma, _outra))
    assert "Too many requests" in str(erro.value) and "sem rede" in str(erro.value)


def test_so_o_cnpj_entra_na_url(monkeypatch):
    """Regra da casa: nada além do que o usuário digitou sai daqui, e só para
    host que está em constante de módulo."""
    vistas = []

    def espiao(url):
        vistas.append(url)
        return {"status": "OK", "nome": "XP INVESTIMENTOS CCTVM S/A"}

    monkeypatch.setattr(cnpj, "_pegar", espiao)
    assert cnpj.consultar("02.332.886/0001-04")["nome"] == "XP INVESTIMENTOS CCTVM S/A"
    assert vistas == [f"https://{cnpj.RECEITAWS}/v1/cnpj/{XP}"]


def test_a_reserva_tambem_fala_com_host_da_whitelist(monkeypatch):
    vistas = []

    def espiao(url):
        vistas.append(url)
        if cnpj.RECEITAWS in url:
            raise cnpj.ConsultaFalhou("Too many requests")
        return {"razao_social": "PETROLEO BRASILEIRO S A"}

    monkeypatch.setattr(cnpj, "_pegar", espiao)
    assert cnpj.consultar(PETROBRAS)["fonte"] == "BrasilAPI"
    assert vistas[-1] == f"https://{cnpj.BRASILAPI}/api/cnpj/v1/{PETROBRAS}"
