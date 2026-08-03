# Peculium — Design (ARQUITETURA FECHADA 2026-08-02 — reservada para implementação)

Gerenciador de investimentos pessoais. Programa **desktop**, monousuário, com o
acervo inteiro num **arquivo cifrado por senha mestra**. Segue o Licitarium na
forma (pywebview + SQLite + PyInstaller) e não a família SGx (server + navegador).

> Identidade visual, com as notas históricas de cada escolha: **`design/IDENTIDADE.md`**
> — leitura obrigatória antes de mexer na marca.

## 1. Decisões fechadas

1. **Desktop, sem servidor.** Um processo, `pywebview` + ponte `js_api`. Nenhuma
   porta escutando, nenhum token de sessão, nenhum login de rede.
2. **Cofre.** Todo o banco vive cifrado num arquivo `.pec`; abre com senha mestra.
   Sem senha e sem chave de recuperação, o dado não volta — dito na tela de
   criação, não escondido no manual.
3. **Razão append-only.** `lancamentos` é imutável; posição, preço médio e
   resultado são **derivados por recomputação**. Correção é estorno, nunca UPDATE.
4. **Preço médio é global por ativo**, nunca por corretora — é a regra da RFB, e é
   o que faz portabilidade entre instituições não inventar lucro.
5. **Rede desligada por padrão.** O programa é integralmente utilizável offline.
6. **Fases**: v1.0 renda variável + módulo IR; v1.1 renda fixa e Tesouro.
7. **Dependências**: `pywebview`, `cryptography`, `openpyxl`. Nada mais — o resto é
   stdlib. As três são justificadas em §12.
8. **Repositório público, MIT, CI + Zenodo**, como os outros cinco. O repositório
   guarda código; o cofre nunca sai da máquina.

## 2. Modelo de ameaça

Declarado antes do desenho, para que cada medida responda a um adversário real e
nenhuma seja teatro.

| Adversário | Resolve? | Como |
|---|---|---|
| Quem furta o notebook, ou lê o disco/backup | **Sim** | O `.pec` é opaco sem a senha; nem o esquema é legível |
| Quem tem acesso à mesma rede local | **Sim, por construção** | Não existe porta escutando — não há o que atacar |
| Backup do arquivo em nuvem | **Sim** | O arquivo já é o cofre; sincronizar não expõe nada além do tamanho e da data |
| Malware rodando como o usuário, com o app aberto | **Não** | A chave está na memória do processo. Nada em software local resolve isso, e prometer que resolve seria mentira |
| Provedor de cotação inferindo a carteira | **Parcial** | Só o ticker sai — nunca quantidade, valor ou documento. Ainda assim, **o conjunto de tickers consultados revela a composição** (não os valores). Quem não aceita isso mantém a cotação desligada, que é o padrão |
| Relatório exportado | **Não, por natureza** | CSV e HTML saem em claro. A tela avisa ao exportar; CPF sai mascarado nos documentos impressos |

Fora do modelo: coação física, keylogger de hardware, adversário com acesso
privilegiado ao sistema operacional.

## 3. O cofre

### 3.1 Formato do arquivo

```
peculium.pec
  magic      b"PECVLIVM"          8 bytes
  versao     uint8                 formato do envelope
  hdr_len    uint16 big-endian
  header     JSON, em claro        kdf, salt, params, os dois embrulhos da DEK
  nonce      12 bytes
  corpo      AES-256-GCM(dump do SQLite)  + tag de 16 bytes
```

O `header` em claro entra como **AAD** do GCM: mexer no cabeçalho invalida a tag,
então trocar os parâmetros do KDF por outros mais fracos não passa despercebido.

### 3.2 Duas chaves, não uma

A DEK (32 bytes aleatórios) cifra o banco. A DEK é guardada **embrulhada duas
vezes** no cabeçalho:

- `wrap_senha` — DEK cifrada com a chave derivada da senha mestra;
- `wrap_recuperacao` — DEK cifrada com uma **chave de recuperação** de 256 bits,
  exibida uma única vez na criação do cofre, para o usuário imprimir e guardar
  fora da máquina.

