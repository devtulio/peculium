# Peculium — Design

> Arquitetura fechada em 2026-08-02 e **implementada**; este documento acompanha
> o código, não o antecede. Onde os dois divergirem, o código está certo e este
> arquivo está velho.

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
6. **Fases**: v1.0 entregou renda variável e o módulo de IR; a v0.2 trouxe a
   curva da renda fixa e a v0.3 os leitores de nota por corretora. Renda fixa
   está fechada.
7. **Dependências**: `pywebview`, `cryptography`, `openpyxl`, `pypdf`. Nada mais —
   o resto é stdlib. As quatro são justificadas em §12.
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

Instância única por cofre, porque duas janelas no mesmo arquivo se sobrescreveriam
em silêncio. A trava é um **bloqueio do sistema operacional** (`msvcrt.locking` no
Windows, `flock` fora dele) sobre um arquivo ao lado do `.pec`: se o processo
morrer, o SO solta sozinho. Trava por PID gravado em arquivo deixaria resto de
processo morto barrando o usuário do próprio cofre.

Trancar a tela **fecha o cofre no processo**, não só recarrega o HTML — senão a
chave continuaria na memória e a abertura seguinte esbarraria na trava que ele
mesmo segura.

Rotação: os **3 dumps anteriores** ficam como `peculium.pec.1` … `.pec.3`. Também
cifrados — backup é cópia de arquivo, sem rotina própria.

### 3.4 Apagar todos os dados

Operação destrutiva, exposta em Configurações › Zona de risco. Três decisões que
a governam:

**A confirmação é uma frase digitada** (`APAGAR TUDO`), não um botão. Um botão
atrás de um "OK" fica a um clique de um acidente que não tem desfazer.

**A cópia de antes fica fora do rodízio.** Os três backups automáticos giram a
cada gravação — três lançamentos depois do apagamento, nenhum deles teria mais o
dado antigo. `Cofre.instantaneo()` grava uma cópia com a data no nome que
ninguém rotaciona; ela é a única volta atrás que existe, e abre com a senha do
momento em que foi tirada.

**`VACUUM` não é limpeza, é apagamento.** `DELETE` marca a página como livre e
deixa os bytes onde estavam; como o banco inteiro é serializado e cifrado a cada
gravação, sem o `VACUUM` o dado apagado continuaria dentro do arquivo —
recuperável por quem tem a senha, que é exatamente de quem o usuário quis apagar.

A lista de tabelas vem do `sqlite_master`, nunca escrita à mão: uma lista fica
desatualizada assim que alguém acrescenta uma tabela, e o resultado silencioso
seria um "apagou tudo" que não apagou tudo. Sobrevivem só `config` (preferência,
não registro) e `series` (dado público do BCB em cache). Senha mestra e chave de
recuperação não mudam: isto esvazia o cofre, não recria.

### 3.5 Identidade da instituição

A mesma corretora chega com nomes diferentes em cada documento. Num acervo real:
`XP INVESTIMENTOS CCTVM S/A`, a mesma com ponto final, `XP INVESTIMENTOS` e o
nome societário por extenso — quatro grafias, mais duas do Inter. Casando pelo
texto cru são **seis cadastros para três corretoras**, e a posição por
instituição perde o sentido.

`textos.nome_instituicao()` reduz o nome ao de fantasia: sem acento, pontuação
nem forma societária (`S/A`, `CCTVM`, `DTVM`, e as versões por extenso). O
resultado vira a coluna `chave`, com índice único, e **todo** caminho que cria
instituição passa por `lancamentos.instituicao()`.

A busca normaliza o nome gravado na hora, em vez de confiar na coluna: assim uma
linha que entrou por fora continua sendo encontrada. A coluna existe para o
índice único, não para a busca.

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
               -- séries do BCB/SGS: CDI, SELIC, IPCA
rf_titulos    (ativo_id INTEGER PK, emissao TEXT, indexador TEXT, taxa REAL,
               pu_base REAL, vencimento TEXT, emissor TEXT, isento INT, obs TEXT)
notas         (id INTEGER PK, numero TEXT, corretora TEXT, cnpj TEXT,
               data_pregao TEXT, valor_operacoes REAL, total_custos REAL, …)
