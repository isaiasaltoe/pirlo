"""End-to-end tests: bin/pirlo runs against fake CLIs in a throwaway repository."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIRLO = ROOT / "bin" / "pirlo"
STUBS = ROOT / "tests" / "stubs"

AUTHOR_WORKER = {"cli": "agy", "model": "gemini-3.8-flash-medium"}


def link(folder, cli):
    """Put one stub CLI alone in a folder, to fake a machine that has only that CLI."""
    wrapper = folder / cli
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{STUBS / "fake_cli.py"}" {cli} "$@"\n')
    wrapper.chmod(0o755)


class PirloCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.home.mkdir()
        self.repo = base / "repo"
        self.repo.mkdir()
        self.record = base / "calls.jsonl"
        self.git("init", "-q")
        (self.repo / "app.rb").write_text("puts 'hi'\n")
        self.git("add", ".")
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
        self.env = {
            "PATH": f"{STUBS}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(self.home),
            "PIRLO_HOME": str(self.home / ".config" / "pirlo"),
            "STUB_RECORD": str(self.record),
            "PIRLO_NO_NOTIFY": "1",
            # The test runner may itself run inside Claude Code: only the variables set here count.
            "PIRLO_NO_PROCESS_LEAD": "1",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)

    def pirlo(self, *args, stdin=None, cwd=None, **env):
        full = dict(self.env, **env)
        return subprocess.run(
            [sys.executable, str(PIRLO), *args], cwd=cwd or self.repo, env=full, input=stdin,
            capture_output=True, text=True, timeout=60,
        )

    def save(self, worker, scope="user", **extra):
        data = dict({"version": 2, "worker": worker}, **extra)
        result = self.pirlo("save", "--scope", scope, stdin=json.dumps(data))
        self.assertEqual(result.returncode, 0, result.stderr)

    def calls(self):
        if not self.record.exists():
            return []
        return [json.loads(line) for line in self.record.read_text().splitlines()]

    def log(self):
        path = self.home / ".config" / "pirlo" / "usage.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class DetectAndPropose(PirloCase):
    def test_detect_lists_clis_login_and_models(self):
        out = self.pirlo("detect", "--json")
        clis = {c["cli"]: c for c in json.loads(out.stdout)}
        self.assertTrue(all(clis[c]["installed"] and clis[c]["loggedIn"] for c in ("agy", "codex", "claude")))
        self.assertIn("gemini-4-argon-medium", clis["agy"]["models"])
        self.assertNotIn("codex-auto-review", clis["codex"]["models"])
        self.assertEqual(self.calls(), [], "detection must run no prompt")

    def test_detect_sees_logged_out(self):
        clis = {c["cli"]: c for c in json.loads(self.pirlo("detect", "--json", STUB_LOGGED_OUT="1").stdout)}
        self.assertFalse(clis["agy"]["loggedIn"])
        self.assertFalse(clis["codex"]["loggedIn"])
        self.assertFalse(clis["claude"]["loggedIn"])

    def test_propose_for_claude_lead_with_antigravity(self):
        out = json.loads(self.pirlo("propose", "--leader", "claude").stdout)
        self.assertEqual(out["config"]["workers"], [
            AUTHOR_WORKER, {"cli": "codex", "model": "gpt-6-luna", "effort": "medium"}, {"cli": "native"}])

    def test_propose_puts_the_leads_brands_last(self):
        out = json.loads(self.pirlo("propose", "--leader", "agy,codex").stdout)
        self.assertEqual([w["cli"] for w in out["config"]["workers"]], ["claude", "codex", "agy"])

    def test_propose_for_any_lead(self):
        out = json.loads(self.pirlo("propose", "--leader", "kimi").stdout)
        self.assertEqual([w["cli"] for w in out["config"]["workers"]], ["agy", "codex", "claude"])

    def test_propose_codex_only(self):
        only = Path(self.tmp.name) / "only"
        only.mkdir()
        link(only, "codex")
        out = json.loads(self.pirlo("propose", "--leader", "codex",
                                    PATH=f"{only}{os.pathsep}/usr/bin:/bin").stdout)
        self.assertEqual(out["config"]["workers"], [{"cli": "codex", "model": "gpt-6-luna", "effort": "medium"}])
        self.assertIn("shares a subscription with a lead", " ".join(out["notes"]))

    def test_propose_claude_only_uses_native_subagent(self):
        only = Path(self.tmp.name) / "only"
        only.mkdir()
        link(only, "claude")
        out = json.loads(self.pirlo("propose", "--leader", "claude",
                                    PATH=f"{only}{os.pathsep}/usr/bin:/bin").stdout)
        self.assertEqual(out["config"]["workers"], [{"cli": "native"}])


class Antigravity(PirloCase):
    """agy's real output, as captured from agy 1.4.7."""

    def test_bad_model_reports_agys_message_not_the_model_list(self):
        self.save(AUTHOR_WORKER)
        out = self.pirlo("ask", "x", STUB_AGY="bad-model")
        self.assertIn("PIRLO_FAILED", out.stdout)
        self.assertIn("status 1: invalid model selection", out.stdout)

    def test_prompt_says_the_shell_is_off_without_rules(self):
        self.save(AUTHOR_WORKER)
        self.pirlo("ask", "x")
        self.assertIn("You cannot run shell commands", self.calls()[0]["argv"][-1])

    def test_allow_agy_adds_read_only_rules_and_the_prompt_lists_them(self):
        settings = self.home / ".gemini" / "antigravity-cli" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"model": "x", "permissions": {"allow": ["command(ls)"]}}))
        out = self.pirlo("allow", "agy")
        self.assertIn("command(git log)", out.stdout)
        data = json.loads(settings.read_text())
        self.assertEqual(data["model"], "x")
        self.assertEqual(data["permissions"]["allow"].count("command(ls)"), 1)
        self.assertNotIn("command(find)", data["permissions"]["allow"])
        self.assertIn("already", self.pirlo("allow", "agy").stdout)
        self.save(AUTHOR_WORKER)
        self.pirlo("ask", "x")
        self.assertIn("only commands starting with these are allowed: ls, git log", self.calls()[0]["argv"][-1])

    def test_print_timeout_says_why_the_reply_is_empty(self):
        self.save(AUTHOR_WORKER)
        out = self.pirlo("ask", "x", STUB_AGY="timeout")
        self.assertIn("empty reply: [agy] print timeout", out.stdout)


