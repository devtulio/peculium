"""Apuração mensal de IR sobre renda variável (DESIGN.md §8).

Consome a lista de vendas que o `razao` produz — já com natureza (swing ou day
trade) e classe do ativo — e devolve a memória de cálculo mês a mês.

Três baldes que **não se compensam entre si**:

| Balde       | Alíquota | Isenção                        | Compensa com |
|-------------|----------|--------------------------------|--------------|
| SWING       | 15%      | Vendas de ações ≤ R$ 20.000/mês | Só swing     |
| DAY_TRADE   | 20%      | Nenhuma                        | Só day trade |
| FII         | 20%      | Nenhuma                        | Só FII       |

O módulo apura e informa. **Não transmite nada à Receita e não emite DARF
oficial** — imprime o cálculo para o usuário conferir e pagar.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

import razao
from textos import competencia_br

SWING = "SWING"
DAY_TRADE = "DAY_TRADE"
FII = "FII"

ALIQUOTA = {SWING: 0.15, DAY_TRADE: 0.20, FII: 0.20}
LIMITE_ISENCAO = 20_000.0
PISO_DARF = 10.0            # Lei 9.430/96 art. 68 §1º: abaixo disso, acumula
CODIGO_DARF = "6015"        # ganhos líquidos em renda variável, pessoa física

# Só ação e unit entram no limite de isenção. ETF e BDR são negociados na mesma
# bolsa e compensam prejuízo com elas, mas não têm isenção.
ISENTAVEIS = ("ACAO", "UNIT")

# Renda fixa NÃO entra na apuração mensal: o imposto é retido na fonte pela
# tabela regressiva e é definitivo. Deixá-la cair no balde swing geraria DARF de
# 15% sobre um rendimento que já foi tributado — imposto pago duas vezes.
EXCLUSIVA = ("RF", "TESOURO", "FUNDO")

# Lei 11.033/2004 art. 1º: alíquota pelo prazo decorrido, em dias corridos.
REGRESSIVA = ((180, 0.225), (360, 0.20), (720, 0.175), (10 ** 9, 0.15))


def aliquota_regressiva(dias: int) -> float:
    return next(taxa for limite, taxa in REGRESSIVA if dias <= limite)


@dataclass
class Balde:
    competencia: str          # AAAA-MM
    balde: str
    valor_vendas: float
    resultado: float
    prejuizo_anterior: float
    compensado: float
    base: float
    aliquota: float
    imposto: float
    irrf: float               # do mês, mais o excedente que veio de trás
    a_pagar: float
    prejuizo_acumulado: float
    irrf_acumulado: float


@dataclass
class Isencao:
    """O mês em que houve venda de ações, com ou sem isenção aplicada."""
    competencia: str
    vendas_acoes: float
    aplicada: bool
    resultado_isento: float = 0.0
    prejuizo_descartado: float = 0.0


@dataclass
class Darf:
    competencia: str          # mês de apuração em que o valor fechou
    vencimento: str
    codigo: str
    valor: float
    de_meses_anteriores: float
    composicao: dict[str, float]


@dataclass
class Fisco:
    baldes: list[Balde] = field(default_factory=list)
    isencoes: list[Isencao] = field(default_factory=list)
    darfs: list[Darf] = field(default_factory=list)
    prejuizo: dict[str, float] = field(default_factory=dict)
    irrf_a_compensar: dict[str, float] = field(default_factory=dict)
    acumulado_pendente: float = 0.0        # abaixo do piso, esperando o mês seguinte
    exclusiva: list[razao.Venda] = field(default_factory=list)   # renda fixa
    avisos: list[str] = field(default_factory=list)

    def mes(self, competencia: str) -> list[Balde]:
        return [b for b in self.baldes if b.competencia == competencia]


def _brl(valor: float) -> str:
    """1234.5 -> '1.234,50'. O aviso vai para a tela do usuário, em português."""
    return f"{valor:,.2f}".translate(str.maketrans(",.", ".,"))


def balde_de(v: razao.Venda) -> str:
    """FII vai para o balde de FII mesmo em day trade: o ganho é sempre 20% e só
    compensa com FII, então separá-lo por natureza criaria compensação indevida."""
    if v.classe == FII:
        return FII
    return DAY_TRADE if v.natureza == razao.DAY_TRADE else SWING


def vencimento(competencia: str) -> str:
    """Último dia útil do mês seguinte ao da apuração.

    # ponytail: só fim de semana, sem tabela de feriados. Nenhum feriado nacional
    # do calendário atual cai no último dia útil de um mês; se algum passar a
    # cair, entra a tabela — e o teste que amarra isso é o de vencimento.
    """
    ano, mes = int(competencia[:4]), int(competencia[5:7])
    ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    dia = date(ano, mes, calendar.monthrange(ano, mes)[1])
    while dia.weekday() >= 5:
        dia -= timedelta(days=1)
    return dia.isoformat()


def _isencao(f: Fisco, competencia: str, swing: list[razao.Venda]) -> list[razao.Venda]:
    """Aplica (ou não) a isenção dos R$ 20 mil e devolve o que resta tributável."""
    acoes = [v for v in swing if v.classe in ISENTAVEIS]
    if not acoes:
        return swing
    vendas_acoes = sum(v.valor_bruto for v in acoes)
    if vendas_acoes > LIMITE_ISENCAO:
        f.isencoes.append(Isencao(competencia, vendas_acoes, aplicada=False))
        return swing

    resultado = sum(v.resultado for v in acoes)
    isento = Isencao(competencia, vendas_acoes, aplicada=True)
    if resultado >= 0:
        isento.resultado_isento = resultado
    else:
        # Entendimento da RFB: prejuízo em venda isenta não é compensável. Parte
        # da doutrina discorda — por isso o valor fica registrado e vai à tela,
        # em vez de sumir no cálculo (DESIGN.md §8).
        isento.prejuizo_descartado = -resultado
        f.avisos.append(
            f"{competencia_br(competencia)}: prejuízo de R$ {_brl(-resultado)} em venda dentro da "
            f"isenção dos R$ 20 mil não foi compensado — entendimento da RFB")
    f.isencoes.append(isento)
    return [v for v in swing if v.classe not in ISENTAVEIS]


def _apurar_balde(f: Fisco, competencia: str, nome: str,
                  vendas: list[razao.Venda]) -> float:
    prejuizo_anterior = f.prejuizo.get(nome, 0.0)
    irrf_anterior = f.irrf_a_compensar.get(nome, 0.0)
    resultado = sum(v.resultado for v in vendas)
    irrf = sum(v.irrf for v in vendas) + irrf_anterior

    if resultado > 0:
        compensado = min(resultado, prejuizo_anterior)
        base = resultado - compensado
    else:
        compensado, base = 0.0, 0.0
    imposto = base * ALIQUOTA[nome]
    a_pagar = max(0.0, imposto - irrf)

    f.prejuizo[nome] = prejuizo_anterior - compensado + max(0.0, -resultado)
    f.irrf_a_compensar[nome] = max(0.0, irrf - imposto)
    f.baldes.append(Balde(
        competencia, nome, sum(v.valor_bruto for v in vendas), resultado,
        prejuizo_anterior, compensado, base, ALIQUOTA[nome], imposto, irrf,
        a_pagar, f.prejuizo[nome], f.irrf_a_compensar[nome]))
    return a_pagar


def apurar(ap: razao.Apuracao) -> Fisco:
    """Percorre todos os meses com venda, do primeiro ao último.

    Não dá para apurar um ano isolado: prejuízo e IRRF excedente atravessam
    meses e anos sem prazo de validade."""
    f = Fisco(prejuizo={b: 0.0 for b in ALIQUOTA},
              irrf_a_compensar={b: 0.0 for b in ALIQUOTA})
    por_mes: dict[str, list[razao.Venda]] = {}
    for v in ap.vendas:
        if v.classe in EXCLUSIVA:
            f.exclusiva.append(v)          # tributação exclusiva na fonte
            continue
        por_mes.setdefault(v.data[:7], []).append(v)
    if f.exclusiva:
        f.avisos.append(
            f"{len(f.exclusiva)} resgate(s) de renda fixa ficaram fora da apuração "
            f"mensal: o imposto é retido na fonte pela tabela regressiva e é "
            f"definitivo. Entram no informe anual como tributação exclusiva.")

    for competencia in sorted(por_mes):
        vendas = por_mes[competencia]
        grupos = {nome: [v for v in vendas if balde_de(v) == nome] for nome in ALIQUOTA}
        grupos[SWING] = _isencao(f, competencia, grupos[SWING])

        composicao = {nome: _apurar_balde(f, competencia, nome, linhas)
                      for nome, linhas in grupos.items() if linhas}
        devido = round(sum(composicao.values()), 2)
        if devido <= 0:
            # sem imposto novo não há o que reavaliar: o que estava acumulado
            # continua acumulado, sem repetir o aviso todo mês
            continue

        total = round(devido + f.acumulado_pendente, 2)
        if total < PISO_DARF:
            f.acumulado_pendente = total
            f.avisos.append(
                f"{competencia_br(competencia)}: R$ {_brl(total)} abaixo do piso de R$ "
                f"{_brl(PISO_DARF)} — acumula para o mês seguinte, não some")
            continue
        f.darfs.append(Darf(competencia, vencimento(competencia), CODIGO_DARF,
                            total, f.acumulado_pendente,
                            {k: round(v, 2) for k, v in composicao.items() if v}))
        f.acumulado_pendente = 0.0
    return f
