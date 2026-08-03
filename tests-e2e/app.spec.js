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

  test('o painel mostra os indicadores e os alertas', async ({ page }) => {
    await destrancar(page);
    await expect(page.locator('.cartao')).toHaveCount(6);
    await expect(page.locator('.alerta.grave')).toContainText('DARF');
    await expect(page.locator('#view')).toContainText('R$ 3.006,29');
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

test.describe('configurações', () => {
  test('trocar o tema repinta a interface', async ({ page }) => {
    await destrancar(page);
    await page.click('#menu button[data-view="config"]');
    await page.selectOption('#c-tema', 'aerarium');
    await expect(page.locator('html')).toHaveAttribute('data-tema', 'aerarium');
  });
});
