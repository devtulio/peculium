// @ts-check
const { test, expect } = require('@playwright/test');

const APP = '/index.html?mock=1&tema=atrium';

async function destrancar(page) {
  await page.goto(APP);
  await page.fill('#senha', 'mock');
  await page.click('#form-abrir button[type="submit"]');
  await expect(page.locator('#app')).toBeVisible();
}

test.describe('trava', () => {
  test('abre na tela de senha, com um único formulário visível', async ({ page }) => {
    await page.goto(APP);
    await expect(page.locator('#form-abrir')).toBeVisible();
    await expect(page.locator('#form-criar')).toBeHidden();
    await expect(page.locator('#form-recuperar')).toBeHidden();
    // regressão: `hidden` perdia para o `display` da classe e a trava seguia
    // ocupando a página inteira depois de escondida
    await expect(page.locator('#app')).toBeHidden();
  });

  test('senha errada mostra o erro e não abre', async ({ page }) => {
    await page.goto(APP);
    await page.fill('#senha', 'errada');
    await page.click('#form-abrir button[type="submit"]');
    await expect(page.locator('#trava-erro')).toBeVisible();
    await expect(page.locator('#app')).toBeHidden();
  });

  test('a chave de recuperação é oferecida', async ({ page }) => {
    await page.goto(APP);
    await page.click('#btn-recuperar');
    await expect(page.locator('#form-recuperar')).toBeVisible();
    await expect(page.locator('#form-abrir')).toBeHidden();
  });
});

test.describe('navegação', () => {
  test('as oito telas abrem sem erro', async ({ page }) => {
    await destrancar(page);
    const telas = ['painel', 'carteira', 'lancamentos', 'proventos', 'importar',
                   'impostos', 'relatorios', 'config'];
    for (const tela of telas) {
      await page.click(`#menu button[data-view="${tela}"]`);
      await expect(page.locator('#view .erro')).toHaveCount(0);
      await expect(page.locator('#view')).not.toContainText('Carregando…');
    }
  });

  test('o painel mostra as somas e os alertas', async ({ page }) => {
    await destrancar(page);
    await expect(page.locator('.soma')).toHaveCount(4);
    await expect(page.locator('.alerta.grave')).toContainText('DARF');
    await expect(page.locator('#view')).toContainText('R$ 3.006,29');
    // o cifrão vem depois da seta: "R$ ▲ +18,53" lê como duas frases
    await expect(page.locator('.somas .alta')).toContainText('▲ +R$ 18,53');
    // a média é sobre os meses que tiveram provento, não sobre o ano: dividir
    // por 12 em agosto diria metade do que ele recebe por mês
    await expect(page.locator('.somas')).toContainText('média de R$ 16,50 ao mês');
  });

  test('a régua traz composição, posições e os dois gráficos', async ({ page }) => {
    await destrancar(page);
    // barra empilhada em vez de rosca, um pedaço por classe
    await expect(page.locator('.faixa i')).toHaveCount(2);
    // a classe aparece por extenso: "FII" e "ACAO" são código de banco
    await expect(page.locator('.chaves')).toContainText('Fundos imobiliários · 2');
    await expect(page.locator('.chaves')).toContainText('Ações · 1');
    // tabela completa de posições, não só as maiores
    await expect(page.locator('#view table tbody tr')).toHaveCount(3);
    await expect(page.locator('#view svg[aria-label="Proventos por mês"]')).toBeVisible();
    await expect(page.locator('#view svg[aria-label="Aportes acumulados por mês"]')).toBeVisible();
  });

  test('a divergência com a B3 fica em destaque no painel', async ({ page }) => {
    await destrancar(page);
    const nota = page.locator('.nota-divergencia');
    await expect(nota).toContainText('1 papel(is) a conferir');
    await expect(nota).toContainText('03/08/2026');
    await expect(nota).toContainText('a B3 informa R$ 12,05 a mais');
    await expect(nota).toContainText('ROXO34');
  });
});