apelidos      (especificacao TEXT PK, ativo_id INT, criado_em TEXT)
pagamentos    (id INTEGER PK, competencia TEXT, codigo TEXT, valor REAL,
               multa REAL, juros REAL, data TEXT, obs TEXT, criado_em TEXT)
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
| — | RF | **Renda fixa usa `COMPRA` e `VENDA`**: aplicação é compra, resgate é venda. Ver §6.2 |
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

Notas de **renda fixa** são outro assunto e têm módulo próprio — ver §6.3.

### 6.1.1 Reconciliação nota × B3

A nota e o extrato descrevem **o mesmo negócio** com granularidades e datas
diferentes. Três regras, todas aprendidas errando:

**Reconciliar depois de resolver o ticker, nunca antes.** A nota de renda
variável não traz o código do papel; ele vem do usuário, ou de um apelido já
aprendido. Enquanto a reconciliação rodava no `conferir` — antes da resposta —,
o primeiro negócio de cada papel nunca achava contraparte e **duplicava**. A
função é a mesma, chamada duas vezes: no `conferir` para a tela, e no `gravar`
com os tickers já resolvidos.

**Casar no agregado do dia, não linha a linha.** A B3 agrupa execuções que a
nota detalha: 68+12 de um lado, 1+11+68 do outro. Somando o dia os dois fecham.
Compara-se **quantidade e valor**: só a quantidade colaria a nota no negócio
errado quando há duas ordens do mesmo papel no dia com preços diferentes.

**Totais que não batem não são reconciliados.** Aí é negócio de verdade
diferente, e apagar o da B3 perderia lançamento.

Na renda fixa há ainda duas diferenças de forma: a nota é do dia da **negociação**
e o extrato registra a **liquidação** (janela de seis dias), e os dois lados
nomeiam o papel de jeitos diferentes quando a nota não traz código utilizável —
casa-se por quantidade, PU e emissor, não pelo código.

## 6.2 Renda fixa (`renda_fixa.py`, `series.py`)

**Título de renda fixa é um ativo com preço unitário.** Aplicação é compra,
resgate é venda — e com isso o razão inteiro serve sem uma linha de mudança:
quantidade, preço médio, custo e posição funcionam igual. O que muda é de onde vem
a cotação: em vez de mercado, a **curva**, gravada em `cotacoes` com origem
`CURVA`. Daí para frente, carteira, painel e relatórios não sabem que renda fixa é
diferente.

**A curva pertence ao papel, não à compra** — por isso `rf_titulos` é chaveada
pelo ativo. Dois aportes no mesmo CDB são o mesmo título com o mesmo PU; o que
muda é a quantidade, como no Tesouro.

Base de cálculo, com os códigos **conferidos contra a API do BCB**, não assumidos:
série **12** é o CDI diário em % ao dia, **11** a Selic diária, **433** o IPCA
mensal.

- **A série do BCB só publica em dia útil**, então contar registros entre duas
  datas é contar dias úteis. Não existe tabela de feriados neste programa.
- **Percentual do CDI incide sobre a taxa diária, não sobre o fator**:
  `1 + 0,1%×1,10`, e não `(1+0,1%)^1,10`.
- **Fora da cobertura da série, o cálculo é recusado** em vez de devolver um número
  menor que a verdade. Patrimônio subavaliado em silêncio é pior que erro visível.
- **O papel para de render no vencimento.**
- **IPCA+ não tem curva**: depende do VNA oficial, que não se reconstrói com a
  série mensal do IPCA. Preço digitado à mão vence o calculado — é assim que esses
  papéis entram.
- **PU de emissão que não bate com o preço da aplicação na mesma data é recusado.**
  Um CDB de R$ 4,50 (450 × R$ 0,01) cadastrado com o padrão de R$ 1,00 vira uma
  posição de R$ 457 — cem vezes o valor — e o custo continua certo, então nada
  denuncia.

Imposto: renda fixa **não entra na apuração mensal** (§8) — é retido na fonte pela
tabela regressiva da Lei 11.033/2004. O IR mostrado é **estimativa** pelo prazo
desde a emissão; o valor retido de verdade vem no extrato da corretora.

## 6.3 Notas de renda fixa (`importar_nota_rf.py`)

