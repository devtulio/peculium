"""Leitura de número e data em formato brasileiro.

Vive fora dos importadores porque os três (B3, nota de corretagem e, na v1.1,
renda fixa) precisam da mesma conversão — e um bug aqui é um bug de dinheiro.
"""
from __future__ import annotations

import re
from datetime import datetime

_MILHAR = re.compile(r"^-?\d{1,3}(\.\d{3})+$")


def numero(valor) -> float:
    """Aceita 1.234,56 / 1234.56 / 1.500 / R$ 1.234,56 / '-' / vazio.

    O caso difícil é `1.500` sem vírgula nenhuma: pode ser mil e quinhentos
    (pt-BR) ou um e meio (en-US). Resolve pelo formato — ponto só é milhar
    quando separa grupos de exatamente três dígitos.

    # ponytail: um arquivo en-US com o valor 1.500 (um e meio) seria lido como
    # 1500. Os documentos aqui são todos pt-BR; se entrar arquivo de outra
    # origem, o formato vira parâmetro.
    """
    if valor is None or isinstance(valor, (int, float)):
        return float(valor or 0)
    texto = str(valor).strip().replace("R$", "").replace(" ", "").replace("\xa0", "")
    if texto in ("", "-", "--"):
        return 0.0
    if "," in texto:                       # pt-BR: ponto é milhar, vírgula é decimal
        texto = texto.replace(".", "").replace(",", ".")
    elif _MILHAR.match(texto):
        texto = texto.replace(".", "")
    try:
        return float(texto)
    except ValueError:
        return 0.0


def data_br(iso: str | None) -> str:
    """`2026-04-23` -> `23/04/2026`.

    O banco guarda ISO porque ordenação e comparação dependem disso; a conversão
    para o formato brasileiro é de apresentação e mora só aqui."""
    if not iso:
        return ""
    partes = str(iso)[:10].split("-")
    return f"{partes[2]}/{partes[1]}/{partes[0]}" if len(partes) == 3 else str(iso)


def competencia_br(iso: str | None) -> str:
    """`2026-07` -> `07/2026`."""
    if not iso:
        return ""
    partes = str(iso)[:7].split("-")
    return f"{partes[1]}/{partes[0]}" if len(partes) == 2 else str(iso)


def data_iso(valor) -> str:
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    texto = str(valor).strip()[:10]
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"data irreconhecível: {valor!r}")
