<p align="center">
  <img src="assets/pirlo.png" alt="Desenho à mão de um jogador de costas, com camisa listrada em preto e branco, /plugins/pirlo e o número 21" width="190">
</p>

# pirlo

Seu agente de código gasta a maior parte da cota **lendo**: 30 mil tokens de log de teste para achar duas falhas, vinte arquivos abertos para descobrir onde um token é validado. O pirlo faz o agente que você usa (o **líder**) passar esse trabalho braçal para **workers mais baratos**, sozinho, e receber só um resumo com `arquivo:linha`. Quando uma IA fica sem cota, ele troca de marca sozinho.

O nome é uma homenagem ao Andrea Pirlo, o regista que recebia a bola, decidia e distribuía.

## Instalação

Linux, WSL ou macOS, com Python 3.9 ou mais novo. Na pasta do projeto:

```bash
curl -fsSL https://raw.githubusercontent.com/isaiasaltoe/pirlo/main/install.sh | sh
```

O setup abre no terminal, em português ou inglês, explica cada pergunta e pergunta:

- em quais IAs usar o pirlo como líder. Ele detecta as que você tem: Claude Code, Codex, Antigravity, Gemini CLI, Kimi, Copilot CLI, opencode, Cursor CLI e outras;
- se o pirlo fica ativo em todos os repositórios ou só neste;
- a ordem dos workers, uma IA de cada marca;
- se pode liberar os comandos de leitura do pirlo no Claude Code e gravar a regra que deixa o pirlo sair do sandbox do Codex.

No fim, ele instala o plugin em cada IA escolhida. Para mudar alguma resposta, rode `pirlo setup` de novo.

## Como funciona

<p align="center">
  <img src="assets/como-funciona.svg" alt="Você pede ao líder para rodar os testes. O líder roda bin/rails test e manda a saída ao pirlo, ou pede para rastrear algo no código com pirlo ask. Saída curta volta direto. O resto vai para a fila de workers (agy, codex, native), que passa para o próximo quando um fica sem cota. O worker devolve as falhas com arquivo:linha ao líder." width="880">
</p>

Você não chama nada: escreve normalmente, e o líder delega.

| Você pede | O líder roda |
| --- | --- |
| "roda os testes" | `bin/rails test 2>&1 \| pirlo digest` |
| "o CI quebrou, o que foi?" | `gh run view --log-failed \| pirlo digest` |
| "o que mudou nessa branch?" | `git diff main... \| pirlo digest` |
| "onde a gente valida o token?" | `pirlo ask "onde o login valida o token?"` |
| "renomeia `user_id` para `account_id` nos testes" | `pirlo edit "..."` |

- **Quem roda o comando é o líder**, com as permissões que você já deu a ele. O pirlo só lê a saída. Saída curta volta direto, sem chamar worker.
- **O worker roda só leitura.** Se ele mexer em algum arquivo, a resposta avisa.
- **Não compensa** em design ou em edições pequenas. Nesses casos, o líder faz sozinho.

## Quando a cota acaba

**Worker sem cota.** O pirlo passa a tarefa para a próxima marca da fila, na mesma chamada, e deixa a que acabou descansando até o reset. A marca do líder fica por último, para poupar a cota dele. `pirlo show` mostra a fila e as cotas.

**Líder sem cota.** No Claude Code, o pirlo monta sozinho o `.pirlo/passe.md`, com o que você pediu, a última resposta e os arquivos alterados, e avisa. Abra outra IA na mesma pasta e diga "continua". Nos outros líderes, rode `pirlo passe`.

## Comandos

| Comando | O que faz |
| --- | --- |
| `pirlo setup` | configura idioma, IAs, escopo e workers |
| `pirlo show` | mostra a fila de workers, as cotas e quem está descansando |
| `pirlo savings` | estima quanto o líder deixou de ler; no Claude Code, `/pirlo:savings` |
| `pirlo passe` | deixa o trabalho pronto para outra IA continuar |
| `pirlo detect` | lista as IAs instaladas, o login e os modelos, sem gastar cota |

A economia é uma **estimativa**, porque não dá para saber quanto o líder teria lido sem o pirlo. Cada delegação grava uma linha em `~/.config/pirlo/usage.jsonl`, sem custar tokens.

## Configuração

O setup escreve `~/.config/pirlo/config.json` (global) ou `.pirlo/config.json` (só no projeto, fora do git):

```json
{
  "workers": [
    { "cli": "agy", "model": "gemini-3.8-flash-medium" },
    { "cli": "codex", "model": "gpt-6-luna", "effort": "medium" },
    { "cli": "native" }
  ],
  "switchAt": 90
}
```

| Campo | O que faz |
| --- | --- |
| `workers` | a fila, em ordem. `cli` pode ser `agy`, `codex`, `claude`, `native` (o subagente do Claude Code) ou um adaptador |
| `switchAt` | a partir de quantos % da cota uma marca vai para o fim da fila (90) |
| `inlineOutputChars` | até quantos caracteres a saída volta direto, sem worker (2500) |
| `restrictivePlugins` | plugins que deixam os workers só leitura (`["fessor"]`) |
| `adapters` | outro CLI como worker, como `{"meu-cli": {"command": ["meu-cli", "--print", "{prompt}"]}}` |

## Compatível com o fessor

Com o [fessor](https://github.com/isaiasaltoe/fessor) ativo no projeto, os workers ficam só leitura e nunca resolvem exercícios.

## Termos de serviço

Cada worker é o CLI oficial, logado na sua própria assinatura. O pirlo não usa proxies de assinatura nem repassa tokens de login.

## Desenvolvimento

```bash
python3 -m unittest discover -s tests -v
```

É uma versão inicial. O Antigravity e o Codex como workers ainda não foram testados com contas reais.

## Licença

MIT