Aqui **não existe "o parser"**: existem adaptadores, um por corretora, escolhidos
pelo conteúdo do arquivo. Ao contrário da renda variável, onde quase toda corretora
usa o layout do Sinacor, **cada uma inventa a sua** para renda fixa — XP e Inter
não têm uma linha em comum. Layout não reconhecido é **recusado com essa
explicação**, em vez de lido pela metade.

Importar cadastra o papel e lança a aplicação de uma vez, com o PU correto — que é
justamente o dado que o cadastro manual erra.

Dois invariantes barram a nota que não fecha: `quantidade × PU = valor bruto` e
`bruto − IR − IOF = líquido`.

**Armadilhas medidas nas notas reais**, cada uma com teste:

- **XP:** o bloco "COMPROMISSADA COM LIQUIDEZ DIÁRIA" repete **todos** os rótulos
  com valores `-`; sem cortar o texto antes dele, lê-se do lugar errado.
- **Inter:** a linha de valores tem **menos campos que o cabeçalho** (a taxa
  negociada vem vazia), então ler por posição erra a quantidade.
- **Inter:** uma nota identificava o papel apenas como `"\x003"`. Usar isso como
  ticker faria **qualquer outro papel também numerado 3 fundir-se com ele** — duas
  aplicações diferentes virariam uma posição só, sem aviso. Quando o código não
  identifica, o ticker é derivado de nome e vencimento e a conferência marca
  **derivado**.

## 6.3.1 Portabilidade e subscrição na Movimentação

**Portabilidade vem em duas linhas** — débito na origem, crédito no destino — e
nenhuma delas sozinha diz para onde o papel foi. O leitor coleta as linhas de
transferência e só as pareia **depois de ler o arquivo inteiro**, casando por
data, papel e quantidade: casar só por data juntaria duas portabilidades do mesmo
dia e trocaria as corretoras entre elas.

Com as duas pontas, o par vira **um** lançamento de transferência (a outra linha
aparece como descartada, com motivo — sumir em silêncio esconderia uma linha que
o arquivo tinha). Com uma ponta só, fica pendente.

**Transferência move posição, não cria.** Se o papel veio de uma corretora que o
Peculium nunca viu, o que falta é a compra original — e quem aponta isso é o
aviso de saldo negativo do razão, que por isso deixou de dizer "falta a
transferência" e passou a nomear as duas causas possíveis.

**Subscrição continua sem virar lançamento**, pelo motivo de sempre: as linhas
nomeiam o papel intermediário (direito `…12`, recibo `…13`), não o que entra na
carteira, e nenhuma traz o valor pago. O que mudou é a orientação: os seis
subtipos exigem coisas diferentes, e **só o "Recibo de Subscrição" vira
posição**. Dizer "lance à mão" para os seis sem distinguir era mandar o usuário
descobrir qual.

## 6.4 Posição da B3 (`importar_posicao.py`) — retrato, não extrato

A B3 exporta seis relatórios. Três interessam, e por motivos diferentes:

| Relatório | O que é | Uso |
|---|---|---|
| Negociação | toda compra e venda | **cria lançamento** |
| Movimentação | proventos, bonificação, aplicação e resgate de RF | **cria lançamento** |
| Posição | fotografia de um instante | **nunca cria lançamento** |
| Consolidado anual/mensal | a mesma fotografia, em outra data | mesmo leitor |
| Proventos Recebidos | subconjunto da Movimentação | não é importado |

**A regra que sustenta o módulo: retrato não vira lançamento.** O relatório de
posição traz quantidade e valor de mercado, mas **não traz o custo de aquisição**.
Criar posição a partir dele inventaria o preço médio e, atrás dele, o imposto —
um erro que não aparece na tela e reaparece na declaração. O que falta de compra
ou venda o usuário lança; o programa não adivinha.

Sobrando isso, o retrato serve para três coisas:

1. **Conferência.** Compara a carteira calculada com a da B3, papel a papel, **na
   data do retrato** — não hoje, senão um consolidado antigo divergiria de tudo
   que foi comprado depois dele. É auditoria independente do sistema inteiro: na
   carteira real apontou exatamente os três lançamentos que faltavam.
