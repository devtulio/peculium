/* Gera as capturas de docs/screenshots a partir da ponte falsa.
 *
 *     node gerar-screenshots.js
 *
 * De propósito NÃO é um `.spec.js`: se fosse, o `npx playwright test` do CI o
 * executaria e reescreveria PNG versionado a cada push.
 */
const path = require('path');
const { chromium } = require('@playwright/test');

const UI = 'file://' + path.resolve(__dirname, '..', 'ui', 'index.html').replace(/\\/g, '/');
const SAIDA = path.resolve(__dirname, '..', 'docs', 'screenshots');

const CENAS = [
  { arquivo: 'atrium.png', tema: 'atrium', tela: 'painel' },
  { arquivo: 'cera.png', tema: 'cera', tela: 'carteira' },
  { arquivo: 'aerarium.png', tema: 'aerarium', tela: 'impostos' },
  { arquivo: 'trava.png', tema: 'atrium', tela: null },
];

(async () => {
  const navegador = await chromium.launch();
  const pagina = await navegador.newPage({
    viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2,
  });

  for (const cena of CENAS) {
    await pagina.goto(`${UI}?mock=1&tema=${cena.tema}`);
    if (cena.tela) {
      await pagina.fill('#senha', 'mock');
      await pagina.click('#form-abrir button[type="submit"]');
      await pagina.waitForSelector('#app', { state: 'visible' });
      await pagina.click(`#menu button[data-view="${cena.tela}"]`);
      await pagina.waitForTimeout(400);
    } else {
      await pagina.waitForSelector('#form-abrir', { state: 'visible' });
    }
    const destino = path.join(SAIDA, cena.arquivo);
    await pagina.screenshot({ path: destino });
    console.log('gravado:', destino);
  }
  await navegador.close();
})();