class LeadDetection(PirloCase):
    def lead(self, cwd=None, **env):
        shown = json.loads(self.pirlo("show", cwd=cwd, **env).stdout)
        return shown["lead"], shown["leadFoundBy"]

    def fake_lead(self, name):
        """A script named like an agent CLI that runs pirlo, as that CLI would."""
        folder = Path(self.tmp.name) / f"lead-{name}"
        folder.mkdir()
        script = folder / name
        script.write_text(f'#!/bin/sh\n"{sys.executable}" "{PIRLO}" show\n')
        script.chmod(0o755)
        return script

    def run_under(self, name, **env):
        full = dict(self.env, **env)
        full.pop("PIRLO_NO_PROCESS_LEAD")
        out = subprocess.run([str(self.fake_lead(name))], cwd=self.repo, env=full,
                             capture_output=True, text=True, timeout=60)
        shown = json.loads(out.stdout)
        return shown["lead"], shown["leadFoundBy"]

    def test_no_lead(self):
        self.assertEqual(self.lead(), (None, None))

    def test_variables_of_each_lead(self):
        self.assertEqual(self.lead(CLAUDECODE="1"), ("claude", "CLAUDECODE"))
        self.assertEqual(self.lead(CODEX_THREAD_ID="t"), ("codex", "CODEX_THREAD_ID"))
        self.assertEqual(self.lead(ANTIGRAVITY_CONVERSATION_ID="c"), ("agy", "ANTIGRAVITY_CONVERSATION_ID"))

    def test_ai_agent_convention(self):
        self.assertEqual(self.lead(AI_AGENT="claude-code_2-1-310_agent"), ("claude", "AI_AGENT"))
        self.assertEqual(self.lead(AI_AGENT="opencode_1-2_agent"), ("opencode", "AI_AGENT"))

    def test_pirlo_lead_wins(self):
        self.assertEqual(self.lead(PIRLO_LEAD="kimi", CLAUDECODE="1"), ("kimi", "PIRLO_LEAD"))

    @unittest.skipUnless(shutil.which("ps"), "needs ps")
    def test_any_known_cli_found_in_the_process_tree(self):
        self.assertEqual(self.run_under("gemini"), ("gemini", "process"))

    @unittest.skipUnless(shutil.which("ps"), "needs ps")
    def test_the_nearest_lead_beats_inherited_variables(self):
        # Codex opened in a Claude Code terminal inherits CLAUDECODE, but Codex is the lead.
        self.assertEqual(self.run_under("codex", CLAUDECODE="1"), ("codex", "process"))

    def test_each_lead_gets_workers_of_another_ai(self):
        # Boot order Claude -> Antigravity: Claude leading uses agy; agy leading uses Claude.
        data = {"version": 3, "leaders": ["claude", "agy"], "workers": [
            AUTHOR_WORKER, {"cli": "native"}, {"cli": "claude", "model": "haiku", "effort": "medium"}]}
        self.pirlo("save", "--scope", "user", stdin=json.dumps(data))
        shown = lambda **env: json.loads(self.pirlo("show", **env).stdout)["nextWorkers"]
        self.assertEqual(shown(CLAUDECODE="1")[0], "agy gemini-3.8-flash-medium")
        self.assertEqual(shown(PIRLO_LEAD="agy")[0], "claude haiku medium")

    def test_native_goes_last_when_another_ai_leads(self):
        data = {"version": 3, "workers": [{"cli": "native"}, AUTHOR_WORKER]}
        self.pirlo("save", "--scope", "user", stdin=json.dumps(data))
        out = self.pirlo("ask", "x", PIRLO_LEAD="agy")
        self.assertIn("stub reply from agy", out.stdout)

    def test_codex_lead_gets_no_native_fallback(self):
        self.save({"cli": "agy", "model": "m"})
        out = self.pirlo("ask", "x", CODEX_THREAD_ID="t", STUB_FAIL="1")
        self.assertIn("PIRLO_FAILED", out.stdout)
        self.assertNotIn("PIRLO_NATIVE", out.stdout)