2. **Cotações oficiais, sem rede.** Fechamento na renda variável, preço na curva
   na renda fixa e valor atualizado no Tesouro — que é o **único** jeito de
   precificar o Tesouro IPCA+, cuja curva não se reconstrói sem o VNA oficial.
3. **Cadastro de renda fixa.** Emissor, indexador, emissão e vencimento vêm
   prontos.

**Armadilhas medidas nos relatórios reais**, cada uma com teste:

- O Tesouro **não tem código de negociação**. Sem um ticker estável, cada
  importação criaria outro ativo para o mesmo papel; ele é derivado do par
  indexador/vencimento (`TESOURO-IPCA-JUROS-2037`).
- A quantidade vem em formato **americano**, e o Tesouro é o único papel
  fracionado: ler `1.500` como milhar multiplicaria a posição por mil.
- O preço do retrato é o de **hoje**, nunca o PU de emissão. Usá-lo como base de
  um CDB emitido a R$ 1,00 e valendo R$ 1,0295 levantaria a curva inteira 3%; o
  PU vem da aplicação lançada, ou de R$ 1,00 por convenção.
- A B3 deixa o **indexador em branco** em boa parte dos CDBs. Sem ele o título
  não é cadastrado, e a tela diz por quê — o preço dela já entrou, então a
  posição continua certa.
- A posição **não traz a taxa**. Um título com taxa zero geraria curva plana e —
  pior — sobrescreveria o preço oficial da própria B3; `renda_fixa.pu()` recusa
  calcular, e `cotacoes.PRIORIDADE` põe MANUAL acima de B3, e B3 acima de CURVA.

## 7. Rede (`cotacoes.py`) — opcional e contida

Desligada por padrão. Quando ligada:

- **Whitelist de host no código**, jamais em configuração do banco;
- sai só o ticker; nunca quantidade, valor, instituição ou documento;
- timeout curto, falha nunca bloqueia — o programa abre e funciona sem rede;
- **preço digitado à mão sempre vence** o preço baixado, e a origem fica gravada em
  `cotacoes.origem`.

Fontes: cotação de renda variável por provedor plugável (o padrão é API pública,
não contratual — **pode quebrar, e quebrar é aceitável**) e as séries do BCB
(SGS), que alimentam a curva da renda fixa — ver §6.2.

Verificação de versão nova (GitHub API) segue a mesma regra: opcional, silenciosa
ao falhar, e **nunca baixa nem troca binário sozinho**.

## 7.1 Consulta de CNPJ (`cnpj.py`) — opcional e contida

Mesma disciplina do `cotacoes.py`, e pelos mesmos motivos: whitelist de host em
constante de módulo, timeout curto, e **só o CNPJ que o usuário acabou de digitar
sai daqui**. Nada consulta sozinho — a consulta é um clique explícito num campo
que o usuário está preenchendo.

Duas fontes, como na família SGx: **ReceitaWS** primeiro, **BrasilAPI** como
reserva. A reserva não é redundância decorativa: o plano gratuito da ReceitaWS
concede três consultas por minuto, e a segunda tentativa é o caso normal.

**Os dígitos verificadores são conferidos antes de sair para a rede.** Um dígito
trocado voltaria como "não encontrado" depois de uma ida à internet e de gastar
uma das três consultas do minuto; conferindo aqui, o erro é imediato e exato. A
mesma checagem barra o CNPJ errado na gravação do cadastro — errado guardado
volta como "não encontrado" toda vez que alguém tentar usá-lo.

No modelo de ameaça (§2), a linha é: **revela em qual corretora o usuário tem
conta, nunca o que ele tem lá.**

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
  acumulada** e continuam em branco: a série já está disponível desde a v0.2, mas
  a regra de acumulação (Selic mensal a partir do mês seguinte ao vencimento, mais
  1% no mês do pagamento) ainda não foi implementada. Enquanto não for, o campo
  fica vazio — estimar juros dentro de conta de imposto é exatamente o que este
  programa não faz.
- `a_vencer()` alimenta o alerta do painel: o que vence na janela mais o vencido.

### 8.1.1 Juros de mora (Lei 9.430/96, art. 61 §3)