Consequências que justificam o desenho: **a DEK nunca muda**, então trocar a senha
refaz só o embrulho dela — o banco não precisa ser recifrado com chave nova; e
esquecer a senha não é fatal para quem guardou a chave de recuperação, que abre o
mesmo cofre por outro embrulho.

**Caveat que precisa estar visível para o usuário, não só aqui:** como a DEK é a
mesma, **os backups anteriores continuam abrindo com a senha antiga** — eles
carregam o embrulho velho. Trocar a senha porque ela vazou exige apagar os
backups, e a tela tem de dizer isso na hora.

KDF: `hashlib.scrypt`, `n=2**17, r=8, p=1, dklen=32` (128 MiB; **0,30 s medidos**
na máquina de desenvolvimento). Salt de 16 bytes, renovado a cada troca de senha.

Chave de recuperação: 256 bits em **base32 agrupada de 4 em 4** — sem distinção de
caixa e sem os pares que se confundem no papel, porque ela existe para ser
impressa e redigitada à mão.

**O atraso progressivo entre tentativas erradas na tela é contra dedo errado, não
contra atacante** — quem tem o arquivo ataca offline, sem passar pela nossa tela.
Quem defende ali é o custo do scrypt. Registrar isso aqui para ninguém confundir
os dois no futuro.

### 3.3 Ciclo de vida

Abrir: derivar chave → desembrulhar DEK → decifrar → `sqlite3.deserialize()` num
banco **em memória**. Nada em claro toca o disco em nenhum momento.

Gravar: `serialize()` → cifrar com nonce novo → arquivo temporário → `os.replace`
atômico. Acontece **a cada commit**, não ao fechar: crash perde no máximo a última
transação.

```
# ponytail: banco inteiro em memória e regravado por commit. Carteira pessoal fica
# em poucos MB e a regravação custa milissegundos. Teto: ~100 MB, quando o custo
# por commit passa a doer — aí a saída é cifra por página (SQLCipher), não remendo.
```

Instância única por cofre: arquivo de trava com o PID ao lado do `.pec`; PID morto
libera. Duas janelas no mesmo cofre se sobrescreveriam em silêncio.

Rotação: os **3 dumps anteriores** ficam como `peculium.1.pec` … `.3.pec`. Também
cifrados — backup é cópia de arquivo, sem rotina própria.

## 4. Esquema SQLite

```sql
config        (chave TEXT PK, valor TEXT)   -- tema, paleta_daltonica, cotacao_online…
instituicoes  (id INTEGER PK, nome TEXT, cnpj TEXT, ativo INT DEFAULT 1)
ativos        (id INTEGER PK, ticker TEXT UNIQUE, nome TEXT, classe TEXT,
               cnpj TEXT, isin TEXT, segmento TEXT, ativo INT DEFAULT 1)
               -- classe: ACAO | FII | ETF | BDR | UNIT | RF | TESOURO

lancamentos   (id INTEGER PK, data TEXT, tipo TEXT,
               ativo_id INT, instituicao_id INT, instituicao_destino_id INT,
               quantidade REAL, preco REAL, valor REAL,
               custos REAL DEFAULT 0, irrf REAL DEFAULT 0,
               origem TEXT, hash_origem TEXT UNIQUE, importacao_id INT,
               estorna_id INT, obs TEXT, criado_em TEXT)
               -- origem: MANUAL | B3_NEGOCIACAO | B3_MOVIMENTACAO | ESTORNO

eventos       (id INTEGER PK, ativo_id INT, data_ex TEXT, tipo TEXT,
               fator REAL, ativo_destino_id INT, obs TEXT)
               -- tipo: DESDOBRAMENTO | GRUPAMENTO | CONVERSAO | INCORPORACAO

cotacoes      (ativo_id INT, data TEXT, fechamento REAL, origem TEXT,
               PRIMARY KEY (ativo_id, data))
series        (indice TEXT, data TEXT, valor REAL, PRIMARY KEY (indice, data))
rf_titulos    (lancamento_id INTEGER PK, indexador TEXT, taxa REAL,
               vencimento TEXT, emissor TEXT, isento INT)   -- v1.1
importacoes   (id INTEGER PK, arquivo TEXT, tipo TEXT, em TEXT,
               linhas INT, novas INT, duplicadas INT, erros INT)
auditoria     (id INTEGER PK, em TEXT, acao TEXT, detalhe TEXT)
```

