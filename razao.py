"""Motor de posição do Peculium (DESIGN.md §5).

O razão é append-only: este módulo nunca escreve. Lê `lancamentos` e `eventos` em
ordem cronológica e devolve posição, preço médio e resultado das vendas.

Duas regras que valem mais que o resto do arquivo:

* **Preço médio é global por ativo, nunca por corretora** — é a regra da RFB, e é
  o que faz a portabilidade entre instituições não inventar lucro tributável.
* **Day trade é detectado, não declarado** — compra e venda do mesmo ativo, mesma
  instituição, no mesmo dia.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from textos import data_br

EPS = 1e-9

SWING = "SWING"
DAY_TRADE = "DAY_TRADE"

PROVENTOS = ("DIVIDENDO", "JCP", "RENDIMENTO")
EVENTOS_FATOR = ("DESDOBRAMENTO", "GRUPAMENTO")
EVENTOS_TROCA = ("CONVERSAO", "INCORPORACAO")


class ErroDeRazao(Exception):
    pass


@dataclass
class Posicao:
    ativo_id: int
    ticker: str
    classe: str
    quantidade: float = 0.0
    custo_total: float = 0.0

    @property
    def preco_medio(self) -> float:
        return self.custo_total / self.quantidade if self.quantidade > EPS else 0.0


@dataclass
class Venda:
    data: str
    ativo_id: int
    ticker: str
    classe: str
    instituicao_id: int
    quantidade: float
    valor_bruto: float       # o que a Receita chama de valor da alienação
    custos: float            # corretagem, emolumentos e taxas da venda
    irrf: float              # retido na fonte ("dedo-duro")
    custo_base: float        # preço médio na data × quantidade (ou custo do dia, no day trade)
    natureza: str            # SWING | DAY_TRADE

    @property
    def valor_liquido(self) -> float:
        return self.valor_bruto - self.custos

    @property
    def resultado(self) -> float:
        return self.valor_liquido - self.custo_base


@dataclass
class Provento:
    data: str
    ativo_id: int
    ticker: str
    tipo: str
    valor: float
    irrf: float


@dataclass
class Apuracao:
    posicoes: dict[int, Posicao] = field(default_factory=dict)
    por_instituicao: dict[tuple[int, int], float] = field(default_factory=dict)
    vendas: list[Venda] = field(default_factory=list)
    proventos: list[Provento] = field(default_factory=list)
    custos: float = 0.0
    avisos: list[str] = field(default_factory=list)

    def carteira(self) -> list[Posicao]:
        """Só o que ainda está em carteira, em ordem de ticker."""
        return sorted((p for p in self.posicoes.values() if p.quantidade > EPS),
                      key=lambda p: p.ticker)


def _ativos(conn: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    return {r["id"]: r for r in conn.execute("SELECT * FROM ativos")}


def _lancamentos_validos(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Correção é estorno, nunca UPDATE: some o estorno e o lançamento estornado.

    O par fica visível no extrato — quem some é o efeito, não o registro."""
    estornados = {r[0] for r in
                  conn.execute("SELECT estorna_id FROM lancamentos "
                               "WHERE estorna_id IS NOT NULL")}
    return [r for r in conn.execute(
        "SELECT * FROM lancamentos WHERE estorna_id IS NULL ORDER BY data, id")
        if r["id"] not in estornados]


def _pos(ap: Apuracao, ativos: dict, ativo_id: int) -> Posicao:
    if ativo_id not in ap.posicoes:
        a = ativos[ativo_id]
        ap.posicoes[ativo_id] = Posicao(ativo_id, a["ticker"], a["classe"])
    return ap.posicoes[ativo_id]


def _mover(ap: Apuracao, ativo_id: int, instituicao_id: int | None, qtd: float,
           ticker: str = "", data: str = "") -> None:
    if instituicao_id is None:
        return
    chave = (ativo_id, instituicao_id)
    saldo = ap.por_instituicao.get(chave, 0.0) + qtd
    # saldo negativo numa corretora é quase sempre transferência não importada:
    # a posição global fecha e o furo passaria batido sem este aviso
    if saldo < -EPS:
        ap.avisos.append(
            f"{data_br(data)}: {ticker or ativo_id} fica com saldo negativo "
            f"({saldo:g}) na instituição {instituicao_id} — falta a transferência")
    ap.por_instituicao[chave] = saldo
    if abs(saldo) < EPS:
        del ap.por_instituicao[chave]


