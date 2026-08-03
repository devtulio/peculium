# Peculium

[![CI](https://github.com/devtulio/peculium/actions/workflows/ci.yml/badge.svg)](https://github.com/devtulio/peculium/actions/workflows/ci.yml)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-63234c)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-63234c)](https://www.python.org/)
[![Plataforma](https://img.shields.io/badge/plataforma-Windows-63234c)](#instala%C3%A7%C3%A3o)
[![Release](https://img.shields.io/github/v/release/devtulio/peculium?display_name=tag&color=63234c)](https://github.com/devtulio/peculium/releases)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.21767164-63234c)](https://doi.org/10.5281/zenodo.21767164)

Gerenciador de investimentos pessoais. Programa **desktop**, monousuário, com o
acervo inteiro num arquivo cifrado por senha mestra.

> *Peculium*, em direito romano, é o patrimônio que o *filius familias* administrava
> em separado do patrimônio do *pater* — com gestão e escrituração próprias
> (Digesto 15.1, *De peculio*). Patrimônio pessoal sob gestão de quem o opera.

## O que ele faz

- **Carteira** — posição, preço médio e resultado, com marcação a mercado opcional.
- **Lançamento manual** — compra, venda, portabilidade entre corretoras, proventos,
  JCP, bonificação, subscrição e eventos corporativos.
- **Importação** — relatórios de Negociação e Movimentação da B3 (CSV e XLSX) e
  **notas de corretagem em PDF**, que são a única fonte dos custos operacionais.
- **Imposto de renda** — apuração mensal, isenção dos R$ 20 mil, prejuízo
  acumulado, DARF e controle do que já foi pago.
- **Relatórios** — nove, em HTML timbrado e CSV, incluindo a posição pelo custo de
  aquisição em 31/12 para a declaração de bens.

## Instalação

**Executável** — baixe o `.exe` da [página de releases](https://github.com/devtulio/peculium/releases)
e execute. Não há instalador.

**Código-fonte** — funciona em qualquer máquina com Python 3.11+:

```bash
pip install -r requirements.txt
python peculium.py
```

No Windows, `Peculium.cmd` faz o mesmo com um duplo clique.

> **O Windows pode barrar o executável.** Binário novo, sem assinatura digital e
> sem reputação, é bloqueado pelo *Smart App Control* com a mensagem “Uma política
> de Controle de Aplicativo bloqueou este arquivo”. Nesse caso, use o caminho do
> código-fonte — ele não passa por essa verificação. Desligar o Smart App Control
> **não** é recomendado: uma vez desligado, só volta a ligar reinstalando o Windows.

Para conferir um executável antes de confiar nele: `Peculium.exe --verificar`.

## Princípios que governam o código

- **O razão é append-only.** Correção é estorno, nunca alteração. Posição e preço
  médio são recalculados, porque evento corporativo retroativo e reimportação
  exigem recalcular o passado.
- **Preço médio é global por ativo, nunca por corretora** — é a regra da RFB, e é
  o que faz a portabilidade entre instituições não inventar lucro tributável.
- **Nada é estimado dentro de cálculo de imposto.** Sem nota de corretagem, o
  negócio fica com custo zero e marcado como tal; juros de mora só aparecem quando
  a série Selic existir.
- **Rede é opcional e desligada por padrão.** O programa é inteiramente utilizável
  offline; com a cotação ligada, só o código do ativo sai daqui.
- **Datas: guarda ISO, mostra `dd/mm/aaaa`.**

## Segurança

O acervo vive num arquivo `.pec` cifrado em AES-256-GCM, com a chave derivada da
senha mestra por scrypt. O banco é carregado em memória — nada em claro toca o
disco — e **não existe porta de rede aberta**: não há servidor.

Uma **chave de recuperação** de 256 bits é mostrada uma única vez na criação do
cofre e abre o mesmo arquivo sem a senha. Sem ela e sem a senha, não há recuperação.

O modelo de ameaça, incluindo **o que o programa não protege**, está no
[DESIGN.md](DESIGN.md#2-modelo-de-ameaça).

> O Peculium apura e informa. **Não transmite nada à Receita, não emite DARF
> oficial e não substitui contador.**

## Documentação

| Documento | Para quê |
|---|---|
| [MANUAL.html](MANUAL.html) | Manual operacional — abra no navegador; imprime em PDF pelo botão |
| [DESIGN.md](DESIGN.md) | Arquitetura, modelo de ameaça e as decisões que a governam |
| [design/IDENTIDADE.md](design/IDENTIDADE.md) | Identidade visual e as notas históricas de cada escolha |
| [CHANGELOG.md](CHANGELOG.md) | Histórico de versões |

## Desenvolvimento

```bash
python -m pytest tests -q              # 203 testes de unidade e integração
cd tests-e2e && npx playwright test    # 14 testes de interface
python -m PyInstaller --clean --noconfirm Peculium.spec
```

Os testes de interface rodam sobre `ui/mock.js`, uma ponte falsa que responde no
lugar do Python — o pywebview não é dirigível por navegador.

## Licença

MIT — ver [LICENSE](LICENSE).
