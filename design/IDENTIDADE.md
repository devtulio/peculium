# Peculium — Identidade Visual e Notas Históricas

> Documento de referência da identidade do Peculium: o nome, a marca, o selo,
> os temas — e a fundamentação histórica de cada escolha. Decidido em 2026-08-02.
> A régua do projeto, herdada do Licitarium: **fidelidade histórica real, não
> cenográfica** — cada elemento visual corresponde a um artefato ou convenção que
> existiu.

---

## 1. O nome

**Peculium** — do latim *peculium, -i* (neutro), por sua vez de *pecu* / *pecus*
("gado"), a mesma raiz de *pecunia*: a riqueza romana arcaica media-se em cabeças
de gado.

Em direito romano, o **peculium** é o conjunto de bens que o *filius familias* ou
o servo administrava **em separado** do patrimônio do *pater familias*, com
gestão própria e contabilidade própria, ainda que a titularidade formal
permanecesse com o *pater*. Não é uma palavra escolhida por soar latina: é um
instituto com título próprio no Digesto — **D.15.1, *De peculio*** — e ação
processual própria, a *actio de peculio*, pela qual o credor cobrava do *pater*
até o limite do peculium.

Leitura resultante: **patrimônio pessoal, administrado por quem o opera, com
escrituração à parte** — exatamente o que o software faz.

Sobrevive em português como "pecúlio" (poupança, reserva formada aos poucos), o
que dá reconhecimento imediato ao falante de pt-BR sem sacrificar a origem.

Pronúncia: "pecúlium". Grafia do produto: **Peculium** em texto corrido;
**PECVLIVM** apenas no wordmark (§2).

## 2. O wordmark — PECVLIVM

**Nota histórica.** O alfabeto latino clássico não distinguia U de V: o sinal
**V** representava tanto a vogal /u/ quanto a consoante /w/. A letra U como forma
distinta só se consolida na Idade Moderna. Toda inscrição romana autêntica grafa
AVGVSTVS, PVBLICVS, PECVLIVM. O wordmark segue a convenção — é o nome como um
lapicida romano o gravaria.

- Tipografia: serifada (Georgia como fonte de sistema; aproximação acessível da
  *capitalis monumentalis*, a letra das inscrições monumentais romanas).
- Espaçamento largo (letter-spacing ~0.16em), maiúsculas sempre.
- **Os dois V recebem a cor de destaque do tema ativo** — únicos pontos de cor no
  wordmark. Destacar só o segundo V foi testado e descartado: desequilibra a
  palavra, que tem os dois V em posições simétricas.
- Subtítulo institucional (sem serifa, fonte do sistema): "Gestão de patrimônio
  pessoal".

**Divisa: SVVM · CVIQVE** — "a cada um o que é seu", o terceiro dos *iuris
praecepta* de Ulpiano (D.1.1.10: *iuris praecepta sunt haec: honeste vivere,
alterum non laedere, suum cuique tribuere*). Alternativa registrada, para citação
direta do instituto: **DE · PECVLIO**, o título do Digesto.

**Os interpontos (·)**: a epigrafia romana separava palavras com pontos a meia
altura (*interpuncta*), não com espaços. Todos os textos latinos da marca os usam.

## 3. O selo — par oficial

Dois estados do mesmo artefato — o *codex accepti et expensi* —, com papéis
distintos:

| Papel | Artefato | Arquivo |
|---|---|---|
| **Ícone** (exe, atalho, barra de tarefas, janela) | Tabulae ligatae: o díptico fechado, atado e lacrado | `icone-e3.svg`, `icone-e3-16.svg`, `peculium.ico` |
| **Marca de apresentação** (splash, tela Sobre, README, manual) | Codex aberto, com cera, incisões e estilete | `codex-e1.svg` |

**O artefato.** O *codex accepti et expensi* era o livro-caixa doméstico do
*pater familias*, escriturado em tabuinhas de madeira com campo rebaixado cheio
de **cera enegrecida**: o estilete raspava a cera e revelava a madeira clara
embaixo. Registrava o *acceptum* (recebido) e o *expensum* (gasto) — Cícero o
invoca como prova em juízo. É o ancestral direto do livro-razão, e é a forma
exata do modelo de dados deste sistema, que também é um razão de lançamentos.

### 3.1 O ícone: tabulae ligatae

O díptico **fechado, atado pelo *linum*** (o cordão) e **lacrado** com o
*sigillum* em púrpura, com o **P** capitular gravado no lacre e o corte das
lâminas visível na base.

