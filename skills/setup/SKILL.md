---
name: setup
description: Set up pirlo - find the AI CLIs, order the workers and pick the scope, and save the config.
disable-model-invocation: true
allowed-tools: Bash(pirlo *), Bash(claude plugin *)
---

Set up pirlo for the user. Talk to the user in their language; keep it short.

Tell the user the full setup also runs in a terminal with `pirlo setup`. Then:

1. Run `pirlo detect` and `pirlo propose --leader claude`. Detection runs no prompts and spends no quota.
2. Show the user, in a compact table, each CLI (installed, logged in, models found) and the proposed workers in order (CLI, model, effort). Explain in one line each:
   - pirlo uses the first worker and moves to the next by itself when one runs low or out of quota; workers on other subscriptions (Antigravity, Codex...) spare the Claude quota, so the lead's own brand goes last.
   - `native` means this Claude Code subagent (haiku) does the work itself, with no other subscription.
   - A CLI that is installed but not logged in must be logged in first (the user runs its login command).
3. Ask with AskUserQuestion, in one call:
   - Workers: accept the order, or reorder, drop or change models (only models `pirlo detect` listed).
   - Scope: all repositories (user, saved in `~/.config/pirlo/config.json`) or only this repository (local, saved in `.pirlo/config.json`, which pirlo keeps out of git).
   - Permissions (recommended): let pirlo's read-only commands (`ask`, `digest`, `savings`, `detect`, `show`) run without prompts. pirlo never runs the project's commands itself: the lead runs them under the user's own rules and pipes the output to `pirlo digest`. `pirlo edit` keeps asking, because it changes files.
4. Save: `pirlo save --scope <user|local> <<'EOF'` followed by the config JSON and `EOF`. Keep `version`, `leaders` and `workers`.
5. If the user accepted the permissions, run `pirlo allow`.
6. Match the plugin scope to the choice, if needed, and tell the user what you ran:
   - user: `claude plugin enable pirlo@pirlo --scope user`
   - local: `claude plugin enable pirlo@pirlo --scope local`. If pirlo is also enabled for the user, repositories without a local config stay inactive.
7. Finish with two lines: delegation now happens on its own, and `/pirlo:savings` shows the estimated savings.

If `pirlo` is not found, use `"${CLAUDE_PLUGIN_ROOT}/bin/pirlo"`. It needs Python 3.9+.