class Ask(PirloCase):
    def test_agy_read_only_call(self):
        self.save(AUTHOR_WORKER)
        out = self.pirlo("ask", "where is the greeting?", STUB_REPLY="app.rb:1 prints hi")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("app.rb:1 prints hi", out.stdout)
        self.assertIn("[pirlo: agy gemini-3.8-flash-medium, ", out.stdout)
        argv = self.calls()[0]["argv"]
        self.assertNotIn("--mode", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "gemini-3.8-flash-medium")
        prompt = argv[-1]
        self.assertTrue(prompt.startswith("--print="))
        self.assertIn("READ-ONLY", prompt)
        self.assertIn("path:line", prompt)
        self.assertIn("where is the greeting?", prompt)
        entry = self.log()[0]
        self.assertEqual((entry["kind"], entry["cli"], entry["ok"]), ("ask", "agy", True))
        self.assertEqual(entry["usage"], {"inputTokens": 5200, "cachedTokens": 1200, "outputTokens": 140})
        for key in ("ts", "repo", "model", "durationMs", "promptChars", "replyChars"):
            self.assertIn(key, entry)

    def test_codex_read_only_sandbox_and_usage(self):
        self.save({"cli": "codex", "model": "gpt-6-luna", "effort": "low"})
        out = self.pirlo("ask", "find the config loader")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("stub reply from codex", out.stdout)
        call = self.calls()[0]
        argv = call["argv"]
        self.assertEqual(argv[0], "exec")
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertIn('model_reasoning_effort="low"', argv)
        self.assertEqual(argv[-1], "-")
        self.assertIn("find the config loader", call["stdin"])
        self.assertEqual(self.log()[0]["usage"], {"inputTokens": 9000, "cachedTokens": 6000, "outputTokens": 210})

    def test_claude_worker_usage_counts_cache(self):
        self.save({"cli": "claude", "model": "haiku"})
        out = self.pirlo("ask", "summarize README")
        self.assertEqual(out.returncode, 0, out.stderr)
        argv = self.calls()[0]["argv"]
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "plan")
        self.assertIn("Agent", argv)
        self.assertIn("--no-session-persistence", argv)
        self.assertEqual(self.log()[0]["usage"]["inputTokens"], 31003)

    def test_custom_adapter_with_prompt_argument(self):
        script = Path(self.tmp.name) / "mycli"
        script.write_text("#!/bin/sh\necho \"answer for: $2\"\n")
        script.chmod(0o755)
        self.save({"cli": "mycli", "model": "m1"},
                  adapters={"mycli": {"command": [str(script), "{model}", "{prompt}"], "format": "text"}})
        out = self.pirlo("ask", "count the files")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("answer for:", out.stdout)
        self.assertIn("count the files", out.stdout)

    def test_custom_adapter_cannot_edit_without_edit_command(self):
        self.save({"cli": "mycli"}, adapters={"mycli": {"command": ["true"]}})
        out = self.pirlo("edit", "rename")
        self.assertEqual(out.returncode, 1)
        self.assertIn("cannot edit", out.stdout)

    def test_task_on_stdin(self):
        self.save(AUTHOR_WORKER)
        self.pirlo("ask", stdin='what does "hi" mean?')
        self.assertIn('what does "hi" mean?', self.calls()[0]["argv"][-1])

    def test_native_worker_hands_back(self):
        self.save({"cli": "native"})
        out = self.pirlo("ask", "anything")
        self.assertIn("PIRLO_NATIVE", out.stdout)
        self.assertEqual(self.calls(), [])

    def test_unconfigured_inside_claude_code_is_native(self):
        out = self.pirlo("ask", "anything", CLAUDECODE="1")
        self.assertIn("PIRLO_NATIVE", out.stdout)

    def test_unconfigured_elsewhere_asks_for_setup(self):
        out = self.pirlo("ask", "anything")
        self.assertEqual(out.returncode, 2)
        self.assertIn("setup", out.stderr)

    def test_worker_failure_is_reported_and_logged(self):
        self.save(AUTHOR_WORKER)
        out = self.pirlo("ask", "x", STUB_FAIL="1")
        self.assertEqual(out.returncode, 1)
        self.assertIn("PIRLO_FAILED", out.stdout)
        self.assertIn("out of quota", out.stdout)
        self.assertFalse(self.log()[0]["ok"])

    def test_long_reply_is_cut(self):
        self.save(AUTHOR_WORKER, maxReplyChars=100)
        out = self.pirlo("ask", "x", STUB_REPLY="word " * 200)
        self.assertIn("reply cut at 100 characters", out.stdout)
        self.assertLess(len(out.stdout), 400)

    def test_read_only_tripwire(self):
        self.save(AUTHOR_WORKER)
        out = self.pirlo("ask", "x", STUB_WRITE=str(self.repo / "intruder.txt"))
        self.assertIn("WARNING: the worker changed files although it was read-only: intruder.txt", out.stdout)
        self.assertEqual(self.log()[0]["filesChanged"], 1)

    def test_edit_mode_and_changed_files(self):
        self.save(AUTHOR_WORKER)
        out = self.pirlo("edit", "rename foo to bar", STUB_WRITE=str(self.repo / "app.rb"))
        argv = self.calls()[0]["argv"]
        self.assertEqual(argv[argv.index("--mode") + 1], "accept-edits")
        self.assertIn("Files changed: app.rb", out.stdout)
        self.assertEqual(self.log()[0]["kind"], "edit")

    def test_no_recursion_inside_a_worker(self):
        self.save(AUTHOR_WORKER)
        out = self.pirlo("ask", "x", PIRLO_WORKER="1")
        self.assertEqual(out.returncode, 2)
        self.assertEqual(self.calls(), [])