Tipos de lançamento:

| Tipo | Mexe em | Observação |
|---|---|---|
| `COMPRA` / `VENDA` | quantidade, custo | `custos` entra no preço médio na compra e reduz o ganho na venda |
| `TRANSFERENCIA` | só a instituição | **Não é venda**: carrega custo e data de origem para o destino |
| `DIVIDENDO` / `JCP` / `RENDIMENTO` | caixa | JCP tem IRRF de 15% na fonte; dividendo é isento |
| `AMORTIZACAO` | reduz o custo | FII amortizando devolve principal — não é rendimento |
| `BONIFICACAO` | quantidade **e** custo | Entra pelo valor declarado pela companhia, não a custo zero |
| `SUBSCRICAO` | quantidade, custo | |
| `APLICACAO` / `RESGATE` | RF (v1.1) | Casa com `rf_titulos` |
| `TAXA` / `IRRF` | caixa | Custódia, taxas avulsas, DARF pago |

Índices: `lancamentos(data)`, `lancamentos(ativo_id, data)`, `cotacoes(data)`.
`hash_origem UNIQUE` é o que torna a reimportação idempotente **no banco**, e não
só na conferência da tela.

## 5. Motor de posição (`razao.py`)

Lê todos os lançamentos ordenados por `(data, id)`, aplica os eventos
corporativos no caminho, e devolve:

- posição por ativo: quantidade, custo total, **preço médio global**;
- quantidade por instituição (para conferir com a corretora);
- apuração por venda: custo médio **na data da venda**, resultado, natureza
  (swing / day trade), balde de compensação;
- proventos por ativo e por competência.

Regras que o motor implementa e que não podem ser digitadas pelo usuário:

- **Day trade é detectado, não declarado**: compra e venda do mesmo ativo, mesma
  instituição, mesmo dia. Digitar day trade à mão é fonte garantida de erro de IR.
- **Desdobramento e grupamento não mudam o custo total**, só quantidade e preço
  médio. Bonificação muda os dois.
- **Venda com quantidade maior que a posição** é erro de dado (importação
  incompleta, quase sempre), não venda a descoberto: bloqueia e aponta o ativo.
- **Saldo negativo numa instituição vira aviso, não erro.** É o caso da
  transferência que faltou na importação: a posição global fecha certinho e o
  furo passaria batido se só a global fosse conferida. A apuração continua — o
  IR não depende de em qual corretora o papel estava.

```
# ponytail: recomputação integral a cada leitura, sem cache. Uma carteira pessoal
# tem ordem de 10^4 lançamentos e o recálculo roda em milissegundos. Cache
# incremental só se passar de ~10^5 — e aí o invalidador é o retroativo, que é
# justamente o caso difícil.
```

Cheque obrigatório: `tests/test_razao.py` com carteira sintética cobrindo
desdobramento retroativo, portabilidade, bonificação e day trade.

## 6. Importação B3 (`importar_b3.py`)

Dois relatórios da Área do Investidor:

- **Negociação** — compras e vendas (data, tipo, mercado, instituição, código,
  quantidade, preço, valor);
- **Movimentação** — proventos, eventos, transferências (entrada/saída, data,
  movimentação, produto, instituição, quantidade, preço unitário, valor).

XLSX por `openpyxl` em modo read-only; CSV pela stdlib.

- **Idempotência por hash canônico da linha** (`hash_origem`). Os extratos da B3 se
  sobrepõem no período: reimportar é o caso normal, não a exceção. O hash inclui o
  **número da ocorrência da linha dentro do arquivo** — sem ele, duas ordens
  idênticas no mesmo dia (mesma quantidade, mesmo preço) viram uma só, em silêncio.
- **"Transferência - Liquidação" da Movimentação é descartada**: é a entrega dos
  negócios que já vêm na Negociação. Sem esse filtro, importar os dois relatórios
  duplica a carteira inteira. Todo descarte aparece na conferência com o motivo.
- **O relatório de Negociação não traz corretagem nem emolumentos.** Todo preço
  médio importado nasce sem custos, e a conferência avisa isso em toda importação.
