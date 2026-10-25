---
name: setup
description: Set up pirlo - find the worker CLIs, map the cheap, standard and strong tiers, pick the scope and save the config.
disable-model-invocation: true
allowed-tools: Bash(pirlo *), Bash(claude plugin *)
---

Set up pirlo for the user. Talk to the user in their language; keep it short.

1. Run `pirlo detect` and `pirlo propose --leader claude`. Detection runs no prompts and spends no quota.
2. Show the user, in a compact table: each CLI (installed, logged in, models found) and the proposed tiers (tier, CLI, model, effort). Explain in one line each:
   - `cheap`: running tests/builds/lint, reading logs, searches. `standard`: tracing code across files, combining sources. `strong`: the hardest reading. Planning and decisions stay with the lead.
   - `native` means this Claude Code subagent (haiku) does the work itself, with no other subscription.
   - A CLI that is installed but not logged in must be logged in first (the user runs its login command).
3. Ask with AskUserQuestion, in one call:
   - Mapping: accept the proposal, or adjust it (then ask which tier gets which CLI, model and effort; only use models `pirlo detect` listed).
   - Scope: all repositories (user, saved in `~/.config/pirlo/config.json`) or only this repository (local, saved in `.pirlo/config.json`, which pirlo keeps out of git).
4. Save: `pirlo save --scope <user|local> <<'EOF'` followed by the config JSON and `EOF`. Keep `version`, `leader` and `tiers`.
5. Match the plugin scope to the choice, if needed, and tell the user what you ran:
   - user: `claude plugin enable pirlo@pirlo --scope user`
   - local: `claude plugin enable pirlo@pirlo --scope local`. If pirlo is also enabled for the user, repositories without a local config stay inactive.
6. Suggest adding `"Bash(pirlo ask *)"` and `"Bash(pirlo savings*)"` to `permissions.allow` in `~/.claude/settings.json`, so delegations do not prompt. `pirlo exec` runs arbitrary commands, so leave it prompting; the user can approve each command with "don't ask again".
7. Finish with two lines: delegation now happens on its own, and `/pirlo:savings` shows the estimated savings.

If `pirlo` is not found, use `"${CLAUDE_PLUGIN_ROOT}/bin/pirlo"`. It needs Python 3.8+.
