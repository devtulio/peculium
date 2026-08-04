"""Entrada manual de lançamentos e eventos corporativos (DESIGN.md §9).

É o único caminho de escrita no razão fora dos importadores — e existe para que
a validação não fique espalhada na tela. Toda gravação daqui deixa linha em
`auditoria`.

Correção **nunca** é UPDATE: `estornar()` grava o espelho e o razão passa a
ignorar o par, que continua visível no extrato.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

import textos

NEGOCIO = ("COMPRA", "VENDA")
POSICAO = ("BONIFICACAO", "SUBSCRICAO")
PROVENTO = ("DIVIDENDO", "JCP", "RENDIMENTO", "AMORTIZACAO")
CAIXA = ("TAXA", "IRRF")
TRANSFERENCIA = "TRANSFERENCIA"
TIPOS = (*NEGOCIO, *POSICAO, *PROVENTO, *CAIXA, TRANSFERENCIA)

EVENTOS_FATOR = ("DESDOBRAMENTO", "GRUPAMENTO")
EVENTOS_TROCA = ("CONVERSAO", "INCORPORACAO")
EVENTOS = (*EVENTOS_FATOR, *EVENTOS_TROCA)


class DadoInvalido(ValueError):
    """Erro de preenchimento — mensagem vai direto para a tela."""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def auditar(conn, acao: str, detalhe: str) -> None:
    conn.execute("INSERT INTO auditoria (em, acao, detalhe) VALUES (?,?,?)",
                 (_agora(), acao, detalhe))


def _data(valor, hoje: str | None = None) -> str:
    """Aceita ISO ou dd/mm/aaaa e devolve ISO. Recusa data futura.

    Lançamento no futuro corrompe em silêncio toda pergunta sobre "a posição
    hoje" — e não existe compra que ainda não aconteceu."""
    try:
        iso = textos.data_iso(valor)
    except ValueError as e:
        raise DadoInvalido(str(e)) from e
    if iso > (hoje or date.today().isoformat()):
        raise DadoInvalido(f"data no futuro: {textos.data_br(iso)}")
    return iso


def _ativo_id(conn, ativo) -> int:
    if ativo is None:
        raise DadoInvalido("ativo é obrigatório para este tipo de lançamento")
    if isinstance(ativo, int):
        if conn.execute("SELECT 1 FROM ativos WHERE id=?", (ativo,)).fetchone():
            return ativo
        raise DadoInvalido(f"ativo {ativo} não existe")
    linha = conn.execute("SELECT id FROM ativos WHERE upper(ticker)=?",
                         (str(ativo).strip().upper(),)).fetchone()
    if linha is None:
        raise DadoInvalido(f"ativo {ativo} não cadastrado")
    return linha[0]


def _instituicao_id(conn, instituicao, obrigatoria: bool = True) -> int | None:
    if instituicao is None:
        if obrigatoria:
            raise DadoInvalido("instituição é obrigatória para este tipo")
        return None
    if isinstance(instituicao, int):
        if conn.execute("SELECT 1 FROM instituicoes WHERE id=?",
                        (instituicao,)).fetchone():
            return instituicao
        raise DadoInvalido(f"instituição {instituicao} não existe")
    achado = _por_nome(conn, instituicao)
    if achado is None:
        raise DadoInvalido(f"instituição {instituicao} não cadastrada")
    return achado


def _por_nome(conn, nome: str) -> int | None:
    """Casa pelo nome NORMALIZADO, calculado na hora sobre o que está gravado.

    Não depende da coluna `chave` estar preenchida: ela existe para o índice
    único, não para a busca. Assim uma linha que entrou por fora (migração
    parcial, SQL direto) continua sendo encontrada."""
    alvo = textos.nome_instituicao(nome)
    if not alvo:
        return None
    for linha in conn.execute("SELECT id, nome, chave FROM instituicoes"):
        if (linha["chave"] or textos.nome_instituicao(linha["nome"])) == alvo:
            return linha["id"]
    return None


