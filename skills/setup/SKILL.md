---
name: setup
description: Set up pirlo - pick the AIs in leadership order and the scope, and save the config.
disable-model-invocation: true
allowed-tools: Bash(pirlo *), Bash(claude plugin *)
---

Set up pirlo for the user. Talk to the user in their language; keep it short.

Tell the user the full setup also runs in a terminal with `pirlo setup`. Then:

1. Run `pirlo detect`. It runs no prompts and spends no quota. Show a compact table: each CLI (installed, logged in, models found). A CLI that is installed but not logged in must be logged in first (the user runs its login command).
2. Ask with AskUserQuestion, in one call:
   - AIs in leadership order: the first is the lead the user works with every day; when its quota runs out, the next one takes over. The workers are the lightest models of these same AIs.
   - Scope: all repositories (user, saved in `~/.config/pirlo/config.json`) or only this repository (local, saved in `.pirlo/config.json`, which pirlo keeps out of git).
   - Permissions (recommended): let pirlo's read-only commands (`ask`, `digest`, `savings`, `detect`, `show`) run without prompts. pirlo never runs the project's commands itself: the lead runs them under the user's own rules and pipes the output to `pirlo digest`. `pirlo edit` keeps asking, because it changes files.
   - Only if Antigravity is chosen: allow read-only shell commands (git log, git diff, cat, grep...) for its worker, which otherwise denies every command.
3. Run `pirlo propose --only --leader <the chosen AIs in order, comma-separated>`. Show the workers in order (CLI, model, effort) and say in one line: pirlo first uses the AI the user leads with least, moves on by itself when one runs out of quota, and keeps the calling lead's own brand last. `native` means this Claude Code subagent (haiku) does the work. The user may change a model (only models `pirlo detect` listed).
4. Save: `pirlo save --scope <user|local> <<'EOF'` followed by the config JSON and `EOF`. Keep `version`, `leaders` and `workers`.
5. If the user accepted the permissions, run `pirlo allow`; for Antigravity, `pirlo allow agy`.
6. Match the plugin scope to the choice, if needed, and tell the user what you ran:
   - user: `claude plugin enable pirlo@pirlo --scope user`
   - local: `claude plugin enable pirlo@pirlo --scope local`. If pirlo is also enabled for the user, repositories without a local config stay inactive.
7. Finish with two lines: delegation now happens on its own, and `/pirlo:savings` shows the estimated savings.

If `pirlo` is not found, use `"${CLAUDE_PLUGIN_ROOT}/bin/pirlo"`. It needs Python 3.9+.
