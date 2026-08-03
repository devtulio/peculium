"""Notas de renda fixa em PDF, um adaptador por corretora (DESIGN.md §6.3).

Ao contrário das notas de renda variável — que praticamente toda corretora gera
pelo Sinacor, com o mesmo layout —, **cada corretora inventa a sua** para renda
fixa. XP e Inter não têm uma linha em comum. Por isso aqui não existe "o parser":
existem adaptadores, escolhidos pelo conteúdo do arquivo.

Nota de renda fixa **não tem custos operacionais** — só IOF e IR, quando há. O
que ela traz de valioso são os dados do papel: emissor, indexador, taxa,
emissão, vencimento e o preço unitário, que é justamente o que o cadastro manual
pedia e o que erra a posição em ordem de grandeza quando vai errado.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import importar_nota
import renda_fixa
import textos

APLICACAO = "APLICACAO"
RESGATE = "RESGATE"

CRIA = "CRIA"
JA_IMPORTADA = "JA_IMPORTADA"

_DATA = r"\d{2}/\d{2}/\d{4}"


class NotaRFInconsistente(Exception):
    """A nota não fecha aritmeticamente — não se grava o que não confere."""


class LayoutDesconhecido(Exception):
    pass


@dataclass
class NotaRF:
    corretora: str
    numero: str
    tipo: str                    # APLICACAO | RESGATE
    data: str
    codigo: str                  # o código do papel: CDB5267UW6V
    nome: str
    emissor: str
    indexador: str               # CDI | PRE | IPCA
    taxa: float
    emissao: str
    vencimento: str | None
    quantidade: float
    pu: float
    valor_bruto: float
    ir: float = 0.0
    iof: float = 0.0
    valor_liquido: float = 0.0
    carencia: str | None = None
    avisos: list[str] = field(default_factory=list)

    @property
    def ticker(self) -> str:
        """O código do papel, quando serve de identificador — senão, um derivado.

        A Inter às vezes põe um código de verdade (`CDB626BO9OA`) e às vezes um
        número solto: uma nota real trazia `CDB CREDITO -  3`. Usar `3` como
        ticker faria qualquer outro papel também codificado `3` **fundir-se com
        este**, virando uma posição só, em silêncio. Quando o código não
        identifica, o ticker é derivado do nome e do vencimento, que juntos
        distinguem o papel."""
        # o campo chega a trazer byte de controle: numa nota real veio "\x003"
        limpo = re.sub(r"[^A-Za-z0-9]", "", self.codigo).upper()
        if re.fullmatch(r"[A-Z]{2,}[A-Z0-9]{4,}", limpo):
            return limpo
        base = re.sub(r"[^A-Z0-9]+", "-", self.nome.upper()).strip("-")[:18]
        return f"{base}-{self.vencimento or self.emissao}"

    @property
    def codigo_ambiguo(self) -> bool:
        return self.ticker != self.codigo.upper()

    @property
    def pu_de_emissao(self) -> float | None:
        """Só se sabe o PU de emissão quando a aplicação é na própria emissão.

        Comprar um papel já emitido paga o PU corrigido, e o de emissão teria de
        vir de outra fonte — informar 1,00 no lugar erraria a posição em ordem de
        grandeza, que é exatamente o que o cadastro se recusa a aceitar."""
        return self.pu if self.data == self.emissao else None


# --------------------------------------------------------------------- comuns

def _num(texto) -> float:
    return textos.numero(texto)


def _indexador(bruto: str) -> str:
    t = (bruto or "").strip().upper()
    if "IPCA" in t:
        return "IPCA"
    if "CDI" in t or "DI" == t or "PÓS" in t or "POS" in t:
        return "CDI"
    if "PRE" in t or "PRÉ" in t:
        return "PRE"
    return t


def _conferir(nota: NotaRF) -> None:
    """Dois invariantes, na mesma disciplina da nota de renda variável.

    Recusa em vez de gravar número que não fecha: aqui o estrago seria um título
    com preço unitário errado, que multiplica a posição inteira."""
    esperado = nota.quantidade * nota.pu
    if abs(esperado - nota.valor_bruto) > max(0.01, nota.valor_bruto * 1e-6):
        raise NotaRFInconsistente(
            f"quantidade {nota.quantidade:g} × PU {nota.pu:g} = {esperado:.2f}, "
            f"mas a nota diz bruto de {nota.valor_bruto:.2f}")
    liquido = nota.valor_bruto - nota.ir - nota.iof
    if nota.valor_liquido and abs(liquido - nota.valor_liquido) > 0.01:
        raise NotaRFInconsistente(
            f"bruto {nota.valor_bruto:.2f} − IR {nota.ir:.2f} − IOF "
            f"{nota.iof:.2f} = {liquido:.2f}, mas a nota diz líquido de "
            f"{nota.valor_liquido:.2f}")


# --------------------------------------------------------------------- XP

def _xp(texto: str) -> list[NotaRF]:
    # O bloco "COMPROMISSADA COM LIQUIDEZ DIÁRIA" repete TODOS os rótulos com
    # valores "-". Cortar o texto antes dele é o que impede a leitura errada.
    corte = texto.find("COMPROMISSADA")
    util = texto[:corte] if corte > 0 else texto

    def achar(padrao, alvo=None):
        m = re.search(padrao, alvo or util, re.I)
        return m.group(1).strip() if m else None

    numero = achar(r"N[úu]mero\s*(\d+)")
    if not numero:
        raise LayoutDesconhecido("nota da XP sem número")
    operacao = achar(rf"Opera[çc][ãa]o\s*({_DATA})")
    linha = re.search(
        r"Quantidade\s*([\d.,]+)\s*Pre[çc]o Unit[áa]rio\s*([\d.,]+)\s*"
        r"Valor Bruto\s*([\d.,]+)\s*IOF\s*([\d.,]+)\s*IR\s*([\d.,]+)\s*"
        r"Valor l[íi]quido\s*([\d.,]+)", util, re.I)
    if linha is None:
        raise LayoutDesconhecido("nota da XP sem a linha de quantidade e preço")

    titulo = achar(r"T[íi]tulo\s*(.+?)\s*Cust[óo]dia") or ""
    codigo = ""
    for parte in reversed(titulo.split()):
        if re.fullmatch(r"[A-Z0-9]{8,}", parte):
            codigo = parte
            break
    taxa_bruta = achar(r"Taxa do Neg[óo]cio\s*(.+)") or ""
    percentual = re.search(r"([\d.,]+)\s*%", taxa_bruta)

    nota = NotaRF(
        corretora="XP INVESTIMENTOS",
        numero=numero,
        tipo=RESGATE if re.search(r"Tipo\s*(RESGATE|VENDA)", util, re.I) else APLICACAO,
        data=textos.data_iso(operacao),
        codigo=codigo,
        nome=achar(r"Ativo\s*(.+?)\s*Vencimento") or "",
        emissor=achar(r"Emissor\s*(.+?)\s{2,}") or achar(r"Emissor\s*(.+?)\s*Indexador") or "",
        indexador=_indexador(achar(r"Indexador\s*(\w+)") or taxa_bruta),
        taxa=_num(percentual.group(1)) if percentual else 0.0,
        emissao=textos.data_iso(achar(rf"Emiss[ãa]o\s*({_DATA})") or operacao),
        vencimento=textos.data_iso(achar(rf"Vencimento\s*({_DATA})")) if
        achar(rf"Vencimento\s*({_DATA})") else None,
        carencia=textos.data_iso(achar(rf"Car[êe]ncia\s*({_DATA})")) if
        achar(rf"Car[êe]ncia\s*({_DATA})") else None,
        quantidade=_num(linha.group(1)), pu=_num(linha.group(2)),
        valor_bruto=_num(linha.group(3)), iof=_num(linha.group(4)),
        ir=_num(linha.group(5)), valor_liquido=_num(linha.group(6)))
    _conferir(nota)
    return [nota]


# --------------------------------------------------------------------- Inter

def _inter(texto: str) -> list[NotaRF]:
    blocos = re.split(r"Nota de Negocia[çc][ãa]o:\s*", texto)[1:]
    if not blocos:
        raise LayoutDesconhecido("nenhuma nota da Inter no arquivo")

    notas = []
    for bloco in blocos:
        numero = re.match(r"(\d+)", bloco.strip())
        if numero is None:
            continue
        # o arquivo é um extrato do período e pode trazer mais de uma nota
        fim = re.search(r"Caracter[íi]sticas do Compromisso", bloco)
        util = bloco[:fim.start()] if fim else bloco

        # o "código" é o que estiver entre o traço e as duas datas: pode ser
        # `CDB626BO9OA` ou simplesmente `3` — ver NotaRF.ticker
        ativo = re.search(
            rf"(.+?)\s*-\s*(\S+)\s+({_DATA})\s+({_DATA})\s+(\S+)\s+([\d.,]+)", util)
        if ativo is None:
            raise LayoutDesconhecido(
                f"nota {numero.group(1)} da Inter sem a linha do título")

        # "450 R$ 0,01 CC": são TRÊS valores para QUATRO colunas — a taxa
        # negociada vem vazia. Ler por posição erraria; lê-se por formato.
        operacao = re.search(r"Forma de Liquida[çc][ãa]o\s*\n\s*([\d.,]+)\s+"
                             r"R\$\s*([\d.,]+)", util)
        valores = re.search(
            r"Valor L[íi]quido\s*\n\s*R\$\s*([\d.,]+)\s+R\$\s*([\d.,]+)\s+"
            r"R\$\s*([\d.,]+)\s+R\$\s*([\d.,]+)", util)
        if operacao is None or valores is None:
            raise LayoutDesconhecido(
                f"nota {numero.group(1)} da Inter sem a linha de valores")

        data = re.search(rf"Data da Opera[çc][ãa]o\s*({_DATA})", util)
        nota = NotaRF(
            corretora="BANCO INTER",
            numero=numero.group(1),
            tipo=RESGATE if re.search(r"Tipo de Opera[çc][ãa]o:\s*Resgate", util, re.I)
            else APLICACAO,
            data=textos.data_iso(data.group(1)),
            codigo=ativo.group(2), nome=ativo.group(1).strip(),
            emissor=(re.search(r"Emissor:\s*(.+)", util) or [None, ""])[1].strip()
            if re.search(r"Emissor:\s*(.+)", util) else "",
            indexador=_indexador(ativo.group(5)), taxa=_num(ativo.group(6)),
            emissao=textos.data_iso(ativo.group(3)),
            vencimento=textos.data_iso(ativo.group(4)),
            quantidade=_num(operacao.group(1)), pu=_num(operacao.group(2)),
            valor_bruto=_num(valores.group(1)), ir=_num(valores.group(2)),
            iof=_num(valores.group(3)), valor_liquido=_num(valores.group(4)))
        _conferir(nota)
        notas.append(nota)
    return notas


ADAPTADORES = (
    ("XP INVESTIMENTOS", re.compile(r"Nota de negocia[çc][ãa]o de t[íi]tulos", re.I), _xp),
    ("BANCO INTER", re.compile(r"Notas de renda fixa|BANCO INTER", re.I), _inter),
)


def e_renda_fixa(texto: str) -> bool:
    """Diz se o PDF é nota de renda fixa, para escolher o leitor certo."""
    return any(marca.search(texto) for _, marca, _ in ADAPTADORES)


def parsear(texto: str) -> list[NotaRF]:
    for _, marca, adaptador in ADAPTADORES:
        if marca.search(texto):
            return adaptador(texto)
    raise LayoutDesconhecido(
        "nenhum adaptador reconheceu o arquivo. Notas de renda fixa não têm "
        "layout comum: cada corretora precisa do seu leitor")


def ler(caminho: str | Path, cpf: str | None = None,
        senhas: tuple[str, ...] = ()) -> list[NotaRF]:
    return parsear(importar_nota.ler_texto(caminho, cpf, senhas))


# --------------------------------------------------------------------- gravação

@dataclass
class Item:
    nota: NotaRF
    situacao: str
    ativo_id: int | None = None
    motivo: str = ""


@dataclass
class Conferencia:
    itens: list[Item] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def por_situacao(self, situacao: str) -> list[Item]:
        return [i for i in self.itens if i.situacao == situacao]


def _hash(nota: NotaRF) -> str:
    crua = f"NOTARF|{nota.corretora}|{nota.numero}|{nota.data}|{nota.ticker}"
    return hashlib.sha256(crua.encode()).hexdigest()


def conferir(conn, notas: list[NotaRF]) -> Conferencia:
    conf = Conferencia()
    ja = {r[0] for r in conn.execute(
        "SELECT hash_origem FROM lancamentos WHERE hash_origem IS NOT NULL")}
    ativos = {str(r[0]).upper(): r[1] for r in conn.execute("SELECT ticker, id FROM ativos")}

    for nota in notas:
        ativo_id = ativos.get(nota.ticker)
        if _hash(nota) in ja:
            conf.itens.append(Item(nota, JA_IMPORTADA, ativo_id, "já importada"))
            continue
        conf.itens.append(Item(
            nota, CRIA, ativo_id,
            "título já cadastrado: entra só a aplicação" if ativo_id else
            "título novo: entra o cadastro e a aplicação"))
        conf.avisos += nota.avisos
        if nota.pu_de_emissao is None:
            conf.avisos.append(
                f"{nota.ticker}: a operação é de {textos.data_br(nota.data)} e o "
                f"papel foi emitido em {textos.data_br(nota.emissao)}. O preço "
                f"unitário de emissão não vem na nota — confirme-o depois, no "
                f"cadastro do título, senão a posição sai errada.")
        if nota.indexador == "IPCA":
            conf.avisos.append(
                f"{nota.ticker}: IPCA+ não tem curva calculável — o preço "
                f"unitário terá de ser informado à mão na Carteira.")
    return conf


def gravar(conn, conf: Conferencia, classe: str = "RF") -> dict:
    import lancamentos

    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    criados = titulos = 0
    for item in conf.por_situacao(CRIA):
        nota = item.nota
        ativo_id = item.ativo_id
        if ativo_id is None:
            classe_alvo = "TESOURO" if "TESOURO" in nota.nome.upper() else classe
            ativo_id = conn.execute(
                "INSERT INTO ativos (ticker, nome, classe) VALUES (?,?,?)",
                (nota.ticker, nota.nome or None, classe_alvo)).lastrowid

        instituicao = conn.execute("SELECT id FROM instituicoes WHERE upper(nome)=?",
                                   (nota.corretora.upper(),)).fetchone()
        if instituicao is None:
            instituicao = (conn.execute("INSERT INTO instituicoes (nome) VALUES (?)",
                                        (nota.corretora,)).lastrowid,)

        conn.execute(
            "INSERT OR IGNORE INTO lancamentos (data, tipo, ativo_id, instituicao_id,"
            " quantidade, preco, valor, irrf, origem, hash_origem, obs, criado_em)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (nota.data, "COMPRA" if nota.tipo == APLICACAO else "VENDA", ativo_id,
             instituicao[0], nota.quantidade, nota.pu, nota.valor_bruto, nota.ir,
             f"NOTA_RF_{nota.corretora.split()[0]}", _hash(nota),
             f"nota {nota.numero}", agora))
        criados += 1

        # o cadastro do papel só entra na aplicação: no resgate os dados do
        # título já existem, e sobrescrever com o PU do dia seria o erro
        if nota.tipo == APLICACAO and renda_fixa.titulo(conn, ativo_id) is None:
            renda_fixa.cadastrar(
                conn, ativo_id=ativo_id, emissao=nota.emissao,
                indexador=nota.indexador, taxa=nota.taxa,
                pu_base=nota.pu_de_emissao or 1.0, vencimento=nota.vencimento,
                emissor=nota.emissor, obs=f"da nota {nota.numero}")
            titulos += 1
        lancamentos.auditar(conn, "NOTA_RF",
                            f"{nota.corretora} {nota.numero} {nota.ticker}")
    return {"lancamentos": criados, "titulos": titulos,
            "ja_importadas": len(conf.por_situacao(JA_IMPORTADA))}
