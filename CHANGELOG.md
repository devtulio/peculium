# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/);
versionamento [semântico](https://semver.org/lang/pt-BR/).

## [0.11.1] — 2026-08-04

Segunda rodada da auditoria, agora **contra a API e os arquivos de verdade**. A
primeira foi estática e de unidade e passou por cima destes três: nenhum deles
existe fora do encontro com o mundo real.

### Corrigido — a curva de renda fixa nunca funcionou

Dois defeitos empilhados, e o segundo só aparecia depois de corrigir o primeiro.

- **A série diária do Banco Central nunca descia.** `baixar()` pedia a série
  inteira de uma vez e a API do SGS **recusa** pedido longo de série diária.
  Medido contra a API: sem intervalo devolve `406 Not Acceptable`, 11 anos idem,
  10 anos estoura o tempo de leitura, 2 anos passa. CDI e Selic diária falhavam
  em silêncio, e a renda fixa dizia "ligue a rede em Configurações" com a rede
  ligada. Agora vai em fatias de 5 anos, emendadas — vão entre elas seria o
  defeito de série furada de volta.
- **E não adiantaria baixar.** `atualizar_curvas` pedia sempre a curva de
  **hoje**, e o Banco Central publica o CDI com um dia útil de atraso: falharia
  todo dia, dizendo "atualize as séries" logo depois de atualizá-las. Agora
  calcula até onde a série alcança e grava o PU **na data em que ele vale** —
  adiantá-lo seria inventar um dia de rendimento. `cotacoes.preco()` já cobre a
  diferença, porque procura a última cotação até a data pedida.
- **A tabela mostrava o PU certo E o aviso de série faltando na mesma linha.**
  `posicao()` não aplicava o mesmo recorte. Aviso que grita sem motivo é o que
  faz o usuário parar de ler avisos.

### Corrigido — transferência da corretora para ela mesma

Num acervo real a B3 traz débito e crédito na **mesma** corretora: troca de
conta ou de custódia dentro dela, que não move nada entre instituições. O par
virava um lançamento de transferência de A para A, com dois estragos:

- a **porta manual recusa exatamente isso** (`lancar` exige instituições
  diferentes), então o importador gravava o que o razão proíbe — `gravar()` faz
  `INSERT` direto e nenhuma validação do razão alcança o dado importado;
- o razão debitava antes de creditar e gritava **"saldo negativo"** numa posição
  que fecha em zero. Eram três alarmes graves no painel, todos falsos.

A comparação é pelo nome **normalizado**: no arquivo real as duas pontas vinham
como "TORO CTVM LTDA" e "TORO CTVM", que comparadas cruas passariam batido.

### Verificado e íntegro

O que a mesma varredura exercitou contra dado real e passou: cotação online do
Yahoo, consulta de CNPJ na ReceitaWS, os **10 relatórios** em HTML e CSV (sem
estouro, colunas alinhadas), as 9 telas da API, os juros de mora com a Selic
mensal de verdade, e o leitor de posição contra **seis consolidados anuais**
(2020 a 2025), que trouxe datas, classes e valores corretos em todos.

Custo de aquisição confere pelas cinco portas que o calculam — razão, painel,
carteira, relatório de posição e relatório de bens —, e o mesmo vale para valor
de mercado e proventos.

## [0.11.0] — 2026-08-04

Auditoria do sistema inteiro: 17 módulos lidos linha a linha, cada hipótese
reproduzida rodando o código real. Saíram 25 achados, e este release fecha todos.
Sobre o que já existia, 32 testes de unidade e 4 de tela novos — cada um
verificado por mutação, neutralizando a correção para ver o teste morder.

### Adicionado — o preço à mão, que o sistema mandava digitar e não tinha onde

**Clicar em qualquer linha da Carteira abre o preço unitário.** `cotar_manual`
existia na API sem uma única chamada na tela, enquanto três mensagens do
programa mandavam fazer exatamente isso — inclusive o aviso do Tesouro IPCA+ que
entrou na versão anterior. Aquele papel tinha dois caminhos e um era porta
pintada na parede.

Outros três métodos estavam na mesma situação, e ganharam tela:

- **Eventos corporativos agora aparecem**, com botão de remover. Dava para
  cadastrar um desdobramento e nunca mais vê-lo.
- **Pagamento de DARF pode ser cancelado.** Um valor digitado errado ficava lá
  para sempre.

### Corrigido — graves

- **"Apagar todos os dados" deixava o cofre sem integridade referencial.**
  `PRAGMA foreign_keys` é no-op dentro de transação e os `DELETE` abrem uma, então
  o religar do `finally` não religava nada: até reabrir o programa, lançamento
  apontando para ativo inexistente entrava calado.
- **Série do Banco Central com buraco no meio dava curva errada em silêncio.**
  Cobertura se lê de `min`/`max`, e nenhum dos dois enxerga vão no meio; contar
  linhas só é contar dias úteis se a série for contígua. Com um mês faltando,
  eram 65 dias úteis onde havia 85 e o fator de um CDB saía um ponto percentual
  abaixo da verdade. Agora o vão é detectado, o cálculo se recusa a inventar
  número, e o download refaz a faixa inteira em vez de continuar do fim.
- **Chamadas da interface podiam se atropelar.** O pywebview roda cada chamada
  do JavaScript numa thread nova e a conexão do cofre é compartilhada: o
  `commit()` de uma gravava a importação pela metade de outra. Passam por uma
  trava só.

### Corrigido — apuração e razão

- **DARF pago parcialmente cobrava duas vezes os encargos já pagos.** Um de
  R$ 3.750,00 com R$ 1.000,00 pagos mais R$ 33,00 de multa e R$ 12,00 de juros
  dizia faltar R$ 2.795,00 quando faltavam R$ 2.750,00 de principal.
- **IRRF excedente atravessava o ano-calendário.** Ele abate o imposto dos meses
  seguintes **do mesmo ano** (IN RFB 1585, art. 63 §5); o que sobra em 31/12 vai
  para o ajuste anual da declaração, não para janeiro. O prejuízo, esse sim,
  atravessa anos sem prazo — e continua atravessando.
- **Evento corporativo repetido era aplicado duas vezes.** Dois desdobramentos
  1:2 idênticos faziam 100 ações virarem 400, e sem tela de listagem não havia
  como descobrir.
- **A tela de impostos mostrava o prejuízo de hoje em qualquer ano.** Abrir 2025
  exibia o acumulado atual — um número que nunca existiu naquele dezembro.
- **Corrigir um lançamento perdia o vínculo com a nota de corretagem.** O
  negócio sumia da nota e o extrato passava a dizer "MANUAL" numa linha que veio
  de documento. (O `hash_origem` continua ficando com o original de propósito.)
- **O relatório de custos contava lançamento estornado**, e o painel contava o
  mês cujo único aporte havia sido estornado — ao lado de um total do ano zerado,
  na mesma tela.

### Corrigido — arestas

- **Classe de ativo entrava sem validação:** `CRIPTO` era aceito. A única lista
  das sete vivia no JavaScript, e foi uma cópia incompleta dela que, na v0.9.3,
  fez todo CDB entrar como ação. Aquela correção tirou as cópias; esta põe a
  defesa atrás delas. Ticker repetido também deixou de responder em SQL.
- **Prévia de importação pendente podia ser substituída** por outra e gravar o
  arquivo errado: o token vinha do tamanho do dicionário, não de um contador.
- **Arquivo de cofre truncado devolvia erro cru** (`struct.error`,
  `JSONDecodeError`) em vez de dizer que o arquivo não serve. E o cabeçalho, que
  não é autenticado, passou a ter teto de memória — `n = 2**30` faria o scrypt
  tentar alocar cerca de um terabyte.
- **Gravação do cofre agora faz `fsync`** antes de trocar o arquivo. O rodízio de
  backups protegia contra queda do processo; contra queda de energia, quem
  protege é o `fsync`.
- **Atualizar cotações com ticker fora do cadastro** virava `KeyError` cru, e
  valor vazio numa série do Banco Central derrubava o download inteiro.
- **`vencido` na renda fixa** usava sempre a data de hoje: a posição de 31/12 do
  ano passado marcava como vencido o papel que só venceu depois dela.

### Empacotamento

- **O executável ganhou recurso de versão do Windows** (nome, descrição,
  copyright). Binário sem assinatura e sem metadado não tem por onde ganhar
  reputação — não substitui assinatura, só deixa de piorar. O parâmetro é
  `version=`, não `version_file=`: o `EXE()` do PyInstaller lê os extras de
  `**kwargs` e **ignora em silêncio** o nome que não conhece, então a primeira
  tentativa gerou um binário com todos os campos vazios e nenhuma linha de aviso.
  O CI passou a conferir o recurso no binário pronto.
- **`mock.js` não viaja mais dentro do executável.** É a ponte falsa dos testes
  de tela, e fonte de dado inventado não tem o que fazer no binário publicado.

## [0.10.1] — 2026-08-04

### Mudado — cadastrar título de renda fixa ficou menos trabalhoso

O aviso "título não cadastrado" pedia indexador, taxa e PU de emissão, e o
formulário abria vazio. Dois dos campos o sistema já sabia:

- **Emissão, PU de emissão e emissor vêm preenchidos** da primeira aplicação já
  lançada. O PU é justamente o campo que mais dói errar — ele erra a posição em
  ordem de grandeza, e em silêncio.
- **O Tesouro IPCA+ passou a dizer a verdade.** Cadastrar a taxa dele não faz o
  preço aparecer: a curva depende do VNA oficial, que não se reconstrói da série
  mensal do IPCA. O formulário avisa isso ao escolher o papel, e aponta o
  caminho que funciona — importar a Posição da B3.

Sobra informar **indexador e taxa**, que nenhum arquivo da B3 traz: o relatório
de posição deixa o indexador em branco na maioria dos CDBs, e a taxa nunca vem.
Quem tem a nota de renda fixa do papel não precisa de nada disso — importar a
nota cadastra o título inteiro.

## [0.10.0] — 2026-08-04

### Adicionado — editar lançamento

Clique em **detalhes**, na tela de Lançamentos. São **duas** operações, e a
diferença entre elas é a regra do razão:

- **Observação** muda no lugar. É anotação: nada em posição, preço médio ou
  imposto depende dela, e por isso é o único campo que pode ser alterado sem
  estorno. Aparece numa coluna nova da tabela.
- **Corrigir valores** abre o formulário preenchido e, ao salvar, **estorna o
  lançamento e relança**. Os dois continuam visíveis no extrato — o razão não
  sobrescreve linha, porque o que o imposto apurou ontem tem de continuar
  conferível. Aceita um motivo, que vai para a auditoria.

O `hash_origem` fica com o lançamento original de propósito: assim reimportar o
mesmo arquivo continua reconhecendo a linha como já vista, em vez de criar uma
terceira cópia.

### Corrigido

- **O botão de confirmar não funcionava num diálogo aberto a partir de outro.**
  O evento `close` de um `<dialog>` é disparado numa tarefa enfileirada, não na
  hora; com um ouvinte por abertura, o `close` atrasado do primeiro consumia o
  ouvinte do segundo. Agora o ouvinte é um só e ignora `close` que chegue com o
  diálogo já reaberto.
- **Corrigir preço ou quantidade não recalculava o valor.** Em compra e venda o
  valor gravado vence o cálculo, então a correção gravava o preço novo com o
  total velho. Em provento o valor continua sendo o dado principal e não é
  recalculado.

## [0.9.3] — 2026-08-03

### Corrigido — todo CDB e o Tesouro entravam como AÇÃO

Um defeito só, com dois sintomas.

- **A lista de classes da tela estava incompleta.** Havia três cópias dela no
  JavaScript, e **duas não tinham RF nem TESOURO**. Quando a classe real não
  está entre as opções, o `<select>` cai na primeira — `ACAO` — e é esse valor
  que vai para o banco. Todo CDB e o Tesouro Direto entravam classificados como
  ação. Agora existe **uma** lista, e ela tem as sete classes.
- **A duplicação da renda fixa era consequência disso.** A reconciliação da
  nota com o extrato filtra por classe; com o CDB marcado como ação, ela deixava
  de achar o lançamento da B3 e criava outro. O aporte entrava duas vezes.
- **A tela deixou de poder reclassificar o que o programa sabe.** A escolha da
  interface só vale onde a confirmação foi pedida — um código que começa com CDB
  é renda fixa e ponto. Um defeito de tela não pode corromper o razão.

### Testes

- A tela de conferência do extrato da B3 **não tinha nenhum teste de interface**,
  e é por isso que nada pegou. Agora tem quatro.

## [0.9.2] — 2026-08-03

### Corrigido — cofre da versão anterior não migrava, e a importação falhava

- **`no such column: chave`.** A atualização do esquema rodava o script antes da
  migração. `CREATE TABLE IF NOT EXISTS` não altera tabela que já existe, então
  a coluna nova não nascia — e a linha seguinte do script, que cria o índice
  sobre ela, estourava. A migração que acrescentaria a coluna nunca chegava a
  rodar, e o cofre abria quebrado. **Migração que muda a forma da tabela passou
  a rodar antes do script.**
  - O teste não pegava porque montava um cofre antigo **sem** a tabela
    `instituicoes`; ali o `CREATE TABLE` rodava de verdade. Agora há teste
    contra um banco que **já tem** as tabelas.
- **A migração ficou à prova de tabela faltando**: ela repontava lançamentos sem
  checar se a tabela existia, e migração que estoura no meio degrada o cofre
  inteiro — o que é pior que a duplicata que ela ia corrigir.

### Mudado

- **Cofre que não migrou agora avisa no painel, e não só num toast.** Sete
  segundos é pouco para "telas novas podem falhar": o alerta fica enquanto durar.
- **Renomear uma corretora para o nome de outra explica o que houve**, em vez de
  mostrar `UNIQUE constraint failed: instituicoes.chave`.

## [0.9.1] — 2026-08-03

### Corrigido

- **Código de renda fixa terminado em dígito pedia confirmação de classe.** O
  prefixo já diz o que é: `CDB726AM6KA` era reconhecido e `CDB3268VM70` virava
  pergunta, só porque termina em número. Perguntar a classe de um código que
  começa com CDB é pedir para confirmar o óbvio.

## [0.9.0] — 2026-08-03

### Corrigido — o motor de importação montava a carteira errada

Oito defeitos achados conferindo o acervo completo de um usuário — dez notas de
corretagem e os relatórios da B3 do ano inteiro — contra a posição que a própria
corretora informa. A carteira saía com **R$ 12.689,33** onde o certo eram
**R$ 9.630,65**.

- **A nota duplicava o negócio na primeira vez que via um papel.** A
  reconciliação com a B3 rodava antes de o usuário informar o ticker, e sem
  ticker não há como casar: o negócio entrava de novo por cima do que veio da
  B3. KLBN4 ficava com 570 onde a corretora dizia 285. Da segunda nota em diante
  o apelido já existia e reconciliava certo, o que escondia o problema. Agora a
  reconciliação acontece **depois** de o ticker ser resolvido.
- **A B3 agrupa execuções que a nota detalha.** Num dia real ela trouxe 68+12 e
  a nota 1+11+68; casar linha a linha não fecha nunca. Agora casa pelo
  **agregado do dia**, conferindo quantidade **e** valor — só a quantidade
  colaria a nota no negócio errado quando há duas ordens do mesmo papel no dia.
- **A data da nota não é a data da B3 na renda fixa.** A nota é do dia da
  negociação e o extrato registra a liquidação: 18/06 contra 22/06 num caso
  real, e o mesmo aporte entrava duas vezes. Entrou uma janela de seis dias.
- **O mesmo CDB virava dois ativos.** A nota da Inter que não traz código
  utilizável gera um ticker derivado; a B3 chama o papel pelo código dela. Agora
  casam por quantidade, preço unitário e emissor.
- **A compra de Tesouro Direto era descartada em silêncio.** O importador jogava
  fora toda linha "Compra" da Movimentação dizendo que ela já vinha na
  Negociação — e o Tesouro **não** passa pela bolsa, então não vem. Eram
  R$ 2.079,13 sumindo sem aviso nenhum.
- **O preço da subscrição era jogado fora.** A linha "Direitos de Subscrição -
  Exercido" traz preço unitário e valor, e o programa dizia ao usuário que a B3
  não informava o preço. A subscrição exercida agora vira lançamento sozinha.
- **Os avisos mandavam fazer o que o sistema recusa.** Papel recebido sem
  pagamento (presente, promoção) não pode entrar como COMPRA, que exige preço
  maior que zero. Os avisos passaram a apontar BONIFICAÇÃO.
- **A mesma corretora virava um cadastro por grafia.** Num acervo real havia
  quatro da XP — `XP INVESTIMENTOS CCTVM S/A`, a mesma com ponto final,
  `XP INVESTIMENTOS` e o nome societário por extenso — e duas do Inter: seis
  cadastros para três corretoras. Agora o nome é normalizado (sem acento,
  pontuação nem forma societária) e vira chave única.

### Esquema

- Versão 4: coluna `chave` em `instituicoes`, com índice único. A migração
  **funde** as duplicadas de cofres antigos, repontando os lançamentos antes de
  apagar a cópia — e preserva o CNPJ que só existir na que vai sumir.

## [0.8.0] — 2026-08-03

### Mudado — painel redesenhado

Nova estrutura: **régua de quatro somas** no topo (patrimônio, custo, resultado,
proventos, cada uma com sua nota de contexto), **composição da carteira em barra
empilhada**, **dois gráficos** — proventos mês a mês e aportes acumulados — e a
**tabela completa de posições**, não só as maiores.

- **A divergência com a B3 agora aparece no painel**, com data do retrato,
  quantos papéis conferem e quanto a B3 informa a mais. Para isso o retrato
  importado passou a ser guardado; a comparação é **refeita a cada abertura**,
  então lançar a compra que faltava apaga o aviso sozinho.
- **A média de proventos divide pelos meses que tiveram provento**, não por doze:
  dividir pelo ano em agosto diria metade do que se recebe por mês.
- **A classe aparece por extenso** — "Fundos imobiliários" no lugar de `FII`,
  "Ações" no lugar de `ACAO`. Código de banco não é rótulo de tela.
- **O cifrão vem depois da seta** no resultado: `R$ ▲ +2,60` lê como duas frases.
- Cores de série por tema: no escuro a púrpura não contrasta, e as três séries
  precisam ser distinguíveis **entre si**, não só do fundo.

**Tema continua não escolhendo layout.** Um painel, três temas — amarrar os dois
faria trocar para o escuro à noite render uma estrutura diferente sem ter pedido.

### Esquema

- Versão 3: tabela `posicao_b3`, com o último retrato importado. Cofre antigo
  ganha a tabela ao abrir, sem migração de dado.

## [0.7.1] — 2026-08-03

### Corrigido

- **O formulário de instituição saía espremido.** O CNPJ não é um campo curto:
  carrega o botão de busca ao lado e a nota de privacidade embaixo. Dividindo a
  linha em três, o input ficava com uns 90 px e cortava a própria máscara —
  aparecia `00.000.00` no lugar de `00.000.000/0000-00`. Agora ele ocupa a linha
  inteira, e os campos comuns ganharam uma coluna mínima maior, o que também
  desafogou os outros formulários.

## [0.7.0] — 2026-08-03

### Adicionado

- **Juros de mora do DARF** (Lei 9.430/96, art. 61 §3), a última conta de
  imposto que estava declaradamente incompleta. Soma a Selic acumulada
  mensalmente do mês seguinte ao vencimento até o anterior ao do pagamento, mais
  1% no mês do pagamento — série 4390 do Banco Central, que é acumulada no mês;
  a Selic diária, que o programa já usava para a curva, **não serve** aqui,
  porque a lei manda somar taxas mensais e não capitalizar dias.
  - **O caso mais comum não precisa de série nenhuma:** pagar dentro do mês
    seguinte ao vencimento não fecha nenhum mês inteiro de atraso, então os
    juros são só o 1%.
  - **Faltando um mês da série, o programa recusa calcular** e diz qual falta.
    Juros a menos numa guia é diferença que a Receita cobra depois.
  - A tela de Impostos ganhou coluna de Juros e um botão **Atualizar Selic** —
    quem não tem renda fixa nunca abriria a Carteira, que é onde ficava o único
    botão que baixa séries do BCB.
- **Portabilidade entre corretoras agora é importada sozinha.** Ela vem em duas
  linhas (débito na origem, crédito no destino) e o leitor as pareia por data,
  papel e quantidade; juntas viram um lançamento de transferência. Uma ponta só
  continua pendente, porque metade da portabilidade não diz para onde o papel
  foi.
- **A subscrição passou a orientar por subtipo.** Ela continua não virando
  lançamento — as linhas nomeiam o papel intermediário e nenhuma traz o valor
  pago —, mas agora cada subtipo diz o que fazer, e **só o "Recibo de
  Subscrição" vira posição**.

### Mudado

- O aviso de **saldo negativo numa corretora** dizia "falta a transferência".
  Desde que a portabilidade é importada sozinha, a causa mais comum passou a ser
  outra: a compra anterior, feita na corretora de origem antes do período do
  extrato. O aviso agora nomeia as duas.

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
