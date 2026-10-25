---
name: pirlo-setup
description: Set up pirlo (order the worker CLIs and pick the scope). Use only when the user asks to set up or reconfigure pirlo.
---

Run `pirlo` (or `python3 ../../../bin/pirlo`, relative to this file's folder, if it is not on PATH). Talk to the user in their language; keep it short.

Tell the user the full setup also runs in a terminal with `pirlo setup`. Then:

1. Run `pirlo detect` and `pirlo propose --leader <the CLI you are running in: codex, agy, kimi...>`. They run no prompts and spend no quota.
2. Show a compact table: each CLI (installed, logged in, models) and the proposed workers in order (CLI, model, effort). pirlo uses the first and moves to the next by itself when one runs low or out of quota; your own brand goes last to spare your quota. A CLI that is not logged in must be logged in first.
3. Ask the user: accept the order or reorder, drop or change models (only models `pirlo detect` listed), and the scope: all repositories (user, `~/.config/pirlo/config.json`) or only this one (local, `.pirlo/config.json`, kept out of git).
4. Save: `pirlo save --scope <user|local>` with the config JSON on stdin (quoted heredoc). Keep `version`, `leaders` and `workers`.
5. Tell the user: with local scope, repositories without their own config stay inactive. Delegation now happens on its own, and the pirlo-savings skill (or `pirlo savings`) shows the estimated savings.
