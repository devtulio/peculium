# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/);
versionamento [semântico](https://semver.org/lang/pt-BR/).

## [0.1.0] — 2026-08-03

Primeira versão. Núcleo completo e interface funcionando; renda fixa e Tesouro
ficam para a 1.1.

### Cofre e segurança

- Acervo inteiro num arquivo `.pec` cifrado em **AES-256-GCM**, com a chave
  derivada da senha mestra por **scrypt** (`n=2¹⁷`, ~0,3 s por tentativa).
- **Envelope de duas chaves**: a chave do banco é guardada embrulhada pela senha
  e por uma **chave de recuperação** de 256 bits, mostrada uma única vez na
  criação. Esquecer a senha não é fatal para quem guardou a chave.
- Banco carregado **em memória**; nada em claro toca o disco. Gravação atômica a
  cada transação, com os três dumps anteriores preservados.
- `PRAGMA integrity_check` ao abrir, trava de instância única por cofre e
  **nenhuma porta escutando** — não há servidor.

### Carteira

- Razão **append-only**: correção é estorno, nunca alteração. Posição, preço
  médio e resultado são recalculados do zero.
- **Preço médio global por ativo**, nunca por corretora — regra da RFB, e é o que
  faz a portabilidade entre instituições não inventar lucro tributável.
- Eventos corporativos: desdobramento, grupamento, conversão e incorporação,
  aplicados retroativamente sobre o custo já registrado.
- **Day trade é detectado**, nunca digitado.

### Importação

- Relatórios de **Negociação** e **Movimentação** da B3 (CSV e XLSX), idempotentes
  por hash — reimportar período sobreposto é o caso normal.
- **Nota de corretagem em PDF** (layout Sinacor): a única fonte dos custos, já que
  a B3 não informa corretagem nem emolumentos. Dois invariantes aritméticos
  recusam a nota que não fecha. Custos rateados pro rata pelo valor de cada linha.
- Nada é gravado sem conferência na tela; o arquivo original nunca é guardado.

### Imposto de renda

- Apuração mensal em três baldes que não se compensam entre si: ações swing
  (15%, isenção até R$ 20 mil em vendas), day trade (20%) e FII (20%).
- Prejuízo acumulado sem prazo, IRRF excedente atravessando o mês e **DARF com
  piso de R$ 10** que acumula em vez de sumir.
- **Contas a pagar**: o valor devido é sempre recalculado e só o pagamento é
  gravado, o que denuncia a apuração que mudou depois de paga. Multa de mora
  calculada; juros só quando houver série Selic.

### Relatórios

Posição consolidada, proventos por ativo, **fluxo de caixa mensal dos proventos**,
apuração de IR, contas a pagar, bens e direitos em 31/12, operações, custos
operacionais e rentabilidade por XIRR. Saída em HTML timbrado e CSV.

### Interface

- Oito telas, três temas (Atrium, Cera e Aerarium) e **paleta daltônica opcional**.
- Alta e baixa sempre com sinal e seta: a cor é reforço, nunca a informação.
- Contraste conferido nos três temas, todos acima do mínimo WCAG 2.1 AA.

### Decisões que valem mais que recursos

- **Nada é estimado dentro de cálculo de imposto.** Negócio sem nota fica com
  custo zero e marcado como tal; juros de mora não aparecem sem a série oficial.
- **Rede desligada por padrão.** Com a cotação ligada, só o ticker sai daqui.
- **Datas guardadas em ISO, mostradas em `dd/mm/aaaa`.**

[0.1.0]: https://github.com/devtulio/peculium/releases/tag/v0.1.0