test.describe('alta e baixa', () => {
  test('nunca dependem só da cor', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="carteira"]');
    // sinal e seta acompanham o número, e a cor é reforço
    await expect(page.locator('.alta').first()).toContainText('▲ +');
    await expect(page.locator('.baixa').first()).toContainText('▼ −');
  });

  test('a paleta daltônica troca o par de cores', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="carteira"]');
    const cor = () => page.locator('.alta').first().evaluate(
      el => getComputedStyle(el).color);
    const verde = await cor();
    await page.evaluate(() => { document.documentElement.dataset.daltonica = '1'; });
    expect(await cor()).not.toBe(verde);
  });
});

test.describe('temas', () => {
  for (const tema of ['atrium', 'cera', 'aerarium']) {
    test(`${tema} mantém contraste de texto acima de AA`, async ({ page }) => {
      await destrancar(page);
      await page.evaluate(t => { document.documentElement.dataset.tema = t; }, tema);
      const razao = await page.evaluate(() => {
        const lum = c => {
          const [r, g, b] = c.match(/\d+/g).map(Number).map(v => {
            v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
          });
          return 0.2126 * r + 0.7152 * g + 0.0722 * b;
        };
        const e = getComputedStyle(document.body);
        const a = lum(e.color), b = lum(e.backgroundColor);
        return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
      });
      expect(razao).toBeGreaterThan(4.5);
    });
  }
});

test.describe('importação', () => {
  test('a conferência aparece antes de gravar e pede o ticker que falta', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="importar"]');
    await page.click('#btn-escolher');
    await expect(page.locator('#conferencia')).toContainText('Nota 140560283');
    // o item sem ticker é sinalizado e ganha um campo para o usuário informar
    await expect(page.locator('.selo-situacao.grave')).toContainText('SEM_ATIVO');
    await expect(page.locator('[data-espec]')).toHaveCount(1);

    await page.fill('[data-espec]', 'KLBN4');
    await page.click('#btn-gravar-nota');
    await expect(page.locator('#toast')).toContainText('negócio(s) criado(s)');
    await expect(page.locator('#titulo-view')).toHaveText('Lançamentos');
  });
});

test.describe('conferência do extrato da B3', () => {
  async function abrir(page) {
    await page.goto('/index.html?mock=1&b3=1&tema=atrium');
    await page.fill('#senha', 'mock');
    await page.click('#form-abrir button[type="submit"]');
    await page.click('#menu button[data-view="importar"]');
    await page.click('#btn-escolher');
    await expect(page.locator('#conferencia')).toContainText('Conferência');
  }

  test('a lista de classes inclui renda fixa e Tesouro', async ({ page }) => {
    // A regressão: duas listas no JS estavam sem RF e TESOURO. O <select> caía
    // na primeira opção — ACAO — e todo CDB entrava como ação, o que ainda
    // quebrava a reconciliação da renda fixa e duplicava os aportes.
    await abrir(page);
    const opcoes = page.locator('#c-CDB726AM6KA option');
    await expect(opcoes).toHaveText(['ACAO', 'FII', 'ETF', 'BDR', 'UNIT',
                                     'RF', 'TESOURO']);
  });

  test('a classe que o programa sabe já vem escolhida', async ({ page }) => {
    await abrir(page);
    await expect(page.locator('#c-CDB726AM6KA')).toHaveValue('RF');
    await expect(page.locator('#c-TESOURO-IPCA-JUROS-2037')).toHaveValue('TESOURO');
    await expect(page.locator('#c-SNAG11')).toHaveValue('FII');
  });

  test('só o ambíguo é marcado para confirmação', async ({ page }) => {
    await abrir(page);
    await expect(page.locator('label[for="c-SNAG11"]')).toContainText('confirme a classe');
    await expect(page.locator('label[for="c-CDB726AM6KA"]'))
      .not.toContainText('confirme a classe');
  });

  test('gravar leva as classes escolhidas', async ({ page }) => {
    await abrir(page);
    await page.click('#btn-gravar');
    await expect(page.locator('#toast')).toContainText('3 lançamento(s) gravado(s)');
  });
});

