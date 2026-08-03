# Peculium

Gerenciador de investimentos pessoais. Programa **desktop**, monousuário, com o
acervo inteiro num arquivo cifrado por senha mestra.

> *Peculium*, em direito romano, é o patrimônio que o *filius familias* administrava
> em separado do patrimônio do *pater* — com gestão e escrituração próprias
> (Digesto 15.1, *De peculio*). Patrimônio pessoal sob gestão de quem o opera.

## Estado

**Em desenvolvimento. Ainda não há versão utilizável** — o núcleo está pronto e
testado, a interface não existe.

| Módulo | O que faz |
|---|---|
| `cofre.py` | Arquivo `.pec` cifrado (AES-256-GCM), senha mestra por scrypt, chave de recuperação |
| `razao.py` | Posição, preço médio e resultado, derivados de um razão append-only |
| `fisco.py` | Apuração mensal de IR em baldes que não se compensam, DARF |
| `obrigacoes.py` | Contas a pagar dos DARF: apurado × pago, atraso, multa de mora |
| `importar_b3.py` | Relatórios de Negociação e Movimentação da B3 (CSV/XLSX) |
| `importar_nota.py` | Nota de corretagem em PDF (layout Sinacor) — a única fonte dos custos |
| `cotacoes.py` | Cotação de fechamento, opcional e desligada por padrão |
| `relatorios.py` | Sete relatórios em HTML timbrado e CSV |

## Princípios que governam o código

- **O razão é append-only.** Correção é estorno, nunca UPDATE. Posição e preço
  médio são recalculados, porque evento corporativo retroativo e reimportação
  exigem recalcular o passado.
- **Preço médio é global por ativo, nunca por corretora** — é a regra da RFB, e é
  o que faz a portabilidade entre instituições não inventar lucro tributável.
- **Nada é estimado dentro de cálculo de imposto.** Sem nota de corretagem, o
  negócio fica com custo zero e marcado como tal; juros de mora só aparecem
  quando a série Selic existir.
- **Rede é opcional e desligada por padrão.** O programa é inteiramente utilizável
  offline.
- **Datas: guarda ISO, mostra BR.**

A arquitetura completa, com o modelo de ameaça, está em [DESIGN.md](DESIGN.md).
A identidade visual e suas notas históricas, em
[design/IDENTIDADE.md](design/IDENTIDADE.md).

## Testes

```bash
python -m pytest tests -q
```

## Licença

MIT — ver [LICENSE](LICENSE).
