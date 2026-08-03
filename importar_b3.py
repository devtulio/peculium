"""Importação dos relatórios da Área do Investidor da B3 (DESIGN.md §6).

Dois relatórios, formatos diferentes:

* **Negociação** — compras e vendas.
* **Movimentação** — proventos, eventos e transferências.

`ler()` não grava nada: devolve a conferência para a tela. `gravar()` grava o que
foi conferido. O arquivo original nunca é guardado — traz CPF.

Duas armadilhas do formato que moldam o módulo:

1. **"Transferência - Liquidação" na Movimentação é a entrega dos negócios que já
   vêm na Negociação.** Importar os dois arquivos sem descartar essas linhas
   duplica a carteira inteira.
2. **O relatório de Negociação não traz corretagem nem emolumentos.** Todo preço
   médio importado nasce sem custos, e a conferência precisa dizer isso.
"""
from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import textos

NEGOCIACAO = "NEGOCIACAO"
MOVIMENTACAO = "MOVIMENTACAO"

NOVA = "NOVA"
DUPLICADA = "DUPLICADA"
IGNORADA = "IGNORADA"
PENDENTE = "PENDENTE"
ERRO = "ERRO"

# Movimentação → tipo de lançamento do razão
TIPOS = {
    "dividendo": "DIVIDENDO",
    "juros sobre capital proprio": "JCP",
    "rendimento": "RENDIMENTO",
    "amortizacao": "AMORTIZACAO",
    "bonificacao em ativos": "BONIFICACAO",
    "fracao em ativos": "BONIFICACAO",
    "leilao de fracao": "VENDA",
}

# Renda fixa na Movimentação: o sentido vem de Entrada/Saída, não do rótulo.
# "COMPRA / VENDA" é literalmente o texto que a B3 usa para aplicação em CDB.
RF_MOVIMENTOS = ("aplicacao", "compra / venda", "resgate antecipado",
                 "resgate", "vencimento", "resgate total", "resgate parcial")

# A subscrição inteira fica pendente de lançamento manual. Ela anda em ativos
# intermediários — direito (…11 vira …12), recibo (…13) — e as linhas nomeiam o
# papel intermediário, não o que se recebe: "Direitos de Subscrição - Exercido"
# aparece sobre o MXRF12, mas quem entra na carteira é o MXRF11. Registrar como
# está enche a posição de fantasma (aconteceu numa importação real) e registra
# o custo no ativo errado. O usuário lança a subscrição quando ela se converter.
SUBSCRICAO = "subscricao"

# Descartadas de propósito, com motivo — nunca em silêncio
IGNORAR = {
    "transferencia - liquidacao":
        "entrega dos negócios que já vêm no relatório de Negociação",
    "compra": "já vem no relatório de Negociação",
    "venda": "já vem no relatório de Negociação",
    "desdobramento": "evento corporativo: lance em Eventos, com o fator",
    "grupamento": "evento corporativo: lance em Eventos, com o fator",
    "atualizacao": "sem efeito em posição ou caixa",
    "cessao de direitos": "lance à mão se houve alienação",
    "cessao de direitos - solicitada": "lance à mão se houve alienação",
    "direitos de subscricao - nao exercido": "sem efeito em posição",
    "emprestimo": "aluguel de ativos está fora do escopo da v1",
}

SUFIXO_BDR = ("31", "32", "33", "34", "35", "39")
SUFIXO_ACAO = ("3", "4", "5", "6", "7", "8")


class ArquivoNaoReconhecido(Exception):
    pass


@dataclass
class Linha:
    n: int                      # número da linha no arquivo, para a conferência
    situacao: str
    tipo: str = ""
    data: str = ""
    ticker: str = ""
    instituicao: str = ""
    quantidade: float = 0.0
    preco: float = 0.0
    valor: float = 0.0
    hash: str = ""
    motivo: str = ""
    nome_ativo: str = ""


@dataclass
class Conferencia:
    arquivo: str
    relatorio: str
    linhas: list[Linha] = field(default_factory=list)
    ativos_novos: dict[str, dict] = field(default_factory=dict)
    instituicoes_novas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def por_situacao(self, situacao: str) -> list[Linha]:
        return [l for l in self.linhas if l.situacao == situacao]

    @property
    def novas(self) -> int:
        return len(self.por_situacao(NOVA))

    @property
    def duplicadas(self) -> int:
        return len(self.por_situacao(DUPLICADA))

    @property
    def erros(self) -> int:
        return len(self.por_situacao(ERRO))


# --------------------------------------------------------------------- leitura crua

