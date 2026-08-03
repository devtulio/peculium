"""Cotação de fechamento (DESIGN.md §7). Rede é opcional e contida.

Regras que não são negociáveis:

* **Desligada por padrão.** O programa abre e funciona inteiro sem rede.
* **Whitelist de host no código**, jamais em configuração do banco — dado de
  banco vira alvo; constante de módulo, não.
* **Sai só o ticker.** Nunca quantidade, valor, instituição ou documento.
* **Preço digitado à mão sempre vence** o baixado, e a origem fica gravada.
* **Falha nunca bloqueia.** Sem rede, sem cotação; a carteira continua abrindo.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

HOSTS = ("query1.finance.yahoo.com",)
TIMEOUT = 6
# O ticker entra numa URL: validar o formato é o que impede um "ativo" com
# barra ou dois-pontos no nome de virar outra requisição.
TICKER = re.compile(r"^[A-Z]{4}\d{1,2}$")

MANUAL = "MANUAL"
ONLINE = "ONLINE"


@dataclass
class Resultado:
    atualizadas: int = 0
    ignoradas: int = 0                       # já havia preço manual na data
    falhas: dict[str, str] = field(default_factory=dict)
    desligada: bool = False


def habilitada(conn) -> bool:
    linha = conn.execute("SELECT valor FROM config WHERE chave='cotacao_online'").fetchone()
    return bool(linha) and str(linha[0]) == "1"


def registrar(conn, ativo_id: int, data: str, fechamento: float,
              origem: str = MANUAL) -> bool:
    """Grava a cotação. Devolve False quando respeitou um preço manual existente."""
    atual = conn.execute("SELECT origem FROM cotacoes WHERE ativo_id=? AND data=?",
                         (ativo_id, data)).fetchone()
    if atual and atual[0] == MANUAL and origem != MANUAL:
        return False
    conn.execute("INSERT OR REPLACE INTO cotacoes (ativo_id, data, fechamento, origem)"
                 " VALUES (?,?,?,?)", (ativo_id, data, fechamento, origem))
    return True


def preco(conn, ativo_id: int, ate: str | None = None) -> float | None:
    """Última cotação conhecida até a data — nunca extrapola para frente."""
    if ate:
        linha = conn.execute(
            "SELECT fechamento FROM cotacoes WHERE ativo_id=? AND data<=?"
            " ORDER BY data DESC LIMIT 1", (ativo_id, ate)).fetchone()
    else:
        linha = conn.execute(
            "SELECT fechamento FROM cotacoes WHERE ativo_id=? ORDER BY data DESC LIMIT 1",
            (ativo_id,)).fetchone()
    return linha[0] if linha else None


def _yahoo(ticker: str) -> float:
    url = (f"https://{HOSTS[0]}/v8/finance/chart/{ticker}.SA"
           "?interval=1d&range=1d")
    requisicao = urllib.request.Request(url, headers={"User-Agent": "Peculium"})
    with urllib.request.urlopen(requisicao, timeout=TIMEOUT) as resposta:
        dados = json.load(resposta)
    return float(dados["chart"]["result"][0]["meta"]["regularMarketPrice"])


def cotar(conn, data: str, tickers: list[str] | None = None,
          buscador=_yahoo) -> Resultado:
    """Busca o fechamento dos ativos em carteira e grava com origem ONLINE.

    Nenhuma exceção escapa: a falha de um ticker vira linha no relatório de
    importação, não erro na tela."""
    if not habilitada(conn):
        return Resultado(desligada=True)

    if tickers is None:
        linhas = conn.execute(
            "SELECT DISTINCT a.ticker FROM ativos a"
            " JOIN lancamentos l ON l.ativo_id = a.id WHERE a.ativo = 1")
        tickers = [r[0] for r in linhas]

    ids = {str(r[0]).upper(): r[1] for r in conn.execute("SELECT ticker, id FROM ativos")}
    resultado = Resultado()
    for ticker in tickers:
        alvo = str(ticker).upper()
        if not TICKER.match(alvo):
            resultado.falhas[alvo] = "formato de ticker não reconhecido"
            continue
        try:
            valor = buscador(alvo)
        except (urllib.error.URLError, OSError, KeyError, IndexError,
                ValueError, TypeError) as e:
            resultado.falhas[alvo] = f"{type(e).__name__}: {e}"
            continue
        if registrar(conn, ids[alvo], data, valor, ONLINE):
            resultado.atualizadas += 1
        else:
            resultado.ignoradas += 1
    return resultado