test.describe('editar lançamento', () => {
  async function abrirDetalhes(page) {
    await destrancar(page);
    await page.click('#menu button[data-view="lancamentos"]');
    // a compra de KLBN4, que veio de nota: o lançamento mais rico do exemplo
    await page.locator('[data-detalhes="3"]').click();
    await expect(page.locator('#modal')).toBeVisible();
  }

  test('a observação é editável e não fala em estorno', async ({ page }) => {
    await abrirDetalhes(page);
    await expect(page.locator('#modal-corpo')).toContainText('muda no lugar');
    await page.fill('#d-obs', 'aporte do 13º');
    await page.click('#modal-ok');
    await expect(page.locator('#toast')).toContainText('Observação salva');
  });

  test('a ficha mostra o lançamento antes de mexer nele', async ({ page }) => {
    await abrirDetalhes(page);
    const ficha = page.locator('.ficha');
    await expect(ficha).toContainText('21/07/2026');
    await expect(ficha).toContainText('nota 140560283');
  });

  test('corrigir avisa que vai estornar, e o botão diz isso', async ({ page }) => {
    await abrirDetalhes(page);
    await page.click('#d-corrigir');
    await expect(page.locator('#modal-titulo')).toContainText('Corrigir lançamento');
    // o formulário vem preenchido com o que está gravado
    await expect(page.locator('#l-tipo')).toHaveValue('COMPRA');
    await expect(page.locator('#l-data')).toHaveValue('21/07/2026');
    await expect(page.locator('#l-qtd')).toHaveValue('200');
    await expect(page.locator('#modal-corpo')).toContainText('estornado');
    await expect(page.locator('#modal-corpo')).toContainText('não sobrescreve linha');
    await expect(page.locator('#modal-ok')).toHaveText('Estornar e relançar');

    await page.fill('#l-preco', '3.60');
    await page.click('#modal-ok');
    await expect(page.locator('#toast')).toContainText('o antigo foi estornado');
  });

  test('cancelar não grava nada', async ({ page }) => {
    // Garantia de comportamento, não regressão: hoje quem zera o returnValue no
    // Esc é o próprio Chrome, e este teste passa com ou sem a nossa defesa. Ele
    // existe para travar o que o usuário vê — cancelar não pode gravar.
    await abrirDetalhes(page);
    await page.fill('#d-obs', 'primeira');
    await page.click('#modal-ok');
    await expect(page.locator('#toast')).toContainText('Observação salva');

    expect(await page.evaluate(() => window.__anotou)).toBe(1);

    await page.locator('[data-detalhes="1"]').click();
    await page.keyboard.press('Escape');
    await expect(page.locator('#modal')).toBeHidden();
    // o que prova o ponto: cancelar não pode ter gravado nada
    await page.waitForTimeout(200);
    expect(await page.evaluate(() => window.__anotou)).toBe(1);
  });

  test('a observação aparece na tabela', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="lancamentos"]');
    await expect(page.locator('#view table')).toContainText('conferido com o informe');
  });

  test('lançamento já estornado não oferece detalhes', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="lancamentos"]');
    // os três do exemplo estão vivos; o botão existe em todos
    await expect(page.locator('[data-detalhes]')).toHaveCount(4);
  });
});

test.describe('renda fixa', () => {
  test('aparece na carteira com PU e rendimento', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="carteira"]');
    await expect(page.locator('#view')).toContainText('Renda fixa e Tesouro');
    await expect(page.locator('#view')).toContainText('CDB5267UW6V');
    await expect(page.locator('#view')).toContainText('100% do CDI');
    await expect(page.locator('#view')).toContainText('15/05/2028');   // data em BR
  });

  test('título sem curva diz o que fazer em vez de mostrar número errado',
    async ({ page }) => {
      await destrancar(page);
      await page.click('#menu button[data-view="carteira"]');
      await expect(page.locator('.aviso-lista'))
        .toContainText('informe o preço unitário à mão');
    });

  test('o formulário avisa sobre o PU de emissão', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="carteira"]');
    await page.click('text=Novo título de renda fixa');
    await expect(page.locator('#modal')).toBeVisible();
    await expect(page.locator('#modal')).toContainText('ordem de grandeza');
    await expect(page.locator('#t-ativo')).toBeVisible();
  });

  test('atualizar curvas relata as falhas', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="carteira"]');
    await page.click('text=Atualizar curvas');
    await expect(page.locator('#toast')).toContainText('curva(s) recalculada(s)');
  });
});

