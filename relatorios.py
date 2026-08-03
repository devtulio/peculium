"""Relatórios gerenciais (DESIGN.md §11).

Cada relatório devolve o mesmo `Relatorio`, e os dois renderizadores — HTML
timbrado para impressão e CSV para planilha — servem todos. Impressão sai sempre
em tema claro: papel é papel (mesma regra do Licitarium).

O módulo não calcula regra de negócio: posição vem do `razao`, imposto vem do
`fisco`, cotação vem de `cotacoes`. Aqui só se agrupa e se formata — e é de
propósito, para não existir uma segunda verdade sobre o mesmo número.
"""
from __future__ import annotations

import csv
import io
import html as _html
from dataclasses import dataclass, field
from datetime import date

import cotacoes
import fisco
import obrigacoes as _obrigacoes
import razao
import textos
from textos import competencia_br, data_br

PALETAS = {
    "atrium": {"bg": "#f6f4ef", "papel": "#ffffff", "texto": "#2a2622",
               "suave": "#6b6459", "borda": "#ddd7cb", "marca": "#63234c",
               "alta": "#1a7f4b", "baixa": "#a32020"},
    "cera": {"bg": "#efe6d2", "papel": "#f7f1e2", "texto": "#33291b",
             "suave": "#6a5c43", "borda": "#d8c9a8", "marca": "#63234c",
             "alta": "#1a6b42", "baixa": "#8f2020"},
}


@dataclass
class Relatorio:
    titulo: str
    colunas: list[str]
    linhas: list[list] = field(default_factory=list)
    rodape: list[str] = field(default_factory=list)
    numericas: set[int] = field(default_factory=set)   # colunas alinhadas à direita
    avisos: list[str] = field(default_factory=list)


# --------------------------------------------------------------------- formato

def brl(valor: float) -> str:
    return f"{valor:,.2f}".translate(str.maketrans(",.", ".,"))


def pct(valor: float) -> str:
    return f"{valor:,.2f}%".translate(str.maketrans(",.", ".,"))


def sinal(valor: float) -> str:
    """Alta e baixa nunca só por cor: sinal e seta acompanham o número sempre
    (IDENTIDADE.md §7). O CSV herda isso de graça."""
    if abs(valor) < 0.005:
        return brl(0)
    return f"{'▲ +' if valor > 0 else '▼ −'}{brl(abs(valor))}"


# --------------------------------------------------------------------- relatórios

def posicao(conn, data: str | None = None) -> Relatorio:
    ap = razao.apurar(conn, data)
    carteira = ap.carteira()
    precos = {p.ativo_id: cotacoes.preco(conn, p.ativo_id, data) for p in carteira}
    mercado_total = sum((precos[p.ativo_id] or p.preco_medio) * p.quantidade
                        for p in carteira)

    linhas, custo_total, sem_cotacao = [], 0.0, []
    for p in sorted(carteira, key=lambda x: x.ticker):
        cotacao = precos[p.ativo_id]
        if cotacao is None:
            sem_cotacao.append(p.ticker)
        valor = (cotacao or p.preco_medio) * p.quantidade
        custo_total += p.custo_total
        linhas.append([p.ticker, p.classe, f"{p.quantidade:g}", brl(p.preco_medio),
                       brl(p.custo_total), brl(cotacao) if cotacao else "—",
                       brl(valor), sinal(valor - p.custo_total),
                       pct(100 * valor / mercado_total if mercado_total else 0)])

    rel = Relatorio(
        "Posição consolidada",
        ["Ativo", "Classe", "Quantidade", "Preço médio", "Custo total",
         "Cotação", "Valor de mercado", "Resultado", "% da carteira"],
        linhas, numericas={2, 3, 4, 5, 6, 7, 8},
        rodape=[f"Custo total: R$ {brl(custo_total)}",
                f"Valor de mercado: R$ {brl(mercado_total)}",
                f"Resultado não realizado: R$ {sinal(mercado_total - custo_total)}"])
    if sem_cotacao:
        rel.avisos.append(
            f"Sem cotação, avaliados pelo preço médio: {', '.join(sorted(sem_cotacao))}")
    rel.avisos += ap.avisos
    return rel