A regra é somar a **Selic acumulada mensalmente**, do mês **seguinte** ao
vencimento até o mês **anterior** ao do pagamento, e acrescentar **1% no mês do
pagamento**. Somam-se taxas mensais; **não se capitaliza dia a dia** — por isso a
série que serve é a **4390** (Selic acumulada no mês, % a.m.), e não a 11 (Selic
diária), que o programa já usava para a curva da renda fixa. A distinção foi
conferida contra a API do BCB, não suposta.

Duas consequências que valem registrar:

**O caso mais comum não precisa de série nenhuma.** Pagar dentro do mês seguinte
ao vencimento não fecha nenhum mês inteiro de atraso: os juros são só o 1% do mês
do pagamento. É o DARF esquecido por poucos dias, e ele passa a sair completo
mesmo sem rede.

**Faltando um mês da série, o programa recusa calcular** e diz qual mês falta, em
vez de somar o que tem. Juros a menos numa guia de recolhimento é diferença que a
Receita cobra depois — a regra da casa (nada estimado dentro de conta de imposto)
vale para menos tanto quanto para mais.

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

## 10.0 Painel: régua, composição e tabela

Estrutura escolhida entre três desenhos, e a decisão que importa registrar é a
que **não** foi tomada: **tema não escolhe layout.** Um só painel roda nos três
temas. Amarrar os dois faria o usuário trocar para o escuro à noite e ganhar uma
estrutura diferente sem ter pedido, e multiplicaria por três o que o teste de
contraste precisa cobrir.

O que o painel mostra, nessa ordem: **régua de quatro somas** (patrimônio, custo,
resultado, proventos), **composição em barra empilhada** (com três ou quatro
classes ela compara proporções melhor que a rosca, e é legível sem legenda
separada), os **dois gráficos** de proventos e aportes, e a **tabela completa de
posições** — não só as maiores.

Duas regras de conteúdo:

**A média de proventos divide pelos meses que tiveram provento**, nunca por doze.
Dividir pelo ano em agosto diria metade do que o usuário recebe por mês.

**A divergência com a B3 fica em destaque, não escondida.** Patrimônio que não
bate com a corretora é o sintoma mais caro que este programa pode ter, e o painel
o encara. Para isso o retrato importado passou a ser **guardado** (`posicao_b3`,
esquema v3): só o que a B3 disse, nunca a conclusão — a comparação é refeita a
cada abertura, senão lançar a compra que faltava não apagaria o aviso.

**Cores de série (`--serie1..4`) são por tema.** No escuro a púrpura não
contrasta, e as séries precisam ser distinguíveis **entre si**, não só do fundo:
lá elas viram âmbar, rosa e azul.

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

## 10.2 Tabelas ordenáveis

Toda tabela sai do mesmo `tabela()`, então ordenar é um ponto só. Três decisões:

**O cabeçalho é um `<button>` de verdade**, não um `<th>` com `onclick`: botão
nativo já traz foco, Enter e Espaço, e `aria-sort` no `<th>` anuncia a ordem ao
leitor de tela. A seta é reforço visual, não a informação.

**A chave de ordenação não é o texto da célula.** A célula já vem formatada para
leitura, e ordenar por ela poria `10/01/2026` antes de `05/12/2025` e
`1.029,52` antes de `285`. `chaveDeOrdem()` reconhece data `dd/mm/aaaa`,
competência `mm/aaaa` e número em pt-BR — incluindo o menos de `sinal()`, que é
U+2212 e não o hífen do teclado.

**Número vem antes de texto**, para que `—` e vazio não se misturem com valores.
O `sort` do JS é estável, então linhas de mesma chave preservam a ordem em que
vieram.

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
  cotacoes.py          # cotação de mercado, rede opcional
  series.py            # séries do BCB (SGS): a base da curva da renda fixa
  renda_fixa.py        # título como ativo com PU; curva, posição e IR regressivo
  importar_nota_rf.py  # nota de renda fixa: um adaptador por corretora
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

**Hoje**: cripto · ativos no exterior e Lei 14.754/2023 · fundos com come-cotas ·
opções e derivativos · multiusuário · sincronização em nuvem · auto-update de
binário · transmissão à Receita · juros de mora do DARF (ver §8.1) · curva do
Tesouro IPCA+, que depende do VNA oficial.

**Sempre**: cotação em tempo real, ordens, corretagem, qualquer execução de
operação. O Peculium **registra e apura** — não opera.
