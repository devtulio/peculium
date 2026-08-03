# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/);
versionamento [semântico](https://semver.org/lang/pt-BR/).

## [0.6.0] — 2026-08-03

### Adicionado

- **Toda tabela ordena pelo cabeçalho.** Clique para ordenar, clique de novo
  para inverter. A chave não é o texto da célula: data, competência e número em
  pt-BR são reconhecidos, senão `10/01/2026` viria antes de `05/12/2025` e
  `1.029,52` antes de `285`. O cabeçalho é um botão de verdade, com `aria-sort`
  e navegação por teclado.
- **Ativos e instituições agora são editáveis** em Configurações › Cadastros:
  clique na linha. Renomear é seguro — os lançamentos apontam para o cadastro, e
  não para o texto do ticker. Trocar a classe fica registrado na auditoria, com
  o antes e o depois, porque a classe muda a alíquota do imposto. Também dá para
  **arquivar** um cadastro: ele deixa de ser oferecido em formulário novo, sem
  apagar nem esconder lançamento nenhum.
- **Busca de CNPJ no cadastro de instituição**, como na família SGx. O CNPJ é o
  primeiro campo, e é ele que preenche a razão social. ReceitaWS primeiro,
  BrasilAPI como reserva — o plano gratuito da ReceitaWS concede três consultas
  por minuto, então a reserva é o caso normal, não a exceção. **Só o CNPJ
  digitado sai daqui.**
- **Dígitos verificadores conferidos**, na busca e na gravação. Antes de ir à
  rede, porque um dígito trocado voltaria como "não encontrado" depois de gastar
  uma das três consultas do minuto; e na gravação, porque CNPJ errado guardado
  volta como "não encontrado" toda vez que alguém tentar usá-lo.
- A **máscara do CNPJ é aplicada na leitura**: o que a importação da B3 gravou
  só com dígitos passa a aparecer formatado.

## [0.5.0] — 2026-08-03

### Adicionado — apagar todos os dados

Em **Configurações › Zona de risco**. Apaga lançamentos, ativos, instituições,
importações, notas, cotações, títulos de renda fixa, pagamentos de DARF e o
histórico de auditoria.

- **A confirmação é uma frase digitada** (`APAGAR TUDO`), não um botão: uma
  operação sem desfazer não pode ficar a um clique de distância de um acidente.
- **Uma cópia do cofre é guardada antes**, com a data no nome e **fora do
  rodízio** dos três backups automáticos — eles giram a cada gravação, e três
  lançamentos depois do reset nenhum deles teria mais o dado antigo. É a única
  volta atrás que existe, e abre com a senha do momento em que foi tirada.
- **O dado sai do arquivo, não só das consultas.** `DELETE` deixa os bytes numa
  página livre e o banco inteiro vai cifrado para o disco: sem `VACUUM`, quem
  tem a senha ainda leria o que foi mandado apagar.
- Sobrevivem só as **preferências** (tema, CPF, senhas de PDF) e as **séries do
  Banco Central**, que são dado público em cache. **Senha mestra e chave de
  recuperação não mudam** — o cofre é o mesmo, vazio.

## [0.4.2] — 2026-08-03

### Corrigido — "Atualizar cotações" acusava falha onde não havia

- **Renda fixa não é mais consultada na bolsa.** CDB e Tesouro não têm código de
  negociação, então cada um virava uma linha de falha no relatório de cotação.
  Numa carteira real dava **dez falhas e zero atualizações com tudo certo** — o
  relatório dizia que a cotação estava quebrada quando não estava. O preço desses
  papéis vem da curva ou da posição da B3.
- **O relatório passou a dizer quantas cotações foram ignoradas**, e por quê.
  Importar a posição da B3 e cotar em seguida mostrava zero atualizações sem
  nenhuma explicação: o preço oficial da B3 já estava lá e vence o baixado.

## [0.4.1] — 2026-08-03

### Corrigido — achado ao conferir a carteira real depois da importação completa

- **O bloco "Renda fixa e Tesouro" sumia da Carteira.** Ele era montado a partir
  dos títulos *cadastrados*, e papel sem cadastro é o caso **normal**: a
  Movimentação da B3 cria o ativo de renda fixa sem dizer indexador nem taxa. O
  resultado era ver cinco CDBs na tabela principal e o bloco de renda fixa
  simplesmente não existir. Agora ele percorre a carteira, e o papel sem cadastro
  aparece com o último preço conhecido e a explicação do que falta informar.
- **O relatório de Renda fixa quebrava** com esses mesmos papéis, porque a
  alíquota regressiva conta da emissão e a emissão só existe no cadastro. Agora a
  coluna sai como `—`: sem cadastro não há estimativa a dar, e inventar uma seria
  estimativa dentro de conta de imposto.
- **A mensagem da portabilidade dizia o que não era verdade.** Ela afirmava que o
  arquivo não traz a instituição de destino; ele traz — a portabilidade vem em
  **duas linhas**, débito na origem e crédito no destino. A linha continua
  pendente (metade dela não diz para onde o papel foi), mas agora informa papel,
  data, quantidade, corretora e lado, e avisa que **transferência move posição,
  não cria**: se o papel veio de uma corretora que o Peculium nunca viu, o que
  falta é a compra original.

## [0.4.0] — 2026-08-03

### Adicionado — conferência contra a B3

- **Leitor do relatório de Posição** (`importar_posicao.py`), que também lê os
  consolidados anual e mensal. Ele **nunca cria lançamento**: retrato traz
  quantidade e valor de mercado, não o custo de aquisição, e inventá-lo
  corromperia o preço médio e, atrás dele, o imposto. O que faz:
  - **confere** a carteira calculada contra a da B3, papel a papel, **na data do
    retrato** — auditoria independente do sistema inteiro;
  - **grava os preços oficiais do dia** sem precisar de rede, inclusive o do
    **Tesouro IPCA+**, que não tem outro jeito de ser precificado porque a curva
    dele não se reconstrói sem o VNA oficial;
  - **completa o cadastro de renda fixa** com emissor, indexador e datas.
- **Instruções na tela de importação** dizendo quais dos seis relatórios da B3
  baixar, e por quê. Proventos Recebidos e o consolidado mensal ficam de fora: o
  primeiro repete a Movimentação, o segundo é o mesmo retrato em outra data.
- **Precedência de origem nas cotações**: o preço digitado à mão vence sempre;
  entre os automáticos, o oficial da B3 vence a curva calculada. Sem essa ordem,
  recalcular curvas apagava o preço bom com um estimado.

### Corrigido

- **Título sem taxa não inventa mais curva.** A posição da B3 não informa a taxa;
  com taxa zero a curva saía plana e sobrescrevia o preço oficial. `renda_fixa.pu()`
  agora recusa calcular e diz o que falta.
- **Preço unitário na tela ganhou casas decimais.** Os CDBs são emitidos a
  R$ 0,01 e, com duas casas, a coluna de PU inteira virava `0,01`.

## [0.3.2] — 2026-08-03

### Corrigido — a planilha da B3 não importava

- **A planilha da B3 declara uma dimensão falsa** (`A1:A1`). O leitor acreditava
  nela e enxergava só a primeira coluna, então o cabeçalho chegava com um campo
  só e o arquivo era recusado como "não é da Área do Investidor da B3".
- **A planilha usa ponto decimal**, ao contrário do CSV. O valor `9.919` de um
  provento virava `9919` — mil vezes o real. A convenção decimal passou a ser
  decidida **uma vez por arquivo**, pelo conjunto dos valores, em vez de
  adivinhada número a número.
- **Renda fixa na Movimentação** (`APLICAÇÃO`, `RESGATE ANTECIPADO`,
  `COMPRA / VENDA`) era recusada como movimentação desconhecida. Agora entra, com
  o sentido vindo de Entrada/Saída.
- **O código do papel de renda fixa vinha errado**: em `CDB - CDB726AWP4H - BANCO`
  o leitor pegava `CDB`, o que faria **todos os CDBs virarem o mesmo ativo**.

### Mudado

- **Subscrição fica pendente de lançamento manual.** As linhas nomeiam o direito
  ou o recibo (`MXRF12`, `MXRF13`), não o ativo que entra na carteira — importar
  como está criava posição fantasma e registrava o custo no ativo errado.
- **Venda sem posição anterior não derruba mais a apuração.** O extrato da B3
  cobre uma janela e a compra pode ser anterior a ela; um resgate órfão fazia a
  carteira inteira sumir da tela. Agora a venda é ignorada, com aviso explícito
  de que ficou fora da posição **e** do imposto — inventar o custo produziria
  imposto errado.

## [0.3.1] — 2026-08-03

### Corrigido

- **Cofre criado por versão anterior não migrava.** O esquema só era atualizado na
  *criação* do cofre, nunca na abertura — então um cofre da v0.1.x continuava com
  o formato antigo e a Carteira morria com o erro cru do SQLite
  (`no such column: t.ativo_id`). A atualização passou a acontecer ao abrir, e
  fica gravada.
- **Migração que falha não impede mais abrir o cofre.** Um cofre que não abre é
  muito pior que uma tela quebrada: agora ele abre avisando, e o resto do
  programa continua funcionando.

### Mudado

- A janela abre **maximizada**.

## [0.3.0] — 2026-08-03

### Notas de renda fixa

Fecha a renda fixa: o título deixa de precisar de cadastro à mão.

- Leitores de **nota de renda fixa em PDF**, um por corretora — XP e Inter.
  Diferente da renda variável, onde quase toda corretora usa o mesmo layout do
  Sinacor, aqui **cada uma inventa a sua**, e as duas não têm uma linha em comum.
- Importar a nota **cadastra o papel e lança a aplicação de uma vez**, com
  emissor, indexador, taxa, emissão, vencimento e o preço unitário certo — que
  era justamente o dado difícil do cadastro manual.
- Arquivo de corretora ainda não suportada é **recusado com essa explicação**, em
  vez de ser lido pela metade.
- Dois invariantes barram a nota que não fecha: quantidade × preço unitário tem
  de dar o valor bruto, e bruto − IR − IOF tem de dar o líquido.

### Proteção contra fusão de papéis

Uma nota real da Inter identificava o título apenas como `3`. Usar isso como
código faria **qualquer outro papel também numerado `3` fundir-se com ele** —
duas aplicações diferentes virariam uma posição só, sem aviso. Quando o código
da nota não identifica o papel, o programa deriva um do nome e do vencimento e
marca a linha como **derivado** na conferência.

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

[0.3.2]: https://github.com/devtulio/peculium/releases/tag/v0.3.2
[0.3.1]: https://github.com/devtulio/peculium/releases/tag/v0.3.1
[0.3.0]: https://github.com/devtulio/peculium/releases/tag/v0.3.0
[0.2.0]: https://github.com/devtulio/peculium/releases/tag/v0.2.0
[0.1.1]: https://github.com/devtulio/peculium/releases/tag/v0.1.1
[0.1.0]: https://github.com/devtulio/peculium/releases/tag/v0.1.0
