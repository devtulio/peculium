"""Renda fixa e Tesouro Direto (DESIGN.md §6.2).

**Título de renda fixa é um ativo com preço unitário.** Aplicação é compra,
resgate é venda, e com isso o razão inteiro serve sem uma linha de mudança:
quantidade, preço médio, custo e posição funcionam igual. O que muda é de onde
vem a cotação — em vez de mercado, é a **curva**, calculada a partir da série do
BCB e gravada em `cotacoes` com origem `CURVA`.

Como a curva é do papel, um preço digitado à mão continua vencendo o calculado
(regra do `cotacoes`): é assim que o Tesouro IPCA+, que não tem curva
reconstruível sem o VNA oficial, entra no sistema.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import cotacoes
import fisco
import series
import textos

CLASSES = ("RF", "TESOURO")
CURVA = "CURVA"

INDEXADORES = {
    "CDI": "% do CDI",
    "PRE": "taxa anual prefixada",
    "IPCA": "IPCA + taxa (preço digitado à mão)",
}


@dataclass
class Titulo:
    ativo_id: int
    ticker: str
    nome: str
    classe: str
    emissao: str
    indexador: str
    taxa: float
    pu_base: float
    vencimento: str | None
    emissor: str | None
    isento: bool

    def venceu_ate(self, data: str | None = None) -> bool:
        """Já venceu na data consultada — que nem sempre é hoje: a posição de
        31/12 do ano passado não pode marcar como vencido o papel que venceu
        depois dela."""
        return bool(self.vencimento) and self.vencimento < (
            data or date.today().isoformat())

    @property
    def vencido(self) -> bool:
        return self.venceu_ate()

    def descricao(self) -> str:
        if self.indexador == "CDI":
            return f"{self.taxa:g}% do CDI"
        if self.indexador == "PRE":
            return f"{self.taxa:g}% ao ano, prefixado"
        return f"IPCA + {self.taxa:g}%"


@dataclass
class Resultado:
    atualizados: int = 0
    ignorados: int = 0                       # havia preço manual na data
    falhas: dict[str, str] = field(default_factory=dict)


def _linha(r) -> Titulo:
    return Titulo(r["ativo_id"], r["ticker"], r["nome"] or "", r["classe"],
                  r["emissao"], r["indexador"], r["taxa"], r["pu_base"],
                  r["vencimento"], r["emissor"], bool(r["isento"]))


def cadastrar(conn, *, ativo_id: int, emissao: str, indexador: str, taxa: float,
              pu_base: float = 1.0, vencimento: str | None = None,
              emissor: str = "", isento: bool = False, obs: str = "") -> int:
    indexador = str(indexador or "").strip().upper()
    if indexador not in INDEXADORES:
        raise ValueError(f"indexador deve ser um de: {', '.join(INDEXADORES)}")
    classe = conn.execute("SELECT classe FROM ativos WHERE id=?", (ativo_id,)).fetchone()
    if classe is None:
        raise ValueError(f"ativo {ativo_id} não existe")
    if classe[0] not in CLASSES:
        raise ValueError(f"ativo é da classe {classe[0]}; título de renda fixa "
                         f"precisa ser {' ou '.join(CLASSES)}")
    if float(pu_base) <= 0:
        raise ValueError("preço unitário de emissão precisa ser maior que zero")
    emissao = textos.data_iso(emissao)
    vencimento = textos.data_iso(vencimento) if vencimento else None
    if vencimento and vencimento <= emissao:
        raise ValueError("vencimento precisa ser depois da emissão")
    _conferir_pu_base(conn, ativo_id, emissao, float(pu_base))
    conn.execute(
        "INSERT OR REPLACE INTO rf_titulos (ativo_id, emissao, indexador, taxa,"
        " pu_base, vencimento, emissor, isento, obs) VALUES (?,?,?,?,?,?,?,?,?)",
        (ativo_id, emissao, indexador, float(taxa), float(pu_base), vencimento,
         emissor or None, int(bool(isento)), obs or None))
    return ativo_id


def _conferir_pu_base(conn, ativo_id: int, emissao: str, pu_base: float) -> None:
    """O PU de emissão errado erra a posição em ordem de grandeza, em silêncio.

    Caso real que motivou a checagem: uma nota da Inter com 450 unidades a
    R$ 0,01 (R$ 4,50 aplicados). Cadastrada com o `pu_base` padrão de R$ 1,00, a
    posição virava R$ 457 — cem vezes o valor. O custo continuava certo, então
    nada denunciava o erro além do rendimento absurdo."""
    linha = conn.execute(
        "SELECT data, preco FROM lancamentos WHERE ativo_id=? AND tipo='COMPRA'"
        "  AND estorna_id IS NULL AND preco > 0"
        "  AND id NOT IN (SELECT estorna_id FROM lancamentos"
        "                 WHERE estorna_id IS NOT NULL)"
        " ORDER BY data, id LIMIT 1", (ativo_id,)).fetchone()
    if linha is None or linha["data"] != emissao:
        return                      # compra depois da emissão: o PU já rendeu
    if abs(pu_base - linha["preco"]) > 0.005 * max(1.0, linha["preco"]):
        raise ValueError(
            f"o preço unitário de emissão ({pu_base:g}) não bate com o preço da "
            f"aplicação na mesma data ({linha['preco']:g}). Informe o PU da nota, "
            f"senão a posição sai errada em ordem de grandeza")


def titulo(conn, ativo_id: int) -> Titulo | None:
    linha = conn.execute(
        "SELECT t.*, a.ticker, a.nome, a.classe FROM rf_titulos t"
        " JOIN ativos a ON a.id = t.ativo_id WHERE t.ativo_id=?", (ativo_id,)).fetchone()
    return _linha(linha) if linha else None


def listar(conn) -> list[Titulo]:
    return [_linha(r) for r in conn.execute(
        "SELECT t.*, a.ticker, a.nome, a.classe FROM rf_titulos t"
        " JOIN ativos a ON a.id = t.ativo_id ORDER BY t.vencimento, a.ticker")]


def pu(conn, ativo_id: int, data: str | None = None) -> float:
    """Preço unitário na curva. Levanta `SerieIndisponivel` quando não dá para
    calcular — nunca devolve um número aproximado no lugar."""
    t = titulo(conn, ativo_id)
    if t is None:
        raise ValueError(f"ativo {ativo_id} não é um título de renda fixa")
    if t.taxa <= 0:
        # a posição da B3 traz emissor, indexador e datas, mas NÃO a taxa. Sem
        # ela a curva sairia plana e, pior, sobrescreveria o preço oficial que a
        # própria B3 informou. Melhor não ter curva do que ter uma errada.
        raise series.SerieIndisponivel(
            f"{t.ticker}: a taxa do título não foi informada — complete o "
            f"cadastro ou importe a nota de renda fixa")
    data = data or date.today().isoformat()
    # depois do vencimento o papel para de render: o valor congela no vencimento
    limite = min(data, t.vencimento) if t.vencimento else data
    return t.pu_base * series.fator(conn, t.indexador, t.emissao, limite, t.taxa)


def atualizar_curvas(conn, data: str | None = None) -> Resultado:
    """Grava o PU de cada título em `cotacoes`. A partir daí carteira, painel e
    relatórios enxergam renda fixa sem saber que ela é diferente."""
    data = data or date.today().isoformat()
    resultado = Resultado()
    for t in listar(conn):
        try:
            valor = pu(conn, t.ativo_id, data)
        except series.SerieIndisponivel as e:
            resultado.falhas[t.ticker] = str(e)
            continue
        if cotacoes.registrar(conn, t.ativo_id, data, valor, CURVA):
            resultado.atualizados += 1
        else:
            resultado.ignorados += 1
    return resultado


def ir_estimado(conn, ativo_id: int, resgate: str, ganho: float) -> dict:
    """Estimativa **informativa** do IR retido num resgate.

    O imposto de renda fixa é retido na fonte e o valor verdadeiro vem no extrato
    da corretora — é ele que deve ser lançado no campo IRRF. Isto aqui serve para
    conferir a ordem de grandeza e para planejar o prazo, nunca para virar guia
    de recolhimento.

    O prazo conta da **emissão do título**; se houve aportes em datas diferentes,
    a corretora aplica a alíquota de cada aplicação, e o número exato só sai do
    extrato dela."""
    t = titulo(conn, ativo_id)
    if t is None:
        raise ValueError(f"ativo {ativo_id} não é um título de renda fixa")
    dias = (date.fromisoformat(textos.data_iso(resgate))
            - date.fromisoformat(t.emissao)).days
    if t.isento:
        return {"dias": dias, "aliquota": 0.0, "imposto": 0.0, "isento": True,
                "observacao": "papel isento de IR para pessoa física"}
    aliquota = fisco.aliquota_regressiva(dias)
    return {"dias": dias, "aliquota": aliquota,
            "imposto": round(max(0.0, ganho) * aliquota, 2), "isento": False,
            "observacao": "estimativa pelo prazo desde a emissão; o valor retido "
                          "de verdade vem no extrato da corretora"}


def sugestao(conn, ativo_id: int) -> dict:
    """O que o cadastro do título pode preencher sozinho, a partir do que já foi
    lançado.

    A primeira aplicação diz a **emissão** e o **PU de emissão** — que é o campo
    que mais dói errar, porque o PU errado erra a posição em ordem de grandeza.
    Sobra o usuário informar indexador e taxa, que nenhum arquivo da B3 traz.

    Devolve também o **emissor**, quando o nome que a Movimentação da B3 gravou
    no ativo o carrega ("CDB - CDB726AM6KA - BANCO INTER S/A")."""
    linha = conn.execute(
        "SELECT data, preco FROM lancamentos WHERE ativo_id=? AND tipo='COMPRA'"
        "  AND preco > 0 AND estorna_id IS NULL"
        "  AND id NOT IN (SELECT estorna_id FROM lancamentos"
        "                 WHERE estorna_id IS NOT NULL)"
        " ORDER BY data, id LIMIT 1", (ativo_id,)).fetchone()
    ativo = conn.execute("SELECT ticker, nome, classe FROM ativos WHERE id=?",
                         (ativo_id,)).fetchone()
    nome = (ativo["nome"] or "") if ativo else ""
    return {
        "ativo_id": ativo_id,
        "emissao": linha["data"] if linha else None,
        "pu_base": linha["preco"] if linha else None,
        # "CDB - CDB726AM6KA - BANCO INTER S/A" -> "BANCO INTER S/A"
        "emissor": nome.split(" - ")[-1].strip() if " - " in nome else "",
        # o IPCA+ não tem curva reconstruível: dizer isso na hora do cadastro
        # evita o usuário procurar uma taxa que não vai resolver o aviso
        "sem_curva": bool(ativo and ativo["classe"] == "TESOURO"
                          and "IPCA" in (ativo["ticker"] or "").upper()),
    }


def posicao(conn, data: str | None = None) -> list[dict]:
    """Renda fixa em carteira com o valor na curva, para a tela e o relatório.

    **Percorre a carteira, não a tabela de títulos.** Percorrer os títulos
    escondia o papel que está na carteira sem cadastro — e isso é o caso normal,
    não a exceção: a Movimentação da B3 cria o ativo de renda fixa sem dizer
    indexador nem taxa. O usuário via cinco CDBs na tabela principal e o bloco de
    renda fixa simplesmente não existir."""
    import razao

    data = data or date.today().isoformat()
    saida = []
    for p in razao.apurar(conn, data).carteira():
        if p.classe not in CLASSES:
            continue
        t = titulo(conn, p.ativo_id)
        if t is None:
            erro = ("título não cadastrado: informe indexador, taxa e PU de "
                    "emissão para ter a curva. O valor abaixo é o último preço "
                    "conhecido")
            unitario = cotacoes.preco(conn, p.ativo_id, data)
        else:
            try:
                unitario, erro = pu(conn, p.ativo_id, data), None
            except series.SerieIndisponivel as e:
                unitario = cotacoes.preco(conn, p.ativo_id, data)
                erro = str(e)
        bruto = (unitario or p.preco_medio) * p.quantidade
        saida.append({
            "ativo_id": p.ativo_id, "ticker": p.ticker, "classe": p.classe,
            "emissor": t.emissor if t else None,
            "indexador": t.descricao() if t else "—",
            "emissao": t.emissao if t else None,
            "vencimento": t.vencimento if t else None,
            "vencido": t.venceu_ate(data) if t else False,
            "quantidade": p.quantidade, "custo": p.custo_total,
            "pu": unitario, "bruto": bruto, "rendimento": bruto - p.custo_total,
            "isento": t.isento if t else False, "erro": erro,
        })
    return saida