- **Portabilidade fica pendente, não entra sozinha**: o arquivo não diz a
  instituição de destino, e adivinhar quebraria o custo de aquisição.
- **Mercado fracionário é o mesmo ativo**: `PETR4F` normaliza para `PETR4`, senão o
  preço médio global se parte em dois.
- **Sufixo 11 nunca é classificado sozinho** (FII, ETF e unit dividem o número, e a
  classe muda a alíquota): a conferência exige confirmação.
- **Tela de conferência antes de gravar**: novos, duplicados, e o que não casou com
  ativo conhecido. Nada entra sem passar por ela.
- **O arquivo original não é guardado** — traz CPF. Só ficam as linhas
  normalizadas e o registro em `importacoes`.
- Cabeçalho da B3 muda sem aviso: o leitor casa coluna **por nome normalizado**, e
  falha com mensagem nomeando a coluna que faltou — nunca por posição.

## 6.1 Nota de corretagem (`importar_nota.py`) — a única fonte dos custos

A B3 não informa corretagem nem emolumentos; a nota informa. **Não existe cálculo
de custo estimado neste programa**, e a razão é empírica: medido em 7 notas reais
da XP, a taxa operacional é **valor fixo por nota** — R$ 9,80 nas duas notas que
continham ação, zero nas cinco que só tinham FII e Fiagro. Nenhuma alíquota sobre
valor reproduz isso. Negócio sem nota fica com custo zero e **aparece no relatório
como "sem custos"** — não se inventa número dentro de cálculo de imposto.

**Dois invariantes aritméticos são o porteiro.** A nota só é aceita se:

1. a soma **assinada** das linhas (compra positiva, venda negativa, pelo D/C de
   cada linha) reconstruir o "Valor líquido das operações"; e
2. `operações + custos + IRRF` reconstruir o "Líquido para <data>", também com
   sinal — em nota de venda o líquido é crédito.

Falhou, **recusa a nota** em vez de gravar número errado. Quando a diferença é
exatamente o IRRF, a mensagem diz isso, porque essa leitura só se decide com uma
nota de venda real — que o acervo atual não tem.

Conferido contra as 7 notas reais: 19 negócios, os dois invariantes fechando e o
rateio reconciliando ao centavo em todas.

**Rateio pro rata pelo valor financeiro de cada linha, com a última absorvendo o
resíduo** do arredondamento a centavos. Sem absorver, três linhas iguais rateando
R$ 10,00 dão R$ 9,99 e o custo de aquisição passa a divergir da nota que o
comprova. O IRRF rateia **só entre as vendas**.

**Três fatos do layout** (extração por `pypdf`, que não devolve ordem visual):

- No cabeçalho o rótulo vem **antes** do valor; no resumo financeiro o valor vem
  **antes** do rótulo. São duas convenções opostas no mesmo arquivo.
- A coluna de observação é opcional e a especificação ocupa de uma a três linhas,
  então cada negócio se lê **pelas pontas**: três campos na frente, quatro atrás.
- `ER`, `ED`, `EJ`, `NM`, `N2` são etiquetas do papel e ficam na especificação; só
  `@ # D T ...` são observação. Confundi-las comeria parte do nome do ativo.

**A nota não traz ticker**, exceto nos FII, onde ele vem embutido
(`FII MAXI REN MXRF11 CI`). O resto se resolve pela tabela `apelidos`, aprendida
uma vez por ativo. Por isso a nota **não é fonte de negócio, é fonte de custo**:
reconcilia com o que veio da B3 por data, sentido, quantidade e preço, e só cria o
negócio quando não há contraparte. Enriquecer é **estorno mais relançamento** — o
razão é append-only e a correção fica visível no extrato.

**Senha: não há regra confiável.** Medido: parte das notas da XP não tem senha,
parte usa uma de três dígitos que **não** deriva do CPF, e uma nota da Inter abriu
com os **6 primeiros dígitos** dele. Então a senha cadastrada por corretora (no
cofre) é tentada primeiro e é o único caminho garantido; os candidatos derivados
do CPF são conveniência.

**Renda fixa fica para a v1.1** e precisa de adaptador por corretora: XP e Inter
têm layouts completamente diferentes entre si e do Sinacor, e notas de RF não têm
corretagem nem emolumentos — só IOF e IR.