def proventos(conn, ano: int | None = None) -> Relatorio:
    ap = razao.apurar(conn)
    recebidos = [p for p in ap.proventos if ano is None or p.data[:4] == str(ano)]
    posicoes = {p.ticker: p for p in ap.posicoes.values()}

    por_ativo: dict[str, dict[str, float]] = {}
    for p in recebidos:
        alvo = por_ativo.setdefault(p.ticker, {"DIVIDENDO": 0.0, "JCP": 0.0,
                                               "RENDIMENTO": 0.0, "irrf": 0.0})
        alvo[p.tipo] += p.valor
        alvo["irrf"] += p.irrf

    linhas, total = [], 0.0
    for ticker, valores in sorted(por_ativo.items()):
        soma = valores["DIVIDENDO"] + valores["JCP"] + valores["RENDIMENTO"]
        total += soma
        custo = posicoes[ticker].custo_total if ticker in posicoes else 0.0
        linhas.append([ticker, brl(valores["DIVIDENDO"]), brl(valores["JCP"]),
                       brl(valores["RENDIMENTO"]), brl(valores["irrf"]), brl(soma),
                       pct(100 * soma / custo) if custo else "—"])

    rel = Relatorio(
        f"Proventos recebidos{f' — {ano}' if ano else ''}",
        ["Ativo", "Dividendos", "JCP", "Rendimentos", "IRRF", "Total",
         "Yield on cost"], linhas, numericas={1, 2, 3, 4, 5, 6},
        rodape=[f"Total recebido: R$ {brl(total)}"])
    rel.avisos.append(
        "Yield on cost usa o custo da posição ATUAL: aporte novo derruba o "
        "percentual sem que o provento tenha caído.")
    return rel


def fluxo_proventos(conn, meses: int = 12, ate: str | None = None) -> Relatorio:
    """Provento mês a mês — a pergunta de quem investe para gerar caixa.

    O relatório por ativo responde "qual paga mais"; este responde "quanto entra
    por mês". São perguntas diferentes e a segunda precisa da série temporal."""
    ap = razao.apurar(conn)
    if not ap.proventos:
        return Relatorio("Fluxo de caixa dos proventos",
                         ["Competência", "Dividendos", "JCP", "Rendimentos",
                          "IRRF", "Total", "Média 3 meses"], numericas={1, 2, 3, 4, 5, 6})

    fim = (ate or max(p.data for p in ap.proventos))[:7]
    por_mes: dict[str, dict[str, float]] = {}
    for p in ap.proventos:
        if p.data[:7] > fim:
            continue
        alvo = por_mes.setdefault(p.data[:7], {"DIVIDENDO": 0.0, "JCP": 0.0,
                                               "RENDIMENTO": 0.0, "AMORTIZACAO": 0.0,
                                               "irrf": 0.0})
        alvo[p.tipo] = alvo.get(p.tipo, 0.0) + p.valor
        alvo["irrf"] += p.irrf

    # Preencher os meses vazios é o que mantém a média honesta: listar só os
    # meses que pagaram infla a média de quem recebe trimestralmente.
    ano, mes = int(fim[:4]), int(fim[5:7])
    competencias: list[str] = []
    for _ in range(meses):
        competencias.append(f"{ano:04d}-{mes:02d}")
        mes -= 1
        if mes == 0:
            ano, mes = ano - 1, 12
    competencias.reverse()
    primeiro = min(por_mes) if por_mes else fim
    competencias = [c for c in competencias if c >= primeiro]

    linhas, totais = [], []
    vazio = {"DIVIDENDO": 0.0, "JCP": 0.0, "RENDIMENTO": 0.0,
             "AMORTIZACAO": 0.0, "irrf": 0.0}
    for i, competencia in enumerate(competencias):
        v = por_mes.get(competencia, vazio)
        total = v["DIVIDENDO"] + v["JCP"] + v["RENDIMENTO"] + v["AMORTIZACAO"]
        totais.append(total)
        janela = totais[max(0, i - 2):i + 1]
        linhas.append([competencia_br(competencia), brl(v["DIVIDENDO"]), brl(v["JCP"]),
                       brl(v["RENDIMENTO"]), brl(v["irrf"]), brl(total),
                       brl(sum(janela) / len(janela))])

    recebido = sum(totais)
    media = recebido / len(totais) if totais else 0.0
    custo = sum(p.custo_total for p in ap.carteira())
    rodape = [f"Recebido em {len(totais)} mês(es): R$ {brl(recebido)}",
              f"Média mensal: R$ {brl(media)}",
              f"Projeção anualizada (média × 12): R$ {brl(media * 12)}"]
    if custo:
        rodape.append(f"Yield anualizado sobre o custo da carteira: "
                      f"{pct(100 * media * 12 / custo)}")
    rel = Relatorio("Fluxo de caixa dos proventos",
                    ["Competência", "Dividendos", "JCP", "Rendimentos", "IRRF",
                     "Total", "Média 3 meses"], linhas, rodape,
                    numericas={1, 2, 3, 4, 5, 6})
    rel.avisos.append(
        "A projeção é a média do período multiplicada por 12 — extrapolação "
        "simples, não previsão. Provento não é contratado: corte de dividendo, "
        "aporte novo e mês atípico deslocam o número.")
    return rel