**Nota histórica.** Atos jurídicos romanos — testamento, contrato, quitação —
eram escritos em tabuinhas, **amarrados com um cordão e selados** pelas
testemunhas; só se abriam sob autoridade competente. O ícone não ilustra apenas o
livro: ilustra **o livro sob lacre**, que é literalmente o que o programa é — um
razão que só abre com a chave.

Decisões de desenho, todas conferidas na folha de prova (`icone-prova-barra.png`):

- **Uma volta de cordão, não uma cruz.** A primeira versão cruzava o *linum* na
  vertical e na horizontal, e o resultado lia **embrulho de presente**. Uma banda
  só resolve, e continua fiel: o cordão dava a volta na peça.
- **O corte das lâminas na base**, encostado na capa. Com folga, lê como sombra
  solta; sem ele, a peça lê como caixa em vez de pilha de tabuinhas.
- **Sigillum sobre o nó**, com anel de bronze e o P em Georgia bold.

### 3.2 A marca de apresentação: o codex aberto

O díptico **aberto em uso**: duas molduras com o *margo* elevado, campo de cera
enegrecida, incisões claras em **duas colunas — descrição à esquerda, valor
alinhado à direita**, anéis de bronze na dobradiça, e o **estilete** atravessando
a peça.

O estilete tem **ponta afiada num extremo e espátula achatada no outro** — a
espátula alisava a cera para apagar. É o detalhe que identifica o objeto; sem
ele, o traço vira uma linha qualquer.

### 3.3 Regras de uso do selo

1. Ícone e marca de apresentação não se substituem: lacrado = identificação
   compacta; aberto = apresentação com respiro.
2. Não recolorir, não esticar, não rotacionar; não acrescentar texto na capa do
   ícone além do P do lacre.
3. O `.ico` é **multi-frame com arte dupla**: frames 256/128/64/48 usam a arte
   completa (`icone-e3.svg`); frames **32/24/16** usam a arte dedicada
   (`icone-e3-16.svg` — capa e P, sem cordão nem lacre).
4. **O corte é em 32, não em 24 como no Licitarium.** O *sigillum* é detalhe fino
   e o frame de 32 já sai borrado com a arte completa — verificado na folha de
   prova, não estimado.
5. A arte pequena mantém **capa escura com letra clara**: serve às duas barras de
   tarefas do Windows (a massa aparece na clara, a letra aparece na escura).
   Campo claro invertido foi testado e reprovado — some na barra clara.
6. Regenerar sempre por `gerar_ico.py` (Pillow: desenho a 1024 px, redução
   LANCZOS, SHARPEN nos frames ≤32 px, frames do maior para o menor, fundo
   transparente). Depois de trocar o `.ico`, limpar o cache de ícones do Explorer
   — senão o Windows continua exibindo o antigo.

## 4. Cores

| Cor | Hex | Papel na marca | Nota |
|---|---|---|---|
| Púrpura tíria | `#63234c` | Capa das tabuinhas, molduras, destaque dos temas claros | Tinta de *murex*, a cor mais cara do mundo romano e restringida por lei ao patrimônio da elite |
| Púrpura escura | `#4a1a3a` | Lacre, dobradiça | |
| Púrpura clara | `#8d3f72` | *Margo*, filetes, lâmina superior | |
| Cera | `#332a1a` | Campo de escrita | Cera enegrecida com fuligem, como a das tabuinhas reais |
| Osso | `#e9e1d0` | Incisões do estilete, P do lacre | A madeira clara revelada sob a cera |
| Linum | `#cfc4aa` | Cordão | Linho cru |
| Aurum | `#b08d3e` | Anel do lacre, anéis da dobradiça | Bronze das ferragens |
| Argentum | `#9aa3ab` | Estilete | Ferro/bronze do instrumento |

**Por que púrpura e não verde.** A cor da marca precisa ser **neutra em relação a
ganho e perda**: verde ou vermelho institucional brigaria com o significado que
essas cores têm dentro da tela (§7). A púrpura é historicamente exata para
patrimônio e não disputa com nenhum token semântico.

O par selo usa essa paleta fixa, **independente do tema ativo** — a marca não muda
de cor com o tema (exceção: os V do wordmark, §2).

## 5. Os três temas

Selecionáveis nas configurações, persistidos no banco; **Atrium é o padrão**.
Implementação: CSS custom properties trocadas por `data-theme` no `<html>` — um
layout, três peles.