## 7. Rede (`cotacoes.py`) — opcional e contida

Desligada por padrão. Quando ligada:

- **Whitelist de host no código**, jamais em configuração do banco;
- sai só o ticker; nunca quantidade, valor, instituição ou documento;
- timeout curto, falha nunca bloqueia — o programa abre e funciona sem rede;
- **preço digitado à mão sempre vence** o preço baixado, e a origem fica gravada em
  `cotacoes.origem`.

Fontes: cotação de renda variável por provedor plugável (o padrão é API pública,
não contratual — **pode quebrar, e quebrar é aceitável**); para a v1.1, séries do
BCB (SGS: CDI, IPCA, Selic) e preços do Tesouro Transparente.

Verificação de versão nova (GitHub API) segue a mesma regra: opcional, silenciosa
ao falhar, e **nunca baixa nem troca binário sozinho**.

## 8. Módulo IR (`fisco.py`)

Apuração mensal em **baldes que não se compensam entre si**:

| Balde | Alíquota | Isenção | Compensa com |
|---|---|---|---|
| Ações, swing trade | 15% | Vendas ≤ R$ 20.000 no mês | Só swing |
| Day trade | 20% | Nenhuma | Só day trade |
| FII | 20% | Nenhuma | Só FII |
| ETF e BDR | 15% | Nenhuma | Swing |

Saídas: resultado do mês por balde, prejuízo acumulado (sem prazo de validade),
imposto devido, **DARF com piso de R$ 10** — abaixo disso acumula para o mês
seguinte, não desaparece —, e o IRRF retido para dedução.

Decisões que o código fixou e que não são óbvias no enunciado da lei:

- **O limite de isenção é sobre o valor bruto da alienação**, não sobre o líquido
  de custos — e não é faixa: passou de R$ 20.000, tributa o ganho inteiro, não só
  o excesso.
- **FII em day trade continua no balde de FII.** O ganho é 20% e só compensa com
  FII; separá-lo por natureza abriria compensação indevida com day trade de ações.
- **IRRF excedente atravessa o mês.** O "dedo-duro" de 1% no day trade costuma
  passar do imposto devido; sem carregar o excedente, o usuário pagaria duas vezes.
- **Vencimento do DARF = último dia útil do mês seguinte**, considerando só fim de
  semana. Nenhum feriado nacional do calendário atual cai no último dia útil de um
  mês; se passar a cair, entra tabela de feriados.
- Apurar um ano isolado é impossível: prejuízo e IRRF excedente atravessam meses e
  anos sem prazo. A apuração sempre percorre a história inteira.

Relatórios anuais: **posição em 31/12 com custo de aquisição** (Bens e Direitos),
rendimentos isentos (dividendos), tributação exclusiva (JCP, FII).

**Ponto controverso, tratado com aviso e não com decisão silenciosa**: prejuízo
apurado em venda dentro da isenção dos R$ 20 mil. O entendimento da RFB é que não
é compensável; parte da doutrina discorda. O padrão do sistema é **não compensar**,
com selo na tela explicando e apontando o valor que estaria em jogo.

O sistema apura e informa. **Não transmite nada à Receita e não emite DARF
oficial** — imprime a memória de cálculo para o usuário conferir e pagar.

## 8.1 Contas a pagar dos DARF (`obrigacoes.py`)

**O valor devido nunca é gravado.** É recalculado do razão a cada consulta, porque
uma nota de corretagem importada depois muda a apuração de um mês já fechado.
Gravar o DARF criaria uma segunda verdade que o lançamento retroativo desmente.

O que se guarda é o **pagamento** (`pagamentos`), que é fato consumado. O
cruzamento dos dois produz o sinal mais útil do módulo: *pagou R$ 1.500 e a
apuração agora dá R$ 1.520*. Situações: `ACUMULANDO` (abaixo do piso, ainda não é
DARF), `PENDENTE`, `VENCIDO`, `PAGO`, `PARCIAL`, `A_MAIOR`.

- **Pagamento órfão aparece**, não some: se a apuração deixou de gerar DARF para
  aquele mês, a linha continua na tela pedindo conferência.
