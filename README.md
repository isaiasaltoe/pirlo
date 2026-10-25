# pirlo

Faz o agente que você usa (o **líder**) passar o trabalho braçal para **workers mais baratos**, sem você chamar nenhum comando. O líder continua pensando: planeja, decide e escreve o código que importa. O pirlo cuida de rodar testes, ler logs longos, ler documentação e fazer buscas amplas, e devolve só um resumo curto com referências `arquivo:linha`.

O nome é uma homenagem ao Andrea Pirlo, que controlava o meio-campo: recebia a bola, decidia e distribuía.

## Por que isso economiza

A maior parte da cota não vai para o raciocínio do líder. Vai para o que ele **lê**: 30 mil tokens de log de teste para achar duas falhas, um PDF inteiro para achar um parágrafo. No pirlo, quem lê é um worker mais barato, num contexto separado, e o líder recebe só o resumo destilado. É a mesma ideia do cookbook "plan big, execute small" da Anthropic: a economia vem de *quem lê*.

## Como funciona

```text
você ──► líder (Claude Code ou Codex)
           │  tarefa braçal? delega sozinho
           ▼
         pirlo ──► roda o comando (testes, build, lint, LaTeX)
           │       saída curta? devolve direto, sem worker
           ▼
         worker: CLI oficial em modo só leitura
         (agy com Gemini Flash, codex com modelo barato, claude com Haiku...)
           │
           ▼
         resumo curto com arquivo:linha ──► líder
         + uma linha no log local (usage.jsonl)
```

Três comandos fazem o trabalho:

| Comando | Para quê | Quem lê o material bruto |
| --- | --- | --- |
| `pirlo exec -- <comando>` | rodar testes, build, lint, compilar LaTeX | o próprio pirlo roda o comando; o worker só lê a saída |
| `pirlo ask "<tarefa>"` | ler arquivos, docs, PDFs, buscar no código | o worker, em modo só leitura |
| `pirlo edit "<tarefa>"` | edição mecânica pedida explicitamente (renomear, formatar, repetir um padrão) | o worker, com permissão de edição |

**Por que o `exec` roda o comando no pirlo, e não no worker?** Em modo só leitura, os workers não conseguem rodar comandos sozinhos: o `agy --mode plan` para e espera aprovação humana, e o sandbox `read-only` do Codex impede os testes de gravar cache e arquivos temporários. Então o pirlo roda o comando, guarda a saída completa em `.pirlo/runs/` e entrega ao worker só a tarefa de ler. Se a saída for curta (até 2.500 caracteres), ele nem chama o worker: devolve a saída direto, sem gastar cota de ninguém.

## Instalação

Precisa de Python 3.8 ou mais novo. O pirlo só usa a biblioteca padrão.

### Claude Code

Em todos os repositórios (recomendado se você usa em vários projetos):

```bash
claude plugin install pirlo --marketplace isaiasaltoe/pirlo --scope user
```

Só no repositório atual (rode na pasta do projeto):

```bash
claude plugin install pirlo --marketplace isaiasaltoe/pirlo --scope local
```

O escopo `local` grava em `.claude/settings.local.json`, que não vai para o git.

### Codex

```bash
codex plugin marketplace add isaiasaltoe/pirlo
codex plugin add pirlo@pirlo
```

O Codex instala plugins para o usuário inteiro. Para usar só em um repositório, escolha o escopo `local` no setup: os outros repositórios ficam inativos.

## Setup

No Claude Code, rode `/pirlo:setup`. No Codex, peça "configure o pirlo".

O setup:

1. detecta quais CLIs estão instalados e logados (`claude`, `agy`, `codex`) e lista os modelos de cada um. **Não gasta cota**: usa `claude auth status`, `codex login status`, `codex debug models` (o catálogo local) e `agy models`;
2. propõe o mapeamento dos níveis `cheap`, `standard` e `strong` com o que você tem, e deixa você ajustar;
3. pergunta o escopo: todos os repositórios (`~/.config/pirlo/config.json`) ou só este (`.pirlo/config.json`, fora do git);
4. salva a configuração.

Exemplo de proposta para quem tem Claude e Google AI Pro, com o Claude Code como líder:

| Nível | Worker | Para quê |
| --- | --- | --- |
| `cheap` | `agy` com `gemini-3.8-flash-low` | rodar testes, ler logs, buscas |
| `standard` | `agy` com `gemini-3.8-flash-high` | seguir código por vários arquivos, juntar fontes |
| `strong` | `agy` com `gemini-4-argon-medium` | a leitura mais difícil |

Planejamento, arquitetura, design e decisões ficam sempre com o líder.

Outras combinações:

- **Só Claude:** os três níveis ficam `native`. O próprio subagente `pirlo:worker`, que roda em Haiku, faz a leitura. Funciona sem setup.
- **Só Codex:** o líder é o Codex, e os workers são modelos mais baratos do próprio Codex via `codex exec` em sandbox `read-only`.
- **Claude e Codex:** o líder é o Claude Code, e os workers são o `codex exec` com modelo barato.

Os IDs dos modelos nunca ficam fixos no código: vêm do que cada CLI lista na sua máquina.