| Tema | Caráter | Fundo | Destaque | Inspiração |
|---|---|---|---|---|
| **Atrium** (padrão) | Claro, sóbrio | `#f6f4ef` | Púrpura `#63234c` | O átrio da *domus*, onde ficava a arca da casa — a luz do *compluvium* |
| **Cera** | Claro, sépia, serifado nos valores | `#efe6d2` | Púrpura `#63234c` | A tabuinha encerada; serifas e materiais da marca |
| **Aerarium** | Escuro, painel | `#14121a` | Âmbar `#e0a94a` | O *Aerarium Saturni*, o tesouro de Roma guardado **no subsolo** do Templo de Saturno |

Tokens: `--bg --surface --surface2 --text --muted --border --accent --accent-fg
--alta --baixa --erro --radius --shadow`.

No tema escuro o destaque **não** é a púrpura: `#63234c` sobre `#14121a` não
alcança contraste suficiente. Vale a mesma regra descoberta no Licitarium — o que
muda é a tinta, não a mistura do fundo.

## 6. Tipografia

- **Marca e wordmark**: Georgia (serifada de sistema, presente em todo Windows) —
  aproximação pragmática da capitalis monumentalis sem dependência de webfont. No
  `.ico`, Georgia **Bold**.
- **Interface**: fonte do sistema (`system-ui` / Segoe UI).
- **Todo número de dinheiro**: `font-variant-numeric: tabular-nums`, sem exceção.
  Coluna de valor desalinhada é erro de leitura, não questão de gosto.

## 7. Acessibilidade

Padrão WCAG 2.1 AA, mesma régua da família. Além do contraste mínimo de 4.5:1 nos
três temas, foco visível, navegação por teclado e SVG decorativo com
`aria-hidden`, este produto tem uma regra própria:

**Alta e baixa nunca se comunicam só por cor.** Todo resultado traz **sinal
(+/−)**, **seta (▲/▼)** e **valor**; a cor é reforço. Deuteranopia atinge cerca de
8% dos homens e colapsa justamente o par verde/vermelho. A configuração **paleta
daltônica** troca o par por azul/laranja mantendo o contraste AA.

## 8. Explorações descartadas (registro de decisão)

- **Nomes**: *Aerarium* (tesouro de Roma — preciso, mas era o tesouro **público**;
  sobreviveu como nome do tema escuro); *Argentarium* (do *argentarius*, banqueiro
  — sabor de banca, não de patrimônio pessoal); *Thesaurium* (genérico demais).
- **Selo, rodada 1**: **arca** (cofre doméstico romano — colide com ícone de app
  de backup e de cofre de senhas); **statera** (a balança romana de braço
  desigual — puxa para o território jurídico, já ocupado pelo SGDP na família).
- **Selo, rodada 2**: **tessera nummularia** (etiqueta de osso do conferidor de
  moedas, com a fórmula SPECTAVIT — historicamente ótima, mas a 16 px vira
  etiqueta genérica); **abacus** romano (lê como grade ou calculadora, o clichê de
  todo app financeiro); **aureus de Iuno Moneta** (disco é a silhueta mais
  disputada que existe, e "moeda dourada" é a cara de app de cripto).
- **Sem desenho**: *sacculus* (saco de moedas — clichê); templo/frontão (lê
  "banco" ou "governo"); **gráfico de linha ou de velas** — descartado pelo
  critério do projeto, que é artefato histórico e não metáfora de mercado.
- Histórico navegável: `selo-v1.html` (6 direções), `selo-v2.html` (variações da
  tessera + novas direções), `selo-v3.html` (refino do codex, com a prova na barra
  de tarefas).

## 9. Arquivos da identidade

```
design/
  IDENTIDADE.md          ← este documento
  icone-e3.svg           arte oficial do ícone (frames 48px+)
  icone-e3-16.svg        arte dedicada aos frames 32/24/16px
  codex-e1.svg           marca de apresentação (codex aberto)
  peculium.ico           ícone multi-frame (256/128/64/48/32/24/16)
  gerar_ico.py           gerador do .ico (fonte da verdade da rasterização)
  icone-preview-*.png    provas ampliadas da última geração
  icone-prova-barra.png  frames reais sobre barra de tarefas escura e clara
  selo-v1.html, selo-v2.html, selo-v3.html
                         histórico de exploração (não são artes finais)
```
