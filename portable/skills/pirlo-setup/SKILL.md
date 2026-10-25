---
name: pirlo-setup
description: Set up pirlo (pick the AIs in leadership order and the scope). Use only when the user asks to set up or reconfigure pirlo.
---

Run `pirlo` (or `python3 ../../../bin/pirlo`, relative to this file's folder, if it is not on PATH). Talk to the user in their language; keep it short.

Tell the user the full setup also runs in a terminal with `pirlo setup`. Then:

1. Run `pirlo detect` (no prompts, no quota). Show a compact table: each CLI (installed, logged in, models). A CLI that is not logged in must be logged in first.
2. Ask the user for the AIs in leadership order (the first is the everyday lead; when its quota runs out, the next takes over) and the scope: all repositories (user, `~/.config/pirlo/config.json`) or only this one (local, `.pirlo/config.json`, kept out of git).
3. Run `pirlo propose --only --leader <the chosen AIs in order, comma-separated>`. The workers are the lightest models of those AIs: pirlo first uses the one the user leads with least, moves on by itself when one runs out of quota, and keeps the calling lead's brand last. The user may change a model (only models `pirlo detect` listed).
4. Save: `pirlo save --scope <user|local>` with the config JSON on stdin (quoted heredoc). Keep `version`, `leaders` and `workers`. If Antigravity is a worker, offer `pirlo allow agy`: it allows read-only shell commands (git log, cat, grep...) that its worker otherwise denies.
5. Tell the user: with local scope, repositories without their own config stay inactive. Delegation now happens on its own, and the pirlo-savings skill (or `pirlo savings`) shows the estimated savings.