def _aplicar_evento(ap: Apuracao, ativos: dict, ev: sqlite3.Row) -> None:
    pos = ap.posicoes.get(ev["ativo_id"])
    if pos is None or pos.quantidade <= EPS:
        return
    saldos = {k: v for k, v in ap.por_instituicao.items() if k[0] == ev["ativo_id"]}
    if ev["tipo"] in EVENTOS_FATOR:
        # desdobramento e grupamento mexem na quantidade e NÃO no custo total:
        # o preço médio se ajusta sozinho, que é exatamente o efeito correto
        pos.quantidade *= ev["fator"]
        for (_, inst), q in saldos.items():
            ap.por_instituicao[(ev["ativo_id"], inst)] = q * ev["fator"]
    elif ev["tipo"] in EVENTOS_TROCA:
        if ev["ativo_destino_id"] is None:
            raise ErroDeRazao(f"{ev['tipo']} de {pos.ticker} sem ativo de destino")
        destino = _pos(ap, ativos, ev["ativo_destino_id"])
        destino.quantidade += pos.quantidade * ev["fator"]
        destino.custo_total += pos.custo_total          # o custo migra inteiro
        for (_, inst), q in saldos.items():
            _mover(ap, ev["ativo_destino_id"], inst, q * ev["fator"])
            _mover(ap, ev["ativo_id"], inst, -q)
        pos.quantidade = 0.0
        pos.custo_total = 0.0
    else:
        raise ErroDeRazao(f"evento de tipo desconhecido: {ev['tipo']}")


def _negociacoes_do_dia(ap: Apuracao, ativos: dict, data: str,
                        linhas: list[sqlite3.Row]) -> None:
    """Compras e vendas do dia, agrupadas por (ativo, instituição).

    O agrupamento é o que permite detectar day trade — e é também a unidade certa
    de apuração, porque a Receita apura o day trade pelo líquido do dia."""
    grupos: dict[tuple[int, int], dict[str, list]] = {}
    for l in linhas:
        chave = (l["ativo_id"], l["instituicao_id"])
        grupos.setdefault(chave, {"COMPRA": [], "VENDA": []})[l["tipo"]].append(l)

    for (ativo_id, inst_id), g in grupos.items():
        pos = _pos(ap, ativos, ativo_id)
        qc = sum(l["quantidade"] for l in g["COMPRA"])
        qv = sum(l["quantidade"] for l in g["VENDA"])
        # compra entra pelo bruto MAIS custos; a venda guarda bruto e custos
        # separados, porque o limite de isenção da Receita é sobre o BRUTO
        pm_compra = (sum(l["valor"] + l["custos"] for l in g["COMPRA"]) / qc) if qc else 0.0
        bruto_un = (sum(l["valor"] for l in g["VENDA"]) / qv) if qv else 0.0
        custo_un = (sum(l["custos"] for l in g["VENDA"]) / qv) if qv else 0.0
        irrf_un = (sum(l["irrf"] for l in g["VENDA"]) / qv) if qv else 0.0
        ap.custos += sum(l["custos"] for l in g["COMPRA"] + g["VENDA"])

        q_dt = min(qc, qv)
        if q_dt > EPS:
            ap.vendas.append(Venda(data, ativo_id, pos.ticker, pos.classe, inst_id,
                                   q_dt, q_dt * bruto_un, q_dt * custo_un,
                                   q_dt * irrf_un, q_dt * pm_compra, DAY_TRADE))

        qc_liq, qv_liq = qc - q_dt, qv - q_dt   # um dos dois é sempre zero
        if qc_liq > EPS:
            pos.quantidade += qc_liq
            pos.custo_total += qc_liq * pm_compra
            _mover(ap, ativo_id, inst_id, qc_liq, pos.ticker, data)
        if qv_liq > EPS:
            if qv_liq > pos.quantidade + EPS:
                # quase sempre importação incompleta, não venda a descoberto
                raise ErroDeRazao(
                    f"{data_br(data)}: venda de {qv_liq:g} de {pos.ticker} com posição de "
                    f"{pos.quantidade:g} — falta lançamento anterior")
            custo_base = qv_liq * pos.preco_medio
            ap.vendas.append(Venda(data, ativo_id, pos.ticker, pos.classe, inst_id,
                                   qv_liq, qv_liq * bruto_un, qv_liq * custo_un,
                                   qv_liq * irrf_un, custo_base, SWING))
            pos.quantidade -= qv_liq
            pos.custo_total -= custo_base
            _mover(ap, ativo_id, inst_id, -qv_liq, pos.ticker, data)


