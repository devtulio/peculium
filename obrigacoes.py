"""Controle de contas a pagar dos DARF (DESIGN.md §8.1).

O princípio que molda o módulo: **o valor devido nunca é gravado**. Ele é
recalculado do razão a cada consulta, porque uma nota de corretagem importada
depois muda a apuração de um mês já fechado. O que se guarda é o **pagamento**,
que é fato consumado — e o cruzamento dos dois produz o sinal mais útil daqui:
"pagou R$ 1.500 e a apuração agora dá R$ 1.520".

O módulo apura encargos de mora, mas **não emite DARF nem transmite nada**.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import fisco
import razao

# Situações, da mais tranquila à mais urgente
ACUMULANDO = "ACUMULANDO"     # abaixo do piso de R$ 10, ainda não é DARF
PAGO = "PAGO"
PENDENTE = "PENDENTE"
PARCIAL = "PARCIAL"
A_MAIOR = "A_MAIOR"
VENCIDO = "VENCIDO"

# Lei 9.430/96 art. 61: multa de mora de 0,33% por dia de atraso, limitada a 20%.
MULTA_DIA = 0.0033
MULTA_TETO = 0.20


@dataclass
class Obrigacao:
    competencia: str
    codigo: str
    vencimento: str                  # vazio enquanto está acumulando
    valor_apurado: float
    valor_pago: float = 0.0
    data_pagamento: str = ""
    situacao: str = PENDENTE
    dias_atraso: int = 0
    multa: float = 0.0
    juros: float | None = None       # None = depende da Selic, que não temos
    composicao: dict[str, float] = field(default_factory=dict)
    observacoes: list[str] = field(default_factory=list)

    @property
    def total_a_pagar(self) -> float:
        """Só faz sentido no que ainda não foi quitado."""
        if self.situacao in (PAGO, A_MAIOR, ACUMULANDO):
            return 0.0
        return round(max(0.0, self.valor_apurado - self.valor_pago)
                     + self.multa + (self.juros or 0.0), 2)


def encargos(valor: float, vencimento: str, pagamento: str,
             selic_acumulada: float | None = None) -> tuple[int, float, float | None]:
    """Devolve (dias de atraso, multa, juros).

    A multa é determinística e está na lei. **Os juros não**: dependem da Selic
    acumulada do período, que só existe no banco depois que a série do BCB for
    importada (v1.1). Até lá o campo vem `None` e a tela mostra um traço —
    inventar juros dentro de conta de imposto é exatamente o que este programa
    não faz."""
    atraso = (date.fromisoformat(pagamento) - date.fromisoformat(vencimento)).days
    if atraso <= 0:
        return 0, 0.0, 0.0
    multa = round(valor * min(MULTA_DIA * atraso, MULTA_TETO), 2)
    juros = None if selic_acumulada is None else round(valor * selic_acumulada, 2)
    return atraso, multa, juros


def _pagos(conn) -> dict[tuple[str, str], dict]:
    """Pagamentos somados por competência e código — parcelamento é permitido."""
    resumo: dict[tuple[str, str], dict] = {}
    for linha in conn.execute(
            "SELECT competencia, codigo, sum(valor) AS valor, sum(multa) AS multa,"
            " sum(juros) AS juros, max(data) AS data, count(*) AS n"
            " FROM pagamentos GROUP BY competencia, codigo"):
        resumo[(linha["competencia"], linha["codigo"])] = dict(linha)
    return resumo


def listar(conn, hoje: str | None = None) -> list[Obrigacao]:
    hoje = hoje or date.today().isoformat()
    f = fisco.apurar(razao.apurar(conn))
    pagos = _pagos(conn)
    obrigacoes: list[Obrigacao] = []

    for darf in f.darfs:
        chave = (darf.competencia, darf.codigo)
        pago = pagos.pop(chave, None)
        o = Obrigacao(darf.competencia, darf.codigo, darf.vencimento, darf.valor,
                      composicao=dict(darf.composicao))
        if darf.de_meses_anteriores:
            o.observacoes.append(
                f"inclui R$ {darf.de_meses_anteriores:.2f} de meses anteriores que "
                f"ficaram abaixo do piso")

        if pago is None:
            if hoje > darf.vencimento:
                o.situacao = VENCIDO
                o.dias_atraso, o.multa, o.juros = encargos(
                    darf.valor, darf.vencimento, hoje)
                o.observacoes.append(
                    "multa de mora de 0,33% ao dia (teto de 20%) calculada até hoje; "
                    "juros dependem da série Selic, ainda não importada")
            else:
                o.situacao = PENDENTE
        else:
            o.valor_pago = pago["valor"]
            o.data_pagamento = pago["data"]
            o.multa, o.juros = pago["multa"], pago["juros"]
            diferenca = round(o.valor_pago - darf.valor, 2)
            if abs(diferenca) < 0.01:
                o.situacao = PAGO
            elif diferenca < 0:
                o.situacao = PARCIAL
                o.observacoes.append(
                    f"faltam R$ {-diferenca:.2f} — ou o pagamento foi a menor, ou a "
                    f"apuração subiu depois de pago (lançamento retroativo)")
            else:
                o.situacao = A_MAIOR
                o.observacoes.append(
                    f"pagos R$ {diferenca:.2f} a mais — ou o pagamento foi a maior, "
                    f"ou a apuração caiu depois de pago (lançamento retroativo)")
            if pago["n"] > 1:
                o.observacoes.append(f"{pago['n']} pagamentos somados")
        obrigacoes.append(o)

    # Pagamento sem DARF correspondente: quase sempre é a apuração que mudou e
    # zerou o mês. Some da lista se não for mostrado — então é mostrado.
    for (competencia, codigo), pago in sorted(pagos.items()):
        o = Obrigacao(competencia, codigo, "", 0.0, pago["valor"], pago["data"],
                      A_MAIOR, multa=pago["multa"], juros=pago["juros"])
        o.observacoes.append(
            "há pagamento registrado, mas a apuração deste mês não gera DARF — "
            "confira se um lançamento retroativo mudou o cálculo")
        obrigacoes.append(o)

    if f.acumulado_pendente:
        ultima = max((d.competencia for d in f.darfs), default="")
        o = Obrigacao(max(ultima, ""), fisco.CODIGO_DARF, "", f.acumulado_pendente,
                      situacao=ACUMULANDO)
        o.observacoes.append(
            f"abaixo do piso de R$ {fisco.PISO_DARF:.2f}: acumula para o mês em que "
            f"houver novo imposto — não vence e não some")
        obrigacoes.append(o)

    return sorted(obrigacoes, key=lambda x: (x.vencimento or "9999", x.competencia))


def a_vencer(conn, dias: int = 15, hoje: str | None = None) -> list[Obrigacao]:
    """Para o alerta do painel: o que vence dentro da janela, mais o vencido."""
    hoje = hoje or date.today().isoformat()
    limite = date.fromisoformat(hoje).toordinal() + dias
    return [o for o in listar(conn, hoje)
            if o.situacao == VENCIDO
            or (o.situacao in (PENDENTE, PARCIAL) and o.vencimento
                and date.fromisoformat(o.vencimento).toordinal() <= limite)]


def registrar(conn, competencia: str, valor: float, data: str,
              codigo: str = fisco.CODIGO_DARF, multa: float = 0.0,
              juros: float = 0.0, obs: str = "") -> int:
    """Registra um pagamento. Vários por competência são permitidos — quem paga
    em atraso às vezes paga o principal e os encargos em guias separadas."""
    if valor <= 0:
        raise ValueError("pagamento precisa de valor positivo")
    date.fromisoformat(data)          # valida cedo, não na leitura
    return conn.execute(
        "INSERT INTO pagamentos (competencia, codigo, valor, multa, juros, data,"
        " obs, criado_em) VALUES (?,?,?,?,?,?,?,?)",
        (competencia, codigo, valor, multa, juros, data, obs or None,
         datetime.now(timezone.utc).isoformat(timespec="seconds"))).lastrowid


def cancelar(conn, pagamento_id: int) -> bool:
    cur = conn.execute("DELETE FROM pagamentos WHERE id=?", (pagamento_id,))
    return cur.rowcount > 0