class Switching(PirloCase):
    CODEX = {"cli": "codex", "model": "gpt-6-luna", "effort": "medium"}

    def save_chain(self, *workers, **extra):
        data = dict({"version": 3, "workers": list(workers)}, **extra)
        self.assertEqual(self.pirlo("save", "--scope", "user", stdin=json.dumps(data)).returncode, 0)

    def state(self):
        return json.loads((self.home / ".config" / "pirlo" / "state.json").read_text())

    def test_quota_error_moves_to_the_next_brand_in_the_same_call(self):
        self.save_chain(AUTHOR_WORKER, self.CODEX)
        out = self.pirlo("ask", "x", STUB_FAIL="1", STUB_FAIL_CLI="agy")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("stub reply from codex", out.stdout)
        self.assertIn("agy gemini-3.8-flash-medium out of quota", out.stdout)
        self.assertEqual([c["cli"] for c in self.calls()], ["agy", "codex"])
        self.assertIn("agy", self.state()["cooldown"])
        self.assertTrue(self.log()[0]["notes"])

    def test_a_resting_brand_is_not_called_again(self):
        self.save_chain(AUTHOR_WORKER, self.CODEX)
        self.pirlo("ask", "x", STUB_FAIL="1", STUB_FAIL_CLI="agy")
        self.record.unlink()
        out = self.pirlo("ask", "y")
        self.assertEqual([c["cli"] for c in self.calls()], ["codex"])
        self.assertIn("agy skipped: out of quota until", out.stdout)

    def test_other_errors_also_move_on_but_do_not_rest(self):
        self.save_chain(AUTHOR_WORKER, self.CODEX)
        out = self.pirlo("ask", "x", STUB_FAIL="1", STUB_FAIL_CLI="agy", STUB_FAIL_MSG="segfault")
        self.assertIn("stub reply from codex", out.stdout)
        self.assertNotIn("agy", self.state().get("cooldown", {}))

    def test_the_leads_brand_goes_last(self):
        self.save_chain(self.CODEX, AUTHOR_WORKER)
        self.pirlo("ask", "x", CODEX_THREAD_ID="t1")
        self.assertEqual([c["cli"] for c in self.calls()], ["agy"])

    def test_claude_code_lead_prefers_other_brands_over_native(self):
        self.save_chain({"cli": "native"}, AUTHOR_WORKER)
        out = self.pirlo("ask", "x", CLAUDECODE="1")
        self.assertIn("stub reply from agy", out.stdout)

    def test_native_is_the_last_resort_in_claude_code(self):
        self.save_chain(AUTHOR_WORKER, {"cli": "native"})
        out = self.pirlo("ask", "x", CLAUDECODE="1", STUB_FAIL="1")
        self.assertIn("PIRLO_NATIVE", out.stdout)
        self.assertIn("out of quota", out.stdout)

    def test_codex_reading_above_the_line_goes_last(self):
        folder = self.home / ".codex" / "sessions" / "2026" / "10" / "25"
        folder.mkdir(parents=True)
        limits = {"primary": {"used_percent": 95.0, "window_minutes": 300, "resets_at": 4102444800},
                  "secondary": {"used_percent": 40.0, "window_minutes": 10080, "resets_at": 4102444800}}
        (folder / "rollout-1.jsonl").write_text(json.dumps(
            {"timestamp": "2026-10-25T10:00:00Z", "type": "event_msg",
             "payload": {"type": "token_count", "rate_limits": limits}}) + "\n")
        self.save_chain(self.CODEX, AUTHOR_WORKER)
        out = self.pirlo("ask", "x")
        self.assertEqual([c["cli"] for c in self.calls()], ["agy"])
        self.assertIn("codex last: 95% of its quota used", out.stdout)

    def test_claude_reading_is_saved_and_used_next_time(self):
        self.save_chain({"cli": "claude", "model": "haiku"}, AUTHOR_WORKER)
        self.pirlo("ask", "x", STUB_CLAUDE_USED="0.97")
        self.assertEqual(self.state()["quota"]["claude"]["windows"]["5h"]["usedPercent"], 97.0)
        self.record.unlink()
        self.pirlo("ask", "y")
        self.assertEqual([c["cli"] for c in self.calls()], ["agy"])

    def test_digest_switches_too(self):
        self.save_chain(AUTHOR_WORKER, self.CODEX)
        out = self.pirlo("digest", stdin=BIG_OUTPUT, STUB_FAIL="1", STUB_FAIL_CLI="agy")
        self.assertIn("stub reply from codex", out.stdout)
        self.assertEqual(self.log()[0]["cli"], "codex")

    def test_show_lists_the_next_workers(self):
        self.save_chain(AUTHOR_WORKER, self.CODEX)
        shown = json.loads(self.pirlo("show", CODEX_THREAD_ID="t").stdout)
        self.assertEqual(shown["lead"], "codex")
        self.assertEqual(shown["nextWorkers"], ["agy gemini-3.8-flash-medium", "codex gpt-6-luna medium"])


class Fessor(PirloCase):
    def enable_fessor(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.local.json").write_text(
            json.dumps({"enabledPlugins": {"fessor@fessor": True}}))

    def test_fessor_forces_read_only_and_no_solutions(self):
        self.enable_fessor()
        self.save(AUTHOR_WORKER)
        out = self.pirlo("edit", "fix the exercise")
        self.assertIn("PIRLO_RESTRICTED", out.stdout)
        argv = self.calls()[0]["argv"]
        self.assertNotIn("--mode", argv)
        self.assertIn("Never solve exercises", argv[-1])
        self.assertTrue(self.log()[0]["restricted"])

    def test_fessor_via_agents_md(self):
        (self.repo / "AGENTS.md").write_text("# project\n\n# fessor\n\nVocê é o fessor\n")
        self.save(AUTHOR_WORKER)
        self.pirlo("ask", "explain")
        self.assertIn("Never solve exercises", self.calls()[0]["argv"][-1])

    def test_disabled_fessor_is_ignored(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.local.json").write_text(
            json.dumps({"enabledPlugins": {"fessor@fessor": False}}))
        self.save(AUTHOR_WORKER)
        self.pirlo("ask", "explain")
        self.assertNotIn("Never solve exercises", self.calls()[0]["argv"][-1])

    def test_native_mentions_restriction(self):
        self.enable_fessor()
        self.save({"cli": "native"})
        self.assertIn("student", self.pirlo("ask", "x").stdout)