- **Vários pagamentos por competência somam** — quem paga em atraso às vezes
  recolhe principal e encargos em guias separadas.
- **Multa de mora sim, juros não.** A multa é determinística (Lei 9.430/96 art.
  61: 0,33% por dia, teto de 20%) e é calculada. Os **juros dependem da Selic
  acumulada**, que só existe depois da série do BCB (v1.1): até lá o campo vem
  vazio e a tela mostra um traço. Estimar juros dentro de conta de imposto é
  exatamente o que este programa não faz.
- `a_vencer()` alimenta o alerta do painel: o que vence na janela mais o vencido.

## 8.2 Entrada manual (`lancamentos.py`)

Único caminho de escrita no razão fora dos importadores. Existe para a validação
não ficar espalhada na tela — e porque `eventos` estava implementado no razão e
**inalcançável**: não havia como cadastrar um desdobramento.

- Aceita data em ISO ou `dd/mm/aaaa`, e **recusa data futura**: lançamento no
  futuro corrompe em silêncio toda pergunta sobre "a posição hoje".
- Aceita ativo por ticker ou id, instituição por nome ou id; o que não existe
  falha nomeando o campo, não com erro de chave estrangeira.
- **Toda gravação deixa linha em `auditoria`** — tabela que existia sem ninguém
  escrever nela.
- `estornar()` recusa estornar duas vezes e recusa estornar um estorno.
- Evento não tem estorno: quem erra o fator remove o cadastro (a remoção fica na
  auditoria). Evento é fato da companhia, não do usuário.
- Um teste amarra a lista de tipos aceitos aqui à que o `razao` sabe processar —
  as duas divergirem seria um lançamento gravável e inapurável.

## 9. Processo e ponte Python↔UI

```python
webview.create_window("Peculium", "ui/index.html", js_api=Api())
```

```python
class Api:
    abrir_cofre(senha) / criar_cofre(senha) / trocar_senha(atual, nova)
    painel()                          # KPIs + séries do dashboard
    carteira(filtros)                 # posição consolidada
    lancar(dados) / estornar(id)      # nunca editar
    listar_lancamentos(filtros, pagina)
    importar(caminho)  -> conferência # não grava
    confirmar_importacao(token)       # grava o que foi conferido
    proventos(periodo) / apurar_ir(ano, mes)
    cotar(tickers)                    # só se cotacao_online estiver ligada
    relatorio(nome, params, formato)  # html | csv, diálogo de salvar nativo
    get_config() / set_config(...)
```

Cofre fechado = só `abrir_cofre` e `criar_cofre` respondem; qualquer outra chamada
devolve erro. A janela abre na tela de senha, não na aplicação.

Atributos públicos do `js_api` são inspecionados pelo pywebview — **a janela e a
chave ficam em atributos privados** (`_janela`, `_dek`). Erro já cometido no
Licitarium; não repetir.

## 10. UI

Abas: **Painel · Carteira · Lançamentos · Proventos · Importar · Impostos ·
Relatórios · Configurações**.

- **Painel**: patrimônio total, resultado do dia e do mês, aportes do ano,
  proventos recebidos no ano, alocação por classe, maiores posições, alertas
  (DARF do mês, importação pendente, ativo sem cotação).
- **Carteira**: posição por ativo com preço médio, marcação a mercado, resultado
  não realizado, % da carteira; agrupável por classe ou instituição.
- **Lançamentos**: extrato filtrável, com o estorno visível — o razão mostra a
  correção, não a esconde.
- Três peles por `data-theme` (Atrium, Cera, Aerarium), WCAG 2.1 AA, e a regra do
  §7 de `IDENTIDADE.md`: alta e baixa **nunca só por cor**.

## 10.1 Datas: guarda ISO, mostra BR

O banco guarda **sempre** `AAAA-MM-DD` (e competência como `AAAA-MM`): ordenação,
comparação de vigência e o corte de 31/12 da declaração dependem disso. Data em
`dd/mm/aaaa` no banco ordenaria por dia, não por ano.

Toda conversão para o formato brasileiro é de **apresentação** e mora num lugar
só — `textos.data_br()` e `textos.competencia_br()`. Vale para tabela, rodapé,
aviso, título de relatório e mensagem de erro: nada que chegue aos olhos do
usuário sai em ISO. `23/04/2026`, `07/2026`.

