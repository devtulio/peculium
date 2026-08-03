"""Peculium — janela e ponte com a interface (DESIGN.md §9).

Um processo, sem servidor HTTP: `pywebview` abre a janela e expõe esta classe ao
JavaScript. Não existe porta, sessão nem token — o que protege o dado é o cofre.

Com o cofre fechado **só** `criar_cofre`, `abrir_cofre` e `abrir_com_recuperacao`
respondem; qualquer outra chamada devolve erro.
"""
from __future__ import annotations

import functools
import json
import sys
import traceback
from datetime import date
from pathlib import Path

import cofre
import cotacoes
import esquema
import fisco
import importar_b3
import importar_nota
import lancamentos
import obrigacoes
import razao
import relatorios
import renda_fixa
import series
import textos

VERSAO = "0.2.0"


def raiz() -> Path:
    """Onde estão os arquivos do programa.

    Congelado em onefile, o PyInstaller descompacta tudo num diretório temporário
    e aponta `sys._MEIPASS` para ele; `__file__` ali é o script dentro do pacote e
    não serve para achar a `ui/`."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


PASTA = Path.home() / "AppData" / "Local" / "Peculium"
COFRE = PASTA / "peculium.pec"
# Preferências que precisam ser lidas ANTES de abrir o cofre — só cosmético,
# nada aqui é sensível. O tema tem de estar disponível para a tela de senha
# nascer na cor certa, e ele vive dentro do banco cifrado.
PREFERENCIAS = PASTA / "preferencias.json"


def _resposta(funcao):
    """Toda chamada devolve {ok, dados} ou {ok:false, erro}. Traceback fica no
    console do processo, nunca na tela."""
    @functools.wraps(funcao)
    def envelope(self, *args, **kwargs):
        try:
            return {"ok": True, "dados": funcao(self, *args, **kwargs)}
        except Exception as e:                       # noqa: BLE001 — fronteira
            traceback.print_exc()
            return {"ok": False, "erro": str(e), "tipo": type(e).__name__}
    return envelope


def _exige_cofre(funcao):
    @functools.wraps(funcao)
    def envelope(self, *args, **kwargs):
        if self._aberto is None:
            raise PermissionError("cofre fechado")
        return funcao(self, *args, **kwargs)
    return envelope


def preferencias() -> dict:
    try:
        return json.loads(PREFERENCIAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def salvar_preferencias(dados: dict) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    PREFERENCIAS.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


class Api:
    def __init__(self, caminho: Path | None = None):
        # atributos públicos são inspecionados pelo pywebview e virariam método
        # no JS — tudo que não é chamada da UI fica privado
        self._caminho = Path(caminho or COFRE)
        self._aberto: cofre.Cofre | None = None
        self._janela = None
        self._conferencias: dict[str, object] = {}

    # ------------------------------------------------------------------ cofre

    @_resposta
    def estado(self) -> dict:
        return {"versao": VERSAO, "existe": self._caminho.exists(),
                "aberto": self._aberto is not None,
                "caminho": str(self._caminho),
                "preferencias": preferencias()}

    def _fechar(self) -> bool:
        """Fecha o cofre e esquece o que estava em memória.

        Chamado antes de qualquer abertura: sem isto, trancar a tela (que só
        recarrega o HTML) deixava o cofre aberto no Python, e a abertura seguinte
        esbarrava na **própria** trava de instância — "já está aberto em outra
        janela", sem outra janela nenhuma."""
        if self._aberto is None:
            return False
        self._aberto.fechar()
        self._aberto = None
        self._conferencias.clear()   # conferência pendente traz dado da carteira
        return True

    @_resposta
    def fechar_cofre(self) -> dict:
        """Trancar de verdade: a chave sai da memória do processo, e não só a
        tela volta para a senha."""
        return {"fechado": self._fechar()}

    @_resposta
    def criar_cofre(self, senha: str) -> dict:
        if len(senha or "") < 8:
            raise ValueError("a senha mestra precisa de pelo menos 8 caracteres")
        self._fechar()
        self._aberto, chave = cofre.criar(self._caminho, senha)
        return {"chave_recuperacao": chave}

    @_resposta
    def abrir_cofre(self, senha: str) -> dict:
        self._fechar()
        self._aberto = cofre.abrir(self._caminho, senha)
        return self._resumo_inicial()

    @_resposta
    def abrir_com_recuperacao(self, chave: str) -> dict:
        self._fechar()
        self._aberto = cofre.abrir_com_recuperacao(self._caminho, chave)
        return self._resumo_inicial()

    @_resposta
    @_exige_cofre
    def trocar_senha(self, atual: str, nova: str) -> dict:
        if len(nova or "") < 8:
            raise ValueError("a senha mestra precisa de pelo menos 8 caracteres")
        self._aberto.trocar_senha(atual, nova)
        return {"aviso": "Os backups anteriores continuam abrindo com a senha "
                         "antiga: eles guardam o embrulho velho da mesma chave. "
                         "Se você trocou a senha porque ela vazou, apague-os."}

    def _resumo_inicial(self) -> dict:
        return {"config": self._config(), "versao": VERSAO}

    @property
    def _conn(self):
        return self._aberto.conn

    def _gravar(self) -> None:
        self._aberto.commit()

    # ------------------------------------------------------------------ config

    def _config(self) -> dict:
        padrao = {"tema": "atrium", "paleta_daltonica": "0", "cotacao_online": "0",
                  "cpf": "", "senhas_pdf": ""}
        for linha in self._conn.execute("SELECT chave, valor FROM config"):
            padrao[linha["chave"]] = linha["valor"]
        return padrao

    @_resposta
    @_exige_cofre
    def config(self) -> dict:
        return self._config()

    @_resposta
    @_exige_cofre
    def salvar_config(self, mudancas: dict) -> dict:
        for chave, valor in (mudancas or {}).items():
            self._conn.execute(
                "INSERT OR REPLACE INTO config (chave, valor) VALUES (?,?)",
                (str(chave), str(valor)))
        self._gravar()
        atual = self._config()
        salvar_preferencias({"tema": atual["tema"],
                             "paleta_daltonica": atual["paleta_daltonica"]})
        return atual

    # ------------------------------------------------------------------ painel

    @_resposta
    @_exige_cofre
    def painel(self) -> dict:
        ap = razao.apurar(self._conn)
        carteira = ap.carteira()
        hoje = date.today().isoformat()
        ano = hoje[:4]

        classes: dict[str, float] = {}
        mercado = custo = 0.0
        sem_cotacao = []
        for p in carteira:
            preco = cotacoes.preco(self._conn, p.ativo_id)
            if preco is None:
                sem_cotacao.append(p.ticker)
            valor = (preco or p.preco_medio) * p.quantidade
            mercado += valor
            custo += p.custo_total
            classes[p.classe] = classes.get(p.classe, 0.0) + valor

        proventos_ano = sum(p.valor for p in ap.proventos if p.data[:4] == ano)
        aportes_ano = self._conn.execute(
            "SELECT coalesce(sum(valor + custos), 0) FROM lancamentos"
            " WHERE tipo IN ('COMPRA','SUBSCRICAO') AND estorna_id IS NULL"
            "   AND data LIKE ? AND id NOT IN (SELECT estorna_id FROM lancamentos"
            "   WHERE estorna_id IS NOT NULL)", (f"{ano}-%",)).fetchone()[0]

        alertas = []
        for o in obrigacoes.a_vencer(self._conn, dias=15, hoje=hoje):
            alertas.append({
                "tipo": "darf", "grave": o.situacao == obrigacoes.VENCIDO,
                "texto": (f"DARF {textos.competencia_br(o.competencia)} de "
                          f"R$ {relatorios.brl(o.total_a_pagar)} "
                          + (f"vencido em {textos.data_br(o.vencimento)}"
                             if o.situacao == obrigacoes.VENCIDO
                             else f"vence em {textos.data_br(o.vencimento)}"))})
        if sem_cotacao:
            alertas.append({"tipo": "cotacao", "grave": False,
                            "texto": f"{len(sem_cotacao)} ativo(s) sem cotação, "
                                     f"avaliados pelo preço médio"})
        for aviso in ap.avisos:
            alertas.append({"tipo": "razao", "grave": True, "texto": aviso})

        return {
            "patrimonio": mercado, "custo": custo, "resultado": mercado - custo,
            "proventos_ano": proventos_ano, "aportes_ano": aportes_ano,
            "ativos": len(carteira), "alertas": alertas,
            "classes": [{"classe": k, "valor": v} for k, v in
                        sorted(classes.items(), key=lambda x: -x[1])],
            "maiores": [{"ticker": p.ticker, "classe": p.classe,
                         "valor": (cotacoes.preco(self._conn, p.ativo_id)
                                   or p.preco_medio) * p.quantidade,
                         "custo": p.custo_total}
                        for p in sorted(carteira, key=lambda p: -p.custo_total)[:8]],
        }

    # ------------------------------------------------------------------ dados

    @_resposta
    @_exige_cofre
    def carteira(self) -> list[dict]:
        saida = []
        for p in razao.apurar(self._conn).carteira():
            preco = cotacoes.preco(self._conn, p.ativo_id)
            saida.append({"ativo_id": p.ativo_id, "ticker": p.ticker,
                          "classe": p.classe, "quantidade": p.quantidade,
                          "preco_medio": p.preco_medio, "custo": p.custo_total,
                          "cotacao": preco,
                          "mercado": (preco or p.preco_medio) * p.quantidade})
        return saida

    @_resposta
    @_exige_cofre
    def listar_lancamentos(self, filtros: dict | None = None) -> list[dict]:
        filtros = filtros or {}
        onde, parametros = [], []
        if filtros.get("ano"):
            onde.append("l.data LIKE ?")
            parametros.append(f"{filtros['ano']}-%")
        if filtros.get("ativo_id"):
            onde.append("l.ativo_id = ?")
            parametros.append(filtros["ativo_id"])
        if filtros.get("tipo"):
            onde.append("l.tipo = ?")
            parametros.append(filtros["tipo"])
        clausula = (" WHERE " + " AND ".join(onde)) if onde else ""
        return [dict(r) | {"data_br": textos.data_br(r["data"])} for r in
                self._conn.execute(
                    "SELECT l.*, a.ticker, i.nome AS instituicao, n.numero AS nota,"
                    " (SELECT id FROM lancamentos e WHERE e.estorna_id = l.id)"
                    "   AS estornado_por"
                    " FROM lancamentos l"
                    " LEFT JOIN ativos a ON a.id = l.ativo_id"
                    " LEFT JOIN instituicoes i ON i.id = l.instituicao_id"
                    " LEFT JOIN notas n ON n.id = l.nota_id"
                    + clausula + " ORDER BY l.data DESC, l.id DESC LIMIT 500",
                    parametros)]

    @_resposta
    @_exige_cofre
    def lancar(self, dados: dict) -> dict:
        identificador = lancamentos.lancar(self._conn, **_limpar(dados))
        self._gravar()
        return {"id": identificador}

    @_resposta
    @_exige_cofre
    def estornar(self, lancamento_id: int, motivo: str = "") -> dict:
        identificador = lancamentos.estornar(self._conn, int(lancamento_id), motivo)
        self._gravar()
        return {"id": identificador}

    @_resposta
    @_exige_cofre
    def registrar_evento(self, dados: dict) -> dict:
        identificador = lancamentos.registrar_evento(self._conn, **_limpar(dados))
        self._gravar()
        return {"id": identificador}

    @_resposta
    @_exige_cofre
    def listar_eventos(self) -> list[dict]:
        return [dict(r) | {"data_br": textos.data_br(r["data_ex"])} for r in
                self._conn.execute(
                    "SELECT e.*, a.ticker, d.ticker AS ticker_destino FROM eventos e"
                    " JOIN ativos a ON a.id = e.ativo_id"
                    " LEFT JOIN ativos d ON d.id = e.ativo_destino_id"
                    " ORDER BY e.data_ex DESC")]

    @_resposta
    @_exige_cofre
    def remover_evento(self, evento_id: int) -> dict:
        removido = lancamentos.remover_evento(self._conn, int(evento_id))
        self._gravar()
        return {"removido": removido}

    @_resposta
    @_exige_cofre
    def cadastros(self) -> dict:
        return {
            "ativos": [dict(r) for r in self._conn.execute(
                "SELECT id, ticker, nome, classe, ativo FROM ativos ORDER BY ticker")],
            "instituicoes": [dict(r) for r in self._conn.execute(
                "SELECT id, nome, cnpj, ativo FROM instituicoes ORDER BY nome")],
            "tipos": list(lancamentos.TIPOS), "eventos": list(lancamentos.EVENTOS),
        }

    @_resposta
    @_exige_cofre
    def cadastrar_ativo(self, dados: dict) -> dict:
        ticker = str(dados.get("ticker", "")).strip().upper()
        classe = str(dados.get("classe", "")).strip().upper()
        if not ticker or not classe:
            raise ValueError("ticker e classe são obrigatórios")
        identificador = self._conn.execute(
            "INSERT INTO ativos (ticker, nome, classe) VALUES (?,?,?)",
            (ticker, dados.get("nome") or None, classe)).lastrowid
        lancamentos.auditar(self._conn, "ATIVO", f"#{identificador} {ticker} {classe}")
        self._gravar()
        return {"id": identificador}

    @_resposta
    @_exige_cofre
    def cadastrar_instituicao(self, dados: dict) -> dict:
        nome = str(dados.get("nome", "")).strip()
        if not nome:
            raise ValueError("nome é obrigatório")
        identificador = self._conn.execute(
            "INSERT INTO instituicoes (nome, cnpj) VALUES (?,?)",
            (nome, dados.get("cnpj") or None)).lastrowid
        lancamentos.auditar(self._conn, "INSTITUICAO", f"#{identificador} {nome}")
        self._gravar()
        return {"id": identificador}

    # ------------------------------------------------------------------ impostos

    @_resposta
    @_exige_cofre
    def impostos(self, ano: int | None = None) -> dict:
        ano = int(ano or date.today().year)
        f = fisco.apurar(razao.apurar(self._conn))
        return {
            "ano": ano,
            "baldes": [vars(b) for b in f.baldes if b.competencia[:4] == str(ano)],
            "prejuizo": f.prejuizo, "avisos": f.avisos,
            "obrigacoes": [vars(o) | {"total_a_pagar": o.total_a_pagar}
                           for o in obrigacoes.listar(self._conn)],
            "anos": [r[0] for r in self._conn.execute(
                "SELECT DISTINCT substr(data,1,4) FROM lancamentos ORDER BY 1 DESC")],
        }

    @_resposta
    @_exige_cofre
    def pagar(self, dados: dict) -> dict:
        identificador = obrigacoes.registrar(
            self._conn, dados["competencia"], float(dados["valor"]),
            textos.data_iso(dados["data"]), multa=float(dados.get("multa") or 0),
            juros=float(dados.get("juros") or 0), obs=dados.get("obs", ""))
        lancamentos.auditar(self._conn, "PAGAMENTO",
                            f"DARF {textos.competencia_br(dados['competencia'])} "
                            f"R$ {float(dados['valor']):.2f}")
        self._gravar()
        return {"id": identificador}

    @_resposta
    @_exige_cofre
    def cancelar_pagamento(self, pagamento_id: int) -> dict:
        removido = obrigacoes.cancelar(self._conn, int(pagamento_id))
        self._gravar()
        return {"removido": removido}

    # ------------------------------------------------------------------ importar

    @_resposta
    def escolher_arquivo(self, tipos: str = "") -> str | None:
        import webview

        filtros = ("Relatórios e notas (*.csv;*.xlsx;*.pdf)", "Todos (*.*)") \
            if not tipos else (tipos, "Todos (*.*)")
        escolhido = self._janela.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False, file_types=filtros)
        return escolhido[0] if escolhido else None

    @_resposta
    @_exige_cofre
    def importar(self, caminho: str) -> dict:
        alvo = Path(caminho)
        token = f"imp{len(self._conferencias) + 1}"
        if alvo.suffix.lower() == ".pdf":
            config = self._config()
            nota = importar_nota.ler(
                alvo, cpf=config.get("cpf") or None,
                senhas=tuple(s for s in (config.get("senhas_pdf") or "").split(",") if s))
            conferencia = importar_nota.conferir(self._conn, nota)
            self._conferencias[token] = ("NOTA", conferencia)
            return {"token": token, "origem": "NOTA",
                    "nota": {"numero": nota.numero, "corretora": nota.corretora,
                             "data": textos.data_br(nota.data_pregao),
                             "operacoes": nota.valor_operacoes,
                             "custos": nota.total_custos, "liquido": nota.liquido},
                    "ja_importada": conferencia.ja_importada,
                    "avisos": conferencia.avisos,
                    "itens": [{"situacao": i.situacao,
                               "especificacao": i.negocio.especificacao,
                               "ticker": i.negocio.ticker, "motivo": i.motivo,
                               "sentido": i.negocio.sentido,
                               "quantidade": i.negocio.quantidade,
                               "preco": i.negocio.preco,
                               "custos": i.negocio.custos} for i in conferencia.itens]}
        conferencia = importar_b3.ler(alvo, self._conn)
        self._conferencias[token] = ("B3", conferencia)
        return {"token": token, "origem": "B3", "relatorio": conferencia.relatorio,
                "novas": conferencia.novas, "duplicadas": conferencia.duplicadas,
                "erros": conferencia.erros, "avisos": conferencia.avisos,
                "ativos_novos": conferencia.ativos_novos,
                "instituicoes_novas": conferencia.instituicoes_novas,
                "linhas": [{"n": l.n, "situacao": l.situacao, "tipo": l.tipo,
                            "data": textos.data_br(l.data), "ticker": l.ticker,
                            "instituicao": l.instituicao, "quantidade": l.quantidade,
                            "valor": l.valor, "motivo": l.motivo}
                           for l in conferencia.linhas]}

    @_resposta
    @_exige_cofre
    def confirmar_importacao(self, token: str, tickers: dict | None = None,
                             classes: dict | None = None) -> dict:
        origem, conferencia = self._conferencias.pop(token)
        if origem == "NOTA":
            resumo = importar_nota.gravar(self._conn, conferencia, tickers, classes)
        else:
            resumo = {"gravadas": importar_b3.gravar(self._conn, conferencia, classes)}
        self._gravar()
        return resumo

    # ------------------------------------------------------------------ cotação

    @_resposta
    @_exige_cofre
    def cotar(self) -> dict:
        resultado = cotacoes.cotar(self._conn, date.today().isoformat())
        self._gravar()
        return vars(resultado)

    # ------------------------------------------------------------- renda fixa

    @_resposta
    @_exige_cofre
    def renda_fixa(self) -> dict:
        return {"posicao": renda_fixa.posicao(self._conn),
                "titulos": [vars(t) | {"descricao": t.descricao(),
                                       "vencido": t.vencido}
                            for t in renda_fixa.listar(self._conn)],
                "indexadores": renda_fixa.INDEXADORES,
                "series": {i: series.cobertura(self._conn, i)
                           for i in series.SERIES}}

    @_resposta
    @_exige_cofre
    def cadastrar_titulo(self, dados: dict) -> dict:
        limpos = _limpar(dados)
        renda_fixa.cadastrar(
            self._conn, ativo_id=int(limpos["ativo_id"]),
            emissao=limpos["emissao"], indexador=limpos["indexador"],
            taxa=float(limpos["taxa"]), pu_base=float(limpos.get("pu_base") or 1),
            vencimento=limpos.get("vencimento"), emissor=limpos.get("emissor") or "",
            isento=str(limpos.get("isento") or "0") == "1")
        self._gravar()
        return {"ativo_id": int(limpos["ativo_id"])}

    @_resposta
    @_exige_cofre
    def atualizar_curvas(self) -> dict:
        """Um botão só: busca o que falta da série do BCB e recalcula os PU.

        A série vem primeiro porque sem ela a curva não avança — e o erro que o
        usuário veria seria "atualize as séries", que é o que este botão faz."""
        baixadas = series.baixar(self._conn)
        resultado = renda_fixa.atualizar_curvas(self._conn)
        self._gravar()
        return {"series": vars(baixadas), "curvas": vars(resultado)}

    @_resposta
    @_exige_cofre
    def cotar_manual(self, ativo_id: int, data: str, valor: float) -> dict:
        cotacoes.registrar(self._conn, int(ativo_id), textos.data_iso(data),
                           float(valor), cotacoes.MANUAL)
        self._gravar()
        return {"ok": True}

    # ------------------------------------------------------------------ relatórios

    _RELATORIOS = {
        "posicao": ("Posição consolidada", lambda c, p: relatorios.posicao(c)),
        "proventos": ("Proventos por ativo",
                      lambda c, p: relatorios.proventos(c, p.get("ano"))),
        "fluxo": ("Fluxo de caixa dos proventos",
                  lambda c, p: relatorios.fluxo_proventos(c, int(p.get("meses") or 12))),
        "apuracao": ("Apuração de IR",
                     lambda c, p: relatorios.apuracao(c, int(p["ano"]))),
        "obrigacoes": ("Contas a pagar — DARF", lambda c, p: relatorios.obrigacoes(c)),
        "renda_fixa": ("Renda fixa e Tesouro", lambda c, p: relatorios.renda_fixa(c)),
        "bens": ("Bens e direitos",
                 lambda c, p: relatorios.bens_direitos(c, int(p["ano"]))),
        "operacoes": ("Operações",
                      lambda c, p: relatorios.operacoes(c, p.get("ano"))),
        "custos": ("Custos operacionais",
                   lambda c, p: relatorios.custos(c, p.get("ano"))),
        "rentabilidade": ("Rentabilidade", lambda c, p: relatorios.rentabilidade(c)),
    }

    @_resposta
    @_exige_cofre
    def relatorios_disponiveis(self) -> list[dict]:
        return [{"chave": k, "titulo": v[0]} for k, v in self._RELATORIOS.items()]

    @_resposta
    @_exige_cofre
    def relatorio(self, chave: str, params: dict | None = None) -> dict:
        titulo, construtor = self._RELATORIOS[chave]
        rel = construtor(self._conn, params or {})
        return {"titulo": rel.titulo, "colunas": rel.colunas, "linhas": rel.linhas,
                "rodape": rel.rodape, "avisos": rel.avisos,
                "numericas": sorted(rel.numericas)}

    @_resposta
    @_exige_cofre
    def salvar_relatorio(self, chave: str, formato: str,
                         params: dict | None = None) -> dict:
        import webview

        titulo, construtor = self._RELATORIOS[chave]
        rel = construtor(self._conn, params or {})
        sugestao = f"{rel.titulo}.{formato}".replace("/", "-")
        destino = self._janela.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=sugestao)
        if not destino:
            return {"salvo": False}
        caminho = Path(destino if isinstance(destino, str) else destino[0])
        conteudo = (relatorios.csv_texto(rel) if formato == "csv"
                    else relatorios.documento(rel, self._config()["tema"]))
        caminho.write_text(conteudo, encoding="utf-8-sig" if formato == "csv" else "utf-8")
        return {"salvo": True, "caminho": str(caminho)}


