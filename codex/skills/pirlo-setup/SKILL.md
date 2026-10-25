---
name: pirlo-setup
description: Set up pirlo (worker CLIs, cheap/standard/strong tiers, scope). Use only when the user asks to set up or reconfigure pirlo.
---

`<pirlo>` is `python3 ../../../bin/pirlo` relative to this file's folder. Talk to the user in their language; keep it short.

1. Run `<pirlo> detect` and `<pirlo> propose --leader codex`. They run no prompts and spend no quota.
2. Show a compact table: each CLI (installed, logged in, models) and the proposed tiers (tier, CLI, model, effort). `cheap`: tests, builds, lint, logs, searches. `standard`: tracing code across files. `strong`: the hardest reading. Planning and decisions stay with you. A CLI that is not logged in must be logged in first.
3. Ask the user: accept or adjust the mapping (only models `detect` listed), and the scope: all repositories (user, `~/.config/pirlo/config.json`) or only this one (local, `.pirlo/config.json`, kept out of git).
4. Save: `<pirlo> save --scope <user|local>` with the config JSON on stdin (quoted heredoc). Keep `version`, `leader` and `tiers`.
5. Tell the user: Codex plugins are installed for the user; with local scope, repositories without their own config stay inactive. Then: delegation happens on its own, and the pirlo-savings skill shows the estimated savings.