Isso inclui os avisos que o `razao` e o `fisco` produzem — eles são texto de tela,
ainda que nasçam em módulo de domínio.

## 11. Relatórios (`relatorios.py`)

HTML timbrado para impressão + CSV, mesmo motor do Licitarium (impressão sempre em
tema claro; papel é papel).

1. Posição consolidada — por classe, instituição e ativo
2. Evolução patrimonial mensal — **separando aporte de valorização**, que é a única
   forma de a série dizer alguma coisa
3. Rentabilidade — **XIRR** (retorno do dinheiro, o que o investidor quer saber) e
   TWR (retorno da carteira, comparável a índice)
4. Proventos — por ativo, por mês, com *yield on cost*
5. Apuração de IR mensal — memória de cálculo, DARF, prejuízo acumulado
5.1. Contas a pagar — DARF apurado × pago, atraso, multa, total em aberto
6. Informe anual — Bens e Direitos em 31/12, isentos, tributação exclusiva
7. Operações — extrato completo, conferência de importação
8. Custos — corretagem e emolumentos por período e por instituição
9. Alocação alvo × real — desvio e sugestão de rebalanceamento

## 12. Dependências, uma a uma

| Dep | Por quê não dá para evitar |
|---|---|
| `pywebview` | A janela. Alternativa seria abrir porta local, que é justamente o que se quer evitar |
| `cryptography` | AES-GCM não existe na stdlib. **Escrever cifra própria está fora de cogitação** |
| `openpyxl` | Ler XLSX. Escrever é fácil na unha (a família já faz); ler exige o parser |
| `pypdf` | Ler a nota de corretagem, que é a única fonte dos custos. Python puro, sem extensão C — não complica o PyInstaller |

KDF (`hashlib.scrypt`), SQLite, CSV, HTTP, JSON e ZIP são stdlib.

## 13. Layout do repositório

```
Peculium/
  peculium.py          # entry: tela de senha, janela, classe Api
  cofre.py             # formato do .pec, KDF, envelope de chaves, gravação atômica
  esquema.py           # DDL do banco, aplicada dentro do cofre
  textos.py            # número e data em pt-BR, comuns aos importadores
  lancamentos.py       # entrada manual: validação, estorno, evento, auditoria
  razao.py             # motor de posição, preço médio, eventos corporativos
  fisco.py             # apuração de IR, baldes, DARF
  obrigacoes.py        # contas a pagar dos DARF: pagamento é fato, valor é derivado
  importar_b3.py       # leitores XLSX/CSV + conferência
  importar_nota.py     # nota de corretagem em PDF (Sinacor): custos e rateio
  cotacoes.py          # rede opcional (v1.0 renda variável; v1.1 BCB/Tesouro)
  relatorios.py        # HTML timbrado + CSV
  ui/index.html  ui/estilo.css  ui/app.js
  tests/               # pytest: cofre, razão, fisco, importação (carteira sintética)
  tests-e2e/           # Playwright com ponte mockada
  Peculium.spec        # PyInstaller (onefile, windowed, ícone)
  .github/workflows/   # CI: testes em push; exe anexado ao release por tag
  design/              # identidade (ver IDENTIDADE.md)
  README.md  LICENSE(MIT)  CHANGELOG.md  MANUAL.html
```

Cofre do usuário em `%LOCALAPPDATA%\Peculium\peculium.pec` — o exe pode estar em
pasta sem escrita.

**`.gitignore` blindado**: `*.pec`, `*.db`, `*.xlsx`, `*.csv` na raiz. Fixture de
teste é **carteira sintética**; extrato real nunca entra no repositório, nem em
teste, nem em captura de tela do manual.

## 14. Fora do escopo

**v1.0**: renda fixa e Tesouro (v1.1) · cripto · ativos no exterior e Lei
14.754/2023 · fundos com come-cotas · opções e derivativos · multiusuário ·
sincronização em nuvem · auto-update de binário · transmissão à Receita.

**Sempre**: cotação em tempo real, ordens, corretagem, qualquer execução de
operação. O Peculium **registra e apura** — não opera.