BIG_OUTPUT = "".join(f"ok line {i}\n" for i in range(400)) + "app/models/user.rb:42: Error: undefined method\n"


class Digest(PirloCase):
    def test_short_output_skips_the_worker(self):
        self.save(AUTHOR_WORKER)
        out = self.pirlo("digest", "--label", "rails test", stdin="3 tests, 0 failures\n")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("$ rails test", out.stdout)
        self.assertIn("3 tests, 0 failures", out.stdout)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.log()[0]["cli"], "none")

    def test_long_output_goes_to_the_worker_with_a_saved_log(self):
        self.save(AUTHOR_WORKER)
        out = self.pirlo("digest", "--label", "rails test", "--task", "list failures", stdin=BIG_OUTPUT,
                         STUB_REPLY="1 failure: app/models/user.rb:42 undefined method")
        self.assertIn("401 lines of output", out.stdout)
        self.assertIn("1 failure", out.stdout)
        logs = list((self.repo / ".pirlo" / "runs").glob("*.log"))
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].read_text(), BIG_OUTPUT)
        self.assertEqual((self.repo / ".pirlo" / ".gitignore").read_text(), "*\n")
        prompt = self.calls()[0]["argv"][-1]
        self.assertIn("The command `rails test`", prompt)
        self.assertIn("list failures", prompt)
        self.assertIn("app/models/user.rb:42: Error", prompt)
        entry = self.log()[0]
        self.assertEqual(entry["kind"], "digest")
        self.assertEqual(entry["outputChars"], len(BIG_OUTPUT))

    def test_huge_output_is_passed_as_a_file(self):
        self.save(AUTHOR_WORKER, embedOutputChars=1000)
        self.pirlo("digest", stdin=BIG_OUTPUT)
        prompt = self.calls()[0]["argv"][-1]
        self.assertIn("saved in the file", prompt)
        self.assertNotIn("<output>", prompt)

    def test_worker_failure_falls_back_to_free_excerpt(self):
        self.save(AUTHOR_WORKER)
        out = self.pirlo("digest", stdin=BIG_OUTPUT, STUB_FAIL="1")
        self.assertIn("worker failed", out.stdout)
        self.assertRegex(out.stdout, r"\.pirlo/runs/[^:]+\.log:401: app/models/user.rb:42: Error")

    def test_native_returns_excerpt(self):
        self.save({"cli": "native"})
        out = self.pirlo("digest", stdin=BIG_OUTPUT)
        self.assertIn("PIRLO_NATIVE", out.stdout)
        self.assertIn("Last 30 lines", out.stdout)
        self.assertLess(len(out.stdout), 4000)

    def test_real_pipe_with_ansi_colors(self):
        self.save(AUTHOR_WORKER)
        out = subprocess.run(
            f"printf '\\033[31mFAIL\\033[0m x\\n' 2>&1 | {sys.executable} {PIRLO} digest",
            shell=True, cwd=self.repo, env=dict(self.env), capture_output=True, text=True)
        self.assertIn("FAIL x", out.stdout)
        self.assertNotIn("\x1b", out.stdout)


class ScopeAndSavings(PirloCase):
    def test_local_scope_keeps_other_repos_inactive(self):
        self.save(AUTHOR_WORKER, scope="local")
        self.assertTrue((self.repo / ".pirlo" / "config.json").exists())
        self.assertEqual((self.repo / ".pirlo" / ".gitignore").read_text(), "*\n")
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        out = self.pirlo("ask", "x", cwd=other)
        self.assertEqual(out.returncode, 2)
        self.assertIn("not set up for this repository", out.stderr)
        self.assertEqual(self.pirlo("ask", "x").returncode, 0)

    def test_local_overrides_user(self):
        self.save(AUTHOR_WORKER)
        self.save({"cli": "codex", "model": "gpt-6-luna"}, scope="local")
        self.pirlo("ask", "x")
        self.assertEqual(self.calls()[0]["cli"], "codex")
        shown = json.loads(self.pirlo("show").stdout)
        self.assertEqual(shown["source"], "local")
        self.assertEqual(shown["config"]["worker"]["cli"], "codex")
        self.assertEqual(shown["config"]["scope"], "local")

    def test_save_rejects_bad_config(self):
        bad = self.pirlo("save", "--scope", "user", stdin=json.dumps({"worker": {"cli": "nope"}}))
        self.assertEqual(bad.returncode, 2)
        self.assertIn("unknown worker cli", bad.stderr)

    def test_savings_report_is_an_explicit_estimate(self):
        self.save(AUTHOR_WORKER)
        self.pirlo("digest", stdin=BIG_OUTPUT)
        self.pirlo("ask", "x")
        self.pirlo("digest", stdin="short\n")
        out = self.pirlo("savings")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("ESTIMATE", out.stdout)
        self.assertIn("estimate, not a measurement", out.stdout)
        self.assertIn("agy gemini-3.8-flash-medium: 2 runs", out.stdout)
        data = json.loads(self.pirlo("savings", "--json").stdout)
        self.assertEqual(data["runs"], 3)
        self.assertEqual(data["skipped"], 1)
        self.assertGreater(data["savedLow"], 1000)
        self.assertGreaterEqual(data["savedHigh"], data["savedLow"] + 5000 - 200)

    def test_savings_with_empty_log(self):
        self.assertIn("No delegations", self.pirlo("savings").stdout)