def apuracao(conn, ano: int) -> Relatorio:
    f = fisco.apurar(razao.apurar(conn))
    linhas = [[competencia_br(b.competencia), b.balde, brl(b.valor_vendas),
               sinal(b.resultado),
               brl(b.prejuizo_anterior), brl(b.compensado), brl(b.base),
               pct(b.aliquota * 100), brl(b.imposto), brl(b.irrf), brl(b.a_pagar),
               brl(b.prejuizo_acumulado)]
              for b in f.baldes if b.competencia[:4] == str(ano)]

    rodape = []
    for darf in (d for d in f.darfs if d.competencia[:4] == str(ano)):
        composicao = ", ".join(f"{k} R$ {brl(v)}" for k, v in darf.composicao.items())
        atraso = (f" (inclui R$ {brl(darf.de_meses_anteriores)} de meses anteriores)"
                  if darf.de_meses_anteriores else "")
        rodape.append(f"DARF {competencia_br(darf.competencia)} — código "
                      f"{darf.codigo} — R$ {brl(darf.valor)}{atraso}, vence "
                      f"{data_br(darf.vencimento)} [{composicao}]")
    if f.acumulado_pendente:
        rodape.append(f"Abaixo do piso, aguardando o próximo mês: "
                      f"R$ {brl(f.acumulado_pendente)}")
    exclusiva = [v for v in f.exclusiva if v.data[:4] == str(ano)]
    if exclusiva:
        rodape.append(
            f"Tributação exclusiva na fonte (renda fixa), {len(exclusiva)} "
            f"resgate(s): rendimento de R$ "
            f"{brl(sum(v.resultado for v in exclusiva))}, IRRF retido de R$ "
            f"{brl(sum(v.irrf for v in exclusiva))} — declarar como rendimento "
            f"sujeito a tributação exclusiva, fora desta apuração")
    for balde, saldo in f.prejuizo.items():
        if saldo:
            rodape.append(f"Prejuízo a compensar em {balde}: R$ {brl(saldo)}")

    rel = Relatorio(
        f"Apuração de IR — {ano}",
        ["Competência", "Balde", "Vendas", "Resultado", "Prejuízo anterior",
         "Compensado", "Base", "Alíquota", "Imposto", "IRRF", "A pagar",
         "Prejuízo acumulado"], linhas, rodape,
        numericas={2, 3, 4, 5, 6, 7, 8, 9, 10, 11}, avisos=list(f.avisos))
    rel.avisos.append("Memória de cálculo para conferência. O Peculium não "
                      "transmite nada à Receita nem emite DARF oficial.")
    for isencao in (i for i in f.isencoes if i.competencia[:4] == str(ano)):
        if isencao.aplicada:
            rel.avisos.append(
                f"{competencia_br(isencao.competencia)}: vendas de ações de R$ "
                f"{brl(isencao.vendas_acoes)} dentro do limite de R$ "
                f"{brl(fisco.LIMITE_ISENCAO)} — ganho isento de R$ "
                f"{brl(isencao.resultado_isento)}")
    return rel