def instituicao(conn, nome: str, cnpj: str | None = None) -> int:
    """Acha ou cria a instituição, casando pelo NOME NORMALIZADO.

    Ponto único de entrada para os importadores. Casar pelo texto cru fazia a
    mesma corretora virar um cadastro por grafia: num acervo real havia quatro
    da XP — `XP INVESTIMENTOS CCTVM S/A`, a mesma com ponto final,
    `XP INVESTIMENTOS` e o nome societário por extenso."""
    limpo = str(nome or "").strip()
    if not limpo:
        raise DadoInvalido("instituição sem nome")
    chave = textos.nome_instituicao(limpo)
    achado = _por_nome(conn, limpo)
    if achado is not None:
        conn.execute("UPDATE instituicoes SET chave=coalesce(chave, ?),"
                     " cnpj=coalesce(cnpj, ?) WHERE id=?", (chave, cnpj, achado))
        return achado
    return conn.execute(
        "INSERT INTO instituicoes (nome, chave, cnpj) VALUES (?,?,?)",
        (limpo, chave, cnpj)).lastrowid


def _positivo(valor: float, campo: str) -> float:
    numero = float(valor or 0)
    if numero <= 0:
        raise DadoInvalido(f"{campo} precisa ser maior que zero")
    return numero


def lancar(conn, *, data, tipo: str, ativo=None, instituicao=None,
           quantidade: float = 0, preco: float = 0, valor: float | None = None,
           custos: float = 0.0, irrf: float = 0.0, destino=None,
           obs: str = "", hoje: str | None = None) -> int:
    tipo = str(tipo).strip().upper()
    if tipo not in TIPOS:
        raise DadoInvalido(f"tipo desconhecido: {tipo}. "
                           f"Use um de: {', '.join(sorted(TIPOS))}")
    iso = _data(data, hoje)
    if float(custos or 0) < 0 or float(irrf or 0) < 0:
        raise DadoInvalido("custos e IRRF não podem ser negativos")

    ativo_id = instituicao_id = destino_id = None
    if tipo in NEGOCIO:
        ativo_id = _ativo_id(conn, ativo)
        instituicao_id = _instituicao_id(conn, instituicao)
        quantidade = _positivo(quantidade, "quantidade")
        preco = _positivo(preco, "preço")
        valor = float(valor) if valor is not None else round(quantidade * preco, 2)
    elif tipo == TRANSFERENCIA:
        ativo_id = _ativo_id(conn, ativo)
        instituicao_id = _instituicao_id(conn, instituicao)
        destino_id = _instituicao_id(conn, destino)
        if destino_id == instituicao_id:
            raise DadoInvalido("transferência precisa de instituições diferentes")
        quantidade = _positivo(quantidade, "quantidade")
        valor = float(valor or 0)
    elif tipo in POSICAO:
        ativo_id = _ativo_id(conn, ativo)
        instituicao_id = _instituicao_id(conn, instituicao, obrigatoria=False)
        quantidade = _positivo(quantidade, "quantidade")
        # bonificação a custo zero infla o ganho na venda futura; o valor
        # declarado pela companhia é o custo de entrada
        valor = float(valor or 0)
        if tipo == "SUBSCRICAO" and valor <= 0:
            raise DadoInvalido("subscrição precisa do valor pago")
    elif tipo in PROVENTO:
        ativo_id = _ativo_id(conn, ativo)
        instituicao_id = _instituicao_id(conn, instituicao, obrigatoria=False)
        valor = _positivo(valor, "valor")
    else:                                     # TAXA, IRRF
        instituicao_id = _instituicao_id(conn, instituicao, obrigatoria=False)
        valor = _positivo(valor, "valor")

    identificador = conn.execute(
        "INSERT INTO lancamentos (data, tipo, ativo_id, instituicao_id,"
        " instituicao_destino_id, quantidade, preco, valor, custos, irrf, origem,"
        " obs, criado_em) VALUES (?,?,?,?,?,?,?,?,?,?, 'MANUAL', ?, ?)",
        (iso, tipo, ativo_id, instituicao_id, destino_id, quantidade or 0,
         preco or 0, valor or 0, float(custos or 0), float(irrf or 0),
         obs or None, _agora())).lastrowid
    auditar(conn, "LANCAR", f"#{identificador} {tipo} {textos.data_br(iso)} "
                            f"valor {valor:.2f}")
    return identificador


