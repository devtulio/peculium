// @ts-check
const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: '.',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['html', { open: 'never' }], ['list']] : 'list',
  // 10s e não os 5s do padrão: no runner do Windows a primeira renderização
  // atrasa o bastante para dar falso negativo (mesma correção da família SGCD).
  expect: { timeout: 10_000 },
  use: {
    baseURL: 'http://127.0.0.1:8766',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  // A interface é servida como arquivo estático porque o pywebview não é
  // dirigível por navegador; quem responde às chamadas é a ponte falsa.
  webServer: {
    command: 'python -m http.server 8766 --directory ../ui',
    url: 'http://127.0.0.1:8766/index.html',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