def obrigacoes(conn, hoje: str | None = None) -> Relatorio:
    lista = _obrigacoes.listar(conn, hoje)
    linhas, avisos = [], []
    for o in lista:
        linhas.append([competencia_br(o.competencia), o.codigo,
                       data_br(o.vencimento) or "—", brl(o.valor_apurado),
                       brl(o.valor_pago) if o.valor_pago else "—",
                       data_br(o.data_pagamento) or "—", o.situacao,
                       str(o.dias_atraso) if o.dias_atraso else "—",
                       brl(o.multa) if o.multa else "—",
                       brl(o.juros) if o.juros else "—",
                       brl(o.total_a_pagar) if o.total_a_pagar else "—"])
        for texto in o.observacoes:
            avisos.append(f"{competencia_br(o.competencia)}: {texto}")

    devido = sum(o.total_a_pagar for o in lista)
    rodape = [f"Total em aberto: R$ {brl(devido)}"]
    vencidos = [o for o in lista if o.situacao == _obrigacoes.VENCIDO]
    if vencidos:
        rodape.append(f"{len(vencidos)} obrigação(ões) vencida(s)")
    return Relatorio(
        "Contas a pagar — DARF",
        ["Competência", "Código", "Vencimento", "Apurado", "Pago", "Data do pgto.",
         "Situação", "Dias em atraso", "Multa", "Juros", "Total a pagar"],
        linhas, rodape, numericas={3, 4, 7, 8, 9, 10}, avisos=avisos)


def renda_fixa(conn, data: str | None = None) -> Relatorio:
    import renda_fixa as _rf

    linhas, custo_total, bruto_total = [], 0.0, 0.0
    sem_curva = []
    for p in _rf.posicao(conn, data):
        custo_total += p["custo"]
        bruto_total += p["bruto"]
        # a alíquota regressiva conta da emissão, e a emissão só existe no
        # cadastro: sem ele não há estimativa a dar, e inventar uma seria
        # estimativa dentro de conta de imposto
        ir = (_rf.ir_estimado(conn, p["ativo_id"], data or date.today().isoformat(),
                              p["rendimento"])
              if _rf.titulo(conn, p["ativo_id"]) else None)
        if p["erro"]:
            sem_curva.append(f"{p['ticker']}: {p['erro']}")
        linhas.append([
            p["ticker"], p["emissor"] or "—", p["indexador"],
            data_br(p["vencimento"]) or "—",
            f"{p['quantidade']:g}", brl(p["custo"]),
            brl(p["pu"]) if p["pu"] else "—", brl(p["bruto"]),
            sinal(p["rendimento"]),
            "—" if ir is None else "isento" if p["isento"]
            else f"{ir['aliquota'] * 100:.1f}%",
            "—" if ir is None else brl(ir["imposto"]),
            brl(p["bruto"] - (ir["imposto"] if ir else 0.0))])

    rel = Relatorio(
        "Renda fixa e Tesouro",
        ["Título", "Emissor", "Indexador", "Vencimento", "Quantidade", "Custo",
         "PU", "Bruto", "Rendimento", "Alíquota", "IR estimado", "Líquido"],
        linhas, numericas={4, 5, 6, 7, 8, 9, 10, 11},
        rodape=[f"Custo total: R$ {brl(custo_total)}",
                f"Valor bruto: R$ {brl(bruto_total)}",
                f"Rendimento acumulado: R$ {sinal(bruto_total - custo_total)}"])
    rel.avisos.append(
        "O IR é estimativa pelo prazo desde a emissão: o valor retido de verdade "
        "vem no extrato da corretora, e é ele que deve ser lançado. Com aportes "
        "em datas diferentes, cada aplicação tem sua própria alíquota.")
    rel.avisos += sem_curva
    return rel


