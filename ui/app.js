/* Peculium — lógica da interface e ponte com o Python.
   Script clássico de propósito: o pywebview abre o index por caminho de arquivo
   e o CORS bloqueia type="module" em file://, o que abriria a janela em branco. */

const $ = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

const brl = v => (Number(v) || 0).toLocaleString('pt-BR',
  { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const qtd = v => (Number(v) || 0).toLocaleString('pt-BR', { maximumFractionDigits: 8 });
/* Preço unitário tem casas que preço de tela não tem: os CDBs são emitidos a
   R$ 0,01 e, com duas casas, a coluna inteira virava "0,01". */
const pu = v => (Number(v) || 0).toLocaleString('pt-BR',
  { minimumFractionDigits: 2, maximumFractionDigits: 6 });

/* Alta e baixa nunca só por cor: sinal, seta e valor sempre juntos.
   `moeda` põe o R$ DEPOIS da seta — "R$ ▲ +2,60" lê como se o cifrão fosse de
   outra frase. */
function sinal(v, moeda = false) {
  const n = Number(v) || 0;
  const cifrao = moeda ? 'R$ ' : '';
  if (Math.abs(n) < 0.005) return `<span>${cifrao}${brl(0)}</span>`;
  const classe = n > 0 ? 'alta' : 'baixa';
  return `<span class="${classe}">${n > 0 ? '▲ +' : '▼ −'}${cifrao}${brl(Math.abs(n))}</span>`;
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
  // O cabeçalho é um <button> de verdade, e não um <th> com onclick: ordenar
  // precisa funcionar pelo teclado, e botão nativo já traz foco, Enter e Espaço.
  const cab = colunas.map((c, i) =>
    `<th class="${numericas.includes(i) ? 'n' : ''}" aria-sort="none">
       <button type="button" class="ord" data-col="${i}">${esc(c)}<span
         class="seta" aria-hidden="true"></span></button></th>`).join('');
  const corpo = linhas.map(l => {
    const celulas = (l.celulas || l).map((v, i) =>
      `<td class="${numericas.includes(i) ? 'n' : ''}">${v}</td>`).join('');
    const editavel = l.editar
      ? ` data-editar="${l.editar}" tabindex="0" role="button" title="Clique para editar"`
      : '';
    return `<tr class="${l.classe || ''}${l.editar ? ' editavel' : ''}"${editavel}>${celulas}</tr>`;
  }).join('');
  return `<table><thead><tr>${cab}</tr></thead><tbody>${corpo}</tbody></table>`;
}

/* ── ordenação das tabelas ─────────────────────────────────────────────── */

const DATA_BR = /^(\d{2})\/(\d{2})\/(\d{4})$/;
const COMPETENCIA_BR = /^(\d{2})\/(\d{4})$/;

/* A célula é texto já formatado para leitura; ordenar por ele direto poria
   10/01/2026 antes de 05/12/2025 e "1.029,52" antes de "285". */
function chaveDeOrdem(texto) {
  const t = String(texto).trim();
  let m = DATA_BR.exec(t);
  if (m) return Number(m[3] + m[2] + m[1]);
  m = COMPETENCIA_BR.exec(t);
  if (m) return Number(m[2] + m[1]);
  // o menos que o sinal() desenha é U+2212, não o hífen do teclado
  const limpo = t.replace(/^R\$\s*/, '').replace(/[▲▼\s%]/g, '')
    .replace('−', '-').replace(/\./g, '').replace(',', '.');
  if (limpo && /^[+-]?\d+(\.\d+)?$/.test(limpo)) return Number(limpo);
  return t.toLowerCase();
}

function compararOrdem(a, b) {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  // número antes de texto: "—" e vazio não se misturam com valores
  if (typeof a === 'number') return -1;
  if (typeof b === 'number') return 1;
  return a.localeCompare(b, 'pt-BR');
}

function ordenarPor(botao) {
  const th = botao.closest('th');
  const tab = th.closest('table');
  const coluna = Number(botao.dataset.col);
  const descendente = th.getAttribute('aria-sort') === 'ascending';
  [...tab.tHead.rows[0].cells].forEach(c => c.setAttribute('aria-sort', 'none'));
  th.setAttribute('aria-sort', descendente ? 'descending' : 'ascending');

  const corpo = tab.tBodies[0];
  const sinalOrdem = descendente ? -1 : 1;
  // sort é estável: linhas com a mesma chave mantêm a ordem em que vieram
  [...corpo.rows]
    .sort((x, y) => compararOrdem(chaveDeOrdem(x.cells[coluna]?.textContent ?? ''),
                                  chaveDeOrdem(y.cells[coluna]?.textContent ?? ''))
                    * sinalOrdem)
    .forEach(tr => corpo.appendChild(tr));
}

// Delegado no documento: as tabelas nascem de innerHTML a cada troca de tela, e
// religar ouvinte a cada render seria uma linha esquecida em cada tela nova.
document.addEventListener('click', evento => {
  const botao = evento.target.closest('table th button.ord');
  if (botao) ordenarPor(botao);
});

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
  const total = d.patrimonio || 1;
  const pct = v => brl(100 * v / total) + '%';
  const alertas = d.alertas.map(a =>
    `<div class="alerta ${a.grave ? 'grave' : ''}">
       <span class="marcador">${a.grave ? '!' : 'i'}</span>
       <span>${esc(a.texto)}</span></div>`).join('');

  $('#view').innerHTML = `
    ${alertas}
    <div class="somas">
      ${soma('Patrimônio', 'R$ ' + brl(d.patrimonio),
             `${d.ativos} ativo(s) em ${d.classes.length} classe(s)`)}
      ${soma('Custo de aquisição', 'R$ ' + brl(d.custo),
             d.meses_de_aporte ? `aportado em ${d.meses_de_aporte} mês(es)` : '—')}
      ${soma('Resultado não realizado', sinal(d.resultado, true),
             d.custo
               ? (d.resultado >= 0 ? '+' : '−')
                 + brl(Math.abs(100 * d.resultado / d.custo)) + '% sobre o custo'
               : '—')}
      ${soma('Proventos no ano', 'R$ ' + brl(d.proventos_ano),
             d.meses_com_provento
               ? `média de R$ ${brl(d.proventos_ano / d.meses_com_provento)} ao mês`
               : 'nenhum recebido este ano')}
    </div>

    <div class="painel-colunas">
      <div>
        <div class="bloco" style="margin-bottom:1rem"><h3>Composição da carteira</h3>
          ${faixaClasses(d.classes, total)}
          ${divergencia(d.divergencia)}
        </div>
      </div>
      <div>
        <div class="bloco" style="margin-bottom:1rem"><h3>Proventos mês a mês</h3>
          ${barrasProventos(d.proventos_mes || [])}
        </div>
        <div class="bloco"><h3>Aportes acumulados</h3>
          ${linhaAportes(d.aportes_mes || [])}
        </div>
      </div>
    </div>

    <div class="bloco" style="margin-top:1rem"><h3>Posições</h3>
      ${tabela(['Ativo', 'Classe', 'Quantidade', 'Preço médio', 'Valor', '% carteira'],
        d.posicoes.map(p => [
          esc(p.ticker), esc(nomeClasse(p.classe)), qtd(p.quantidade),
          pu(p.custo / (p.quantidade || 1)), brl(p.valor), pct(p.valor)]),
        { numericas: [2, 3, 4, 5],
          vazio: 'Carteira vazia — importe ou lance uma compra' })}
    </div>`;
}

const NOME_CLASSE = {
  ACAO: 'Ações', FII: 'Fundos imobiliários', ETF: 'ETF', BDR: 'BDR',
  UNIT: 'Units', RF: 'Renda fixa', TESOURO: 'Tesouro Direto',
};
const nomeClasse = c => NOME_CLASSE[c] || c;

function soma(rotulo, valor, nota) {
  return `<div class="soma"><div class="k">${esc(rotulo)}</div>
    <div class="v">${valor}</div><div class="n">${esc(nota)}</div></div>`;
}

/* Barra empilhada em vez de rosca: com três ou quatro classes ela compara
   proporções melhor, e não precisa de legenda separada para ser lida. */
function faixaClasses(classes, total) {
  if (!classes.length) return '<p class="vazio">Carteira vazia</p>';
  const faixa = classes.map((c, i) =>
    `<i style="width:${100 * c.valor / total}%;background:var(--serie${(i % 4) + 1})"
        title="${esc(nomeClasse(c.classe))}"></i>`).join('');
  const chaves = classes.map((c, i) => `
    <div><span><span class="pip" style="background:var(--serie${(i % 4) + 1})"></span>${esc(nomeClasse(c.classe))}
      · ${c.ativos}</span>
      <span>R$ ${brl(c.valor)} <b>${brl(100 * c.valor / total)}%</b></span></div>`).join('');
  return `<div class="faixa">${faixa}</div><div class="chaves">${chaves}</div>`;
}

/* O painel encara a diferença em vez de escondê-la: patrimônio que não bate com
   a corretora é o sintoma mais caro que este programa pode ter. */
function divergencia(d) {
  if (!d) return '';
  const lista = d.itens.map(i =>
    `<li><b>${esc(i.ticker)}</b> — ${esc(i.observacao)}</li>`).join('');
  return `<div class="nota-divergencia">
    <p><b>${d.itens.length} papel(is) a conferir.</b>
      Comparado com a posição da B3 de ${esc(d.data)}: ${d.confere} de ${d.total}
      conferem${d.a_mais ? `, e a B3 informa R$ ${brl(d.a_mais)} a mais` : ''}.</p>
    <ul>${lista}</ul></div>`;
}

function barrasProventos(meses) {
  if (!meses.length) return '<p class="vazio">Nenhum provento recebido</p>';
  const teto = Math.max(...meses.map(m => m.valor)) || 1;
  const larg = 400 / meses.length;
  const barras = meses.map((m, i) => {
    const h = Math.max(2, 88 * m.valor / teto);
    return `<rect x="${18 + i * larg + larg * 0.22}" y="${118 - h}"
              width="${larg * 0.56}" height="${h}" rx="2"
              fill="var(--serie${(i % 4) + 1})"></rect>
      <text x="${18 + i * larg + larg / 2}" y="${112 - h}" text-anchor="middle"
        font-family="var(--serif-valor)" font-size="10" fill="currentColor">${brl(m.valor)}</text>
      <text x="${18 + i * larg + larg / 2}" y="134" text-anchor="middle"
        font-size="9.5" fill="var(--suave)">${esc(m.competencia)}</text>`;
  }).join('');
  return `<svg viewBox="0 0 420 145" width="100%" height="145" role="img"
    aria-label="Proventos por mês">
    <line x1="14" y1="118" x2="414" y2="118" stroke="var(--borda)"/>${barras}</svg>`;
}

function linhaAportes(meses) {
  if (meses.length < 2) return '<p class="vazio">Aportes insuficientes para o gráfico</p>';
  const teto = Math.max(...meses.map(m => m.acumulado)) || 1;
  const x = i => 30 + i * (380 / (meses.length - 1));
  const y = v => 118 - 92 * v / teto;
  const pontos = meses.map((m, i) => `${x(i)} ${y(m.acumulado)}`).join(' L ');
  const bolas = meses.map((m, i) =>
    `<circle cx="${x(i)}" cy="${y(m.acumulado)}" r="3" fill="var(--serie1)"/>`).join('');
  const rotulos = meses.map((m, i) =>
    `<text x="${x(i)}" y="134" text-anchor="middle" font-size="9.5"
       fill="var(--suave)">${esc(m.competencia)}</text>`).join('');
  return `<svg viewBox="0 0 420 145" width="100%" height="145" role="img"
    aria-label="Aportes acumulados por mês">
    <line x1="24" y1="118" x2="414" y2="118" stroke="var(--borda)"/>
    <line x1="24" y1="72" x2="414" y2="72" stroke="var(--borda)" opacity=".45"/>
    <line x1="24" y1="26" x2="414" y2="26" stroke="var(--borda)" opacity=".45"/>
    <path d="M ${pontos}" fill="none" stroke="var(--serie1)" stroke-width="2.2"/>
    ${bolas}${rotulos}
    <text x="20" y="29" text-anchor="end" font-size="9.5"
      fill="var(--suave)">${teto >= 1000 ? (teto / 1000).toFixed(1).replace('.', ',') + ' K'
                                         : brl(teto)}</text>
    <text x="20" y="121" text-anchor="end" font-size="9.5" fill="var(--suave)">0</text></svg>`;
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
      // "ignoradas" precisa aparecer: sem isso, importar a posição da B3 e
      // logo depois cotar mostrava zero atualizações e nenhuma explicação
      const falhas = Object.keys(r.falhas).length;
      toast(`${r.atualizadas} cotação(ões) atualizada(s)`
          + (r.ignoradas ? `, ${r.ignoradas} já tinha(m) preço de fonte melhor` : '')
          + (falhas ? `, ${falhas} falha(s)` : ''));
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
                  p.pu == null ? '—' : pu(p.pu), brl(p.bruto),
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
      <p>O Peculium reconhece o arquivo sozinho — escolha e ele sabe o que fazer.
        Estes são os que valem a pena baixar, na ordem:</p>
      <ol class="guia-importar">
        <li><strong>Negociação</strong> — B3, Extratos › Negociação (XLSX ou CSV).<br>
          Toda compra e venda. <em>É o que forma a carteira.</em></li>
        <li><strong>Movimentação</strong> — B3, Extratos › Movimentação (XLSX ou CSV).<br>
          Dividendos, JCP, rendimento de FII, bonificação, aplicação e resgate de
          renda fixa. <em>É o que forma o caixa.</em></li>
        <li><strong>Nota de corretagem</strong> — no site da corretora (PDF).<br>
          Só a nota traz corretagem, emolumentos e taxas.
          <em>Sem ela o custo fica menor do que foi, e o imposto maior.</em></li>
        <li><strong>Posição</strong> — B3, Extratos › Posição (XLSX).<br>
          Confere a sua carteira contra a da B3 e traz os preços oficiais do dia
          — inclusive o do Tesouro IPCA+, que não tem outro jeito de precificar.
          <em>Não cria lançamento nenhum.</em></li>
      </ol>
      <p class="trava-nota"><strong>Baixe Negociação e Movimentação pelo período
        mais longo que a B3 deixar.</strong> Compra que ficou de fora não some da
        conta: ela reaparece na Posição como divergência, e sem o custo de
        aquisição o preço médio e o imposto saem errados.</p>
      <p class="trava-nota"><strong>Proventos Recebidos</strong> e o
        <strong>consolidado mensal</strong> não precisam ser importados: o
        primeiro repete o que já vem na Movimentação, e o segundo é o mesmo
        retrato da Posição em outra data.</p>
      <p class="trava-nota">Nada é gravado antes da sua conferência. O arquivo
        original não é guardado — ele traz CPF.</p>
      <button type="button" class="primario" id="btn-escolher">Escolher arquivo…</button>
    </div>
    <div id="conferencia"></div>`;
  $('#btn-escolher').addEventListener('click', async () => {
    const caminho = await tentar(() => api('escolher_arquivo'));
    if (!caminho) return;
    const c = await tentar(() => api('importar', caminho));
    ({ NOTA: conferirNota, NOTA_RF: conferirNotaRF, B3: conferirB3,
       POSICAO: conferirPosicao })[c.origem](c);
  });
}

const SITUACOES = {
  CONFERE: ['confere', 'ok'],
  SO_NA_B3: ['só na B3', 'grave'],
  SO_NO_PECULIUM: ['só aqui', 'grave'],
  QUANTIDADE_DIFERE: ['quantidade difere', 'grave'],
};

function conferirPosicao(c) {
  const problemas = c.divergencias.filter(d => d.situacao !== 'CONFERE');
  $('#conferencia').innerHTML = `
    <div class="bloco" style="margin-top:1rem">
      <h3>Posição da B3 em ${esc(c.data)}</h3>
      <div class="cartoes">
        ${cartao('Papéis na B3', c.itens.length)}
        ${cartao('Conferem', c.confere)}
        ${cartao('A resolver', problemas.length)}
      </div>
      <p class="trava-nota">Retrato não vira lançamento: ele traz quantidade e
        valor de mercado, nunca o custo de aquisição. Gravar cria os
        <strong>preços do dia</strong> e completa o cadastro de renda fixa — o
        que faltar de compra ou venda você lança à mão.</p>
      ${listaAvisos(c.avisos)}
      ${problemas.length
        ? `<h3>Divergências</h3>
           ${tabela(['Ativo', 'Situação', 'No Peculium', 'Na B3', 'O que fazer'],
             problemas.map(d => [
               esc(d.ticker),
               `<span class="selo-situacao ${SITUACOES[d.situacao][1]}">${SITUACOES[d.situacao][0]}</span>`,
               qtd(d.no_peculium), qtd(d.na_b3), esc(d.observacao)]),
             { numericas: [2, 3] })}`
        : '<p class="trava-nota">Nenhuma divergência: a carteira calculada bate '
          + 'com a da B3, papel por papel.</p>'}
      <h3>Preços do dia</h3>
      ${tabela(['Ativo', 'Classe', 'Quantidade', 'Preço', 'Valor', 'Instituição'],
        c.itens.map(i => [esc(i.ticker), esc(i.classe), qtd(i.quantidade),
          i.preco == null ? '—' : pu(i.preco),
          i.valor == null ? '—' : brl(i.valor), esc(i.instituicao)]),
        { numericas: [2, 3, 4] })}
      <menu style="display:flex;gap:.6rem;justify-content:flex-end;padding:0">
        <button type="button" class="primario" id="btn-gravar-posicao">
          Gravar preços e cadastro</button>
      </menu>
    </div>`;
  $('#btn-gravar-posicao').addEventListener('click', async () => {
    const r = await tentar(() => api('confirmar_importacao', c.token));
    toast(`${r.cotacoes} cotação(ões), ${r.ativos_novos} ativo(s) e `
        + `${r.titulos} título(s) — nenhum lançamento`);
    irPara('carteira');
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
  // quem não tem renda fixa nunca abre a Carteira, e é lá que mora o botão que
  // baixa as séries do BCB — sem este, a Selic dos juros nunca chegaria
  $('#acoes-view').append(botao('Atualizar Selic', async () => {
    const r = await tentar(() => api('atualizar_series'));
    if (r.desligada)
      return toast('Ligue a rede em Configurações para baixar as séries do BCB', true);
    toast(`${r.gravados} valor(es) de série atualizado(s)`);
    irPara('impostos');
  }));
  const situacaoClasse = s =>
    s === 'PAGO' ? 'ok' : (s === 'VENCIDO' || s === 'PARCIAL' ? 'grave' : '');

  $('#view').innerHTML = `
    <div class="bloco" style="margin-bottom:1rem"><h3>Contas a pagar — DARF</h3>
      ${tabela(['Competência', 'Vencimento', 'Apurado', 'Pago', 'Situação',
                'Atraso', 'Multa', 'Juros', 'Total a pagar', ''],
        d.obrigacoes.map(o => [
          esc(o.competencia), esc(o.vencimento || '—'), brl(o.valor_apurado),
          o.valor_pago ? brl(o.valor_pago) : '—',
          `<span class="selo-situacao ${situacaoClasse(o.situacao)}">${o.situacao}</span>`,
          o.dias_atraso ? o.dias_atraso + ' dia(s)' : '—',
          o.multa ? brl(o.multa) : '—',
          // travessão não é zero: quer dizer que falta a Selic de algum mês, e a
          // lista de avisos abaixo diz qual
          o.juros == null
            ? `<span class="selo-situacao grave" title="falta a Selic de algum mês do período">—</span>`
            : brl(o.juros),
          brl(o.total_a_pagar),
          o.total_a_pagar > 0
            ? `<button type="button" class="link" data-pagar="${esc(o.competencia)}"
                 data-valor="${o.total_a_pagar}" data-multa="${o.multa || 0}"
                 data-juros="${o.juros || 0}">registrar pagamento</button>`
            : '']),
        { numericas: [2, 3, 5, 6, 7, 8], vazio: 'Nenhum DARF apurado' })}
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
          <input id="p-valor" value="${(Number(b.dataset.valor) - Number(b.dataset.multa)
                                        - Number(b.dataset.juros)).toFixed(2)}"></div>
        <div class="campo"><label for="p-multa">Multa</label>
          <input id="p-multa" value="${Number(b.dataset.multa).toFixed(2)}"></div>
        <div class="campo"><label for="p-juros">Juros</label>
          <input id="p-juros" value="${Number(b.dataset.juros).toFixed(2)}"></div>
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
      <p class="trava-nota">Clique numa linha para editar. Renomear um ativo é
        seguro: os lançamentos apontam para o cadastro, não para o texto do
        ticker. Trocar a <strong>classe</strong>, porém, muda a alíquota do
        imposto.</p>
      <div class="painel-colunas" style="margin-top:1rem">
        <div>${tabela(['Ativo', 'Nome', 'Classe'],
          cad.ativos.map(a => ({
            classe: a.ativo ? '' : 'arquivado',
            editar: `ativo:${a.id}`,
            celulas: [esc(a.ticker), esc(a.nome || '—'), esc(a.classe)] })),
          { vazio: 'Nenhum ativo cadastrado' })}</div>
        <div>${tabela(['Instituição', 'CNPJ'],
          cad.instituicoes.map(i => ({
            classe: i.ativo ? '' : 'arquivado',
            editar: `instituicao:${i.id}`,
            celulas: [esc(i.nome), esc(i.cnpj || '—')] })),
          { vazio: 'Nenhuma instituição cadastrada' })}</div>
      </div>
    </div>

    <div class="bloco zona-risco" style="margin-top:1rem"><h3>Zona de risco</h3>
      <p>Apaga <strong>todos os registros</strong>: lançamentos, ativos,
        instituições, importações, notas, cotações, títulos de renda fixa,
        pagamentos de DARF e o histórico de auditoria.</p>
      <p class="trava-nota">Ficam de fora só suas preferências (tema, CPF, senhas
        de PDF) e as séries do Banco Central, que são dado público em cache. A
        senha mestra e a chave de recuperação <strong>não mudam</strong> — o
        cofre é o mesmo, vazio.</p>
      <p class="trava-nota">Uma cópia do cofre é guardada antes, com a data no
        nome e fora do rodízio dos três backups automáticos. Ela abre com a senha
        de agora.</p>
      <button type="button" class="perigo" id="btn-reset">Apagar todos os dados…</button>
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

  $('#btn-reset').addEventListener('click', () => modal('Apagar todos os dados', `
    <p>Isto <strong>não tem desfazer</strong> dentro do programa. A volta atrás é
      abrir a cópia que será guardada agora.</p>
    <p class="trava-nota">Para confirmar, digite <code>APAGAR TUDO</code> abaixo.
      Um botão só não basta para uma operação sem volta.</p>
    <div class="campo"><label for="r-frase">Confirmação</label>
      <input id="r-frase" autocomplete="off" placeholder="APAGAR TUDO"></div>`,
    async dlg => {
      const r = await tentar(() => api('resetar', $('#r-frase', dlg).value));
      ESTADO.cadastros = null;
      modal('Cofre esvaziado', `
        <p>${r.total} registro(s) apagado(s) em ${Object.keys(r.apagados).length}
          tabela(s).</p>
        <p class="trava-nota">Cópia de antes guardada em:<br>
          <code>${esc(r.backup)}</code></p>`,
        async () => { irPara('painel'); }, 'Entendi');
    }, 'Apagar tudo'));

  $('#btn-ativo').addEventListener('click', () => formAtivo());
  $('#btn-inst').addEventListener('click', () => formInstituicao());

  $$('#view tr[data-editar]').forEach(tr => {
    const abrir = () => {
      const [tipo, id] = tr.dataset.editar.split(':');
      if (tipo === 'ativo') formAtivo(cad.ativos.find(a => String(a.id) === id));
      else formInstituicao(cad.instituicoes.find(i => String(i.id) === id));
    };
    tr.addEventListener('click', abrir);
    tr.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrir(); }
    });
  });
}

