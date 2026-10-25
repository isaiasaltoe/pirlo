---
name: pirlo
description: Use proactively for bulky, low-judgment work, so you never read raw material - running tests, builds, linters or LaTeX and digesting long output; reading docs, PDFs or many files for a narrow answer; wide code searches. A cheaper worker CLI does it and returns a short answer with path:line references. Not for planning, design, decisions or small edits.
---

Hand the work to `pirlo`, a script in this plugin at `../../../bin/pirlo` relative to this file's folder. Run it with `python3 <that path>`. It calls other official CLIs, so it needs network: request escalated permissions for it when the sandbox blocks it.

Pick one command. Tier: `cheap` by default; `standard` to trace code across files or combine sources; `strong` only for the hardest reading.
- Run a command and digest its output: `python3 <pirlo> exec --tier cheap --task "what to look for" -- <command>`
- Read, search or answer from the repo or docs: `python3 <pirlo> ask --tier cheap "<task>"` (whole task in the quotes, with paths and the question; use a quoted heredoc on stdin if it has double quotes)
- Mechanical edit the user asked for (rename, format, repeat a pattern): `python3 <pirlo> edit --tier cheap "<task>"`

Use the reply as is; open only the path:line spots you must check. Independent tasks can run as parallel commands. If the reply says `PIRLO_FAILED`, `PIRLO_NATIVE` or pirlo is not set up, do the task yourself. If it says `PIRLO_RESTRICTED`, a learning tool is active: never solve exercises or give fixes.
