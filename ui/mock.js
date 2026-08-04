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
    // 30/01 depois de 05/01 e antes de 18/05: por texto "30/01/2026" iria para o
    // fim da lista, então esta linha é o que separa ordenar por data de ordenar
    // por string
    { id: 4, data_br: '30/01/2026', tipo: 'TAXA', ticker: 'MXRF11',
      instituicao: 'XP INVESTIMENTOS', quantidade: 0, preco: 0, valor: 1.5,
      custos: 0, origem: 'MANUAL' },
    { id: 3, data_br: '21/07/2026', tipo: 'COMPRA', ticker: 'KLBN4',
      instituicao: 'XP INVESTIMENTOS', quantidade: 200, preco: 3.5, valor: 700,
      custos: 8.22, origem: 'NOTA', nota: '140560283',
      ativo_id: 1, instituicao_id: 1, irrf: 0, obs: null },
    { id: 2, data_br: '18/05/2026', tipo: 'DIVIDENDO', ticker: 'MXRF11',
      instituicao: 'XP INVESTIMENTOS', quantidade: 0, preco: 0, valor: 12,
      custos: 0, origem: 'MANUAL', ativo_id: 2, instituicao_id: 1, irrf: 0,
      obs: 'conferido com o informe' },
    { id: 1, data_br: '05/01/2026', tipo: 'COMPRA', ticker: 'MXRF11',
      instituicao: 'XP INVESTIMENTOS', quantidade: 100, preco: 9.71, valor: 971,
      custos: 2.2, origem: 'B3_NEGOCIACAO', estornado_por: null,
      ativo_id: 2, instituicao_id: 1, irrf: 0, obs: null },
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
      estado: () => ok({ versao: '0.10.1', existe: true, aberto: false,
                         caminho: 'mock', preferencias: { tema: 'atrium' } }),
      abrir_cofre: senha => senha === 'mock'
        ? ok({ config, versao: '0.10.1' })
        : erro('senha ou chave de recuperação incorreta'),
      criar_cofre: () => ok({ chave_recuperacao:
        'JHZT-KEE5-FZWP-6MGZ-HDPA-UDLF-YERR-DRUS-RD6N-SHOH-EGWO-XMNS-FHIQ' }),
      abrir_com_recuperacao: () => ok({ config, versao: '0.10.1' }),
      trocar_senha: () => ok({ aviso: 'Os backups anteriores continuam abrindo com a senha antiga.' }),
      fechar_cofre: () => ok({ fechado: true }),
      config: () => ok(config),
      salvar_config: mudancas => { config = { ...config, ...mudancas }; return ok(config); },

      painel: () => ok({
        patrimonio: 3006.29, custo: 2987.76, resultado: 18.53,
        proventos_ano: 33, aportes_ano: 2987.76, ativos: 3,
        meses_com_provento: 2, meses_de_aporte: 3,
        proventos_mes: [{ competencia: 'MAI/26', valor: 12 },
                        { competencia: 'JUN/26', valor: 0 },
                        { competencia: 'JUL/26', valor: 21 }],
        aportes_mes: [{ competencia: 'JAN/26', acumulado: 973.46 },
                      { competencia: 'MAI/26', acumulado: 1978.55 },
                      { competencia: 'JUL/26', acumulado: 2987.76 }],
        posicoes: [
          { ticker: 'KLBN4', classe: 'ACAO', quantidade: 285, valor: 1060.20, custo: 1009.21 },
          { ticker: 'SNAG11', classe: 'FII', quantidade: 100, valor: 1005.09, custo: 1005.09 },
          { ticker: 'MXRF11', classe: 'FII', quantidade: 100, valor: 941.00, custo: 973.46 }],
        divergencia: { data: '03/08/2026', confere: 3, total: 4, a_mais: 12.05,
          itens: [{ ticker: 'ROXO34', situacao: 'SO_NA_B3', no_peculium: 0, na_b3: 1,
                    valor: 12.05,
                    observacao: 'a B3 tem e o Peculium não — falta o lançamento de compra' }] },
        alertas: [
          { tipo: 'darf', grave: true,
            texto: 'DARF 06/2026 de R$ 1.533,00 vencido em 31/07/2026' },
          { tipo: 'cotacao', grave: false,
            texto: '1 ativo(s) sem cotação, avaliados pelo preço médio' }],
        classes: [{ classe: 'FII', valor: 1946.09, ativos: 2 },
                  { classe: 'ACAO', valor: 1060.2, ativos: 1 }],
        maiores: CARTEIRA.map(p => ({ ticker: p.ticker, classe: p.classe,
                                      valor: p.mercado, custo: p.custo })),
      }),
      carteira: () => ok(CARTEIRA),
      listar_lancamentos: () => ok(LANCAMENTOS),
      cadastros: () => ok({
        ativos: [...CARTEIRA.map(p => ({ id: p.ativo_id, ticker: p.ticker,
                                         nome: null, classe: p.classe, ativo: 1 })),
                 { id: 4, ticker: 'CDB5267UW6V', nome: 'CDB Banco XP', classe: 'RF', ativo: 1 },
                 { id: 5, ticker: 'TESOURO-IPCA-2035', nome: 'Tesouro IPCA+ 2035',
                   classe: 'TESOURO', ativo: 1 }],
        instituicoes: [{ id: 1, nome: 'XP INVESTIMENTOS', cnpj: '02.332.886/0001-04', ativo: 1 }],
        ativos_rf: true,
        tipos: ['COMPRA', 'VENDA', 'BONIFICACAO', 'SUBSCRICAO', 'DIVIDENDO', 'JCP',
                'RENDIMENTO', 'AMORTIZACAO', 'TAXA', 'IRRF', 'TRANSFERENCIA'],
        eventos: ['DESDOBRAMENTO', 'GRUPAMENTO', 'CONVERSAO', 'INCORPORACAO'],
      }),
      lancar: () => ok({ id: 99 }),
      estornar: () => ok({ id: 100 }),
      // contador para o teste provar que Esc NÃO executa a ação anterior
      anotar: id => { window.__anotou = (window.__anotou || 0) + 1;
                      return ok({ id }); },
      corrigir: id => ok({ estorno: 101, novo: 102 }),
      registrar_evento: () => ok({ id: 5 }),
      cadastrar_ativo: () => ok({ id: 9 }),
      cadastrar_instituicao: () => ok({ id: 9 }),
      editar_ativo: id => ok({ id }),
      editar_instituicao: id => ok({ id }),
      // 02.332.886/0001-04 é o CNPJ da XP, que já consta do cadastro de exemplo
      consultar_cnpj: v => (String(v).replace(/\D/g, '') === '02332886000104'
        ? ok({ cnpj: '02.332.886/0001-04', nome: 'XP INVESTIMENTOS CCTVM S/A',
               fantasia: 'XP INVESTIMENTOS', situacao: 'ATIVA', fonte: 'ReceitaWS' })
        : erro('CNPJ inválido: confira os 14 dígitos')),
      cotar: () => ok({ atualizadas: 2, ignoradas: 0, falhas: {}, desligada: false }),

      renda_fixa: () => ok({
        posicao: [
          { ativo_id: 4, ticker: 'CDB5267UW6V', classe: 'RF', emissor: 'BANCO XP S.A.',
            indexador: '100% do CDI', emissao: '2026-05-14', vencimento: '2028-05-15',
            vencido: false, quantidade: 1000, custo: 1000, pu: 1.02897,
            bruto: 1028.97, rendimento: 28.97, isento: false, erro: null },
          { ativo_id: 5, ticker: 'TESOURO-IPCA-2035', classe: 'TESOURO', emissor: 'TESOURO NACIONAL',
            indexador: 'IPCA + 6%', emissao: '2026-07-09', vencimento: '2035-05-15',
            vencido: false, quantidade: 0.67, custo: 2079.12, pu: null,
            bruto: 2079.12, rendimento: 0, isento: false,
            erro: 'indexador IPCA não tem curva calculável: informe o preço unitário à mão' },
        ],
        titulos: [], indexadores: { CDI: '% do CDI', PRE: 'taxa anual prefixada',
                                    IPCA: 'IPCA + taxa (preço digitado à mão)' },
        // o que o formulário preenche sozinho, da primeira aplicação lançada
        sugestoes: {
          4: { ativo_id: 4, emissao: '2026-05-14', pu_base: 1,
               emissor: 'BANCO XP S.A.', sem_curva: false },
          5: { ativo_id: 5, emissao: '2026-07-09', pu_base: 4158.25,
               emissor: 'TESOURO NACIONAL', sem_curva: true },
        },
        series: { CDI: ['2026-01-02', '2026-07-30'], SELIC: null, IPCA: null },
      }),
      cadastrar_titulo: () => ok({ ativo_id: 4 }),
      atualizar_curvas: () => ok({
        series: { gravados: 12, falhas: {}, desligada: false },
        curvas: { atualizados: 1, ignorados: 0,
                  falhas: { 'TESOURO-IPCA-2035': 'informe o preço unitário à mão' } },
      }),

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
                       multa: 14.85, juros: 15.00, total_a_pagar: 1529.85,
                       observacoes: ['multa de mora de 0,33% ao dia (teto de 20%) calculada até hoje',
                                     'juros pela Selic acumulada do mês seguinte ao vencimento até o anterior ao pagamento, mais 1% no mês do pagamento (Lei 9.430/96, art. 61 §3)'] }],
        anos: ['2026'],
      }),
      pagar: () => ok({ id: 1 }),
      atualizar_series: () => ok({ gravados: 7, falhas: {}, desligada: false,
                                   cobertura: {} }),
      resetar: frase => (String(frase).trim().toUpperCase() === 'APAGAR TUDO'
        ? ok({ apagados: { ativos: 3, lancamentos: 41 }, total: 44,
               backup: 'C:\mock\peculium.pec.antes-do-reset-20260803-181500' })
        : erro('digite "APAGAR TUDO" para confirmar')),

      relatorios_disponiveis: () => ok([
        { chave: 'posicao', titulo: 'Posição consolidada' },
        { chave: 'fluxo', titulo: 'Fluxo de caixa dos proventos' },
        { chave: 'apuracao', titulo: 'Apuração de IR' }]),
      relatorio: () => ok(RELATORIO),
      salvar_relatorio: () => ok({ salvo: true, caminho: 'C:\\mock\\relatorio.html' }),

      // ?rf=1 devolve nota de renda fixa; ?posicao=1 devolve retrato da B3
      escolher_arquivo: () => ok('C:\\mock\\nota.pdf'),
      importar: () => (new URLSearchParams(location.search).has('b3') ? ok({
        token: 'imp1', origem: 'B3', relatorio: 'MOVIMENTACAO',
        novas: 3, duplicadas: 0, erros: 0,
        avisos: ['O relatório de Negociação da B3 não traz corretagem.'],
        instituicoes_novas: ['XP INVESTIMENTOS CCTVM S/A'],
        // um de cada natureza: o que o programa sabe e o que ele pergunta
        ativos_novos: {
          CDB726AM6KA: { nome: 'CDB BANCO INTER', classe: 'RF', confirmar: false },
          'TESOURO-IPCA-JUROS-2037': { nome: 'Tesouro IPCA+ 2037',
                                       classe: 'TESOURO', confirmar: false },
          SNAG11: { nome: 'SUNO AGRO', classe: 'FII', confirmar: true },
        },
        linhas: [
          { n: 2, situacao: 'NOVA', tipo: 'COMPRA', data: '16/07/2026',
            ticker: 'CDB726AM6KA', instituicao: 'XP', quantidade: 50000,
            valor: 500, motivo: '' },
          { n: 3, situacao: 'NOVA', tipo: 'COMPRA', data: '09/07/2026',
            ticker: 'TESOURO-IPCA-JUROS-2037', instituicao: 'XP',
            quantidade: 0.5, valor: 2079.13, motivo: '' },
          { n: 4, situacao: 'NOVA', tipo: 'COMPRA', data: '23/04/2026',
            ticker: 'SNAG11', instituicao: 'XP', quantidade: 10, valor: 107,
            motivo: '' }],
      }) : new URLSearchParams(location.search).has('posicao') ? ok({
        token: 'imp1', origem: 'POSICAO', data: '03/08/2026', confere: 1,
        avisos: ['CDB123ABC: a B3 não informou o indexador, então o título não '
               + 'foi cadastrado. O preço dela foi gravado e a posição fica correta.'],
        itens: [
          { ticker: 'PETR4', nome: 'PETROBRAS PN', classe: 'ACAO', quantidade: 100,
            preco: 38.5, valor: 3850, instituicao: 'CORRETORA FICTÍCIA' },
          { ticker: 'MXRF11', nome: 'FII MAXI REN', classe: 'FII', quantidade: 100,
            preco: 9.58, valor: 958, instituicao: 'CORRETORA FICTÍCIA' },
          { ticker: 'TESOURO-IPCA-JUROS-2037', nome: 'Tesouro IPCA+ 2037',
            classe: 'TESOURO', quantidade: 0.5, preco: 4120.36, valor: 2060.18,
            instituicao: 'CORRETORA FICTÍCIA' },
          { ticker: 'CDB123ABC', nome: 'CDB BANCO ALFA', classe: 'RF',
            quantidade: 50000, preco: 0.0100421, valor: 502.11,
            instituicao: 'CORRETORA FICTÍCIA' }],
        divergencias: [
          { ticker: 'PETR4', situacao: 'CONFERE', no_peculium: 100, na_b3: 100,
            classe: 'ACAO', observacao: '' },
          { ticker: 'MXRF11', situacao: 'QUANTIDADE_DIFERE', no_peculium: 20,
            na_b3: 100, classe: 'FII',
            observacao: 'a quantidade não bate: falta lançamento, ou algum entrou dobrado' },
          { ticker: 'TESOURO-IPCA-JUROS-2037', situacao: 'SO_NA_B3',
            no_peculium: 0, na_b3: 0.5, classe: 'TESOURO',
            observacao: 'a B3 tem e o Peculium não — falta o lançamento de compra' },
          { ticker: 'VALE3', situacao: 'SO_NO_PECULIUM', no_peculium: 10, na_b3: 0,
            classe: '', observacao: 'está na sua carteira e não na da B3 nesta data' }],
      }) : new URLSearchParams(location.search).has('rf') ? ok({
        token: 'imp1', origem: 'NOTA_RF',
        avisos: ['CDB-CREDITO-2029-07-01: a nota não trouxe um código utilizável.'],
        notas: [
          { numero: '119312735', corretora: 'XP INVESTIMENTOS', situacao: 'CRIA',
            motivo: 'título novo: entra o cadastro e a aplicação',
            data: '14/05/2026', ticker: 'CDB5267UW6V', codigo_ambiguo: false,
            nome: 'CDB BANCO XP', emissor: 'BANCO XP S.A.', indexador: 'CDI',
            taxa: 100, vencimento: '15/05/2028', quantidade: 1000, pu: 1,
            bruto: 1000, ir: 0 },
          { numero: '662299618', corretora: 'BANCO INTER', situacao: 'CRIA',
            motivo: 'título novo: entra o cadastro e a aplicação',
            data: '16/07/2026', ticker: 'CDB-CREDITO-2029-07-01',
            codigo_ambiguo: true, nome: 'CDB CREDITO', emissor: 'BANCO INTER',
            indexador: 'CDI', taxa: 80, vencimento: '01/07/2029',
            quantidade: 50000, pu: 0.01, bruto: 500, ir: 0 }],
      }) : ok({
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
      })),
      confirmar_importacao: () =>
        (new URLSearchParams(location.search).has('b3')
          ? ok({ gravadas: 3 })
          : new URLSearchParams(location.search).has('posicao')
          ? ok({ ativos_novos: 2, cotacoes: 4, titulos: 0, avisos: [] })
          : new URLSearchParams(location.search).has('rf')
          ? ok({ lancamentos: 2, titulos: 2, ja_importadas: 0 })
          : ok({ criados: 2, enriquecidos: 0 })),
    },
  };

  window.dispatchEvent(new Event('pywebviewready'));
})();