const CLASSES_ATIVO = ['ACAO', 'FII', 'ETF', 'BDR', 'UNIT', 'RF', 'TESOURO'];

function formAtivo(a) {
  modal(a ? `Editar ${a.ticker}` : 'Novo ativo', `
    <div class="form-grade">
      <div class="campo"><label for="a-ticker">Ticker</label>
        <input id="a-ticker" value="${a ? esc(a.ticker) : ''}"></div>
      <div class="campo"><label for="a-nome">Nome</label>
        <input id="a-nome" value="${a && a.nome ? esc(a.nome) : ''}"></div>
      <div class="campo"><label for="a-classe">Classe</label>
        <select id="a-classe">${CLASSES_ATIVO.map(k =>
          `<option${a && a.classe === k ? ' selected' : ''}>${k}</option>`).join('')}</select></div>
      ${a ? `<div class="campo"><label for="a-situacao">Situação</label>
        <select id="a-situacao">
          <option value="1"${a.ativo ? ' selected' : ''}>Em uso</option>
          <option value="0"${a.ativo ? '' : ' selected'}>Arquivado</option>
        </select></div>` : ''}
    </div>
    ${a ? `<p class="trava-nota">Renomear é seguro: os lançamentos apontam para o
      cadastro, não para o texto do ticker. <strong>Arquivar não apaga nem
      esconde lançamento</strong> — o ativo só deixa de ser oferecido em
      formulário novo.</p>` : ''}`,
    async dlg => {
      const dados = { ticker: $('#a-ticker', dlg).value, nome: $('#a-nome', dlg).value,
                      classe: $('#a-classe', dlg).value };
      if (a) dados.ativo = Number($('#a-situacao', dlg).value);
      await tentar(() => (a ? api('editar_ativo', a.id, dados)
                            : api('cadastrar_ativo', dados)),
        a ? 'Ativo atualizado' : 'Ativo cadastrado');
      ESTADO.cadastros = null; irPara('config');
    }, a ? 'Salvar' : 'Cadastrar');
}