## Uso

Você não faz nada: escreve normalmente.

- "roda os testes e me diz o que quebrou": o líder delega, o pirlo roda os testes e o worker devolve só as falhas com `arquivo:linha`;
- "o que o capítulo 3 da referência X diz sobre Y?": o worker lê o PDF e responde em poucas linhas;
- "o LaTeX deu erro, o que foi?": o pirlo compila, e o worker lê o `.log` e aponta a linha.

Para tarefas independentes, o líder pode chamar vários workers em paralelo.

**Como o líder sabe que deve delegar?** No Claude Code, por dois caminhos:

1. a descrição do subagente `pirlo:worker`, que o Claude Code usa para decidir quando delegar;
2. um lembrete curto (~110 tokens) que um hook coloca **uma vez no início da sessão**, só nos repositórios em que o pirlo está ativo. Não existe hook a cada prompt.

O segundo caminho existe porque, nos testes, só a descrição do subagente nem sempre bastou: com uma tarefa simples como "rode os testes", o líder às vezes prefere fazer sozinho. Com o lembrete, ele delegou.

No Codex, o mecanismo equivalente é a skill `pirlo`, que o Codex invoca sozinho quando a tarefa bate com a descrição. O Codex não delega para subagentes sem que você peça, por isso o pirlo usa uma skill nele.

## Só leitura por padrão

O worker roda em modo só leitura: `agy --mode plan`, `codex exec --sandbox read-only`, `claude -p --permission-mode plan`. Edição só acontece com `pirlo edit`, quando o pedido é explicitamente mecânico.

O motivo é o custo escondido do retrabalho: se o worker edita mal, o líder precisa reler tudo, e a economia some.

Depois de cada chamada, o pirlo compara o `git status` de antes e de depois:

- em modo só leitura, se algum arquivo mudou, a resposta traz um **aviso** com a lista dos arquivos;
- em modo de edição, a resposta lista os arquivos alterados, para o líder conferir só o `git diff` deles.

## Compatível com o fessor

