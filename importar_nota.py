"""Importação de nota de corretagem em PDF, layout Sinacor (DESIGN.md §6.1).

A nota é a **única fonte dos custos**: o relatório de Negociação da B3 não traz
corretagem nem emolumentos. Medido em 7 notas reais: a taxa operacional é valor
fixo por nota (R$ 9,80 quando há ação, zero quando só há FII/Fiagro) — nenhuma
alíquota sobre valor reproduz isso, e por isso não existe cálculo de custo
estimado neste programa.

Três fatos do layout que o parser precisa respeitar:

1. **O pypdf não devolve ordem visual.** No cabeçalho o rótulo vem antes do valor
   (`Nr. nota` / `140560283`); no resumo financeiro o **valor vem antes do
   rótulo** (`997,50` / `Valor líquido das operações` / `D`).
2. **A coluna de observação é opcional** e a especificação ocupa de uma a três
   linhas, então cada negócio é lido pelas pontas: três campos na frente, quatro
   atrás, e o miolo é especificação mais marcadores.
3. **A nota não traz ticker**, exceto nos FII, onde ele aparece embutido na
   especificação (`FII MAXI REN MXRF11 CI`). O resto se resolve pela tabela de
   apelidos, aprendida uma vez por ativo.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import textos

TOLERANCIA = 0.01          # centavo de arredondamento entre rubricas
TOL_PRECO = 0.005          # casamento de preço com o negócio vindo da B3

CRIA = "CRIA"
ENRIQUECE = "ENRIQUECE"
SEM_ATIVO = "SEM_ATIVO"

_DINHEIRO = re.compile(r"^-?[\d.]+,\d{2}$")
_INICIO = re.compile(r"^\d+-\w+")                    # "1-BOVESPA"
_TICKER = re.compile(r"\b([A-Z]{4}\d{1,2})\b")
_LIQUIDO = re.compile(r"^Líquido para\s+(\d{2}/\d{2}/\d{4})")

# Marcadores da coluna Obs. da nota. As letras excluídas (E, J, M, N, R) são as
# que aparecem nas etiquetas de governança e de evento — ER, ED, EJ, NM, N2 —,
# que fazem parte da especificação e não da observação.
_OBS = set("@#ATCIP8HDXFYBL2")

# Rubricas do resumo financeiro que SÃO custo da operação.
CUSTOS = ("Taxa de liquidação", "Taxa de Registro", "Taxa de termo/opções",
          "Taxa A.N.A.", "Emolumentos", "Taxa de Transf. de Ativos",
          "Taxa Operacional", "Execução", "Taxa de Custódia", "Impostos", "Outros")
# Subtotais: lidos para conferência, nunca somados (dupla contagem).
SUBTOTAIS = ("Total CBLC", "Total Bovespa / Soma", "Total Custos / Despesas")
IRRF = "I.R.R.F. s/ operações"


class NotaInconsistente(Exception):
    """A nota não fecha aritmeticamente — não se grava o que não confere."""


class NotaProtegida(Exception):
    pass


@dataclass
class Negocio:
    sentido: str            # COMPRA | VENDA
    mercado: str
    especificacao: str
    ticker: str             # vazio quando a nota não traz o código
    obs: str
    quantidade: float
    preco: float
    valor: float
    custos: float = 0.0     # rateado pro rata pelo valor financeiro
    irrf: float = 0.0       # rateado só entre as vendas

    @property
    def day_trade(self) -> bool:
        return "D" in self.obs


@dataclass
class Nota:
    numero: str
    corretora: str
    cnpj: str
    data_pregao: str
    data_liquidacao: str
    valor_operacoes: float          # com sinal: positivo quando há saldo a pagar
    total_custos: float
    irrf: float
    liquido: float                  # com sinal, mesma convenção
    rubricas: dict[str, float]
    negocios: list[Negocio] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


# --------------------------------------------------------------------- PDF

def senhas_candidatas(cpf: str | None, conhecidas: tuple[str, ...] = ()) -> list[str]:
    """Ordem de tentativa: senhas que o usuário já cadastrou, depois nenhuma,
    depois as derivadas do CPF.

    Medido nas notas reais: arquivos da mesma corretora divergem entre si — parte
    das notas da XP não tem senha alguma e parte usa os **3 últimos dígitos do CPF
    inteiro**; uma nota da Inter abriu com os **6 primeiros**.

    Cuidado que custou uma rodada: "os 3 últimos" atravessa o hífen. Num CPF
    `123.456.789-09`, os 3 últimos são `909` — e não `789` (últimos 3 do corpo)
    nem `09` (os verificadores). São recortes diferentes e todos precisam estar
    na lista.

    A senha cadastrada por corretora vem primeiro mesmo assim: é o único caminho
    garantido quando a corretora não usa o CPF."""
    candidatas = [s for s in conhecidas if s]
    candidatas.append("")
    digitos = re.sub(r"\D", "", cpf or "")
    if len(digitos) == 11:
        candidatas += [digitos[-3:], digitos[:3], digitos[:6], digitos[6:9],
                       digitos[-2:], digitos, digitos[:9], digitos[:4],
                       digitos[:5], digitos[-4:], digitos[-5:], digitos[-6:]]
    return candidatas


def ler_texto(caminho: str | Path, cpf: str | None = None,
              senhas: tuple[str, ...] = ()) -> str:
    from pypdf import PdfReader

    leitor = PdfReader(Path(caminho))
    if leitor.is_encrypted:
        tentativas = senhas_candidatas(cpf, tuple(senhas))
        if not any(leitor.decrypt(s) for s in tentativas):
            raise NotaProtegida(
                f"{Path(caminho).name}: protegido por senha e nenhuma das "
                f"{len(tentativas)} tentativas abriu — informe a senha desta corretora")
    return "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)


# --------------------------------------------------------------------- parsing

def _sinal(dc: str) -> int:
    """D é débito (dinheiro sai: compra); C é crédito (dinheiro entra: venda)."""
    return 1 if dc.strip().upper().startswith("D") else -1


def _resumo(linhas: list[str]) -> tuple[dict[str, float], dict[str, int]]:
    """Rubricas do resumo financeiro: o valor está na linha ANTERIOR ao rótulo."""
    valores: dict[str, float] = {}
    sinais: dict[str, int] = {}
    rotulos = (*CUSTOS, *SUBTOTAIS, IRRF, "Valor líquido das operações")
    for i, linha in enumerate(linhas):
        for rotulo in rotulos:
            if linha.startswith(rotulo) and rotulo not in valores and i:
                if _DINHEIRO.match(linhas[i - 1]):
                    valores[rotulo] = textos.numero(linhas[i - 1])
                    seguinte = linhas[i + 1] if i + 1 < len(linhas) else ""
                    sinais[rotulo] = _sinal(seguinte) if seguinte in ("D", "C") else 1
    return valores, sinais


def _negocio(bloco: list[str]) -> Negocio:
    if len(bloco) < 6 or bloco[-1].strip().upper() not in ("D", "C"):
        raise NotaInconsistente(f"linha de negócio irreconhecível: {bloco}")
    if not (_DINHEIRO.match(bloco[-2]) and _DINHEIRO.match(bloco[-3])):
        raise NotaInconsistente(f"preço/valor irreconhecíveis: {bloco}")

    sentido = "COMPRA" if bloco[0].strip().upper().startswith("C") else "VENDA"
    meio = bloco[2:-4]
    obs = ""
    if meio and meio[-1] and set(meio[-1]) <= _OBS:
        obs = meio.pop()
    especificacao = re.sub(r"\s+", " ", " ".join(meio)).strip()
    achado = _TICKER.search(especificacao)
    return Negocio(sentido, bloco[1].strip(), especificacao,
                   achado.group(1) if achado else "", obs,
                   textos.numero(bloco[-4]), textos.numero(bloco[-3]),
                   textos.numero(bloco[-2]))


def _negocios(linhas: list[str]) -> tuple[list[Negocio], float]:
    """Devolve os negócios e a soma ASSINADA (compras positivas, vendas negativas).

    O sinal vem da coluna D/C de cada linha — é o que faz o invariante valer
    também em nota de venda e em nota mista."""
    try:
        inicio = linhas.index("D/C") + 1
    except ValueError:
        raise NotaInconsistente("cabeçalho da tabela de negócios não encontrado")
    negocios, soma, i = [], 0.0, inicio
    while i < len(linhas) and _INICIO.match(linhas[i]):
        bloco, i = [], i + 1
        while i < len(linhas) and not _INICIO.match(linhas[i]) \
                and linhas[i] != "NOTA DE NEGOCIAÇÃO":
            bloco.append(linhas[i])
            i += 1
        negocios.append(_negocio(bloco))
        soma += negocios[-1].valor * _sinal(bloco[-1])
    if not negocios:
        raise NotaInconsistente("nenhum negócio na nota")
    return negocios, soma


def _ratear(nota: Nota) -> None:
    """Pro rata pelo valor financeiro de cada linha; a última absorve o resto.

    Sem absorver o resíduo, a soma dos custos rateados não bate com o total da
    nota por causa do arredondamento a centavos — e aí o custo de aquisição
    passa a divergir da nota que o comprova."""
    base = sum(n.valor for n in nota.negocios)
    if base <= 0:
        return
    for chave, total, alvos in (("custos", nota.total_custos, nota.negocios),
                                ("irrf", nota.irrf,
                                 [n for n in nota.negocios if n.sentido == "VENDA"])):
        if not total:
            continue
        if not alvos:
            nota.avisos.append(
                f"nota tem {chave} de {total:.2f} mas nenhuma venda para rateá-lo")
            continue
        divisor = sum(n.valor for n in alvos)
        acumulado = 0.0
        for negocio in alvos[:-1]:
            parcela = round(total * negocio.valor / divisor, 2)
            setattr(negocio, chave, parcela)
            acumulado += parcela
        setattr(alvos[-1], chave, round(total - acumulado, 2))


def parsear(texto: str) -> Nota:
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    negocios, soma_negocios = _negocios(linhas)
    valores, sinais = _resumo(linhas)

    if "Valor líquido das operações" not in valores:
        raise NotaInconsistente("resumo financeiro sem 'Valor líquido das operações'")
    operacoes = valores["Valor líquido das operações"] * sinais["Valor líquido das operações"]
    custos = sum(valores.get(c, 0.0) for c in CUSTOS)
    irrf = valores.get(IRRF, 0.0)

    liquido = 0.0
    liquidacao = ""
    for i, linha in enumerate(linhas):
        achado = _LIQUIDO.match(linha)
        if achado and _DINHEIRO.match(linhas[i - 1]):
            liquidacao = textos.data_iso(achado.group(1))
            seguinte = linhas[i + 1] if i + 1 < len(linhas) else "D"
            liquido = textos.numero(linhas[i - 1]) * _sinal(seguinte)
            break

    # Invariante 1: as linhas de negócio reconstroem o valor das operações.
    if abs(soma_negocios - operacoes) > TOLERANCIA:
        raise NotaInconsistente(
            f"soma dos negócios ({soma_negocios:.2f}) não bate com o valor das "
            f"operações ({operacoes:.2f})")
    # Invariante 2: operações + custos + IRRF reconstroem o líquido a liquidar.
    esperado = operacoes + custos + irrf
    if abs(esperado - liquido) > TOLERANCIA:
        # o diagnóstico vale mais que a recusa seca: diz qual leitura fecharia
        alternativa = "" if abs(operacoes + custos - liquido) > TOLERANCIA else \
            " — fecharia se o IRRF já estivesse dentro das rubricas de custo"
        raise NotaInconsistente(
            f"líquido não confere: operações {operacoes:.2f} + custos {custos:.2f} "
            f"+ IRRF {irrf:.2f} = {esperado:.2f}, nota diz {liquido:.2f}{alternativa}")

    nota = Nota(
        numero=_apos(linhas, "Nr. nota"),
        corretora=_corretora(linhas),
        cnpj=_cnpj(linhas),
        data_pregao=textos.data_iso(_apos(linhas, "Data pregão")),
        data_liquidacao=liquidacao,
        valor_operacoes=operacoes, total_custos=custos, irrf=irrf, liquido=liquido,
        rubricas={k: v for k, v in valores.items()}, negocios=negocios)
    _ratear(nota)
    for negocio in negocios:
        if abs(negocio.quantidade * negocio.preco - negocio.valor) > 0.01:
            nota.avisos.append(
                f"{negocio.especificacao}: {negocio.quantidade:g} × "
                f"{negocio.preco:.2f} não dá {negocio.valor:.2f}")
    return nota


def _apos(linhas: list[str], rotulo: str) -> str:
    """No cabeçalho o rótulo vem ANTES do valor — o oposto do resumo financeiro."""
    for i, linha in enumerate(linhas):
        if linha == rotulo and i + 1 < len(linhas):
            return linhas[i + 1].strip()
    raise NotaInconsistente(f"campo '{rotulo}' não encontrado")


def _cnpj(linhas: list[str]) -> str:
    for linha in linhas:
        achado = re.search(r"C\.?N\.?P\.?J[.:]?\s*([\d./-]{14,20})", linha)
        if achado:
            return re.sub(r"\D", "", achado.group(1))
    return ""


def _corretora(linhas: list[str]) -> str:
    for linha in linhas:
        if "CORRETORA" in _sem_acento(linha).upper() and len(linha) > 12:
            return linha.strip()
    return ""


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def ler(caminho: str | Path, cpf: str | None = None,
        senhas: tuple[str, ...] = ()) -> Nota:
    return parsear(ler_texto(caminho, cpf, senhas))


# --------------------------------------------------------------------- conferência

@dataclass
class Item:
    negocio: Negocio
    situacao: str
    ativo_id: int | None = None
    motivo: str = ""
    # lançamentos da B3 que esta linha da nota substitui. Lista, e não um id,
    # porque a B3 agrupa execuções que a nota detalha: um item da nota pode
    # substituir vários lançamentos, e vários itens podem substituir um só.
    substitui: list[int] = field(default_factory=list)


@dataclass
class Conferencia:
    nota: Nota
    itens: list[Item] = field(default_factory=list)
    ja_importada: bool = False
    avisos: list[str] = field(default_factory=list)

    def por_situacao(self, situacao: str) -> list[Item]:
        return [i for i in self.itens if i.situacao == situacao]


def _hash(nota: Nota, indice: int) -> str:
    crua = f"NOTA|{nota.cnpj}|{nota.numero}|{nota.data_pregao}|{indice}"
    return hashlib.sha256(crua.encode()).hexdigest()


def conferir(conn, nota: Nota) -> Conferencia:
    conf = Conferencia(nota, avisos=list(nota.avisos))
    ja = conn.execute("SELECT id FROM notas WHERE numero=? AND cnpj=? AND data_pregao=?",
                      (nota.numero, nota.cnpj, nota.data_pregao)).fetchone()
    conf.ja_importada = ja is not None

    for negocio in nota.negocios:
        ativo_id = _resolver(conn, negocio)
        if ativo_id is None:
            # Vale tanto para "a nota não diz o código" quanto para "diz, mas o
            # ativo ainda não existe" — o segundo caso é o do FII, que traz o
            # ticker embutido, e deixá-lo passar gravava lançamento sem ativo.
            conf.itens.append(Item(
                negocio, SEM_ATIVO,
                motivo=(f"ativo {negocio.ticker} ainda não cadastrado: confirme a "
                        f"classe" if negocio.ticker else
                        "a nota não traz o código; informe o ticker uma vez e o "
                        "sistema passa a reconhecer")))
            continue
        conf.itens.append(Item(negocio, CRIA, ativo_id))
    _reconciliar(conn, conf)
    return conf


def _resolver(conn, negocio: Negocio) -> int | None:
    """Ativo do negócio, pelo código da nota ou pelo apelido já aprendido."""
    if negocio.ticker:
        linha = conn.execute("SELECT id FROM ativos WHERE upper(ticker)=?",
                             (negocio.ticker.upper(),)).fetchone()
        if linha:
            return linha[0]
    linha = conn.execute("SELECT ativo_id FROM apelidos WHERE especificacao=?",
                         (negocio.especificacao,)).fetchone()
    return linha[0] if linha else None


def _reconciliar(conn, conf: Conferencia) -> None:
    """Casa a nota com o que já veio da B3 **no agregado do dia**.

    Duas coisas que a versão anterior errava, e que juntas dobravam a carteira:

    **Casava linha a linha.** A B3 agrupa execuções que a nota detalha — num dia
    real ela trouxe SNAG11 como 68+12 e a nota como 1+11+68. Nenhuma linha casa
    com nenhuma, e o negócio inteiro entrava de novo por cima do da B3. Somando
    o dia, 80 = 80 e a nota substitui o que estava lá.

    **Rodava antes de o ticker ser resolvido.** Para o papel cujo código a nota
    não traz, o `conferir` não tinha como saber o ativo, então nunca achava
    contraparte — e a primeira nota de cada papel duplicava. Agora esta função é
    chamada duas vezes: no `conferir`, para a tela, e de novo no `gravar`, com
    os tickers que o usuário informou.

    Quantidades diferentes no agregado **não** são reconciliadas: aí é negócio
    de verdade diferente, e apagar o da B3 perderia lançamento."""
    nota = conf.nota
    grupos: dict[tuple[int, str], list[Item]] = {}
    for item in conf.itens:
        if item.ativo_id is not None:
            grupos.setdefault((item.ativo_id, item.negocio.sentido), []).append(item)

    for (ativo_id, sentido), itens in grupos.items():
        linhas = list(conn.execute(
            "SELECT id, quantidade, valor FROM lancamentos"
            " WHERE data=? AND tipo=? AND ativo_id=? AND nota_id IS NULL"
            "   AND estorna_id IS NULL"
            "   AND id NOT IN (SELECT estorna_id FROM lancamentos"
            "                  WHERE estorna_id IS NOT NULL)",
            (nota.data_pregao, sentido, ativo_id)))
        da_nota = sum(i.negocio.quantidade for i in itens)
        da_b3 = sum(l["quantidade"] for l in linhas)
        valor_nota = sum(i.negocio.valor for i in itens)
        valor_b3 = sum(l["valor"] for l in linhas)
        # quantidade E valor: só a quantidade colaria a nota no negócio errado
        # quando há duas ordens do mesmo papel no dia com preços diferentes
        substitui = (bool(linhas) and abs(da_b3 - da_nota) < 1e-9
                     and abs(valor_b3 - valor_nota) <= max(0.02, 0.001 * valor_b3))
        for indice, item in enumerate(itens):
            if substitui:
                item.situacao = ENRIQUECE
                item.motivo = ("negócio já veio da B3: a nota substitui o do dia "
                               "e acrescenta os custos")
                # os estornos ficam todos no primeiro item do grupo: são um por
                # lançamento da B3, e o grupo pode ter contagens diferentes dos
                # dois lados
                item.substitui = [l["id"] for l in linhas] if indice == 0 else []
            else:
                item.situacao = CRIA
                item.motivo = "sem contraparte na B3: a nota cria o negócio"
                item.substitui = []
    return conf


# --------------------------------------------------------------------- gravação

def gravar(conn, conf: Conferencia, tickers: dict[str, str] | None = None,
           classes: dict[str, str] | None = None) -> dict:
    """Grava a nota. `tickers` mapeia especificação → ticker (vira apelido).

    Enriquecer um negócio que veio da B3 é **estorno mais relançamento**, nunca
    UPDATE: o razão é append-only e a correção tem de ficar visível no extrato."""
    if conf.ja_importada:
        return {"nota_id": None, "criados": 0, "enriquecidos": 0, "ja_importada": True}
    tickers = {k: v.upper() for k, v in (tickers or {}).items()}
    classes = {k.upper(): v for k, v in (classes or {}).items()}

    # Validar TUDO antes de escrever qualquer linha: uma gravação recusada no
    # meio deixava a nota no banco e a segunda tentativa batia no UNIQUE.
    pendentes, sem_classe = [], []
    for item in conf.por_situacao(SEM_ATIVO):
        ticker = tickers.get(item.negocio.especificacao) or item.negocio.ticker
        if not ticker:
            pendentes.append(item.negocio.especificacao)
            continue
        existe = conn.execute("SELECT 1 FROM ativos WHERE upper(ticker)=?",
                              (ticker,)).fetchone()
        if not existe and not classes.get(ticker):
            sem_classe.append(ticker)
    if pendentes:
        raise ValueError(f"ticker não informado para: {', '.join(sorted(set(pendentes)))}")
    if sem_classe:
        raise ValueError(f"classe não definida para: {', '.join(sorted(set(sem_classe)))}")

    nota, agora = conf.nota, datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO notas (numero, corretora, cnpj, data_pregao, data_liquidacao,"
        " valor_operacoes, total_custos, liquido, irrf, rubricas, importada_em)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (nota.numero, nota.corretora, nota.cnpj, nota.data_pregao, nota.data_liquidacao,
         nota.valor_operacoes, nota.total_custos, nota.liquido, nota.irrf,
         json.dumps(nota.rubricas, ensure_ascii=False), agora))
    nota_id = cur.lastrowid

    for item in conf.itens:
        if item.situacao != SEM_ATIVO:
            continue
        ticker = tickers.get(item.negocio.especificacao) or item.negocio.ticker
        linha = conn.execute("SELECT id FROM ativos WHERE upper(ticker)=?",
                             (ticker,)).fetchone()
        if linha is None:
            linha = (conn.execute("INSERT INTO ativos (ticker, classe) VALUES (?,?)",
                                  (ticker, classes[ticker])).lastrowid,)
        item.ativo_id = linha[0]
        conn.execute("INSERT OR REPLACE INTO apelidos (especificacao, ativo_id, criado_em)"
                     " VALUES (?,?,?)", (item.negocio.especificacao, item.ativo_id, agora))

    # AGORA, com todos os tickers resolvidos, a reconciliação enxerga o que não
    # enxergava no `conferir`: era exatamente aqui que a primeira nota de cada
    # papel duplicava o negócio que já viera da B3
    _reconciliar(conn, conf)

    instituicao_id = _instituicao(conn, nota, agora)
    criados = enriquecidos = 0
    for indice, item in enumerate(conf.itens):
        negocio = item.negocio
        if item.ativo_id is None:      # trava: negócio sem ativo corrompe o razão
            raise ValueError(f"negócio sem ativo resolvido: {negocio.especificacao}")
        for lancamento_id in item.substitui:
            original = conn.execute("SELECT * FROM lancamentos WHERE id=?",
                                    (lancamento_id,)).fetchone()
            conn.execute(
                "INSERT INTO lancamentos (data, tipo, ativo_id, instituicao_id,"
                " quantidade, preco, valor, origem, estorna_id, obs, criado_em)"
                " VALUES (?,?,?,?,?,?,?,'ESTORNO',?,?,?)",
                (original["data"], original["tipo"], original["ativo_id"],
                 original["instituicao_id"], original["quantidade"], original["preco"],
                 original["valor"], lancamento_id,
                 f"substituído pela nota {nota.numero}, que traz os custos", agora))
        if item.situacao == ENRIQUECE:
            enriquecidos += 1
        else:
            criados += 1
        conn.execute(
            "INSERT OR IGNORE INTO lancamentos (data, tipo, ativo_id, instituicao_id,"
            " quantidade, preco, valor, custos, irrf, origem, hash_origem, nota_id,"
            " criado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (nota.data_pregao, negocio.sentido, item.ativo_id, instituicao_id,
             negocio.quantidade, negocio.preco, negocio.valor, negocio.custos,
             negocio.irrf, "NOTA", _hash(nota, indice), nota_id, agora))
    return {"nota_id": nota_id, "criados": criados, "enriquecidos": enriquecidos,
            "ja_importada": False}


def _instituicao(conn, nota: Nota, agora: str) -> int | None:
    if not nota.cnpj and not nota.corretora:
        return None
    import lancamentos

    if nota.cnpj:
        linha = conn.execute("SELECT id FROM instituicoes WHERE cnpj=?",
                             (nota.cnpj,)).fetchone()
        if linha:
            return linha[0]
    # o corte em " CORRETORA" tira metade do nome societário; do resto cuida
    # `lancamentos.instituicao`, que é o MESMO ponto que o extrato da B3 usa —
    # sem isso a nota e o extrato criavam dois cadastros da mesma corretora
    nome = (nota.corretora or nota.cnpj).split(" CORRETORA")[0].strip()
    return lancamentos.instituicao(conn, nome, nota.cnpj)