class LeaderSupport(PirloCase):
    def test_allow_adds_read_only_rules_once(self):
        settings = self.home / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"model": "sonnet", "permissions": {"allow": ["Bash(git log *)"]}}))
        self.assertEqual(self.pirlo("allow").returncode, 0)
        self.pirlo("allow")
        data = json.loads(settings.read_text())
        allow = data["permissions"]["allow"]
        self.assertEqual(data["model"], "sonnet")
        self.assertEqual(allow.count("Bash(pirlo ask *)"), 1)
        self.assertIn("Bash(pirlo digest*)", allow)
        self.assertIn("Bash(git log *)", allow)
        self.assertFalse(any("edit" in rule for rule in allow))

    def test_allow_refuses_a_file_it_cannot_parse(self):
        settings = self.home / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text("// comment\n{}")
        out = self.pirlo("allow")
        self.assertEqual(out.returncode, 2)
        self.assertEqual(settings.read_text(), "// comment\n{}")

    def test_instructions_cover_the_three_commands(self):
        text = self.pirlo("instructions").stdout
        for command in ("| pirlo digest", "pirlo ask", "pirlo edit"):
            self.assertIn(command, text)

    def test_install_script_puts_pirlo_on_a_bin_dir(self):
        bin_dir = Path(self.tmp.name) / "bin"
        skills = Path(self.tmp.name) / "skills"
        out = subprocess.run(["sh", str(ROOT / "install.sh")], capture_output=True, text=True,
                             env=dict(self.env, PIRLO_BIN_DIR=str(bin_dir), PIRLO_SKILLS_DIR=str(skills),
                                      PIRLO_NO_SETUP="1"))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(os.access(bin_dir / "pirlo", os.X_OK))
        self.assertTrue((skills / "pirlo" / "SKILL.md").is_file())
        self.assertIn("add", out.stdout)


class Setup(PirloCase):
    def setup_run(self, answers, cwd=None, lang="1"):
        # Only the stub CLIs, so the leads found do not depend on the machine.
        path = os.pathsep.join([str(STUBS), os.path.dirname(sys.executable), "/usr/bin", "/bin"])
        return self.pirlo("setup", stdin="\n".join([lang] + answers) + "\n", cwd=cwd,
                          PIRLO_MARKETPLACE="/market", PATH=path)

    def test_three_ais_local(self):
        out = self.setup_run(["1,2,3", "2", "", "", "", "", ""])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("sandbox", out.stdout)
        argvs = [(c["cli"], c["argv"]) for c in self.calls()]
        self.assertIn(("claude", ["plugin", "install", "pirlo", "--marketplace", "/market", "--scope", "local"]), argvs)
        self.assertIn(("codex", ["plugin", "marketplace", "add", "/market"]), argvs)
        self.assertIn(("codex", ["plugin", "add", "pirlo@pirlo"]), argvs)
        config = json.loads((self.repo / ".pirlo" / "config.json").read_text())
        self.assertEqual(config["scope"], "local")
        self.assertEqual(config["leaders"], ["claude", "codex", "agy"])
        # The lightest model of each AI, from the last lead to the main one; claude -p too,
        # for when Codex or Antigravity lead.
        self.assertEqual([w["cli"] for w in config["workers"]], ["agy", "codex", "native", "claude"])
        self.assertEqual(config["workers"][0], AUTHOR_WORKER)
        agy = json.loads((self.home / ".gemini" / "antigravity-cli" / "settings.json").read_text())
        self.assertIn("command(git log)", agy["permissions"]["allow"])
        self.assertIn("# pirlo", (self.repo / "AGENTS.md").read_text())
        self.assertIn("Antigravity", out.stdout)
        rules = (self.home / ".codex" / "rules" / "pirlo.rules").read_text()
        self.assertEqual(rules, (ROOT / "portable" / "pirlo.rules").read_text())
        allow = json.loads((self.home / ".claude" / "settings.json").read_text())["permissions"]["allow"]
        self.assertIn("Bash(pirlo digest*)", allow)

    def test_leadership_order_sets_the_workers(self):
        out = self.setup_run(["3,1", "1", "n", "n", "", "", ""])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("Antigravity → Claude Code", out.stdout)
        config = json.loads((self.home / ".config" / "pirlo" / "config.json").read_text())
        self.assertEqual(config["leaders"], ["agy", "claude"])
        self.assertEqual((config["workers"], config["scope"]), (
            [{"cli": "native"}, {"cli": "claude", "model": "haiku", "effort": "medium"}, AUTHOR_WORKER], "user"))
        install = [c["argv"] for c in self.calls() if c["argv"][:2] == ["plugin", "install"]]
        self.assertEqual(install[0][-2:], ["--scope", "user"])
        self.assertFalse((self.home / ".claude" / "settings.json").exists())

    def test_nothing_changes_when_declined(self):
        out = self.setup_run(["1,2", "2", "", "", "", "n"])
        self.assertEqual(out.returncode, 1)
        self.assertIn("Nada foi alterado", out.stdout)
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.repo / ".pirlo").exists())
        self.assertFalse((self.home / ".config" / "pirlo").exists())

    def test_other_lead_in_this_repo_uses_agents_md(self):
        out = self.setup_run(["4,3", "2", "", "", ""])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("| pirlo digest", (self.repo / "AGENTS.md").read_text())
        self.assertIn("/AGENTS.md", (self.repo / ".git" / "info" / "exclude").read_text())
        self.setup_run(["4,3", "2", "", "", ""])
        self.assertEqual((self.repo / "AGENTS.md").read_text().count("# pirlo"), 1)

    def test_other_lead_outside_a_repo_installs_skills(self):
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        skills = Path(self.tmp.name) / "skills"
        out = self.setup_run(["4,3", "", "", "", str(skills)], cwd=outside)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("global", out.stdout)
        for name in ("pirlo", "pirlo-setup", "pirlo-savings"):
            self.assertTrue((skills / name / "SKILL.md").is_file())

    def test_codex_rule_can_be_declined(self):
        out = self.setup_run(["2", "1", "", "n", ""])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertFalse((self.home / ".codex" / "rules" / "pirlo.rules").exists())
        self.assertIn(("codex", ["plugin", "add", "pirlo@pirlo"]), [(c["cli"], c["argv"]) for c in self.calls()])

    def test_english(self):
        out = self.setup_run(["1", "1", "", ""], lang="2")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("Which AIs do you want", out.stdout)
        self.assertIn("Done.", out.stdout)
        self.assertNotIn("Pronto", out.stdout)
        config = json.loads((self.home / ".config" / "pirlo" / "config.json").read_text())
        self.assertEqual(config["language"], "en")

    def test_both_languages_have_the_same_messages(self):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader("pirlo_cli", str(PIRLO))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader("pirlo_cli", loader))
        loader.exec_module(module)
        self.assertEqual(set(module.TEXT["pt"]), set(module.TEXT["en"]))
        self.assertEqual(module.CODEX_RULES, (ROOT / "portable" / "pirlo.rules").read_text())

    def test_changing_a_model(self):
        out = self.setup_run(["3", "1", "s", "6", "n", "", ""])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        config = json.loads((self.home / ".config" / "pirlo" / "config.json").read_text())
        self.assertEqual(config["workers"], [{"cli": "agy", "model": "gemini-4-argon-high"}])

    def test_gemini_lead_writes_gemini_md(self):
        bin_dir = Path(self.tmp.name) / "more"
        bin_dir.mkdir()
        link(bin_dir, "gemini")
        path = os.pathsep.join([str(bin_dir), str(STUBS), os.path.dirname(sys.executable), "/usr/bin", "/bin"])
        out = self.pirlo("setup", stdin="1\n4,3\n2\n\n\n\n", PIRLO_MARKETPLACE="/market", PATH=path)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("Gemini CLI", out.stdout)
        self.assertIn("# pirlo", (self.repo / "GEMINI.md").read_text())

    def test_jersey_and_thanks_only_on_the_first_setup(self):
        out = self.setup_run(["1", "1", "", ""])
        self.assertIn("/plugins/pirlo", out.stdout)
        self.assertIn("Obrigado por usar o pirlo", out.stdout)
        self.assertIn("https://altoe.dev", out.stdout)
        again = self.setup_run(["1", "1", "", ""])
        self.assertNotIn("/plugins/pirlo", again.stdout)

    def test_invalid_answer_asks_again(self):
        out = self.setup_run(["9", "1", "1", "", ""])
        self.assertIn("Opção inválida", out.stdout)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


