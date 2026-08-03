"""Leitura e escrita de número e data em pt-BR — o par que os importadores e os
relatórios compartilham. Bug aqui é bug de dinheiro ou de competência errada."""
import pytest

import textos


@pytest.mark.parametrize("texto, esperado", [
    ("1.500", 1500.0),        # milhar: grupos de exatamente 3 dígitos
    ("1.234,56", 1234.56),
    ("1234.56", 1234.56),     # decimal: 2 dígitos depois do ponto
    ("10.5", 10.5),
    ("1.234.567", 1234567.0),
    ("R$ 1.234,56", 1234.56),
    ("-", 0.0),
    ("", 0.0),
    ("-1.500", -1500.0),
])
def test_numero(texto, esperado):
    assert textos.numero(texto) == pytest.approx(esperado)


@pytest.mark.parametrize("entrada, esperado", [
    ("23/04/2026", "2026-04-23"),
    ("2026-04-23", "2026-04-23"),
    ("05/01/26", "2026-01-05"),
])
def test_data_iso(entrada, esperado):
    assert textos.data_iso(entrada) == esperado


def test_data_iso_recusa_o_irreconhecivel():
    with pytest.raises(ValueError, match="irreconhecível"):
        textos.data_iso("ontem")


@pytest.mark.parametrize("iso, esperado", [
    ("2026-04-23", "23/04/2026"),
    ("2026-12-31", "31/12/2026"),
    ("2026-04-23T10:00:00", "23/04/2026"),   # tolera carimbo de hora
    ("", ""),
    (None, ""),
])
def test_data_br(iso, esperado):
    assert textos.data_br(iso) == esperado


@pytest.mark.parametrize("iso, esperado", [
    ("2026-07", "07/2026"),
    ("2026-07-21", "07/2026"),               # aceita a data cheia
    ("", ""),
    (None, ""),
])
def test_competencia_br(iso, esperado):
    assert textos.competencia_br(iso) == esperado


def test_ida_e_volta():
    assert textos.data_br(textos.data_iso("23/04/2026")) == "23/04/2026"
