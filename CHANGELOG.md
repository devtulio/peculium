# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/);
versionamento [semântico](https://semver.org/lang/pt-BR/).

## [0.2.0] — 2026-08-03

### Renda fixa e Tesouro Direto

Um título de renda fixa passa a ser tratado como **um ativo com preço unitário**:
a aplicação é uma compra e o resgate é uma venda. Com isso, quantidade, custo e
posição funcionam igual ao resto da carteira, e o que muda é só de onde vem a
cotação.

- **Valor na curva** calculado a partir das séries do Banco Central. Um botão só,
  na Carteira, baixa o que falta da série e recalcula o preço de cada título.
- Suporta **% do CDI** e **prefixado**. O papel para de render no vencimento.
- **Fora da cobertura da série, o cálculo é recusado** em vez de devolver um
  número menor que a verdade — patrimônio subavaliado em silêncio é pior que erro
  visível.
- **Tesouro IPCA+ pede preço à mão**: o preço depende do VNA oficial, que não se
  reconstrói com a série mensal do IPCA. O preço digitado sempre vence o
  calculado, e é assim que esses papéis entram.
- **O cadastro recusa preço unitário de emissão que não bate com a aplicação.**
  Um CDB de R$ 4,50 comprado como 450 unidades a R$ 0,01, cadastrado com o padrão
  de R$ 1,00, viraria uma posição de R$ 457 — cem vezes o valor — com o custo
  ainda certo, então nada denunciaria.
- Relatório próprio, com rendimento e IR estimado por título.

### Imposto de renda

- **Renda fixa não entra mais na apuração mensal.** No balde de swing trade, um
  resgate de CDB geraria DARF de 15% sobre rendimento que já foi tributado na
  fonte — imposto pago duas vezes. Agora sai da apuração e entra a tabela
  regressiva da Lei 11.033/2004.
- A apuração anual passa a informar o total sujeito a **tributação exclusiva na
  fonte**.
- O IR de renda fixa é sempre apresentado como **estimativa**: ele conta o prazo
  desde a emissão e serve para conferir ordem de grandeza. O valor retido de
  verdade vem no extrato da corretora.

### Interno

- Primeira **migração de esquema** (v1 → v2). Ela se recusa a rodar se houver
  dado no formato antigo, em vez de descartar.

## [0.1.1] — 2026-08-03

### Corrigido

- **Trancar impedia reabrir.** O botão *Trancar* apenas recarregava a tela; o cofre
  seguia aberto no processo, segurando a trava de instância única. A abertura
  seguinte esbarrava na **própria** trava e devolvia "peculium.pec já está aberto
  em outra janela" — sem outra janela nenhuma. A única saída era fechar o
  programa.

  Além de travar, isso deixava a chave na memória do processo depois de trancar.
  Agora *Trancar* fecha o cofre de verdade, esquece o que estava carregado e
  descarta conferências de importação pendentes. Abrir o cofre também fecha
  qualquer um que já esteja aberto, para o caso de a janela ser recarregada sem
  passar pelo botão.

## [0.1.0] — 2026-08-03 — [DOI 10.5281/zenodo.21767165](https://doi.org/10.5281/zenodo.21767165)

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

[0.2.0]: https://github.com/devtulio/peculium/releases/tag/v0.2.0
[0.1.1]: https://github.com/devtulio/peculium/releases/tag/v0.1.1
[0.1.0]: https://github.com/devtulio/peculium/releases/tag/v0.1.0