def _limpar(dados: dict) -> dict:
    """Campo vazio do formulário vira None, não string vazia."""
    return {k: (None if v == "" else v) for k, v in (dados or {}).items()}


def verificar() -> int:
    """`Peculium.exe --verificar` — prova que o executável abre e está completo,
    sem criar janela nem tocar no cofre.

    Existe porque um binário recém-gerado pode ser barrado pelo Smart App Control
    do Windows, e trocar o exe que funciona por um bloqueado só se descobre na
    hora errada. Devolve 0 quando está são; o resultado também vai para um
    arquivo, já que a build sem console não tem para onde imprimir."""
    faltando = [nome for nome in ("ui/index.html", "ui/app.js", "ui/estilo.css")
                if not (raiz() / nome).exists()]
    try:
        import webview                                       # noqa: F401
        backend = "webview importado"
    except Exception as e:                                   # noqa: BLE001
        faltando.append(f"pywebview: {e}")
        backend = "webview indisponível"
    laudo = (f"Peculium {VERSAO}\nraiz: {raiz()}\n{backend}\n"
             + ("ÍNTEGRO\n" if not faltando else "FALTANDO: " + ", ".join(faltando)))
    # Build sem console não tem stdout: `print` levanta AttributeError em vez de
    # imprimir, e derrubaria justamente a verificação que deveria tranquilizar.
    try:
        print(laudo)
    except Exception:                                        # noqa: BLE001
        pass
    try:
        (Path(sys.executable).parent / "peculium-verificacao.txt").write_text(
            laudo, encoding="utf-8")
    except OSError:
        pass
    return 0 if not faltando else 1


def main() -> None:
    if "--verificar" in sys.argv:
        raise SystemExit(verificar())

    import webview

    PASTA.mkdir(parents=True, exist_ok=True)
    api = Api()
    tema = preferencias().get("tema", "atrium")
    janela = webview.create_window(
        f"Peculium {VERSAO}", f"{raiz() / 'ui' / 'index.html'}?tema={tema}",
        js_api=api, width=1280, height=820, min_size=(900, 600))
    api._janela = janela
    webview.start()


if __name__ == "__main__":
    main()