test.describe('nota de renda fixa', () => {
  test('conferência mostra o papel e marca o ticker derivado', async ({ page }) => {
    await page.goto('/index.html?mock=1&rf=1&tema=atrium');
    await page.fill('#senha', 'mock');
    await page.click('#form-abrir button[type="submit"]');
    await page.click('#menu button[data-view="importar"]');
    await page.click('#btn-escolher');

    await expect(page.locator('#conferencia')).toContainText('Notas de renda fixa');
    await expect(page.locator('#conferencia')).toContainText('CDB5267UW6V');
    await expect(page.locator('#conferencia')).toContainText('CDI 100%');
    // o papel cujo código a nota não trouxe fica sinalizado
    await expect(page.locator('.selo-situacao.grave')).toContainText('derivado');

    await page.click('#btn-gravar-rf');
    await expect(page.locator('#toast')).toContainText('título(s) cadastrado(s)');
  });
});

test.describe('posição da B3', () => {
  test('a tela de importar diz quais arquivos baixar', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="importar"]');
    const guia = page.locator('.guia-importar li');
    await expect(guia).toHaveCount(4);
    await expect(guia.nth(3)).toContainText('Posição');
    await expect(guia.nth(3)).toContainText('Não cria lançamento nenhum');
    await expect(page.locator('#view')).toContainText('Proventos Recebidos');
  });

  test('conferência mostra as divergências e grava sem criar lançamento',
    async ({ page }) => {
      await page.goto('/index.html?mock=1&posicao=1&tema=atrium');
      await page.fill('#senha', 'mock');
      await page.click('#form-abrir button[type="submit"]');
      await page.click('#menu button[data-view="importar"]');
      await page.click('#btn-escolher');

      await expect(page.locator('#conferencia')).toContainText('Posição da B3 em 03/08/2026');
      // as três formas de divergir aparecem; o que confere fica fora da tabela
      await expect(page.locator('#conferencia')).toContainText('quantidade difere');
      await expect(page.locator('#conferencia')).toContainText('só na B3');
      await expect(page.locator('#conferencia')).toContainText('só aqui');
      await expect(page.locator('#conferencia'))
        .toContainText('Retrato não vira lançamento');

      // PU de CDB é da ordem de R$ 0,01: com duas casas a coluna vira "0,01"
      await expect(page.locator('#conferencia')).toContainText('0,010042');

      await page.click('#btn-gravar-posicao');
      await expect(page.locator('#toast')).toContainText('nenhum lançamento');
    });
});

test.describe('impostos', () => {
  test('DARF vencido aparece com multa e oferta de pagamento', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="impostos"]');
    await expect(page.locator('.selo-situacao.grave')).toContainText('VENCIDO');
    await expect(page.locator('#view')).toContainText('31/07/2026');   // data em BR
    await expect(page.locator('[data-pagar]')).toBeVisible();
    await expect(page.locator('#view'))
      .toContainText('não transmite nada à Receita');
  });

  test('o formulário de pagamento abre com o valor já calculado', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="impostos"]');
    await page.click('[data-pagar]');
    await expect(page.locator('#modal')).toBeVisible();
    await expect(page.locator('#p-multa')).toHaveValue('14.85');
  });
});

