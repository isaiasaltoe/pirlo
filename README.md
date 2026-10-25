<p align="center">
  <img src="assets/pirlo.png" alt="Desenho à mão de um jogador de costas, com camisa listrada em preto e branco, /plugins/pirlo e o número 21" width="190">
</p>

# pirlo

Seu agente de código gasta a maior parte da cota **lendo**: 30 mil tokens de log de teste para achar duas falhas, vinte arquivos abertos para descobrir onde um token é validado. O pirlo faz o agente que você usa (o **líder**) passar esse trabalho braçal para **workers mais baratos**, sozinho, e receber só um resumo com `arquivo:linha`. Quando uma IA fica sem cota, ele troca de marca sozinho.

O nome é uma homenagem ao Andrea Pirlo, o regista que recebia a bola, decidia e distribuía.

## Instalação

> **Testado de verdade até agora:** Claude Code e Antigravity, cada um como líder e como worker, do setup ao passe de uma IA para a outra. O Codex já é suportado, mas ainda não foi testado com uma conta real.

Linux, WSL ou macOS, com Python 3.9 ou mais novo. Na pasta do projeto:

```bash
curl -fsSL https://raw.githubusercontent.com/isaiasaltoe/pirlo/main/install.sh | sh
```

Se você só usa o Claude Code, também dá para instalar direto nele:

```
/plugin install pirlo --marketplace isaiasaltoe/pirlo
```

e depois rodar `/pirlo:setup`.

O setup abre no terminal, em português ou inglês, explica cada pergunta e pergunta:

- quais IAs usar, em ordem de liderança. Ele detecta as que você tem: Claude Code, Codex, Antigravity, Gemini CLI, Kimi, Copilot CLI, opencode, Cursor CLI e outras. A primeira é a que você usa no dia a dia; quando a cota dela acaba, a seguinte assume. Os workers são os modelos mais leves dessas mesmas IAs;
- se o pirlo fica ativo em todos os repositórios ou só neste;
- se pode liberar os comandos de leitura: os do pirlo no Claude Code, a regra que deixa o pirlo sair do sandbox do Codex e comandos como `git log` para o worker do Antigravity.

No fim, ele instala o plugin em cada IA escolhida. Para mudar alguma resposta, rode `pirlo setup` de novo.

## Como funciona

<p align="center">
  <img src="assets/como-funciona.svg" alt="Você pede ao líder para rodar os testes. O líder passa o trabalho braçal aos workers, os modelos leves das suas IAs (Gemini, GPT, Haiku), e recebe só um resumo com as falhas em arquivo:linha. Worker sem cota: o próximo assume. Líder sem cota: a próxima IA continua de onde parou." width="880">
</p>

Você não chama nada: escreve normalmente. Pedidos como estes vão para um worker mais barato, e você recebe só o resumo:

- "roda os testes e me diz o que quebrou"
- "o CI quebrou, o que foi?"
- "o que mudou nessa branch?"
- "onde a gente valida o token do usuário?"

Planejamento, decisões e edições pequenas continuam com o líder.

## Quando a cota acaba

**Worker sem cota.** O pirlo passa o trabalho para a próxima IA da fila sozinho, sem você perceber.

**Líder sem cota.** O pirlo deixa tudo pronto e avisa qual é a próxima IA da sua ordem de liderança: abra ela na mesma pasta e diga "continua". No Claude Code isso é automático; nas outras IAs, rode `pirlo passe` antes.

## Comandos

| Comando | O que faz |
| --- | --- |
| `pirlo setup` | configura idioma, IAs em ordem de liderança e escopo |
| `pirlo show` | mostra a fila de workers, as cotas e quem está descansando |
| `pirlo savings` | estima quanto o líder deixou de ler; no Claude Code, `/pirlo:savings` |
| `pirlo passe` | deixa o trabalho pronto para outra IA continuar |
| `pirlo detect` | lista as IAs instaladas, o login e os modelos, sem gastar cota |

A economia é uma **estimativa**, porque não dá para saber quanto o líder teria lido sem o pirlo.

## Configuração

O setup escreve `~/.config/pirlo/config.json` (global) ou `.pirlo/config.json` (só no projeto, fora do git):

```json
{
  "leaders": ["claude", "codex", "agy"],
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
| `leaders` | as IAs em ordem de liderança: quem assume quando a cota do líder acaba |
| `workers` | a fila, em ordem. `cli` pode ser `agy`, `codex`, `claude`, `native` (o subagente do Claude Code) ou um adaptador |
| `switchAt` | a partir de quantos % da cota uma marca vai para o fim da fila (90) |
| `adapters` | outro CLI como worker, como `{"meu-cli": {"command": ["meu-cli", "--print", "{prompt}"]}}` |

## Termos de serviço

Cada worker é o CLI oficial, logado na sua própria assinatura. O pirlo não usa proxies de assinatura nem repassa tokens de login.

## Inspiração

O pirlo foi inspirado no [alethe-orchestrate](https://github.com/Kc1t/alethe-orchestrate-skill), do [Kauã Miguel](https://github.com/Kc1t).

## Licença

MIT