def bens_direitos(conn, ano: int) -> Relatorio:
    """Posição em 31/12 pelo custo de aquisição, para a declaração."""
    corte = f"{ano}-12-31"
    ap = razao.apurar(conn, ate=corte)   # a posição do ano, não a de hoje
    linhas, total = [], 0.0
    for p in sorted(ap.carteira(), key=lambda x: x.ticker):
        total += p.custo_total
        linhas.append([p.ticker, p.classe, f"{p.quantidade:g}",
                       brl(p.preco_medio), brl(p.custo_total)])
    rel = Relatorio(f"Bens e direitos em {data_br(corte)}",
                    ["Ativo", "Classe", "Quantidade", "Preço médio",
                     "Custo de aquisição"], linhas,
                    [f"Custo total declarável: R$ {brl(total)}"],
                    numericas={2, 3, 4})
    rel.avisos.append("Valor declarado é o CUSTO de aquisição, nunca o valor de "
                      "mercado — bem em renda variável se declara pelo que custou.")
    return rel


def operacoes(conn, ano: int | None = None) -> Relatorio:
    filtro = " WHERE l.data LIKE ?" if ano else ""
    parametros = (f"{ano}-%",) if ano else ()
    linhas = [[data_br(r["data"]), r["tipo"], r["ticker"] or "—",
               r["instituicao"] or "—",
               f"{r['quantidade']:g}", brl(r["preco"]), brl(r["valor"]),
               brl(r["custos"]), r["origem"], r["numero"] or "—"]
              for r in conn.execute(
                  "SELECT l.*, a.ticker, i.nome AS instituicao, n.numero"
                  " FROM lancamentos l"
                  " LEFT JOIN ativos a ON a.id = l.ativo_id"
                  " LEFT JOIN instituicoes i ON i.id = l.instituicao_id"
                  " LEFT JOIN notas n ON n.id = l.nota_id"
                  + filtro + " ORDER BY l.data, l.id", parametros)]
    return Relatorio(f"Operações{f' — {ano}' if ano else ''}",
                     ["Data", "Tipo", "Ativo", "Instituição", "Quantidade",
                      "Preço", "Valor", "Custos", "Origem", "Nota"],
                     linhas, [f"{len(linhas)} lançamentos"],
                     numericas={4, 5, 6, 7})


def custos(conn, ano: int | None = None) -> Relatorio:
    filtro = " AND l.data LIKE ?" if ano else ""
    parametros = (f"{ano}-%",) if ano else ()
    linhas = [[competencia_br(r["mes"]), r["instituicao"] or "—", str(r["n"]),
               brl(r["custos"])]
              for r in conn.execute(
                  "SELECT substr(l.data,1,7) AS mes, i.nome AS instituicao,"
                  " count(*) AS n, sum(l.custos) AS custos FROM lancamentos l"
                  " LEFT JOIN instituicoes i ON i.id = l.instituicao_id"
                  " WHERE l.tipo IN ('COMPRA','VENDA') AND l.estorna_id IS NULL"
                  + filtro + " GROUP BY mes, i.nome ORDER BY mes", parametros)]
    # O que denuncia negócio sem custo é NÃO TER NOTA, não ter custo zero: numa
    # nota grande o rateio de uma linha pequena arredonda para zero legitimamente.
    sem = conn.execute(
        "SELECT count(*) FROM lancamentos WHERE tipo IN ('COMPRA','VENDA')"
        " AND estorna_id IS NULL AND nota_id IS NULL"
        " AND id NOT IN (SELECT estorna_id FROM lancamentos"
        "                WHERE estorna_id IS NOT NULL)").fetchone()[0]
    rel = Relatorio(f"Custos operacionais{f' — {ano}' if ano else ''}",
                    ["Competência", "Instituição", "Negócios", "Custos"],
                    linhas, numericas={2, 3})
    if sem:
        rel.avisos.append(
            f"{sem} negócio(s) sem custos: são os que ainda não têm nota de "
            f"corretagem importada. O Peculium não estima custo — o preço médio "
            f"deles está subavaliado até a nota entrar.")
    return rel