def _chave(texto: str) -> str:
    """Nome de coluna sem acento, caixa nem espaço duplo.

    O cabeçalho da B3 muda sem aviso; casar por nome normalizado sobrevive a
    acento e maiúscula, e falha alto quando a coluna some de verdade."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto)
                         if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


_numero = textos.numero
_data = textos.data_iso


def _linhas_csv(caminho: Path) -> list[list]:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            texto = caminho.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    try:
        dialeto = csv.Sniffer().sniff(texto[:4096], delimiters=";,\t")
    except csv.Error:
        dialeto = csv.excel                      # arquivo de uma coluna só
        dialeto.delimiter = ";"
    return [linha for linha in csv.reader(texto.splitlines(), dialeto) if any(linha)]


def _linhas_xlsx(caminho: Path) -> list[list]:
    from openpyxl import load_workbook

    wb = load_workbook(caminho, read_only=True, data_only=True)
    try:
        planilha = wb[wb.sheetnames[0]]
        # A planilha da B3 declara `<dimension ref="A1:A1"/>`, o que é mentira: o
        # modo read_only acredita e devolve só a coluna A, então o cabeçalho
        # chegava com um campo só e o arquivo era recusado como "não é da B3".
        planilha.reset_dimensions()
        return [list(linha) for linha in planilha.iter_rows(values_only=True)
                if any(c is not None and str(c).strip() for c in linha)]
    finally:
        wb.close()


def _tabela(caminho: Path) -> tuple[list[dict], str]:
    """Acha o cabeçalho e devolve dicionários com as colunas normalizadas.

    O cabeçalho nem sempre é a primeira linha: a B3 às vezes põe título antes."""
    cru = _linhas_xlsx(caminho) if caminho.suffix.lower() in (".xlsx", ".xlsm") \
        else _linhas_csv(caminho)
    for i, linha in enumerate(cru[:15]):
        colunas = [_chave(str(c or "")) for c in linha]
        if "instituicao" in colunas and any("data" in c for c in colunas):
            corpo = cru[i + 1:]
            # a convenção decimal é decidida uma vez, pelo arquivo inteiro: a
            # planilha da B3 escreve em formato americano e o CSV em brasileiro
            formato = textos.formato_numerico(c for l in corpo for c in l)
            return [dict(zip(colunas, valores)) for valores in corpo], formato
    raise ArquivoNaoReconhecido(
        f"{caminho.name}: nenhum cabeçalho com 'Instituição' e 'Data' nas 15 "
        f"primeiras linhas — o arquivo é da Área do Investidor da B3?")


def _exigir(tabela: list[dict], colunas: tuple[str, ...], relatorio: str) -> None:
    faltando = [c for c in colunas if c not in tabela[0]]
    if faltando:
        raise ArquivoNaoReconhecido(
            f"relatório de {relatorio} sem a(s) coluna(s): {', '.join(faltando)}")


# --------------------------------------------------------------------- normalização

def classe_provavel(ticker: str) -> tuple[str, bool]:
    """Devolve (classe sugerida, precisa confirmar).

    O sufixo 11 é ambíguo — FII, ETF e unit dividem o mesmo número — e a diferença
    muda a alíquota do IR. Nunca decidir sozinho nesse caso."""
    if _CODIGO_RF.fullmatch(ticker.upper()) and not re.search(r"\d+$", ticker):
        return "RF", False          # código de papel de renda fixa: CDB726AWP4H
    sufixo = re.search(r"(\d+)$", ticker)
    if not sufixo:
        return "", True
    digitos = sufixo.group(1)
    if digitos in SUFIXO_BDR:
        return "BDR", False
    if digitos == "11":
        return "FII", True
    if digitos in SUFIXO_ACAO:
        return "ACAO", False
    return "", True


_CODIGO_RF = re.compile(r"\b([A-Z]{2,}\d[A-Z0-9]{4,})\b")


def _ticker_rf(produto: str) -> tuple[str, str]:
    """`CDB - CDB726AWP4H - BANCO X` -> (`CDB726AWP4H`, `CDB … BANCO X`).

    O separador é o mesmo da renda variável, mas aqui o **primeiro** pedaço é só
    o tipo do papel: partir igual faria todo CDB virar o ticker `CDB`, fundindo
    títulos diferentes numa posição só."""
    achado = _CODIGO_RF.search(str(produto).upper())
    nome = re.sub(r"\s+", " ", str(produto)).strip()
    return (achado.group(1) if achado else ""), nome


def _ticker(produto: str, mercado: str = "") -> tuple[str, str]:
    """'PETR4 - PETROLEO BRASILEIRO SA' -> ('PETR4', 'PETROLEO BRASILEIRO SA').

    No mercado fracionário o código vem com F no fim (PETR4F): é o mesmo ativo,
    e tratá-lo como outro quebraria o preço médio."""
    partes = re.split(r"\s+-\s+", str(produto).strip(), maxsplit=1)
    codigo = partes[0].strip().upper()
    nome = partes[1].strip() if len(partes) > 1 else ""
    if codigo.endswith("F") and re.search(r"\d", codigo) and \
            ("fracion" in _chave(mercado) or re.match(r"^[A-Z]{4}\d+F$", codigo)):
        codigo = codigo[:-1]
    return codigo, nome


def _hash(relatorio: str, campos: tuple, ocorrencia: int) -> str:
    """Hash canônico da linha, com o número da ocorrência dentro do arquivo.

    Sem a ocorrência, dois negócios idênticos no mesmo dia (mesma quantidade,
    mesmo preço) viram um só. Com ela, reimportar o mesmo arquivo continua
    idempotente e o negócio repetido de verdade entra duas vezes."""
    crua = "|".join([relatorio, *(f"{c}" for c in campos), str(ocorrencia)])
    return hashlib.sha256(crua.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------- leitura

def _ler_negociacao(tabela: list[dict], conf: Conferencia, formato: str) -> None:
    _exigir(tabela, ("data do negocio", "tipo de movimentacao", "instituicao",
                     "codigo de negociacao", "quantidade", "preco"), "Negociação")
    conf.avisos.append(
        "O relatório de Negociação da B3 não traz corretagem nem emolumentos: "
        "os preços médios entram sem custos. Lance os custos à parte.")
    vistos: dict[str, int] = {}
    for i, linha in enumerate(tabela, start=2):
        movimento = _chave(str(linha.get("tipo de movimentacao") or ""))
        if movimento not in ("compra", "venda"):
            conf.linhas.append(Linha(i, IGNORADA,
                                     motivo=f"movimentação '{movimento}' fora de escopo"))
            continue
        try:
            data = _data(linha["data do negocio"])
            ticker, nome = _ticker(linha["codigo de negociacao"],
                                   str(linha.get("mercado") or ""))
            qtd = _numero(linha["quantidade"], formato)
            preco = _numero(linha["preco"], formato)
        except (ValueError, KeyError) as e:
            conf.linhas.append(Linha(i, ERRO, motivo=str(e)))
            continue
        valor = _numero(linha.get("valor"), formato) or qtd * preco
        instituicao = str(linha["instituicao"] or "").strip()
        campos = (movimento, data, ticker, instituicao, f"{qtd:.8f}", f"{valor:.2f}")
        chave = "|".join(campos)
        vistos[chave] = vistos.get(chave, -1) + 1
        conf.linhas.append(Linha(
            i, NOVA, movimento.upper(), data, ticker, instituicao, qtd, preco, valor,
            _hash(NEGOCIACAO, campos, vistos[chave]), nome_ativo=nome))


def _ler_movimentacao(tabela: list[dict], conf: Conferencia, formato: str) -> None:
    _exigir(tabela, ("entrada/saida", "data", "movimentacao", "produto",
                     "instituicao", "quantidade"), "Movimentação")
    vistos: dict[str, int] = {}
    for i, linha in enumerate(tabela, start=2):
        movimento = _chave(str(linha.get("movimentacao") or ""))
        if movimento in IGNORAR:
            conf.linhas.append(Linha(i, IGNORADA, motivo=IGNORAR[movimento]))
            continue
        if movimento.startswith("transferencia"):
            conf.linhas.append(Linha(
                i, PENDENTE, motivo="portabilidade: o arquivo não diz a instituição "
                                    "de destino — lance à mão para preservar o custo"))
            continue
        if SUBSCRICAO in movimento:
            conf.linhas.append(Linha(
                i, PENDENTE, ticker=_ticker(linha.get("produto", ""))[0],
                data=_data(linha["data"]) if linha.get("data") else "",
                motivo="subscrição: a linha nomeia o direito ou o recibo, não o ativo "
                       "que entra na carteira — lance à mão, com o valor pago, quando "
                       "ela se converter"))
            continue

        entrada = _chave(str(linha.get("entrada/saida") or "")).startswith("cred")
        renda_fixa = any(movimento.startswith(m) for m in RF_MOVIMENTOS)
        tipo = ("COMPRA" if entrada else "VENDA") if renda_fixa else TIPOS.get(movimento)
        if tipo is None:
            conf.linhas.append(Linha(i, ERRO, motivo=f"movimentação desconhecida: "
                                                     f"{linha.get('movimentacao')!r}"))
            continue
        try:
            data = _data(linha["data"])
            ticker, nome = (_ticker_rf(linha["produto"]) if renda_fixa
                            else _ticker(linha["produto"]))
            qtd = _numero(linha["quantidade"], formato)
        except (ValueError, KeyError) as e:
            conf.linhas.append(Linha(i, ERRO, motivo=str(e)))
            continue
        if renda_fixa and not ticker:
            conf.linhas.append(Linha(
                i, ERRO, motivo=f"título de renda fixa sem código identificável em "
                                f"{linha.get('produto')!r}"))
            continue
        preco = _numero(linha.get("preco unitario"), formato)
        valor = _numero(linha.get("valor da operacao"), formato) or qtd * preco
        instituicao = str(linha["instituicao"] or "").strip()
        campos = (movimento, data, ticker, instituicao, f"{qtd:.8f}", f"{valor:.2f}")
        chave = "|".join(campos)
        vistos[chave] = vistos.get(chave, -1) + 1
        conf.linhas.append(Linha(
            i, NOVA, tipo, data, ticker, instituicao, qtd, preco, valor,
            _hash(MOVIMENTACAO, campos, vistos[chave]), nome_ativo=nome))


def ler(caminho: str | Path, conn) -> Conferencia:
    """Lê e confere. **Não grava nada** — quem grava é `gravar()`."""
    alvo = Path(caminho)
    tabela, formato = _tabela(alvo)
    if not tabela:
        raise ArquivoNaoReconhecido(f"{alvo.name}: cabeçalho sem nenhuma linha abaixo")
    relatorio = NEGOCIACAO if "codigo de negociacao" in tabela[0] else MOVIMENTACAO
    conf = Conferencia(alvo.name, relatorio)
    (_ler_negociacao if relatorio == NEGOCIACAO
     else _ler_movimentacao)(tabela, conf, formato)

    ja_no_banco = {r[0] for r in conn.execute(
        "SELECT hash_origem FROM lancamentos WHERE hash_origem IS NOT NULL")}
    conhecidos = {r[0].upper() for r in conn.execute("SELECT ticker FROM ativos")}
    instituicoes = {str(r[0]).strip().lower()
                    for r in conn.execute("SELECT nome FROM instituicoes")}
    for l in conf.linhas:
        if l.situacao != NOVA:
            continue
        if l.hash in ja_no_banco:
            l.situacao = DUPLICADA
            l.motivo = "já importada"
            continue
        if l.ticker and l.ticker not in conhecidos and l.ticker not in conf.ativos_novos:
            classe, confirmar = classe_provavel(l.ticker)
            conf.ativos_novos[l.ticker] = {"nome": l.nome_ativo, "classe": classe,
                                           "confirmar": confirmar}
        if l.instituicao and l.instituicao.lower() not in instituicoes and \
                l.instituicao not in conf.instituicoes_novas:
            conf.instituicoes_novas.append(l.instituicao)
    if any(a["confirmar"] for a in conf.ativos_novos.values()):
        conf.avisos.append(
            "Ticker terminado em 11 pode ser FII, ETF ou unit, e a classe muda a "
            "alíquota do IR — confirme antes de gravar.")
    return conf


# --------------------------------------------------------------------- gravação

def gravar(conn, conf: Conferencia, classes: dict[str, str] | None = None) -> int:
    """Grava as linhas NOVAS conferidas. Devolve quantas entraram.

    `classes` sobrescreve a classe sugerida por ticker — é por onde a tela
    devolve o que o usuário confirmou."""
    classes = {k.upper(): v for k, v in (classes or {}).items()}
    faltando = [t for t, a in conf.ativos_novos.items()
                if not (classes.get(t) or a["classe"])]
    if faltando:
        raise ValueError(f"classe não definida para: {', '.join(sorted(faltando))}")

    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO importacoes (arquivo, tipo, em, linhas, novas, duplicadas, erros)"
        " VALUES (?,?,?,?,?,?,?)",
        (conf.arquivo, conf.relatorio, agora, len(conf.linhas), conf.novas,
         conf.duplicadas, conf.erros))
    importacao_id = cur.lastrowid

    for ticker, dados in conf.ativos_novos.items():
        conn.execute("INSERT OR IGNORE INTO ativos (ticker, nome, classe) VALUES (?,?,?)",
                     (ticker, dados["nome"] or None, classes.get(ticker) or dados["classe"]))
    for nome in conf.instituicoes_novas:
        conn.execute("INSERT INTO instituicoes (nome) VALUES (?)", (nome,))

    ativos = {r[0].upper(): r[1] for r in conn.execute("SELECT ticker, id FROM ativos")}
    instituicoes = {str(r[0]).strip().lower(): r[1]
                    for r in conn.execute("SELECT nome, id FROM instituicoes")}
    origem = f"B3_{conf.relatorio}"
    gravadas = 0
    for l in conf.por_situacao(NOVA):
        cur = conn.execute(
            "INSERT OR IGNORE INTO lancamentos (data, tipo, ativo_id, instituicao_id,"
            " quantidade, preco, valor, origem, hash_origem, importacao_id, criado_em)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (l.data, l.tipo, ativos.get(l.ticker),
             instituicoes.get(l.instituicao.lower()),
             l.quantidade, l.preco, l.valor, origem, l.hash, importacao_id, agora))
        gravadas += cur.rowcount
    return gravadas