def estornar(conn, lancamento_id: int, motivo: str = "") -> int:
    original = conn.execute("SELECT * FROM lancamentos WHERE id=?",
                            (lancamento_id,)).fetchone()
    if original is None:
        raise DadoInvalido(f"lançamento {lancamento_id} não existe")
    if original["estorna_id"] is not None:
        raise DadoInvalido("este lançamento já é um estorno")
    ja = conn.execute("SELECT id FROM lancamentos WHERE estorna_id=?",
                      (lancamento_id,)).fetchone()
    if ja:
        raise DadoInvalido(f"lançamento {lancamento_id} já foi estornado "
                           f"pelo #{ja[0]}")

    identificador = conn.execute(
        "INSERT INTO lancamentos (data, tipo, ativo_id, instituicao_id,"
        " instituicao_destino_id, quantidade, preco, valor, custos, irrf, origem,"
        " estorna_id, obs, criado_em)"
        " VALUES (?,?,?,?,?,?,?,?,?,?, 'ESTORNO', ?, ?, ?)",
        (original["data"], original["tipo"], original["ativo_id"],
         original["instituicao_id"], original["instituicao_destino_id"],
         original["quantidade"], original["preco"], original["valor"],
         original["custos"], original["irrf"], lancamento_id,
         motivo or None, _agora())).lastrowid
    auditar(conn, "ESTORNAR", f"#{identificador} estorna #{lancamento_id}"
                              f"{f': {motivo}' if motivo else ''}")
    return identificador


def anotar(conn, lancamento_id: int, obs: str) -> int:
    """Muda a observação **no lugar**, e só ela.

    Observação é anotação, não fato do razão: nada em posição, preço médio ou
    imposto depende dela. Por isso é o único campo que pode ser alterado sem
    estorno — mexer em data, quantidade ou preço é reescrever a história, e a
    história é o que o imposto usa.

    Quem precisa mudar um número usa `corrigir()`, que estorna e relança."""
    linha = conn.execute("SELECT obs FROM lancamentos WHERE id=?",
                         (lancamento_id,)).fetchone()
    if linha is None:
        raise DadoInvalido(f"lançamento {lancamento_id} não existe")
    texto = str(obs or "").strip() or None
    conn.execute("UPDATE lancamentos SET obs=? WHERE id=?", (texto, lancamento_id))
    auditar(conn, "ANOTAR", f"#{lancamento_id}: "
                            f"{linha['obs'] or '(vazio)'} -> {texto or '(vazio)'}")
    return lancamento_id


# Campos que são FATO: mudá-los é estorno e relançamento, nunca UPDATE.
CORRIGIVEIS = ("data", "tipo", "ativo", "instituicao", "destino", "quantidade",
               "preco", "valor", "custos", "irrf", "obs")


def corrigir(conn, lancamento_id: int, *, motivo: str = "", **campos) -> dict:
    """Estorna o lançamento e relança com o que mudou. Devolve os dois ids.

    É a regra append-only feita num passo só: o original continua no extrato, o
    estorno anula o efeito dele e o novo entra com os valores certos. Ninguém
    sobrescreve linha nenhuma — o que o imposto viu ontem continua lá para ser
    conferido.

    O `hash_origem` fica com o original de propósito: assim reimportar o mesmo
    arquivo continua reconhecendo a linha como já vista, em vez de criar uma
    terceira cópia."""
    original = conn.execute("SELECT * FROM lancamentos WHERE id=?",
                            (lancamento_id,)).fetchone()
    if original is None:
        raise DadoInvalido(f"lançamento {lancamento_id} não existe")
    desconhecidos = set(campos) - set(CORRIGIVEIS)
    if desconhecidos:
        raise DadoInvalido(f"campo não corrigível: {', '.join(sorted(desconhecidos))}")

    novo = {
        "data": campos.get("data", original["data"]),
        "tipo": campos.get("tipo", original["tipo"]),
        "ativo": campos.get("ativo", original["ativo_id"]),
        "instituicao": campos.get("instituicao", original["instituicao_id"]),
        "destino": campos.get("destino", original["instituicao_destino_id"]),
        "quantidade": campos.get("quantidade", original["quantidade"]),
        "preco": campos.get("preco", original["preco"]),
        # o valor antigo NÃO pode sobreviver a uma mudança de preço ou
        # quantidade: em compra e venda ele vence o cálculo, e a correção
        # gravaria o preço novo com o total velho
        "valor": _valor_corrigido(original, campos),
        "custos": campos.get("custos", original["custos"]),
        "irrf": campos.get("irrf", original["irrf"]),
        "obs": campos.get("obs", original["obs"]) or "",
    }
    estorno = estornar(conn, lancamento_id, motivo or "corrigido pelo lançamento seguinte")
    identificador = lancar(conn, **novo)
    # A nota e a importação viajam junto. Diferente do `hash_origem`, que fica
    # de propósito com o original (é ele que faz reimportar o mesmo arquivo
    # reconhecer a linha), o vínculo com a NOTA é do negócio, não do registro:
    # sem ele, corrigir o preço fazia o negócio sumir da nota e o extrato passar
    # a dizer "MANUAL" num lançamento que veio de documento.
    conn.execute("UPDATE lancamentos SET origem=?, nota_id=?, importacao_id=?"
                 " WHERE id=?",
                 (f"CORRIGE_{lancamento_id}", original["nota_id"],
                  original["importacao_id"], identificador))
    auditar(conn, "CORRIGIR",
            f"#{lancamento_id} -> #{identificador}"
            f"{f': {motivo}' if motivo else ''}")
    return {"estorno": estorno, "novo": identificador}


