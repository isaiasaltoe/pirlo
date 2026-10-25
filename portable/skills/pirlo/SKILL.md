---
name: pirlo
description: Use proactively for bulky, low-judgment dev work, so you never read raw output - running test suites, builds, type checks, linters or CI logs and digesting their long output; tracing code across many files; reading dependency source, large diffs or git history for a narrow answer. A cheaper worker CLI does it and returns a short answer with path:line references. Not for planning, design, decisions or small edits.
---

Run the `pirlo` command. If it is not on PATH, run `python3 ../../../bin/pirlo` (path relative to this file's folder). It calls other official CLIs, so it needs network: if your sandbox blocks it, request permission to run it outside the sandbox.

- Run a command (tests, build, type check, lint, CI log) and digest its output: run it yourself and pipe it to pirlo, `<command> 2>&1 | pirlo digest --label "<command>" --task "what to look for"`
- Trace code, read dependency source, a large diff or git history and answer: `pirlo ask "<task>"`. Put the whole task in the quotes, with paths and the question; if it has double quotes, pass it on stdin with a quoted heredoc.
- A mechanical edit the user asked for (rename, format, repeat a pattern): `pirlo edit "<task>"`

Use the reply as is; open only the path:line spots you must check. Independent tasks can run as parallel commands. If the reply says `PIRLO_FAILED` or `PIRLO_NATIVE`, or pirlo is not set up, do the task yourself. If it says `PIRLO_RESTRICTED`, a learning tool is active: never solve exercises or give fixes.
