"""Séries do Banco Central (SGS) — a base do valor na curva da renda fixa.

Mesma disciplina de rede do `cotacoes`: **desligada por padrão**, host numa
constante do módulo e falha que nunca derruba a tela.

Códigos conferidos contra a API, não tirados de memória:

| Série | O que devolve | Amostra |
|---|---|---|
| 12  | CDI **diário**, em % ao dia   | `0.052531` |
| 11  | Selic diária, em % ao dia     | `0.052531` |
| 433 | IPCA mensal, em % ao mês      | `0.58`     |

A série 12 é exatamente o fator diário derivado do CDI anualizado
(`(1+14,15%)^(1/252)-1 = 0,052532%`), então é ela que se usa: vem pronta.

**A série só tem dia útil.** Contar os registros entre duas datas é contar os
dias úteis — não existe tabela de feriados neste programa, e não precisa.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date

import textos

HOST = "api.bcb.gov.br"
TIMEOUT = 20

# nome interno -> código da série no SGS
SERIES = {"CDI": 12, "SELIC": 11, "IPCA": 433, "SELIC_MENSAL": 4390}
DIARIAS = ("CDI", "SELIC")          # em % ao dia; IPCA e SELIC_MENSAL são mensais
# A 4390 é a **Selic acumulada no mês**, em % ao mês, com um registro por mês
# datado no dia 1º — conferido contra a API, não suposto. É a série que a Receita
# usa para os juros de mora do art. 61 §3 da Lei 9.430/96; a 11 (Selic diária)
# não serve, porque a lei manda somar taxas mensais, não capitalizar dias.


class SerieIndisponivel(Exception):
    pass


@dataclass
class Resultado:
    gravados: int = 0
    falhas: dict[str, str] = field(default_factory=dict)
    desligada: bool = False
    cobertura: dict[str, tuple[str, str]] = field(default_factory=dict)


def _bcb(codigo: int, inicio: str | None, fim: str | None) -> list[dict]:
    url = f"https://{HOST}/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"
    if inicio:
        url += f"&dataInicial={textos.data_br(inicio)}"
    if fim:
        url += f"&dataFinal={textos.data_br(fim)}"
    requisicao = urllib.request.Request(url, headers={"User-Agent": "Peculium"})
    with urllib.request.urlopen(requisicao, timeout=TIMEOUT) as resposta:
        return json.load(resposta)


def habilitada(conn) -> bool:
    linha = conn.execute("SELECT valor FROM config WHERE chave='cotacao_online'").fetchone()
    return bool(linha) and str(linha[0]) == "1"


def cobertura(conn, indice: str) -> tuple[str, str] | None:
    linha = conn.execute("SELECT min(data), max(data) FROM series WHERE indice=?",
                         (indice,)).fetchone()
    return (linha[0], linha[1]) if linha and linha[0] else None


def baixar(conn, indices: list[str] | None = None, inicio: str | None = None,
           fim: str | None = None, buscador=_bcb) -> Resultado:
    """Baixa e grava. Só busca o que falta: a série já guardada não se rebaixa."""
    if not habilitada(conn):
        return Resultado(desligada=True)
    resultado = Resultado()
    for indice in (indices or list(SERIES)):
        if indice not in SERIES:
            resultado.falhas[indice] = "série desconhecida"
            continue
        ja = cobertura(conn, indice)
        desde = inicio
        if ja and (not inicio or ja[0] <= inicio):
            desde = ja[1]              # continua de onde parou
        try:
            linhas = buscador(SERIES[indice], desde, fim)
        except (urllib.error.URLError, OSError, ValueError, TypeError) as e:
            resultado.falhas[indice] = f"{type(e).__name__}: {e}"
            continue
        for linha in linhas:
            conn.execute(
                "INSERT OR REPLACE INTO series (indice, data, valor) VALUES (?,?,?)",
                (indice, textos.data_iso(linha["data"]), float(linha["valor"])))
            resultado.gravados += 1
        resultado.cobertura[indice] = cobertura(conn, indice)
    return resultado


def dias_uteis(conn, inicio: str, fim: str, indice: str = "CDI") -> int:
    """Dias úteis em (inicio, fim] — a própria série é o calendário."""
    return conn.execute(
        "SELECT count(*) FROM series WHERE indice=? AND data>? AND data<=?",
        (indice, inicio, fim)).fetchone()[0]


def _exige_cobertura(conn, indice: str, inicio: str, fim: str) -> None:
    faixa = cobertura(conn, indice)
    if faixa is None:
        raise SerieIndisponivel(
            f"série {indice} não foi baixada — ligue a rede em Configurações")
    if fim > faixa[1]:
        raise SerieIndisponivel(
            f"série {indice} vai até {textos.data_br(faixa[1])} e o cálculo pede "
            f"{textos.data_br(fim)} — atualize as séries")
    if inicio < faixa[0]:
        raise SerieIndisponivel(
            f"série {indice} começa em {textos.data_br(faixa[0])}, depois de "
            f"{textos.data_br(inicio)}")


def fator_cdi(conn, inicio: str, fim: str, percentual: float = 100.0) -> float:
    """Fator acumulado de um papel indexado a % do CDI, em (inicio, fim].

    Convenção do mercado: o rendimento corre do dia seguinte à aplicação até o
    dia do resgate, e o percentual incide sobre a **taxa diária**, não sobre o
    fator. Recusa calcular fora da cobertura da série em vez de devolver um
    número menor do que a verdade."""
    if fim <= inicio:
        return 1.0
    _exige_cobertura(conn, "CDI", inicio, fim)
    fator = 1.0
    for (taxa,) in conn.execute(
            "SELECT valor FROM series WHERE indice='CDI' AND data>? AND data<=?"
            " ORDER BY data", (inicio, fim)):
        fator *= 1 + (taxa / 100) * (percentual / 100)
    return fator


def fator_prefixado(conn, inicio: str, fim: str, taxa_anual: float) -> float:
    """Prefixado em base 252: `(1 + taxa)^(du/252)`."""
    if fim <= inicio:
        return 1.0
    _exige_cobertura(conn, "CDI", inicio, fim)      # a série é o calendário
    return (1 + taxa_anual / 100) ** (dias_uteis(conn, inicio, fim) / 252)


def fator(conn, indexador: str, inicio: str, fim: str, taxa: float) -> float:
    """`taxa` é o percentual do CDI quando indexado, ou a taxa anual no prefixado."""
    indexador = (indexador or "").strip().upper()
    if indexador in ("CDI", "DI", "POS", "PÓS"):
        return fator_cdi(conn, inicio, fim, taxa)
    if indexador in ("PRE", "PRÉ", "PREFIXADO"):
        return fator_prefixado(conn, inicio, fim, taxa)
    # IPCA+ depende do VNA oficial, que não se reconstrói com a série mensal
    # sozinha; enquanto não houver essa fonte, o preço é digitado à mão.
    raise SerieIndisponivel(
        f"indexador {indexador or '(vazio)'} não tem curva calculável: informe o "
        f"preço unitário à mão na tela de Carteira")


def hoje_iso() -> str:
    return date.today().isoformat()
