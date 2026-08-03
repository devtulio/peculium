/* Ponte falsa para desenvolvimento: `index.html?mock=1`.
   Existe porque o Playwright e o navegador não conseguem falar com o pywebview —
   o mesmo truque do Licitarium. Nenhum dado aqui é real. */

(function () {
  const ok = dados => Promise.resolve({ ok: true, dados });
  const erro = msg => Promise.resolve({ ok: false, erro: msg });

  let config = {
    tema: 'atrium', paleta_daltonica: '0', cotacao_online: '0',
    cpf: '', senhas_pdf: '',
  };

  const CARTEIRA = [
    { ativo_id: 1, ticker: 'KLBN4', classe: 'ACAO', quantidade: 285,
      preco_medio: 3.5411, custo: 1009.21, cotacao: 3.72, mercado: 1060.20 },
    { ativo_id: 2, ticker: 'MXRF11', classe: 'FII', quantidade: 100,
      preco_medio: 9.7346, custo: 973.46, cotacao: 9.41, mercado: 941.00 },
    { ativo_id: 3, ticker: 'SNAG11', classe: 'FII', quantidade: 100,
      preco_medio: 10.0509, custo: 1005.09, cotacao: null, mercado: 1005.09 },
  ];

  const LANCAMENTOS = [
    { id: 3, data_br: '21/07/2026', tipo: 'COMPRA', ticker: 'KLBN4',
      instituicao: 'XP INVESTIMENTOS', quantidade: 200, preco: 3.5, valor: 700,
      custos: 8.22, origem: 'NOTA', nota: '140560283' },
    { id: 2, data_br: '18/05/2026', tipo: 'DIVIDENDO', ticker: 'MXRF11',
      instituicao: 'XP INVESTIMENTOS', quantidade: 0, preco: 0, valor: 12,
      custos: 0, origem: 'MANUAL' },
    { id: 1, data_br: '05/01/2026', tipo: 'COMPRA', ticker: 'MXRF11',
      instituicao: 'XP INVESTIMENTOS', quantidade: 100, preco: 9.71, valor: 971,
      custos: 2.2, origem: 'B3_NEGOCIACAO', estornado_por: null },
  ];

  const RELATORIO = {
    titulo: 'Fluxo de caixa dos proventos',
    colunas: ['Competência', 'Dividendos', 'JCP', 'Rendimentos', 'IRRF', 'Total',
              'Média 3 meses'],
    linhas: [['05/2026', '0,00', '0,00', '12,00', '0,00', '12,00', '12,00'],
             ['06/2026', '0,00', '0,00', '0,00', '0,00', '0,00', '6,00'],
             ['07/2026', '0,00', '0,00', '21,00', '0,00', '21,00', '11,00']],
    rodape: ['Recebido em 3 mês(es): R$ 33,00', 'Média mensal: R$ 11,00',
             'Projeção anualizada (média × 12): R$ 132,00'],
    avisos: ['A projeção é a média do período multiplicada por 12 — extrapolação simples.'],
    numericas: [1, 2, 3, 4, 5, 6],
  };

  window.pywebview = {
    api: {
      estado: () => ok({ versao: '0.1.0', existe: true, aberto: false,
                         caminho: 'mock', preferencias: { tema: 'atrium' } }),
      abrir_cofre: senha => senha === 'mock'
        ? ok({ config, versao: '0.1.0' })
        : erro('senha ou chave de recuperação incorreta'),
      criar_cofre: () => ok({ chave_recuperacao:
        'JHZT-KEE5-FZWP-6MGZ-HDPA-UDLF-YERR-DRUS-RD6N-SHOH-EGWO-XMNS-FHIQ' }),
      abrir_com_recuperacao: () => ok({ config, versao: '0.1.0' }),
      trocar_senha: () => ok({ aviso: 'Os backups anteriores continuam abrindo com a senha antiga.' }),
      config: () => ok(config),
      salvar_config: mudancas => { config = { ...config, ...mudancas }; return ok(config); },

      painel: () => ok({
        patrimonio: 3006.29, custo: 2987.76, resultado: 18.53,
        proventos_ano: 33, aportes_ano: 2987.76, ativos: 3,
        alertas: [
          { tipo: 'darf', grave: true,
            texto: 'DARF 06/2026 de R$ 1.533,00 vencido em 31/07/2026' },
          { tipo: 'cotacao', grave: false,
            texto: '1 ativo(s) sem cotação, avaliados pelo preço médio' }],
        classes: [{ classe: 'FII', valor: 1946.09 }, { classe: 'ACAO', valor: 1060.2 }],
        maiores: CARTEIRA.map(p => ({ ticker: p.ticker, classe: p.classe,
                                      valor: p.mercado, custo: p.custo })),
      }),
      carteira: () => ok(CARTEIRA),
      listar_lancamentos: () => ok(LANCAMENTOS),
      cadastros: () => ok({
        ativos: CARTEIRA.map(p => ({ id: p.ativo_id, ticker: p.ticker,
                                     nome: null, classe: p.classe, ativo: 1 })),
        instituicoes: [{ id: 1, nome: 'XP INVESTIMENTOS', cnpj: '02332886000104', ativo: 1 }],
        tipos: ['COMPRA', 'VENDA', 'BONIFICACAO', 'SUBSCRICAO', 'DIVIDENDO', 'JCP',
                'RENDIMENTO', 'AMORTIZACAO', 'TAXA', 'IRRF', 'TRANSFERENCIA'],
        eventos: ['DESDOBRAMENTO', 'GRUPAMENTO', 'CONVERSAO', 'INCORPORACAO'],
      }),
      lancar: () => ok({ id: 99 }),
      estornar: () => ok({ id: 100 }),
      registrar_evento: () => ok({ id: 5 }),
      cadastrar_ativo: () => ok({ id: 9 }),
      cadastrar_instituicao: () => ok({ id: 9 }),
      cotar: () => ok({ atualizadas: 2, ignoradas: 0, falhas: {}, desligada: false }),

      impostos: () => ok({
        ano: 2026,
        baldes: [{ competencia: '06/2026', balde: 'SWING', valor_vendas: 30000,
                   resultado: 10000, compensado: 0, base: 10000, imposto: 1500,
                   irrf: 0, a_pagar: 1500 }],
        prejuizo: { SWING: 0, DAY_TRADE: 0, FII: 320.5 },
        avisos: [],
        obrigacoes: [{ competencia: '06/2026', codigo: '6015',
                       vencimento: '31/07/2026', valor_apurado: 1500,
                       valor_pago: 0, situacao: 'VENCIDO', dias_atraso: 3,
                       multa: 14.85, juros: null, total_a_pagar: 1514.85,
                       observacoes: ['multa de mora de 0,33% ao dia (teto de 20%); juros dependem da série Selic'] }],
        anos: ['2026'],
      }),
      pagar: () => ok({ id: 1 }),

      relatorios_disponiveis: () => ok([
        { chave: 'posicao', titulo: 'Posição consolidada' },
        { chave: 'fluxo', titulo: 'Fluxo de caixa dos proventos' },
        { chave: 'apuracao', titulo: 'Apuração de IR' }]),
      relatorio: () => ok(RELATORIO),
      salvar_relatorio: () => ok({ salvo: true, caminho: 'C:\\mock\\relatorio.html' }),

      escolher_arquivo: () => ok('C:\\mock\\2026 07 21 NOTA 140560283.pdf'),
      importar: () => ok({
        token: 'imp1', origem: 'NOTA',
        nota: { numero: '140560283', corretora: 'CORRETORA FICTÍCIA',
                data: '21/07/2026', operacoes: 997.5, custos: 11.71, liquido: 1009.21 },
        ja_importada: false,
        avisos: ['O relatório de Negociação da B3 não traz corretagem: lance os custos à parte.'],
        itens: [
          { situacao: 'SEM_ATIVO', especificacao: 'KLABIN S/A PN N2', ticker: '',
            motivo: 'a nota não traz o código; informe o ticker uma vez',
            sentido: 'COMPRA', quantidade: 200, preco: 3.5, custos: 8.22 },
          { situacao: 'CRIA', especificacao: 'FII MAXI REN MXRF11 CI', ticker: 'MXRF11',
            motivo: 'sem contraparte na B3: a nota cria o negócio',
            sentido: 'COMPRA', quantidade: 100, preco: 9.71, custos: 2.2 }],
      }),
      confirmar_importacao: () => ok({ criados: 2, enriquecidos: 0 }),
    },
  };

  window.dispatchEvent(new Event('pywebviewready'));
})();