# --------------------------------------------------------------------- retorno

def xirr(fluxos: list[tuple[date, float]], tentativa: float = 0.1) -> float | None:
    """Taxa interna de retorno com datas irregulares — o "quanto rendeu o meu
    dinheiro", que é a pergunta que o investidor faz.

    Newton primeiro; bisseção quando ele escapa, que é o caso comum de fluxo com
    vários sinais. Devolve taxa anual (0.12 = 12% ao ano)."""
    if len(fluxos) < 2 or all(v >= 0 for _, v in fluxos) or all(v <= 0 for _, v in fluxos):
        return None
    base = min(d for d, _ in fluxos)
    prazos = [((d - base).days / 365.0, v) for d, v in fluxos]

    def vpl(taxa: float) -> float:
        return sum(v / (1 + taxa) ** t for t, v in prazos)

    taxa = tentativa
    for _ in range(60):
        f = vpl(taxa)
        derivada = sum(-t * v / (1 + taxa) ** (t + 1) for t, v in prazos)
        if abs(derivada) < 1e-12:
            break
        proxima = taxa - f / derivada
        if proxima <= -0.9999:
            break
        if abs(proxima - taxa) < 1e-9:
            return proxima
        taxa = proxima
    baixo, alto = -0.9999, 100.0
    if vpl(baixo) * vpl(alto) > 0:
        return None
    for _ in range(300):
        meio = (baixo + alto) / 2
        if vpl(baixo) * vpl(meio) <= 0:
            alto = meio
        else:
            baixo = meio
    return (baixo + alto) / 2


def rentabilidade(conn, ate: str | None = None) -> Relatorio:
    ap = razao.apurar(conn)
    fluxos: list[tuple[date, float]] = []
    for v in ap.vendas:
        fluxos.append((date.fromisoformat(v.data), v.valor_liquido - v.irrf))
    for p in ap.proventos:
        fluxos.append((date.fromisoformat(p.data), p.valor - p.irrf))
    for linha in conn.execute(
            "SELECT data, valor, custos FROM lancamentos"
            " WHERE tipo IN ('COMPRA','SUBSCRICAO') AND estorna_id IS NULL"
            "   AND id NOT IN (SELECT estorna_id FROM lancamentos"
            "                  WHERE estorna_id IS NOT NULL)"):
        fluxos.append((date.fromisoformat(linha[0]), -(linha[1] + linha[2])))

    carteira = ap.carteira()
    mercado = sum((cotacoes.preco(conn, p.ativo_id, ate) or p.preco_medio) * p.quantidade
                  for p in carteira)
    hoje = date.fromisoformat(ate) if ate else date.today()
    if mercado:
        fluxos.append((hoje, mercado))

    taxa = xirr(sorted(fluxos))
    aportado = -sum(v for _, v in fluxos if v < 0)
    recebido = sum(v for _, v in fluxos if v > 0)
    rel = Relatorio(
        "Rentabilidade", ["Indicador", "Valor"],
        [["Aportado (compras e custos)", f"R$ {brl(aportado)}"],
         ["Retornado (vendas, proventos e posição atual)", f"R$ {brl(recebido)}"],
         ["Resultado", f"R$ {sinal(recebido - aportado)}"],
         ["Retorno do dinheiro (XIRR, ao ano)",
          pct(taxa * 100) if taxa is not None else "—"]],
        numericas={1})
    rel.avisos.append(
        "XIRR pondera pelo tempo que cada real ficou aplicado. Não é comparável "
        "com o CDI de um período fixo — para isso é preciso série histórica de "
        "preços, que o programa ainda não guarda.")
    return rel