Quando o [fessor](https://github.com/isaiasaltoe/fessor) está ativo no projeto, o pirlo:

- força o modo só leitura (um `pirlo edit` vira leitura e avisa o líder);
- avisa o worker que o usuário é estudante: ele nunca resolve exercícios nem dá a correção de erros, só relata fatos (o que os arquivos contêm, o que o comando imprimiu, onde as coisas estão).

O pirlo considera o fessor ativo quando encontra `"fessor@...": true` em `enabledPlugins` de `.claude/settings.local.json`, `.claude/settings.json` ou `~/.claude/settings.json`, ou quando encontra uma seção `# fessor` no `AGENTS.md`.

Para respeitar outros plugins pedagógicos ou restritivos, adicione o nome deles em `restrictivePlugins` na configuração. Para forçar o modo só leitura em qualquer lugar, defina `PIRLO_READ_ONLY=1`.

## Quanto economizou

No Claude Code, rode `/pirlo:savings`. No Codex, pergunte pela economia do pirlo. No terminal, rode `pirlo savings`, com `--days 7` para outro período ou `--here` para só o repositório atual.

Cada delegação grava uma linha em `~/.config/pirlo/usage.jsonl` com: data, repositório, CLI, modelo, nível, duração, tamanho do prompt, tamanho da resposta, uso de tokens reportado pelo CLI e sucesso ou falha. O pirlo grava essa linha sozinho, então o log não custa tokens.

O relatório é uma **estimativa**, e diz isso na saída. Não dá para medir quanto o líder teria lido sem o pirlo. Por isso ele mostra uma faixa:

- **piso:** a saída de comandos que o líder nunca viu, menos o que voltou para ele. Esse número é sólido, porque o líder teria lido aquela saída inteira;
- **teto:** o piso mais o que os workers leram nas tarefas `ask`. Os números de tokens vêm do próprio CLI quando ele reporta (`--output-format json` no `agy` e no `claude`, `--json` no `codex`) e, quando não reporta, de uma estimativa por caracteres. É um teto porque inclui o system prompt do próprio worker.

O relatório também mostra o lado do líder: o texto que ele escreveu para delegar e as respostas que leu.

## Custos que o pirlo tem

Para você decidir com números:

| O quê | Custo | Quando |
| --- | --- | --- |
| Descrições do subagente e das skills | ~290 tokens | em toda sessão do Claude Code |
| Lembrete do hook | ~110 tokens | uma vez por sessão, só onde o pirlo está ativo |
| Subagente `pirlo:worker` (Haiku) | ~550 tokens de instruções, mais o contexto base do subagente | a cada delegação no Claude Code |
| `claude -p` como worker | ~34 mil tokens de contexto fixo, quase todo em cache | a cada chamada, se você usar o `claude` como worker externo |

Por isso, para quem só tem Claude, o padrão é `native`: o subagente em Haiku sai bem mais barato que chamar `claude -p`.

A delegação compensa quando há muito para ler: logs grandes, documentação, PDFs, buscas amplas. Não compensa em design de landing page nem em edições pequenas e pontuais. A descrição do subagente diz isso ao líder.

## Permissões

O subagente chama o pirlo pelo Bash, então o Claude Code pode pedir permissão. Para não ser interrompido a cada delegação de leitura, adicione em `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": ["Bash(pirlo ask *)", "Bash(pirlo savings*)"]
  }
}
```

Não libere `pirlo exec` de forma geral: ele roda qualquer comando. Aprove cada comando com "don't ask again", por exemplo `pirlo exec -- bin/rails test`.

No Codex, o pirlo chama outros CLIs, que precisam de rede. O sandbox padrão do Codex bloqueia a rede, então o Codex vai pedir permissão elevada para o comando do pirlo.

## Configuração

O arquivo fica em `~/.config/pirlo/config.json` (escopo user) ou em `.pirlo/config.json` (escopo local, com prioridade). O setup escreve esse arquivo para você, mas dá para editar à mão:

```json
{
  "version": 1,
  "scope": "user",
  "tiers": {
    "cheap": { "cli": "agy", "model": "gemini-3.8-flash-low" },
    "standard": { "cli": "agy", "model": "gemini-3.8-flash-high" },
    "strong": { "cli": "codex", "model": "gpt-5.6-terra", "effort": "medium" }
  },
  "maxReplyWords": 200,
  "maxReplyChars": 6000,
  "inlineOutputChars": 2500,
  "restrictivePlugins": ["fessor"]
}
```

| Campo | O que faz | Padrão |
| --- | --- | --- |
| `tiers` | CLI, modelo e esforço de cada nível. `cli` pode ser `agy`, `codex`, `claude`, `native` ou um adaptador | — |
| `maxReplyWords` | tamanho pedido ao worker | 200 |
| `maxReplyChars` | corte duro da resposta, para proteger o contexto do líder | 6000 |
| `inlineOutputChars` | até esse tamanho, a saída do `exec` volta direto, sem worker | 2500 |
| `embedOutputChars` | até esse tamanho, a saída vai dentro do prompt; acima, vai num arquivo | 50000 |
| `commandTimeoutSeconds` / `workerTimeoutSeconds` | limites de tempo | 900 / 600 |
| `restrictivePlugins` | plugins que forçam o modo só leitura | `["fessor"]` |
| `log` | grava o log de uso | `true` |
| `paths` | caminho de um CLI fora do PATH, como `{"agy": "/opt/agy/bin/agy"}` | — |
| `adapters` | outros CLIs (veja abaixo) | — |

### Outros CLIs

Qualquer CLI com modo não interativo pode virar worker:

```json
{
  "adapters": {
    "meu-cli": {
      "command": ["meu-cli", "--model", "{model}", "--print", "{prompt}"],
      "format": "text"
    }
  },
  "tiers": { "cheap": { "cli": "meu-cli", "model": "modelo-barato" } }
}
```

Confira as flags no `--help` do CLI antes. `format` pode ser `text`, `json` (um objeto) ou `jsonl` (um evento por linha).

`{prompt}`, `{cwd}` e `{model}` são substituídos sem passar por shell. Sem `{prompt}`, a tarefa vai pelo stdin. Um adaptador só edita se tiver `editCommand`. Num adaptador, o modo só leitura depende só das instruções dadas ao worker, por isso a checagem do `git status` é ainda mais importante nele.

## Termos de serviço

Cada worker é o **CLI oficial**, logado na sua própria assinatura e chamado em modo não interativo. O pirlo nunca lê, extrai ou repassa tokens de login, e não usa proxies de assinatura (9Router, CLIProxyAPI, OpenCode com OAuth de assinatura e similares).

O motivo: a Anthropic bloqueia tokens OAuth do Claude Free/Pro/Max fora do Claude Code e do claude.ai, e o Google baniu contas que usaram o OAuth do Gemini/Antigravity em ferramentas de terceiros.

## O que ainda não foi testado de verdade

A primeira versão foi feita numa máquina sem o `agy` e sem as contas do autor. Por isso:

- o `agy` foi testado só com um CLI falso que imita a saída descrita no `agy --help`. O formato exato do `--output-format json` e da lista do `agy models` precisa ser confirmado na máquina real. Se não bater, o pirlo ainda devolve o texto, mas pode não ler o uso de tokens;
- o `codex exec` teve as flags conferidas no `codex` 0.164, mas nunca rodou logado;
- o `claude -p` como worker e a delegação automática no Claude Code foram testados de verdade.

Para conferir na sua máquina:

```bash
pirlo detect                              # CLIs, login e modelos
pirlo ask --tier cheap "o que tem em README.md?"
pirlo savings
```

Fora do Claude Code, o `pirlo` não fica no PATH. Use `python3 <pasta do plugin>/bin/pirlo` (o `codex plugin add` mostra a pasta; no Claude Code ela fica em `~/.claude/plugins/`) ou crie um alias.

## Desenvolvimento

```bash
python3 -m unittest discover -s tests -v
claude plugin validate .
```

Os testes usam CLIs falsos em `tests/stubs/`, que imitam a saída do `agy`, do `codex` e do `claude`.

## Licença

MIT