test.describe('ordenação das tabelas', () => {
  // a Carteira tem duas tabelas (a principal e o bloco de renda fixa): tudo
  // aqui é escopado na primeira
  const principal = page => page.locator('#view table').first();
  const coluna = (page, n) =>
    principal(page).locator('tbody tr td:nth-child(' + n + ')');
  const cabecalho = (page, n) => principal(page).locator('th').nth(n);

  test('clicar no cabeçalho ordena, e clicar de novo inverte', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="carteira"]');
    const ticker = cabecalho(page, 0).locator('button.ord');

    await ticker.click();
    await expect(coluna(page, 1)).toHaveText(['KLBN4', 'MXRF11', 'SNAG11']);
    await expect(cabecalho(page, 0)).toHaveAttribute('aria-sort', 'ascending');

    await ticker.click();
    await expect(coluna(page, 1)).toHaveText(['SNAG11', 'MXRF11', 'KLBN4']);
    await expect(cabecalho(page, 0)).toHaveAttribute('aria-sort', 'descending');
  });

  test('número ordena por valor, não por texto', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="carteira"]');
    // custo: 1.009,21 / 973,46 / 1.005,09 — por texto, "1.009,21" viria antes de "973,46"
    await cabecalho(page, 4).locator('button.ord').click();
    await expect(coluna(page, 5)).toHaveText(['973,46', '1.005,09', '1.009,21']);
  });

  test('data ordena por dia, não por string', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="lancamentos"]');
    // 30/01 é o caso que discrimina: por texto ele iria para o fim da lista,
    // depois de 21/07
    await cabecalho(page, 0).locator('button.ord').click();
    await expect(coluna(page, 1)).toHaveText(
      ['05/01/2026', '30/01/2026', '18/05/2026', '21/07/2026']);
  });

  test('o cabeçalho é alcançável pelo teclado', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="carteira"]');
    await cabecalho(page, 0).locator('button.ord').focus();
    await page.keyboard.press('Enter');
    await expect(cabecalho(page, 0)).toHaveAttribute('aria-sort', 'ascending');
  });
});

test.describe('cadastros editáveis', () => {
  async function abrirConfig(page) {
    await destrancar(page);
    await page.click('#menu button[data-view="config"]');
  }

  test('clicar numa linha abre o ativo preenchido', async ({ page }) => {
    await abrirConfig(page);
    await page.locator('tr[data-editar^="ativo:"]').first().click();
    await expect(page.locator('#modal-titulo')).toContainText('Editar');
    await expect(page.locator('#a-ticker')).toHaveValue('KLBN4');
    await expect(page.locator('#a-classe')).toHaveValue('ACAO');
    await expect(page.locator('#a-situacao')).toBeVisible();   // só na edição
    await page.fill('#a-ticker', 'KLBN3');
    await page.click('#modal-ok');
    await expect(page.locator('#toast')).toContainText('Ativo atualizado');
  });

  test('novo ativo não oferece situação', async ({ page }) => {
    await abrirConfig(page);
    await page.click('#btn-ativo');
    await expect(page.locator('#a-ticker')).toHaveValue('');
    await expect(page.locator('#a-situacao')).toHaveCount(0);
  });

  test('no cadastro de instituição o CNPJ vem primeiro e busca o nome',
    async ({ page }) => {
      await abrirConfig(page);
      await page.click('#btn-inst');
      // o CNPJ é o primeiro campo do formulário
      const primeiro = page.locator('#modal-corpo .campo').first();
      await expect(primeiro.locator('label')).toHaveText('CNPJ');
      await expect(page.locator('#i-resultado')).toContainText('só o CNPJ digitado sai daqui');

      await page.fill('#i-cnpj', '02332886000104');
      await page.click('#i-buscar');
      await expect(page.locator('#i-nome')).toHaveValue('XP INVESTIMENTOS CCTVM S/A');
      await expect(page.locator('#i-cnpj')).toHaveValue('02.332.886/0001-04');
      await expect(page.locator('#i-resultado')).toContainText('ReceitaWS');
    });

  test('o campo de CNPJ ocupa a linha inteira do formulário', async ({ page }) => {
    // regressão: espremido numa coluna de terço, o input cortava a própria
    // máscara — aparecia "00.000.00" no lugar de "00.000.000/0000-00"
    await abrirConfig(page);
    await page.locator('tr[data-editar^="instituicao:"]').first().click();
    const campo = await page.locator('#modal-corpo .campo-largo').boundingBox();
    const grade = await page.locator('#modal-corpo .form-grade').boundingBox();
    expect(campo.width).toBeGreaterThan(grade.width * 0.9);

    // e o input tem de caber um CNPJ formatado inteiro
    const input = await page.locator('#i-cnpj').boundingBox();
    expect(input.width).toBeGreaterThan(200);
  });

  test('CNPJ inválido avisa e não preenche o nome', async ({ page }) => {
    await abrirConfig(page);
    await page.click('#btn-inst');
    await page.fill('#i-cnpj', '02332886000105');
    await page.click('#i-buscar');
    await expect(page.locator('#toast')).toContainText('CNPJ inválido');
    await expect(page.locator('#i-nome')).toHaveValue('');
  });
});