class Passe(PirloCase):
    def transcript(self, folder=None):
        folder = folder or self.home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(self.repo.resolve()))
        folder.mkdir(parents=True, exist_ok=True)
        entries = [
            {"type": "user", "message": {"role": "user", "content": "fix the login test"}},
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Looking at the test."},
                {"type": "tool_use", "name": "Edit", "input": {"file_path": str(self.repo / "app.rb")}},
                {"type": "tool_use", "name": "Write", "input": {"file_path": "/tmp/elsewhere.txt"}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
            {"type": "user", "isMeta": True, "message": {"content": "meta"}},
            {"type": "user", "message": {"content": "<system-reminder>noise</system-reminder>"}},
            {"type": "user", "message": {"content": [{"type": "text", "text": "now the redirect too"}]}},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "The redirect goes to /home."}]}},
        ]
        path = folder / "session.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        return path

    def test_passe_from_a_claude_session_and_git(self):
        self.transcript()
        (self.repo / "app.rb").write_text("puts 'changed'\n")
        out = self.pirlo("passe", "--lead", "claude")
        self.assertEqual(out.returncode, 0, out.stderr)
        text = (self.repo / ".pirlo" / "passe.md").read_text()
        self.assertIn("- fix the login test", text)
        self.assertIn("- now the redirect too", text)
        self.assertNotIn("noise", text)
        self.assertNotIn("meta", text)
        self.assertIn("The redirect goes to /home.", text)
        self.assertIn("- app.rb", text)
        self.assertNotIn("elsewhere", text)
        self.assertIn("M app.rb", text)
        self.assertIn("continue", out.stdout)

    def test_the_session_named_by_claude_code_wins_over_the_newest(self):
        path = self.transcript()
        newer = path.parent / "other.jsonl"
        newer.write_text(json.dumps({"type": "user", "message": {"content": "another session"}}) + "\n")
        os.utime(newer, (time.time() + 60, time.time() + 60))
        self.pirlo("passe", "--lead", "claude", CLAUDE_CODE_SESSION_ID="session")
        self.assertIn("fix the login test", (self.repo / ".pirlo" / "passe.md").read_text())

    def test_passe_names_the_next_lead(self):
        self.save(AUTHOR_WORKER, leaders=["claude", "codex", "agy"])
        self.assertIn("Open Codex here", self.pirlo("passe", "--lead", "claude").stdout)
        self.assertIn("Open Claude Code here", self.pirlo("passe", "--lead", "agy").stdout)

    def test_worker_sessions_are_skipped(self):
        path = self.transcript()
        worker = path.parent / "worker.jsonl"
        worker.write_text(json.dumps({"type": "user", "message": {"content": "You are a worker for another coding agent (the lead)."}}) + "\n")
        os.utime(worker, (time.time() + 60, time.time() + 60))
        self.pirlo("passe", "--lead", "claude")
        self.assertIn("fix the login test", (self.repo / ".pirlo" / "passe.md").read_text())

    def test_rate_limit_hook_writes_the_passe_and_rests_claude(self):
        path = self.transcript(Path(self.tmp.name) / "anywhere")
        self.save(AUTHOR_WORKER)
        payload = {"hook_event_name": "StopFailure", "transcript_path": str(path), "cwd": str(self.repo)}
        out = self.pirlo("hook", "--stop-failure", stdin=json.dumps(payload), cwd=Path(self.tmp.name))
        self.assertEqual(out.returncode, 0, out.stderr)
        text = (self.repo / ".pirlo" / "passe.md").read_text()
        self.assertIn("claude stopped: it hit its usage limit", text)
        self.assertIn("fix the login test", text)
        state = json.loads((self.home / ".config" / "pirlo" / "state.json").read_text())
        self.assertIn("claude", state["cooldown"])

    def test_rate_limit_hook_never_breaks_on_bad_input(self):
        out = self.pirlo("hook", "--stop-failure", stdin="not json")
        self.assertEqual(out.returncode, 0)

    def test_next_session_is_told_and_done_closes_it(self):
        self.save(AUTHOR_WORKER)
        self.pirlo("passe", "--lead", "agy")
        context = json.loads(self.pirlo("hook").stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn(".pirlo/passe.md", context)
        self.pirlo("passe", "--done")
        self.assertFalse((self.repo / ".pirlo" / "passe.md").exists())
        self.assertEqual(len(list((self.repo / ".pirlo").glob("passe-*.md"))), 1)
        context = json.loads(self.pirlo("hook").stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("passe", context)

    def test_instructions_tell_other_leads_about_the_passe(self):
        self.assertIn(".pirlo/passe.md", self.pirlo("instructions").stdout)


class Hook(PirloCase):
    def context(self, **env):
        out = self.pirlo("hook", **env)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"] if out.stdout.strip() else None

    def test_reminds_the_lead_once_when_configured(self):
        self.save(AUTHOR_WORKER)
        self.assertIn("pirlo:worker", self.context())

    def test_silent_without_setup_outside_claude_code(self):
        self.assertIsNone(self.context())

    def test_on_by_default_inside_claude_code(self):
        self.assertIn("pirlo:worker", self.context(CLAUDECODE="1"))
        out = self.pirlo("hook", "--claude-code")
        self.assertIn("pirlo:worker", out.stdout)

    def test_silent_where_local_scope_does_not_apply(self):
        self.save(AUTHOR_WORKER, scope="local")
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        out = self.pirlo("hook", cwd=other, CLAUDECODE="1")
        self.assertEqual(out.stdout, "")

    def test_mentions_fessor(self):
        (self.repo / "AGENTS.md").write_text("# fessor\n")
        self.save(AUTHOR_WORKER)
        self.assertIn("fessor is active", self.context())

    def test_silent_inside_a_worker(self):
        self.save(AUTHOR_WORKER)
        self.assertIsNone(self.context(PIRLO_WORKER="1"))


class PluginFiles(unittest.TestCase):
    def frontmatter(self, path):
        text = path.read_text(encoding="utf-8")
        match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
        self.assertIsNotNone(match, path)
        return dict(line.split(": ", 1) for line in match.group(1).splitlines() if ": " in line)

    def test_manifests_are_valid_json_with_same_version(self):
        versions = set()
        for rel in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
                    ".codex-plugin/plugin.json", ".agents/plugins/marketplace.json"):
            data = json.loads((ROOT / rel).read_text())
            if "version" in data:
                versions.add(data["version"])
        self.assertEqual(len(versions), 1)

    def test_worker_agent_is_cheap_and_read_only(self):
        meta = self.frontmatter(ROOT / "agents" / "worker.md")
        self.assertEqual(meta["name"], "worker")
        self.assertEqual(meta["model"], "haiku")
        self.assertNotIn("Edit", meta["tools"])
        self.assertNotIn("Write", meta["tools"])
        self.assertIn("proactively", meta["description"])

    def test_skills_have_names_and_descriptions(self):
        for path in list((ROOT / "skills").glob("*/SKILL.md")) + list((ROOT / "portable" / "skills").glob("*/SKILL.md")):
            meta = self.frontmatter(path)
            self.assertTrue(meta.get("name") and meta.get("description"), path)

    def test_hook_calls_the_script(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())
        command = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        self.assertIn('"${CLAUDE_PLUGIN_ROOT}/bin/pirlo" hook --claude-code', command)
        self.assertNotIn("UserPromptSubmit", hooks["hooks"])
        stop = hooks["hooks"]["StopFailure"][0]
        self.assertEqual(stop["matcher"], "rate_limit")
        self.assertIn("hook --stop-failure", stop["hooks"][0]["command"])

    def test_portable_skills_point_at_the_script(self):
        skill = ROOT / "portable" / "skills" / "pirlo"
        self.assertTrue((skill / "../../../bin/pirlo").resolve().is_file())


if __name__ == "__main__":
    unittest.main()