def _outros_do_dia(ap: Apuracao, ativos: dict, linhas: list[sqlite3.Row]) -> None:
    for l in linhas:
        tipo = l["tipo"]
        if tipo in ("BONIFICACAO", "SUBSCRICAO"):
            # bonificação entra pelo valor declarado pela companhia, não a custo
            # zero: custo zero infla o ganho na venda futura
            pos = _pos(ap, ativos, l["ativo_id"])
            pos.quantidade += l["quantidade"]
            pos.custo_total += l["valor"] + l["custos"]
            _mover(ap, l["ativo_id"], l["instituicao_id"], l["quantidade"],
                   pos.ticker, l["data"])
        elif tipo == "TRANSFERENCIA":
            # portabilidade NÃO é venda: só troca de instituição, custo intacto
            if l["instituicao_destino_id"] is None:
                raise ErroDeRazao(
                    f"{data_br(l['data'])}: transferência sem instituição de destino")
            tk = ativos[l["ativo_id"]]["ticker"]
            _mover(ap, l["ativo_id"], l["instituicao_id"], -l["quantidade"], tk, l["data"])
            _mover(ap, l["ativo_id"], l["instituicao_destino_id"], l["quantidade"],
                   tk, l["data"])
        elif tipo == "AMORTIZACAO":
            pos = _pos(ap, ativos, l["ativo_id"])
            if l["valor"] > pos.custo_total + EPS:
                # ponytail: excedente de amortização é ganho de capital; por ora
                # avisa e zera o custo. Virar Venda quando aparecer caso real.
                ap.avisos.append(
                    f"{data_br(l['data'])}: amortização de {pos.ticker} maior que o custo "
                    f"({l['valor']:.2f} > {pos.custo_total:.2f}) — excedente é ganho")
                pos.custo_total = 0.0
            else:
                pos.custo_total -= l["valor"]
        elif tipo in PROVENTOS:
            a = ativos[l["ativo_id"]]
            ap.proventos.append(Provento(l["data"], l["ativo_id"], a["ticker"],
                                         tipo, l["valor"], l["irrf"]))
        elif tipo in ("TAXA", "IRRF"):
            ap.custos += l["valor"]
        else:
            raise ErroDeRazao(f"tipo de lançamento desconhecido: {tipo}")


def apurar(conn: sqlite3.Connection, ate: str | None = None) -> Apuracao:
    """Recomputação integral do razão, opcionalmente parando numa data.

    `ate` existe porque a declaração de bens pede a posição **em 31/12**, não a
    de hoje — apurar tudo e mostrar o saldo atual declararia o ano errado.

    # ponytail: sem cache. Carteira pessoal tem ordem de 10^4 lançamentos e isso
    # roda em milissegundos. Cache incremental só acima de ~10^5 — e o
    # invalidador dele seria o lançamento retroativo, que é o caso difícil.
    """
    ativos = _ativos(conn)
    lancs = _lancamentos_validos(conn)
    eventos = list(conn.execute("SELECT * FROM eventos ORDER BY data_ex, id"))
    ap = Apuracao()

    por_dia: dict[str, list[sqlite3.Row]] = {}
    for l in lancs:
        por_dia.setdefault(l["data"], []).append(l)
    ev_dia: dict[str, list[sqlite3.Row]] = {}
    for e in eventos:
        ev_dia.setdefault(e["data_ex"], []).append(e)

    for data in sorted(set(por_dia) | set(ev_dia)):
        if ate and data > ate:
            break
        # o evento vale para quem já tinha o ativo: aplica antes do dia
        for ev in ev_dia.get(data, []):
            _aplicar_evento(ap, ativos, ev)
        linhas = por_dia.get(data, [])
        _outros_do_dia(ap, ativos,
                       [l for l in linhas if l["tipo"] not in ("COMPRA", "VENDA")])
        _negociacoes_do_dia(ap, ativos, data,
                            [l for l in linhas if l["tipo"] in ("COMPRA", "VENDA")])
    return ap


def carteira(conn: sqlite3.Connection, ate: str | None = None) -> list[Posicao]:
    return apurar(conn, ate).carteira()