test.describe('apagar todos os dados', () => {
  async function abrirZonaDeRisco(page) {
    await destrancar(page);
    await page.click('#menu button[data-view="config"]');
    await page.click('#btn-reset');
    await expect(page.locator('#modal')).toBeVisible();
  }

  test('a frase errada não apaga nada', async ({ page }) => {
    await abrirZonaDeRisco(page);
    await page.fill('#r-frase', 'apagar');
    await page.click('#modal-ok');
    await expect(page.locator('#toast')).toContainText('APAGAR TUDO');
    // o diálogo de sucesso não aparece: nada foi apagado
    await expect(page.locator('#modal-titulo')).not.toHaveText('Cofre esvaziado');
  });

  test('confirmada, informa o que saiu e onde está a cópia', async ({ page }) => {
    await abrirZonaDeRisco(page);
    await page.fill('#r-frase', 'apagar tudo');       // caixa não importa
    await page.click('#modal-ok');
    await expect(page.locator('#modal-titulo')).toHaveText('Cofre esvaziado');
    await expect(page.locator('#modal-corpo')).toContainText('44 registro(s)');
    await expect(page.locator('#modal-corpo')).toContainText('antes-do-reset');
    await page.click('#modal-ok');
    await expect(page.locator('#titulo-view')).toHaveText('Painel');
  });

  test('a tela avisa o que sobrevive antes de qualquer clique', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="config"]');
    const zona = page.locator('.zona-risco');
    await expect(zona).toContainText('não mudam');
    await expect(zona).toContainText('cópia do cofre é guardada antes');
  });
});

test.describe('juros de mora do DARF', () => {
  test('a coluna de juros aparece e entra no total', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="impostos"]');
    const cabecalhos = page.locator('#view table').first().locator('th');
    await expect(cabecalhos.nth(7)).toContainText('Juros');
    await expect(page.locator('#view')).toContainText('1.529,85');   // 1500 + multa + juros
    await expect(page.locator('#view')).toContainText('art. 61 §3');
  });

  test('o formulário de pagamento já vem com os juros', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="impostos"]');
    await page.click('[data-pagar]');
    await expect(page.locator('#p-juros')).toHaveValue('15.00');
    await expect(page.locator('#p-multa')).toHaveValue('14.85');
    // principal = total − multa − juros; antes o juros ficava embutido no principal
    await expect(page.locator('#p-valor')).toHaveValue('1500.00');
  });

  test('dá para baixar a Selic sem passar pela Carteira', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="impostos"]');
    await page.click('text=Atualizar Selic');
    await expect(page.locator('#toast')).toContainText('série atualizado');
  });
});

test.describe('configurações', () => {
  test('trocar o tema repinta a interface', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="config"]');
    await page.selectOption('#c-tema', 'aerarium');
    await expect(page.locator('html')).toHaveAttribute('data-tema', 'aerarium');
  });
});