# --------------------------------------------------------------------- saída

def csv_texto(rel: Relatorio) -> str:
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(rel.colunas)
    escritor.writerows(rel.linhas)
    for nota in (*rel.rodape, *rel.avisos):
        escritor.writerow([nota])
    return saida.getvalue()


def documento(rel: Relatorio, tema: str = "atrium", subtitulo: str = "") -> str:
    """HTML timbrado. A impressão ignora o tema da tela e sai sempre clara."""
    p = PALETAS.get(tema, PALETAS["atrium"])
    cabecalho = "".join(
        f'<th class="{"n" if i in rel.numericas else ""}">{_html.escape(c)}</th>'
        for i, c in enumerate(rel.colunas))
    corpo = "".join(
        "<tr>" + "".join(
            f'<td class="{"n" if i in rel.numericas else ""}">'
            f'{_html.escape(str(v))}</td>' for i, v in enumerate(linha)) + "</tr>"
        for linha in rel.linhas) or \
        f'<tr><td colspan="{len(rel.colunas)}" class="vazio">Nada a exibir</td></tr>'
    rodape = "".join(f"<li>{_html.escape(t)}</li>" for t in rel.rodape)
    avisos = "".join(f"<li>{_html.escape(t)}</li>" for t in rel.avisos)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>{_html.escape(rel.titulo)} — Peculium</title>
<style>
 @page {{ size: A4 landscape; margin: 14mm; }}
 body {{ background:{p['bg']}; color:{p['texto']}; margin:0; padding:24px;
        font:14px/1.5 system-ui,Segoe UI,sans-serif; }}
 .folha {{ background:{p['papel']}; border:1px solid {p['borda']}; border-radius:8px;
          padding:24px; max-width:1200px; margin:0 auto; }}
 h1 {{ font:600 20px/1.2 Georgia,serif; margin:0 0 2px; }}
 .marca {{ font:400 12px/1 Georgia,serif; letter-spacing:.16em; color:{p['marca']}; }}
 .sub {{ color:{p['suave']}; font-size:12px; margin:0 0 18px; }}
 table {{ width:100%; border-collapse:collapse; font-size:13px; }}
 th,td {{ padding:6px 8px; border-bottom:1px solid {p['borda']}; text-align:left; }}
 th {{ font-size:11px; text-transform:uppercase; letter-spacing:.08em;
       color:{p['suave']}; }}
 td.n, th.n {{ text-align:right; font-variant-numeric:tabular-nums; }}
 .vazio {{ color:{p['suave']}; text-align:center; padding:20px; }}
 ul {{ margin:14px 0 0; padding-left:18px; font-size:12px; color:{p['suave']}; }}
 .rodape li {{ color:{p['texto']}; }}
 @media print {{ body {{ background:#fff; padding:0; }}
                 .folha {{ border:0; max-width:none; }} }}
</style></head><body><div class="folha">
<div class="marca">PEC<span style="color:{p['marca']}">V</span>LI<span
 style="color:{p['marca']}">V</span>M</div>
<h1>{_html.escape(rel.titulo)}</h1>
<p class="sub">{_html.escape(subtitulo or date.today().strftime('Emitido em %d/%m/%Y'))}</p>
<table><thead><tr>{cabecalho}</tr></thead><tbody>{corpo}</tbody></table>
{f'<ul class="rodape">{rodape}</ul>' if rodape else ''}
{f'<ul>{avisos}</ul>' if avisos else ''}
</div></body></html>"""
