/* Peculium — lógica da interface e ponte com o Python.
   Script clássico de propósito: o pywebview abre o index por caminho de arquivo
   e o CORS bloqueia type="module" em file://, o que abriria a janela em branco. */

const $ = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

const brl = v => (Number(v) || 0).toLocaleString('pt-BR',
  { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const qtd = v => (Number(v) || 0).toLocaleString('pt-BR', { maximumFractionDigits: 8 });

/* Alta e baixa nunca só por cor: sinal, seta e valor sempre juntos. */
function sinal(v) {
  const n = Number(v) || 0;
  if (Math.abs(n) < 0.005) return `<span>${brl(0)}</span>`;
  const classe = n > 0 ? 'alta' : 'baixa';
  return `<span class="${classe}">${n > 0 ? '▲ +' : '▼ −'}${brl(Math.abs(n))}</span>`;
}
const esc = t => String(t ?? '').replace(/[&<>"]/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

let ESTADO = { config: {}, cadastros: null };

/* ── ponte ─────────────────────────────────────────────────────────────── */

async function api(metodo, ...args) {
  const ponte = window.pywebview && window.pywebview.api;
  if (!ponte) throw new Error('ponte com o Python indisponível');
  const r = await ponte[metodo](...args);
  if (!r || r.ok !== true) throw new Error((r && r.erro) || 'falha desconhecida');
  return r.dados;
}

function toast(texto, ruim = false) {
  const el = $('#toast');
  el.textContent = texto;
  el.classList.toggle('ruim', ruim);
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, ruim ? 7000 : 3500);
}

async function tentar(fn, sucesso) {
  try { const r = await fn(); if (sucesso) toast(sucesso); return r; }
  catch (e) { toast(e.message, true); throw e; }
}

/* ── trava ─────────────────────────────────────────────────────────────── */

function mostrarForm(id) {
  ['#form-abrir', '#form-criar', '#form-recuperar', '#chave-nova']
    .forEach(s => { $(s).hidden = s !== id; });
  $('#trava-erro').hidden = true;
}

async function iniciar() {
  const estado = await api('estado');
  $('#versao').textContent = 'v' + estado.versao;
  mostrarForm(estado.existe ? '#form-abrir' : '#form-criar');
  const alvo = $(estado.existe ? '#senha' : '#senha-nova');
  if (alvo) alvo.focus();
}

function erroTrava(mensagem) {
  const el = $('#trava-erro');
  el.textContent = mensagem;
  el.hidden = false;
}

$('#form-abrir').addEventListener('submit', async e => {
  e.preventDefault();
  try { await abrir(await api('abrir_cofre', $('#senha').value)); }
  catch (err) { erroTrava(err.message); $('#senha').select(); }
});

$('#form-criar').addEventListener('submit', async e => {
  e.preventDefault();
  if ($('#senha-nova').value !== $('#senha-conf').value)
    return erroTrava('as duas senhas não conferem');
  try {
    const r = await api('criar_cofre', $('#senha-nova').value);
    $('#chave-valor').textContent = r.chave_recuperacao;
    mostrarForm('#chave-nova');
  } catch (err) { erroTrava(err.message); }
});

$('#btn-chave-ok').addEventListener('click', async () => {
  await abrir({ config: await api('config'), versao: $('#versao').textContent });
});

$('#form-recuperar').addEventListener('submit', async e => {
  e.preventDefault();
  try { await abrir(await api('abrir_com_recuperacao', $('#chave').value)); }
  catch (err) { erroTrava(err.message); }
});

$('#btn-recuperar').addEventListener('click', () => mostrarForm('#form-recuperar'));
$('#btn-voltar-senha').addEventListener('click', () => mostrarForm('#form-abrir'));
// Trancar tem de fechar o cofre no Python, não só recarregar a tela: só
// recarregando, a chave continuava na memória do processo e a próxima abertura
// esbarrava na trava que ele mesmo segurava.
$('#btn-trancar').addEventListener('click', async () => {
  try { await api('fechar_cofre'); } catch (e) { /* recarrega mesmo assim */ }
  location.reload();
});

async function abrir(dados) {
  ESTADO.config = dados.config || {};
  aplicarTema();
  $('#trava').hidden = true;
  $('#app').hidden = false;
  montarMenu();
  await irPara('painel');
  if (dados.aviso) toast(dados.aviso, true);
}

function aplicarTema() {
  document.documentElement.dataset.tema = ESTADO.config.tema || 'atrium';
  document.documentElement.dataset.daltonica = ESTADO.config.paleta_daltonica || '0';
}

/* ── navegação ─────────────────────────────────────────────────────────── */

const VIEWS = {
  painel: ['Painel', verPainel],
  carteira: ['Carteira', verCarteira],
  lancamentos: ['Lançamentos', verLancamentos],
  proventos: ['Proventos', verProventos],
  importar: ['Importar', verImportar],
  impostos: ['Impostos', verImpostos],
  relatorios: ['Relatórios', verRelatorios],
  config: ['Configurações', verConfig],
};

function montarMenu() {
  $('#menu').innerHTML = Object.entries(VIEWS).map(([chave, [titulo]]) =>
    `<li><button type="button" data-view="${chave}">${titulo}</button></li>`).join('');
  $$('#menu button').forEach(b =>
    b.addEventListener('click', () => irPara(b.dataset.view)));
}

async function irPara(chave) {
  const [titulo, render] = VIEWS[chave];
  $('#titulo-view').textContent = titulo;
  $('#acoes-view').innerHTML = '';
  $('#view').innerHTML = '<p class="vazio">Carregando…</p>';
  $$('#menu button').forEach(b =>
    b.toggleAttribute('aria-current', b.dataset.view === chave));
  try { await render(); }
  catch (e) { $('#view').innerHTML = `<p class="erro">${esc(e.message)}</p>`; }
}

/* ── componentes ───────────────────────────────────────────────────────── */

function tabela(colunas, linhas, { numericas = [], vazio = 'Nada a exibir' } = {}) {
  if (!linhas.length) return `<p class="vazio">${vazio}</p>`;
  const cab = colunas.map((c, i) =>
    `<th class="${numericas.includes(i) ? 'n' : ''}">${esc(c)}</th>`).join('');
  const corpo = linhas.map(l => {
    const celulas = (l.celulas || l).map((v, i) =>
      `<td class="${numericas.includes(i) ? 'n' : ''}">${v}</td>`).join('');
    return `<tr class="${l.classe || ''}">${celulas}</tr>`;
  }).join('');
  return `<table><thead><tr>${cab}</tr></thead><tbody>${corpo}</tbody></table>`;
}

function cartao(rotulo, valor) {
  return `<div class="cartao"><div class="rotulo">${esc(rotulo)}</div>
          <div class="valor">${valor}</div></div>`;
}

function botao(texto, aoClicar, classe = 'secundario') {
  const b = document.createElement('button');
  b.type = 'button'; b.className = classe; b.textContent = texto;
  b.addEventListener('click', aoClicar);
  return b;
}

function modal(titulo, corpoHtml, aoConfirmar, rotuloOk = 'Confirmar') {
  $('#modal-titulo').textContent = titulo;
  $('#modal-corpo').innerHTML = corpoHtml;
  $('#modal-ok').textContent = rotuloOk;
  const dlg = $('#modal');
  const aoFechar = async () => {
    dlg.removeEventListener('close', aoFechar);
    if (dlg.returnValue === 'ok') await aoConfirmar(dlg);
  };
  dlg.addEventListener('close', aoFechar);
  dlg.showModal();
  const primeiro = $('#modal-corpo input, #modal-corpo select');
  if (primeiro) primeiro.focus();
}

async function cadastros() {
  if (!ESTADO.cadastros) ESTADO.cadastros = await api('cadastros');
  return ESTADO.cadastros;
}

/* ── painel ────────────────────────────────────────────────────────────── */

async function verPainel() {
  const d = await api('painel');
  const alertas = d.alertas.map(a =>
    `<div class="alerta ${a.grave ? 'grave' : ''}">
       <span class="marcador">${a.grave ? '!' : 'i'}</span>
       <span>${esc(a.texto)}</span></div>`).join('');
  const total = d.classes.reduce((s, c) => s + c.valor, 0) || 1;

  $('#view').innerHTML = `
    ${alertas}
    <div class="cartoes">
      ${cartao('Patrimônio', 'R$ ' + brl(d.patrimonio))}
      ${cartao('Custo de aquisição', 'R$ ' + brl(d.custo))}
      ${cartao('Resultado não realizado', sinal(d.resultado))}
      ${cartao('Proventos no ano', 'R$ ' + brl(d.proventos_ano))}
      ${cartao('Aportes no ano', 'R$ ' + brl(d.aportes_ano))}
      ${cartao('Ativos em carteira', d.ativos)}
    </div>
    <div class="painel-colunas">
      <div class="bloco"><h3>Alocação por classe</h3>
        ${tabela(['Classe', 'Valor', '%'], d.classes.map(c => [
          esc(c.classe), 'R$ ' + brl(c.valor),
          brl(100 * c.valor / total) + '%']), { numericas: [1, 2] })}</div>
      <div class="bloco"><h3>Maiores posições</h3>
        ${tabela(['Ativo', 'Classe', 'Mercado', 'Resultado'], d.maiores.map(m => [
          esc(m.ticker), esc(m.classe), 'R$ ' + brl(m.valor),
          sinal(m.valor - m.custo)]), { numericas: [2, 3] })}</div>
    </div>`;
}

/* ── carteira ──────────────────────────────────────────────────────────── */

async function verCarteira() {
  const [linhas, rf, cad] = await Promise.all([
    api('carteira'), api('renda_fixa'), cadastros()]);
  const mercado = linhas.reduce((s, p) => s + p.mercado, 0) || 1;
  $('#acoes-view').append(
    botao('Atualizar cotações', async () => {
      const r = await tentar(() => api('cotar'));
      if (r.desligada) return toast('Cotação online está desligada nas configurações');
      toast(`${r.atualizadas} cotação(ões) atualizada(s), ${Object.keys(r.falhas).length} falha(s)`);
      irPara('carteira');
    }),
    botao('Atualizar curvas', async () => {
      const r = await tentar(() => api('atualizar_curvas'));
      if (r.series.desligada)
        return toast('Ligue a rede em Configurações para baixar as séries do BCB', true);
      const falhas = Object.values(r.curvas.falhas);
      toast(`${r.curvas.atualizados} curva(s) recalculada(s)` +
            (falhas.length ? ` — ${falhas[0]}` : ''), falhas.length > 0);
      irPara('carteira');
    }),
    botao('Novo título de renda fixa', () => formTitulo(cad, rf.indexadores)));

  $('#view').innerHTML = tabela(
    ['Ativo', 'Classe', 'Quantidade', 'Preço médio', 'Custo', 'Cotação',
     'Valor de mercado', 'Resultado', '% carteira'],
    linhas.map(p => ({
      celulas: [
        esc(p.ticker), esc(p.classe), qtd(p.quantidade), brl(p.preco_medio),
        brl(p.custo),
        p.cotacao == null
          ? `<span class="selo-situacao" title="sem cotação: avaliado pelo preço médio">—</span>`
          : brl(p.cotacao),
        brl(p.mercado), sinal(p.mercado - p.custo),
        brl(100 * p.mercado / mercado) + '%'],
    })),
    { numericas: [2, 3, 4, 5, 6, 7, 8], vazio: 'Carteira vazia — importe ou lance uma compra' });

  if (rf.posicao.length) $('#view').insertAdjacentHTML('beforeend', blocoRendaFixa(rf));
}

function blocoRendaFixa(rf) {
  const semCurva = rf.posicao.filter(p => p.erro);
  return `<div class="bloco" style="margin-top:1.4rem"><h3>Renda fixa e Tesouro</h3>
    ${tabela(['Título', 'Emissor', 'Indexador', 'Vencimento', 'Quantidade',
              'Custo', 'PU', 'Bruto', 'Rendimento'],
      rf.posicao.map(p => ({
        classe: p.vencido ? 'estornado' : '',
        celulas: [esc(p.ticker), esc(p.emissor || '—'), esc(p.indexador),
                  esc(p.vencimento ? p.vencimento.split('-').reverse().join('/') : '—'),
                  qtd(p.quantidade), brl(p.custo),
                  p.pu == null ? '—' : brl(p.pu), brl(p.bruto),
                  sinal(p.rendimento)],
      })), { numericas: [4, 5, 6, 7, 8] })}
    <ul class="aviso-lista">
      ${semCurva.map(p => `<li>${esc(p.ticker)}: ${esc(p.erro)}</li>`).join('')}
      <li>O rendimento é bruto. O IR de renda fixa é retido na fonte pela tabela
          regressiva — veja a estimativa no relatório de Renda fixa.</li>
    </ul></div>`;
}

function formTitulo(cad, indexadores) {
  const elegiveis = cad.ativos.filter(a => ['RF', 'TESOURO'].includes(a.classe));
  if (!elegiveis.length) {
    return modal('Nenhum ativo de renda fixa',
      `<p>Cadastre antes um ativo com a classe <strong>RF</strong> ou
       <strong>TESOURO</strong> em Configurações → Cadastros. O ticker pode ser o
       código do papel que aparece na nota, como <code>CDB5267UW6V</code>.</p>`,
      async () => {}, 'Entendi');
  }
  modal('Título de renda fixa', `
    <div class="form-grade">
      <div class="campo"><label for="t-ativo">Ativo</label>
        <select id="t-ativo">${elegiveis.map(a =>
          `<option value="${a.id}">${esc(a.ticker)}</option>`).join('')}</select></div>
      <div class="campo"><label for="t-emissao">Emissão</label>
        <input id="t-emissao" placeholder="dd/mm/aaaa"></div>
      <div class="campo"><label for="t-venc">Vencimento</label>
        <input id="t-venc" placeholder="dd/mm/aaaa"></div>
      <div class="campo"><label for="t-index">Indexador</label>
        <select id="t-index">${Object.entries(indexadores).map(([k, v]) =>
          `<option value="${k}">${esc(v)}</option>`).join('')}</select></div>
      <div class="campo"><label for="t-taxa">Taxa</label>
        <input id="t-taxa" inputmode="decimal" placeholder="100"></div>
      <div class="campo"><label for="t-pu">PU de emissão</label>
        <input id="t-pu" inputmode="decimal" value="1"></div>
      <div class="campo"><label for="t-emissor">Emissor</label>
        <input id="t-emissor" placeholder="BANCO XP S.A."></div>
      <div class="campo"><label for="t-isento">Isento de IR</label>
        <select id="t-isento"><option value="0">Não</option>
          <option value="1">Sim (LCI, LCA)</option></select></div>
    </div>
    <p class="trava-nota">A <strong>taxa</strong> é o percentual do CDI quando
      pós-fixado (<code>100</code> para 100% do CDI) ou a taxa anual no prefixado.
      O <strong>PU de emissão</strong> tem de ser o da nota: se ele não bater com o
      preço da aplicação, a posição sai errada em ordem de grandeza.</p>`,
    async dlg => {
      await tentar(() => api('cadastrar_titulo', {
        ativo_id: $('#t-ativo', dlg).value, emissao: $('#t-emissao', dlg).value,
        vencimento: $('#t-venc', dlg).value, indexador: $('#t-index', dlg).value,
        taxa: $('#t-taxa', dlg).value.replace(',', '.'),
        pu_base: $('#t-pu', dlg).value.replace(',', '.'),
        emissor: $('#t-emissor', dlg).value, isento: $('#t-isento', dlg).value,
      }), 'Título cadastrado');
      irPara('carteira');
    }, 'Cadastrar');
}

/* ── lançamentos ───────────────────────────────────────────────────────── */

async function verLancamentos() {
  const [linhas, cad] = await Promise.all([api('listar_lancamentos'), cadastros()]);
  $('#acoes-view').append(
    botao('Novo lançamento', () => formLancamento(cad), 'primario'),
    botao('Evento corporativo', () => formEvento(cad)));

  $('#view').innerHTML = tabela(
    ['Data', 'Tipo', 'Ativo', 'Instituição', 'Quantidade', 'Preço', 'Valor',
     'Custos', 'Origem', ''],
    linhas.map(l => ({
      classe: l.estornado_por || l.estorna_id ? 'estornado' : '',
      celulas: [
        esc(l.data_br), esc(l.tipo), esc(l.ticker || '—'), esc(l.instituicao || '—'),
        qtd(l.quantidade), brl(l.preco), brl(l.valor), brl(l.custos),
        esc(l.nota ? 'nota ' + l.nota : l.origem),
        (l.estorna_id || l.estornado_por) ? ''
          : `<button type="button" class="link" data-estornar="${l.id}">estornar</button>`],
    })),
    { numericas: [4, 5, 6, 7], vazio: 'Nenhum lançamento ainda' });

  $$('[data-estornar]').forEach(b => b.addEventListener('click', () =>
    modal('Estornar lançamento',
      `<p>O lançamento continua visível no extrato; o estorno anula o efeito dele.</p>
       <div class="campo"><label for="motivo">Motivo (opcional)</label>
       <input id="motivo"></div>`,
      async dlg => {
        await tentar(() => api('estornar', Number(b.dataset.estornar),
          $('#motivo', dlg).value), 'Lançamento estornado');
        irPara('lancamentos');
      }, 'Estornar')));
}

function formLancamento(cad) {
  const opcoes = (lista, valor = 'id', texto = 'nome') => lista.map(o =>
    `<option value="${esc(o[valor])}">${esc(o[texto])}</option>`).join('');
  modal('Novo lançamento', `
    <div class="form-grade">
      <div class="campo"><label for="l-tipo">Tipo</label>
        <select id="l-tipo">${cad.tipos.map(t =>
          `<option value="${t}">${t}</option>`).join('')}</select></div>
      <div class="campo"><label for="l-data">Data</label>
        <input id="l-data" placeholder="dd/mm/aaaa"></div>
      <div class="campo"><label for="l-ativo">Ativo</label>
        <select id="l-ativo"><option value="">—</option>
          ${opcoes(cad.ativos, 'id', 'ticker')}</select></div>
      <div class="campo"><label for="l-inst">Instituição</label>
        <select id="l-inst"><option value="">—</option>${opcoes(cad.instituicoes)}</select></div>
      <div class="campo"><label for="l-qtd">Quantidade</label>
        <input id="l-qtd" inputmode="decimal"></div>
      <div class="campo"><label for="l-preco">Preço</label>
        <input id="l-preco" inputmode="decimal"></div>
      <div class="campo"><label for="l-valor">Valor</label>
        <input id="l-valor" inputmode="decimal"></div>
      <div class="campo"><label for="l-custos">Custos</label>
        <input id="l-custos" inputmode="decimal"></div>
      <div class="campo"><label for="l-irrf">IRRF</label>
        <input id="l-irrf" inputmode="decimal"></div>
      <div class="campo"><label for="l-destino">Instituição de destino</label>
        <select id="l-destino"><option value="">—</option>${opcoes(cad.instituicoes)}</select></div>
    </div>
    <p class="trava-nota">Data em branco assume hoje. Em compra e venda o valor é
      calculado de quantidade × preço quando deixado vazio.</p>`,
    async dlg => {
      const num = id => { const v = $(id, dlg).value.replace(',', '.').trim();
                          return v === '' ? null : Number(v); };
      await tentar(() => api('lancar', {
        tipo: $('#l-tipo', dlg).value,
        data: $('#l-data', dlg).value || new Date().toLocaleDateString('pt-BR'),
        ativo: $('#l-ativo', dlg).value ? Number($('#l-ativo', dlg).value) : null,
        instituicao: $('#l-inst', dlg).value ? Number($('#l-inst', dlg).value) : null,
        destino: $('#l-destino', dlg).value ? Number($('#l-destino', dlg).value) : null,
        quantidade: num('#l-qtd') || 0, preco: num('#l-preco') || 0,
        valor: num('#l-valor'), custos: num('#l-custos') || 0,
        irrf: num('#l-irrf') || 0,
      }), 'Lançamento gravado');
      irPara('lancamentos');
    }, 'Lançar');
}

function formEvento(cad) {
  const opcoes = cad.ativos.map(a =>
    `<option value="${a.id}">${esc(a.ticker)}</option>`).join('');
  modal('Evento corporativo', `
    <div class="form-grade">
      <div class="campo"><label for="e-tipo">Evento</label>
        <select id="e-tipo">${cad.eventos.map(t =>
          `<option value="${t}">${t}</option>`).join('')}</select></div>
      <div class="campo"><label for="e-ativo">Ativo</label>
        <select id="e-ativo">${opcoes}</select></div>
      <div class="campo"><label for="e-data">Data ex</label>
        <input id="e-data" placeholder="dd/mm/aaaa"></div>
      <div class="campo"><label for="e-fator">Fator</label>
        <input id="e-fator" inputmode="decimal" placeholder="10"></div>
      <div class="campo"><label for="e-destino">Ativo de destino</label>
        <select id="e-destino"><option value="">—</option>${opcoes}</select></div>
    </div>
    <p class="trava-nota"><strong>Fator é sempre o multiplicador da quantidade:</strong>
      desdobramento de 1:10 é <code>10</code>; grupamento de 10:1 é <code>0,1</code>.
      Destino só em conversão e incorporação.</p>`,
    async dlg => {
      await tentar(() => api('registrar_evento', {
        tipo: $('#e-tipo', dlg).value, ativo: Number($('#e-ativo', dlg).value),
        data_ex: $('#e-data', dlg).value || new Date().toLocaleDateString('pt-BR'),
        fator: Number($('#e-fator', dlg).value.replace(',', '.')),
        destino: $('#e-destino', dlg).value ? Number($('#e-destino', dlg).value) : null,
      }), 'Evento registrado');
      irPara('lancamentos');
    }, 'Registrar');
}

/* ── proventos ─────────────────────────────────────────────────────────── */

async function verProventos() {
  const [porAtivo, fluxo] = await Promise.all([
    api('relatorio', 'proventos', {}), api('relatorio', 'fluxo', { meses: 12 })]);
  $('#view').innerHTML = `
    <div class="bloco" style="margin-bottom:1rem"><h3>${esc(fluxo.titulo)}</h3>
      ${tabela(fluxo.colunas, fluxo.linhas.map(l => l.map(esc)),
               { numericas: fluxo.numericas })}
      <ul class="aviso-lista">${[...fluxo.rodape, ...fluxo.avisos]
        .map(t => `<li>${esc(t)}</li>`).join('')}</ul></div>
    <div class="bloco"><h3>${esc(porAtivo.titulo)}</h3>
      ${tabela(porAtivo.colunas, porAtivo.linhas.map(l => l.map(esc)),
               { numericas: porAtivo.numericas })}
      <ul class="aviso-lista">${[...porAtivo.rodape, ...porAtivo.avisos]
        .map(t => `<li>${esc(t)}</li>`).join('')}</ul></div>`;
}

/* ── importar ──────────────────────────────────────────────────────────── */

async function verImportar() {
  $('#view').innerHTML = `
    <div class="bloco">
      <h3>Importar arquivo</h3>
      <p>Aceita os relatórios de <strong>Negociação</strong> e
        <strong>Movimentação</strong> da Área do Investidor da B3 (CSV ou XLSX) e
        a <strong>nota de corretagem</strong> em PDF.</p>
      <p class="trava-nota">Nada é gravado antes da sua conferência. O arquivo
        original não é guardado — ele traz CPF.</p>
      <button type="button" class="primario" id="btn-escolher">Escolher arquivo…</button>
    </div>
    <div id="conferencia"></div>`;
  $('#btn-escolher').addEventListener('click', async () => {
    const caminho = await tentar(() => api('escolher_arquivo'));
    if (!caminho) return;
    const c = await tentar(() => api('importar', caminho));
    ({ NOTA: conferirNota, NOTA_RF: conferirNotaRF, B3: conferirB3 })[c.origem](c);
  });
}

function conferirNotaRF(c) {
  const novas = c.notas.filter(n => n.situacao === 'CRIA');
  $('#conferencia').innerHTML = `
    <div class="bloco" style="margin-top:1rem">
      <h3>Nota${c.notas.length > 1 ? 's' : ''} de renda fixa</h3>
      ${listaAvisos(c.avisos)}
      ${tabela(['Nota', 'Situação', 'Data', 'Título', 'Emissor', 'Indexador',
                'Vencimento', 'Quantidade', 'PU', 'Bruto'],
        c.notas.map(n => [
          esc(n.numero),
          `<span class="selo-situacao ${n.situacao === 'CRIA' ? 'ok' : ''}">${n.situacao}</span>`,
          esc(n.data),
          esc(n.ticker) + (n.codigo_ambiguo
            ? ' <span class="selo-situacao grave" title="a nota não trouxe um código utilizável; o ticker foi derivado do nome e do vencimento">derivado</span>'
            : ''),
          esc(n.emissor), `${esc(n.indexador)} ${n.taxa}%`, esc(n.vencimento),
          qtd(n.quantidade), brl(n.pu), brl(n.bruto)]),
        { numericas: [7, 8, 9] })}
      <menu style="display:flex;gap:.6rem;justify-content:flex-end;padding:0">
        <button type="button" class="primario" id="btn-gravar-rf"
          ${novas.length ? '' : 'disabled'}>Gravar ${novas.length} aplicação(ões)</button>
      </menu>
    </div>`;
  const gravar = $('#btn-gravar-rf');
  if (gravar) gravar.addEventListener('click', async () => {
    const r = await tentar(() => api('confirmar_importacao', c.token));
    toast(`${r.lancamentos} lançamento(s) e ${r.titulos} título(s) cadastrado(s)`);
    irPara('carteira');
  });
}

function listaAvisos(avisos) {
  return avisos && avisos.length
    ? `<ul class="aviso-lista">${avisos.map(a => `<li>${esc(a)}</li>`).join('')}</ul>`
    : '';
}

function conferirB3(c) {
  const novos = Object.entries(c.ativos_novos || {});
  $('#conferencia').innerHTML = `
    <div class="bloco" style="margin-top:1rem">
      <h3>Conferência — ${esc(c.relatorio)}</h3>
      <div class="cartoes">
        ${cartao('Novas', c.novas)}${cartao('Duplicadas', c.duplicadas)}
        ${cartao('Erros', c.erros)}
      </div>
      ${novos.length ? `<h3>Ativos novos</h3><div class="form-grade">${novos.map(
        ([ticker, a]) => `<div class="campo"><label for="c-${ticker}">${esc(ticker)}
          ${a.confirmar ? ' — confirme a classe' : ''}</label>
          <select id="c-${ticker}" data-classe="${esc(ticker)}">
            ${['ACAO', 'FII', 'ETF', 'BDR', 'UNIT'].map(k =>
              `<option value="${k}"${k === a.classe ? ' selected' : ''}>${k}</option>`
            ).join('')}</select></div>`).join('')}</div>` : ''}
      ${listaAvisos(c.avisos)}
      ${tabela(['Linha', 'Situação', 'Data', 'Tipo', 'Ativo', 'Quantidade', 'Valor', 'Motivo'],
        c.linhas.map(l => [l.n, `<span class="selo-situacao ${l.situacao === 'NOVA' ? 'ok' : ''}">${l.situacao}</span>`,
          esc(l.data), esc(l.tipo), esc(l.ticker), qtd(l.quantidade), brl(l.valor),
          esc(l.motivo)]), { numericas: [5, 6] })}
      <menu style="display:flex;gap:.6rem;justify-content:flex-end;padding:0">
        <button type="button" class="primario" id="btn-gravar"
          ${c.novas ? '' : 'disabled'}>Gravar ${c.novas} lançamento(s)</button>
      </menu>
    </div>`;
  const gravar = $('#btn-gravar');
  if (gravar) gravar.addEventListener('click', async () => {
    const classes = {};
    $$('[data-classe]').forEach(s => { classes[s.dataset.classe] = s.value; });
    const r = await tentar(() => api('confirmar_importacao', c.token, null, classes));
    toast(`${r.gravadas} lançamento(s) gravado(s)`);
    irPara('lancamentos');
  });
}

function conferirNota(c) {
  const semAtivo = c.itens.filter(i => i.situacao === 'SEM_ATIVO');
  $('#conferencia').innerHTML = `
    <div class="bloco" style="margin-top:1rem">
      <h3>Nota ${esc(c.nota.numero)} — ${esc(c.nota.data)}</h3>
      <div class="cartoes">
        ${cartao('Operações', 'R$ ' + brl(c.nota.operacoes))}
        ${cartao('Custos', 'R$ ' + brl(c.nota.custos))}
        ${cartao('Líquido', 'R$ ' + brl(c.nota.liquido))}
      </div>
      ${c.ja_importada ? '<p class="erro">Esta nota já foi importada.</p>' : ''}
      ${semAtivo.length ? `<h3>Ativos a identificar</h3>
        <p class="trava-nota">A nota traz o nome de pregão, não o código. Informe o
          ticker uma vez e o sistema passa a reconhecer.</p>
        <div class="form-grade">${semAtivo.map((i, n) => `
          <div class="campo"><label for="t-${n}">${esc(i.especificacao)}</label>
            <input id="t-${n}" data-espec="${esc(i.especificacao)}"
              value="${esc(i.ticker)}" placeholder="ex.: KLBN4"></div>
          <div class="campo"><label for="k-${n}">Classe</label>
            <select id="k-${n}" data-espec-classe="${esc(i.especificacao)}">
              ${['ACAO', 'FII', 'ETF', 'BDR', 'UNIT'].map(k =>
                `<option value="${k}">${k}</option>`).join('')}</select></div>`).join('')}
        </div>` : ''}
      ${listaAvisos(c.avisos)}
      ${tabela(['Situação', 'Especificação', 'Ticker', 'Sentido', 'Quantidade',
                'Preço', 'Custos rateados', 'Observação'],
        c.itens.map(i => [
          `<span class="selo-situacao ${i.situacao === 'SEM_ATIVO' ? 'grave' : 'ok'}">${i.situacao}</span>`,
          esc(i.especificacao), esc(i.ticker || '—'), esc(i.sentido),
          qtd(i.quantidade), brl(i.preco), brl(i.custos), esc(i.motivo)]),
        { numericas: [4, 5, 6] })}
      <menu style="display:flex;gap:.6rem;justify-content:flex-end;padding:0">
        <button type="button" class="primario" id="btn-gravar-nota"
          ${c.ja_importada ? 'disabled' : ''}>Gravar nota</button>
      </menu>
    </div>`;
  const gravar = $('#btn-gravar-nota');
  if (gravar) gravar.addEventListener('click', async () => {
    const tickers = {}, classes = {};
    $$('[data-espec]').forEach(i => {
      if (i.value.trim()) tickers[i.dataset.espec] = i.value.trim().toUpperCase();
    });
    $$('[data-espec-classe]').forEach(s => {
      const t = tickers[s.dataset.especClasse];
      if (t) classes[t] = s.value;
    });
    const r = await tentar(() => api('confirmar_importacao', c.token, tickers, classes));
    toast(`${r.criados} negócio(s) criado(s), ${r.enriquecidos} enriquecido(s) com custos`);
    irPara('lancamentos');
  });
}

/* ── impostos ──────────────────────────────────────────────────────────── */

async function verImpostos() {
  const d = await api('impostos');
  const situacaoClasse = s =>
    s === 'PAGO' ? 'ok' : (s === 'VENCIDO' || s === 'PARCIAL' ? 'grave' : '');

  $('#view').innerHTML = `
    <div class="bloco" style="margin-bottom:1rem"><h3>Contas a pagar — DARF</h3>
      ${tabela(['Competência', 'Vencimento', 'Apurado', 'Pago', 'Situação',
                'Atraso', 'Multa', 'Total a pagar', ''],
        d.obrigacoes.map(o => [
          esc(o.competencia), esc(o.vencimento || '—'), brl(o.valor_apurado),
          o.valor_pago ? brl(o.valor_pago) : '—',
          `<span class="selo-situacao ${situacaoClasse(o.situacao)}">${o.situacao}</span>`,
          o.dias_atraso ? o.dias_atraso + ' dia(s)' : '—',
          o.multa ? brl(o.multa) : '—', brl(o.total_a_pagar),
          o.total_a_pagar > 0
            ? `<button type="button" class="link" data-pagar="${esc(o.competencia)}"
                 data-valor="${o.total_a_pagar}" data-multa="${o.multa || 0}">registrar pagamento</button>`
            : '']),
        { numericas: [2, 3, 5, 6, 7], vazio: 'Nenhum DARF apurado' })}
      <ul class="aviso-lista">${d.obrigacoes.flatMap(o => o.observacoes || [])
        .map(t => `<li>${esc(t)}</li>`).join('')}</ul>
    </div>
    <div class="bloco"><h3>Apuração ${d.ano}</h3>
      ${tabela(['Competência', 'Balde', 'Vendas', 'Resultado', 'Compensado',
                'Base', 'Imposto', 'IRRF', 'A pagar'],
        d.baldes.map(b => [
          esc(b.competencia), esc(b.balde), brl(b.valor_vendas), sinal(b.resultado),
          brl(b.compensado), brl(b.base), brl(b.imposto), brl(b.irrf), brl(b.a_pagar)]),
        { numericas: [2, 3, 4, 5, 6, 7, 8], vazio: 'Nenhuma venda tributável no ano' })}
      <ul class="aviso-lista">
        ${Object.entries(d.prejuizo).filter(([, v]) => v)
          .map(([k, v]) => `<li>Prejuízo a compensar em ${esc(k)}: R$ ${brl(v)}</li>`).join('')}
        ${d.avisos.map(a => `<li>${esc(a)}</li>`).join('')}
        <li>Memória de cálculo para conferência: o Peculium não transmite nada à
            Receita nem emite DARF oficial.</li>
      </ul>
    </div>`;

  $$('[data-pagar]').forEach(b => b.addEventListener('click', () =>
    modal(`Pagamento do DARF ${b.dataset.pagar}`, `
      <div class="form-grade">
        <div class="campo"><label for="p-valor">Principal</label>
          <input id="p-valor" value="${(Number(b.dataset.valor) - Number(b.dataset.multa)).toFixed(2)}"></div>
        <div class="campo"><label for="p-multa">Multa</label>
          <input id="p-multa" value="${Number(b.dataset.multa).toFixed(2)}"></div>
        <div class="campo"><label for="p-juros">Juros</label>
          <input id="p-juros" value="0"></div>
        <div class="campo"><label for="p-data">Data do pagamento</label>
          <input id="p-data" placeholder="dd/mm/aaaa"
            value="${new Date().toLocaleDateString('pt-BR')}"></div>
      </div>`,
      async dlg => {
        const n = id => Number($(id, dlg).value.replace(',', '.')) || 0;
        await tentar(() => api('pagar', {
          competencia: b.dataset.pagar, valor: n('#p-valor'), multa: n('#p-multa'),
          juros: n('#p-juros'), data: $('#p-data', dlg).value,
        }), 'Pagamento registrado');
        irPara('impostos');
      }, 'Registrar')));
}

/* ── relatórios ────────────────────────────────────────────────────────── */

async function verRelatorios() {
  const lista = await api('relatorios_disponiveis');
  const ano = new Date().getFullYear();
  $('#view').innerHTML = `
    <div class="bloco" style="margin-bottom:1rem">
      <div class="form-grade">
        <div class="campo"><label for="r-qual">Relatório</label>
          <select id="r-qual">${lista.map(r =>
            `<option value="${r.chave}">${esc(r.titulo)}</option>`).join('')}</select></div>
        <div class="campo"><label for="r-ano">Ano</label>
          <input id="r-ano" value="${ano}"></div>
        <div class="campo"><button type="button" class="primario" id="r-gerar">Gerar</button></div>
        <div class="campo"><button type="button" class="secundario" id="r-html">Salvar HTML</button></div>
        <div class="campo"><button type="button" class="secundario" id="r-csv">Salvar CSV</button></div>
      </div>
    </div>
    <div id="r-saida"></div>`;

  const params = () => ({ ano: $('#r-ano').value, meses: 12 });
  const gerar = async () => {
    const r = await tentar(() => api('relatorio', $('#r-qual').value, params()));
    $('#r-saida').innerHTML = `<div class="bloco"><h3>${esc(r.titulo)}</h3>
      ${tabela(r.colunas, r.linhas.map(l => l.map(esc)), { numericas: r.numericas })}
      <ul class="aviso-lista">${[...r.rodape, ...r.avisos]
        .map(t => `<li>${esc(t)}</li>`).join('')}</ul></div>`;
  };
  $('#r-gerar').addEventListener('click', gerar);
  $('#r-qual').addEventListener('change', gerar);
  const salvar = formato => async () => {
    const r = await tentar(() => api('salvar_relatorio', $('#r-qual').value,
      formato, params()));
    toast(r.salvo ? 'Salvo em ' + r.caminho : 'Salvamento cancelado');
  };
  $('#r-html').addEventListener('click', salvar('html'));
  $('#r-csv').addEventListener('click', salvar('csv'));
  await gerar();
}

/* ── configurações ─────────────────────────────────────────────────────── */

async function verConfig() {
  const [cfg, cad] = await Promise.all([api('config'), cadastros()]);
  ESTADO.config = cfg;
  $('#view').innerHTML = `
    <div class="bloco" style="margin-bottom:1rem"><h3>Aparência</h3>
      <div class="form-grade">
        <div class="campo"><label for="c-tema">Tema</label>
          <select id="c-tema">
            ${[['atrium', 'Atrium (claro)'], ['cera', 'Cera (sépia)'],
               ['aerarium', 'Aerarium (escuro)']].map(([v, t]) =>
              `<option value="${v}"${cfg.tema === v ? ' selected' : ''}>${t}</option>`).join('')}
          </select></div>
        <div class="campo"><label for="c-dalt">Paleta daltônica</label>
          <select id="c-dalt">
            <option value="0"${cfg.paleta_daltonica === '0' ? ' selected' : ''}>Verde e vermelho</option>
            <option value="1"${cfg.paleta_daltonica === '1' ? ' selected' : ''}>Azul e laranja</option>
          </select></div>
      </div>
      <p class="trava-nota">Alta e baixa sempre trazem sinal e seta além da cor —
        a paleta é reforço, não informação.</p>
    </div>

    <div class="bloco" style="margin-bottom:1rem"><h3>Rede e importação</h3>
      <div class="form-grade">
        <div class="campo"><label for="c-cot">Cotação online</label>
          <select id="c-cot">
            <option value="0"${cfg.cotacao_online === '0' ? ' selected' : ''}>Desligada</option>
            <option value="1"${cfg.cotacao_online === '1' ? ' selected' : ''}>Ligada</option>
          </select></div>
        <div class="campo"><label for="c-cpf">CPF (abre nota protegida)</label>
          <input id="c-cpf" value="${esc(cfg.cpf)}" placeholder="000.000.000-00"></div>
        <div class="campo"><label for="c-senhas">Senhas de PDF (separadas por vírgula)</label>
          <input id="c-senhas" value="${esc(cfg.senhas_pdf)}"></div>
      </div>
      <p class="trava-nota">Com a cotação ligada, só o ticker sai daqui — nunca
        quantidade, valor ou documento. O CPF fica dentro do cofre cifrado e é
        usado apenas para tentar abrir notas protegidas.</p>
    </div>

    <div class="bloco" style="margin-bottom:1rem"><h3>Segurança</h3>
      <div class="form-grade">
        <div class="campo"><label for="s-atual">Senha atual</label>
          <input type="password" id="s-atual"></div>
        <div class="campo"><label for="s-nova">Nova senha</label>
          <input type="password" id="s-nova"></div>
        <div class="campo"><button type="button" class="secundario" id="btn-senha">
          Trocar senha</button></div>
      </div>
    </div>

    <div class="bloco"><h3>Cadastros</h3>
      <div class="form-grade">
        <div class="campo"><button type="button" class="secundario" id="btn-ativo">
          Novo ativo</button></div>
        <div class="campo"><button type="button" class="secundario" id="btn-inst">
          Nova instituição</button></div>
      </div>
      <div class="painel-colunas" style="margin-top:1rem">
        <div>${tabela(['Ativo', 'Nome', 'Classe'],
          cad.ativos.map(a => [esc(a.ticker), esc(a.nome || '—'), esc(a.classe)]),
          { vazio: 'Nenhum ativo cadastrado' })}</div>
        <div>${tabela(['Instituição', 'CNPJ'],
          cad.instituicoes.map(i => [esc(i.nome), esc(i.cnpj || '—')]),
          { vazio: 'Nenhuma instituição cadastrada' })}</div>
      </div>
    </div>`;

  const salvar = async () => {
    ESTADO.config = await tentar(() => api('salvar_config', {
      tema: $('#c-tema').value, paleta_daltonica: $('#c-dalt').value,
      cotacao_online: $('#c-cot').value, cpf: $('#c-cpf').value,
      senhas_pdf: $('#c-senhas').value,
    }), 'Configurações salvas');
    aplicarTema();
  };
  ['#c-tema', '#c-dalt', '#c-cot'].forEach(s =>
    $(s).addEventListener('change', salvar));
  ['#c-cpf', '#c-senhas'].forEach(s => $(s).addEventListener('change', salvar));

  $('#btn-senha').addEventListener('click', async () => {
    const r = await tentar(() => api('trocar_senha', $('#s-atual').value,
      $('#s-nova').value), 'Senha trocada');
    $('#s-atual').value = $('#s-nova').value = '';
    modal('Senha trocada', `<p>${esc(r.aviso)}</p>`, async () => {}, 'Entendi');
  });

  $('#btn-ativo').addEventListener('click', () => modal('Novo ativo', `
    <div class="form-grade">
      <div class="campo"><label for="a-ticker">Ticker</label><input id="a-ticker"></div>
      <div class="campo"><label for="a-nome">Nome</label><input id="a-nome"></div>
      <div class="campo"><label for="a-classe">Classe</label>
        <select id="a-classe">${['ACAO', 'FII', 'ETF', 'BDR', 'UNIT']
          .map(k => `<option>${k}</option>`).join('')}</select></div>
    </div>`, async dlg => {
      await tentar(() => api('cadastrar_ativo', {
        ticker: $('#a-ticker', dlg).value, nome: $('#a-nome', dlg).value,
        classe: $('#a-classe', dlg).value }), 'Ativo cadastrado');
      ESTADO.cadastros = null; irPara('config');
    }, 'Cadastrar'));

  $('#btn-inst').addEventListener('click', () => modal('Nova instituição', `
    <div class="form-grade">
      <div class="campo"><label for="i-nome">Nome</label><input id="i-nome"></div>
      <div class="campo"><label for="i-cnpj">CNPJ</label><input id="i-cnpj"></div>
    </div>`, async dlg => {
      await tentar(() => api('cadastrar_instituicao', {
        nome: $('#i-nome', dlg).value, cnpj: $('#i-cnpj', dlg).value }),
        'Instituição cadastrada');
      ESTADO.cadastros = null; irPara('config');
    }, 'Cadastrar'));
}

/* ── partida ───────────────────────────────────────────────────────────── */

if (window.pywebview && window.pywebview.api) iniciar();
else window.addEventListener('pywebviewready', iniciar);