def _valor_corrigido(original, campos: dict):
    """Devolve `None` quando o valor tem de ser recalculado de quantidade × preço.

    Só em compra e venda: em provento o valor é o dado principal e a quantidade
    é informativa, então recalcular zeraria o lançamento."""
    if "valor" in campos:
        return campos["valor"]
    tipo = campos.get("tipo", original["tipo"])
    if tipo in NEGOCIO and ("quantidade" in campos or "preco" in campos):
        return None
    return original["valor"]


def registrar_evento(conn, *, ativo, data_ex, tipo: str, fator: float,
                     destino=None, obs: str = "", hoje: str | None = None) -> int:
    """Evento corporativo. `fator` é sempre o multiplicador da QUANTIDADE:
    desdobramento de 1:10 é 10; grupamento de 10:1 é 0,1."""
    tipo = str(tipo).strip().upper()
    if tipo not in EVENTOS:
        raise DadoInvalido(f"evento desconhecido: {tipo}. "
                           f"Use um de: {', '.join(sorted(EVENTOS))}")
    ativo_id = _ativo_id(conn, ativo)
    iso = _data(data_ex, hoje)
    fator = _positivo(fator, "fator")
    destino_id = None
    if tipo in EVENTOS_TROCA:
        if destino is None:
            raise DadoInvalido(f"{tipo} precisa do ativo de destino — é para onde "
                               f"o custo migra")
        destino_id = _ativo_id(conn, destino)
        if destino_id == ativo_id:
            raise DadoInvalido(f"{tipo} precisa de um ativo de destino diferente")

    # Evento não tem estorno e o razão aplica todos: cadastrar o mesmo
    # desdobramento duas vezes dobrava a quantidade de novo — 100 ações viravam
    # 400 num 1:2 repetido. Diferente do lançamento, aqui repetir nunca é caso
    # legítimo: a companhia não desdobra duas vezes no mesmo dia pelo mesmo fator.
    ja = conn.execute(
        "SELECT id FROM eventos WHERE ativo_id=? AND data_ex=? AND tipo=?",
        (ativo_id, iso, tipo)).fetchone()
    if ja:
        raise DadoInvalido(
            f"{tipo} de {textos.data_br(iso)} já está cadastrado (evento "
            f"#{ja[0]}). Para trocar o fator, remova o antigo primeiro")

    identificador = conn.execute(
        "INSERT INTO eventos (ativo_id, data_ex, tipo, fator, ativo_destino_id, obs)"
        " VALUES (?,?,?,?,?,?)",
        (ativo_id, iso, tipo, fator, destino_id, obs or None)).lastrowid
    auditar(conn, "EVENTO", f"#{identificador} {tipo} fator {fator:g} "
                            f"em {textos.data_br(iso)}")
    return identificador


def remover_evento(conn, evento_id: int) -> bool:
    """Evento não tem estorno: ele não é fato do usuário, é fato da companhia, e
    quem erra o fator corrige o cadastro. A remoção fica na auditoria."""
    linha = conn.execute("SELECT * FROM eventos WHERE id=?", (evento_id,)).fetchone()
    if linha is None:
        return False
    conn.execute("DELETE FROM eventos WHERE id=?", (evento_id,))
    auditar(conn, "EVENTO_REMOVIDO",
            f"#{evento_id} {linha['tipo']} fator {linha['fator']:g} "
            f"em {textos.data_br(linha['data_ex'])}")
    return True


def historico(conn, limite: int = 200) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM auditoria ORDER BY id DESC LIMIT ?",
                             (limite,)))