function formInstituicao(i) {
  // O CNPJ vem primeiro porque é ele que preenche o resto: digita, busca, e a
  // razão social cai no campo de baixo. Mesmo caminho da família SGx.
  modal(i ? `Editar ${i.nome}` : 'Nova instituição', `
    <div class="form-grade">
      <div class="campo campo-largo"><label for="i-cnpj">CNPJ</label>
        <div class="campo-com-acao">
          <input id="i-cnpj" inputmode="numeric" placeholder="00.000.000/0000-00"
            value="${i && i.cnpj ? esc(i.cnpj) : ''}">
          <button type="button" class="secundario" id="i-buscar">Buscar</button>
        </div>
        <p class="trava-nota" id="i-resultado">Opcional. Ao buscar, <strong>só o
          CNPJ digitado sai daqui</strong> — nada da sua carteira.</p></div>
      <div class="campo"><label for="i-nome">Nome</label>
        <input id="i-nome" value="${i ? esc(i.nome) : ''}"></div>
      ${i ? `<div class="campo"><label for="i-situacao">Situação</label>
        <select id="i-situacao">
          <option value="1"${i.ativo ? ' selected' : ''}>Em uso</option>
          <option value="0"${i.ativo ? '' : ' selected'}>Arquivada</option>
        </select></div>` : ''}
    </div>`,
    async dlg => {
      const dados = { nome: $('#i-nome', dlg).value, cnpj: $('#i-cnpj', dlg).value };
      if (i) dados.ativo = Number($('#i-situacao', dlg).value);
      await tentar(() => (i ? api('editar_instituicao', i.id, dados)
                            : api('cadastrar_instituicao', dados)),
        i ? 'Instituição atualizada' : 'Instituição cadastrada');
      ESTADO.cadastros = null; irPara('config');
    }, i ? 'Salvar' : 'Cadastrar');

  $('#i-buscar').addEventListener('click', async () => {
    const aviso = $('#i-resultado');
    aviso.textContent = 'Consultando…';
    const achado = await tentar(() => api('consultar_cnpj', $('#i-cnpj').value));
    // `tentar` já mostrou o erro; aqui só resta dizer o que fazer sem a consulta
    if (!achado) { aviso.textContent = 'Sem consulta — digite o nome à mão.'; return; }
    $('#i-cnpj').value = achado.cnpj;
    $('#i-nome').value = achado.nome;
    aviso.textContent = `${achado.nome} — ${achado.situacao || 'situação não informada'}`
                      + ` (via ${achado.fonte})`;
  });
}

/* ── partida ───────────────────────────────────────────────────────────── */

if (window.pywebview && window.pywebview.api) iniciar();
else window.addEventListener('pywebviewready', iniciar);
