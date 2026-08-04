"""Leitura de número e data em formato brasileiro.

Vive fora dos importadores porque os três (B3, nota de corretagem e, na v1.1,
renda fixa) precisam da mesma conversão — e um bug aqui é um bug de dinheiro.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

_MILHAR = re.compile(r"^-?\d{1,3}(\.\d{3})+$")


BR = "BR"
US = "US"
AUTO = "AUTO"


def chave(texto: str) -> str:
    """Nome de coluna ou de aba sem acento, caixa nem espaço duplo.

    Os cabeçalhos da B3 mudam sem aviso e variam entre relatórios: casar por
    nome normalizado sobrevive a acento e maiúscula, e falha alto quando a
    coluna some de verdade."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", str(texto or ""))
                         if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


# Formas societárias e qualificações que a mesma corretora escreve de jeitos
# diferentes em cada documento. Não identificam ninguém: só enfeitam o nome.
_JURIDICO = (
    "corretora de cambio titulos e valores mobiliarios",
    "distribuidora de titulos e valores mobiliarios",
    "corretora de titulos e valores mobiliarios",
    "corretora de valores mobiliarios",
    "cctvm", "ctvm", "dtvm", "cvmc",
    "s/a", "s.a.", "sa", "ltda", "eireli", "me", "epp",
)


def nome_instituicao(nome: str) -> str:
    """Chave de identidade de uma corretora, a partir do nome escrito.

    Existe porque a MESMA corretora chega com nomes diferentes em cada
    documento. Num acervo real apareceram quatro grafias da XP —
    `XP INVESTIMENTOS CCTVM S/A`, a mesma com ponto final,
    `XP INVESTIMENTOS` e o nome por extenso — e duas do Inter. Sem esta
    normalização são seis cadastros onde deviam existir dois, e a posição por
    instituição fica sem sentido.

    O que sobra é o nome de fantasia: acento, pontuação, caixa e forma
    societária saem. `BANCO INTER S/A` e `BANCO INTER` viram a mesma coisa;
    `NU INVESTIMENTOS S.A. - CTVM` vira `nu investimentos`."""
    limpo = chave(nome).replace("&", " e ")
    limpo = re.sub(r"[.,/\-]+", " ", limpo)
    limpo = re.sub(r"\s+", " ", limpo).strip()
    for termo in _JURIDICO:
        alvo = re.sub(r"[.,/\-]+", " ", termo)
        alvo = re.sub(r"\s+", " ", alvo).strip()
        limpo = re.sub(rf"(?:^|\s){re.escape(alvo)}(?=\s|$)", " ", limpo)
    return re.sub(r"\s+", " ", limpo).strip()


def formato_numerico(amostras) -> str:
    """Decide a convenção decimal de um arquivo inteiro, por amostragem.

    Existe porque `9.919` é indecidível isoladamente: mil e novecentos e
    dezenove em pt-BR, nove vírgula novecentos e dezenove em en-US. No arquivo
    inteiro a dúvida acaba — **se aparecer vírgula decimal em qualquer valor, o
    arquivo é pt-BR**; senão, o ponto é decimal.

    Caso real que obrigou isto: a planilha da B3 escreve `3.5` e `9.919` em
    formato americano, e a heurística por valor devolvia 9919 — mil vezes o
    valor — num provento da carteira do usuário."""
    for bruto in amostras:
        if bruto is None or isinstance(bruto, (int, float)):
            continue
        if re.search(r"\d,\d", str(bruto)):
            return BR
    return US


def numero(valor, formato: str = AUTO) -> float:
    """Aceita 1.234,56 / 1234.56 / 1.500 / R$ 1.234,56 / '-' / vazio.

    `formato` diz a convenção quando ela é conhecida — use
    `formato_numerico()` para descobri-la a partir do arquivo. Em `AUTO`, o
    ponto só é tratado como milhar quando separa grupos de exatamente três
    dígitos, o que acerta em pt-BR e erra em en-US: por isso quem lê arquivo
    deve decidir o formato uma vez e passar adiante.
    """
    if valor is None or isinstance(valor, (int, float)):
        return float(valor or 0)
    texto = str(valor).strip().replace("R$", "").replace(" ", "").replace("\xa0", "")
    if texto in ("", "-", "--"):
        return 0.0
    if formato == US:
        texto = texto.replace(",", "")     # vírgula só pode ser milhar
    elif "," in texto:                     # pt-BR: ponto é milhar, vírgula é decimal
        texto = texto.replace(".", "").replace(",", ".")
    elif formato != US and _MILHAR.match(texto):
        texto = texto.replace(".", "")     # vale em BR e em AUTO; só US descarta
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
