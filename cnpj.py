"""Consulta de CNPJ na Receita (DESIGN.md §7.1). Rede opcional e contida.

Mesma disciplina do `cotacoes.py`, pelos mesmos motivos:

* **Só acontece quando o usuário clica.** Nada consulta sozinho.
* **Whitelist de host no código**, jamais em configuração do banco.
* **Sai só o CNPJ que o usuário acabou de digitar.** Nunca a carteira, o valor
  ou qualquer outro cadastro.
* **Falha nunca bloqueia**: sem rede, o usuário digita o nome à mão.

Duas fontes, como na família SGx: a ReceitaWS primeiro e a BrasilAPI como
reserva. A ReceitaWS limita a três consultas por minuto no plano gratuito, e é
por isso que a reserva existe — não por redundância decorativa.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

RECEITAWS = "receitaws.com.br"
BRASILAPI = "brasilapi.com.br"
HOSTS = (RECEITAWS, BRASILAPI)
TIMEOUT = 8


class CnpjInvalido(ValueError):
    pass


class ConsultaFalhou(RuntimeError):
    pass


def digitos(valor: str) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def formatar(valor: str) -> str:
    d = digitos(valor)
    if len(d) != 14:
        return str(valor or "")
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def valido(valor: str) -> bool:
    """Confere os dois dígitos verificadores.

    Vale a pena antes de sair para a rede: um dígito trocado devolveria "não
    encontrado" depois de uma ida à internet e de consumir uma das três
    consultas por minuto que a ReceitaWS concede."""
    d = digitos(valor)
    if len(d) != 14 or d == d[0] * 14:
        return False
    for tamanho in (12, 13):
        pesos = [(tamanho - 1 - i) % 8 + 2 for i in range(tamanho)]
        soma = sum(int(d[i]) * pesos[i] for i in range(tamanho))
        resto = soma % 11
        if int(d[tamanho]) != (0 if resto < 2 else 11 - resto):
            return False
    return True


def _receitaws(d: str) -> dict:
    dados = _pegar(f"https://{RECEITAWS}/v1/cnpj/{d}")
    if str(dados.get("status", "")).upper() != "OK":
        raise ConsultaFalhou(dados.get("message") or "CNPJ não encontrado")
    return {"cnpj": formatar(d), "nome": dados.get("nome") or "",
            "fantasia": dados.get("fantasia") or "",
            "situacao": dados.get("situacao") or "", "fonte": "ReceitaWS"}


def _brasilapi(d: str) -> dict:
    dados = _pegar(f"https://{BRASILAPI}/api/cnpj/v1/{d}")
    if dados.get("message"):
        raise ConsultaFalhou(dados["message"])
    return {"cnpj": formatar(d), "nome": dados.get("razao_social") or "",
            "fantasia": dados.get("nome_fantasia") or "",
            "situacao": dados.get("descricao_situacao_cadastral") or "",
            "fonte": "BrasilAPI"}


def _pegar(url: str) -> dict:
    requisicao = urllib.request.Request(url, headers={"User-Agent": "Peculium"})
    with urllib.request.urlopen(requisicao, timeout=TIMEOUT) as resposta:
        return json.load(resposta)


def consultar(valor: str, fontes=(_receitaws, _brasilapi)) -> dict:
    """Razão social a partir do CNPJ. Levanta com a explicação, nunca devolve
    dado pela metade."""
    d = digitos(valor)
    if not valido(d):
        raise CnpjInvalido(
            "CNPJ inválido: confira os 14 dígitos" if len(d) == 14
            else f"o CNPJ precisa de 14 dígitos (você informou {len(d)})")
    motivos = []
    for fonte in fontes:
        try:
            achado = fonte(d)
        except (urllib.error.URLError, OSError, ValueError, KeyError,
                ConsultaFalhou) as e:
            motivos.append(f"{fonte.__name__.strip('_')}: {e}")
            continue
        if achado["nome"]:
            return achado
        motivos.append(f"{fonte.__name__.strip('_')}: resposta sem razão social")
    raise ConsultaFalhou("nenhuma fonte respondeu — " + "; ".join(motivos))
