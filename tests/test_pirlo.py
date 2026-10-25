"""End-to-end tests: bin/pirlo runs against fake CLIs in a throwaway repository."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIRLO = ROOT / "bin" / "pirlo"
STUBS = ROOT / "tests" / "stubs"

AUTHOR_TIERS = {
    "cheap": {"cli": "agy", "model": "gemini-3.8-flash-low"},
    "standard": {"cli": "agy", "model": "gemini-3.8-flash-high"},
    "strong": {"cli": "agy", "model": "gemini-4-argon-medium"},
}


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

    def save(self, tiers, scope="user", **extra):
        data = dict({"version": 1, "tiers": tiers}, **extra)
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
        self.assertEqual(out["config"]["tiers"], AUTHOR_TIERS)

    def test_propose_codex_only(self):
        only = Path(self.tmp.name) / "only"
        only.mkdir()
        link(only, "codex")
        out = json.loads(self.pirlo("propose", "--leader", "codex",
                                    PATH=f"{only}{os.pathsep}/usr/bin:/bin").stdout)
        tiers = out["config"]["tiers"]
        self.assertEqual(tiers["cheap"], {"cli": "codex", "model": "gpt-6-luna", "effort": "low"})
        self.assertEqual(tiers["strong"]["model"], "gpt-5.6-terra")

    def test_propose_claude_only_uses_native_subagent(self):
        only = Path(self.tmp.name) / "only"
        only.mkdir()
        link(only, "claude")
        out = json.loads(self.pirlo("propose", "--leader", "claude",
                                    PATH=f"{only}{os.pathsep}/usr/bin:/bin").stdout)
        self.assertEqual(out["config"]["tiers"]["cheap"], {"cli": "native"})


class Ask(PirloCase):
    def test_agy_read_only_call(self):
        self.save(AUTHOR_TIERS)
        out = self.pirlo("ask", "--tier", "strong", "where is the greeting?", STUB_REPLY="app.rb:1 prints hi")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("app.rb:1 prints hi", out.stdout)
        self.assertIn("[pirlo: agy gemini-4-argon-medium, tier strong", out.stdout)
        argv = self.calls()[0]["argv"]
        self.assertEqual(argv[argv.index("--mode") + 1], "plan")
        self.assertEqual(argv[argv.index("--model") + 1], "gemini-4-argon-medium")
        prompt = argv[-1]
        self.assertTrue(prompt.startswith("--print="))
        self.assertIn("READ-ONLY", prompt)
        self.assertIn("path:line", prompt)
        self.assertIn("where is the greeting?", prompt)
        entry = self.log()[0]
        self.assertEqual((entry["kind"], entry["cli"], entry["tier"], entry["ok"]), ("ask", "agy", "strong", True))
        self.assertEqual(entry["usage"], {"inputTokens": 5200, "cachedTokens": 0, "outputTokens": 140})
        for key in ("ts", "repo", "model", "durationMs", "promptChars", "replyChars"):
            self.assertIn(key, entry)

    def test_codex_read_only_sandbox_and_usage(self):
        self.save({"cheap": {"cli": "codex", "model": "gpt-6-luna", "effort": "low"}})
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
        self.save({"cheap": {"cli": "claude", "model": "haiku"}})
        out = self.pirlo("ask", "summarize README")
        self.assertEqual(out.returncode, 0, out.stderr)
        argv = self.calls()[0]["argv"]
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "plan")
        self.assertIn("Agent", argv)
        self.assertEqual(self.log()[0]["usage"]["inputTokens"], 31003)

    def test_custom_adapter_with_prompt_argument(self):
        script = Path(self.tmp.name) / "mycli"
        script.write_text("#!/bin/sh\necho \"answer for: $2\"\n")
        script.chmod(0o755)
        self.save({"cheap": {"cli": "mycli", "model": "m1"}},
                  adapters={"mycli": {"command": [str(script), "{model}", "{prompt}"], "format": "text"}})
        out = self.pirlo("ask", "count the files")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("answer for:", out.stdout)
        self.assertIn("count the files", out.stdout)

    def test_custom_adapter_cannot_edit_without_edit_command(self):
        self.save({"cheap": {"cli": "mycli"}}, adapters={"mycli": {"command": ["true"]}})
        out = self.pirlo("edit", "rename")
        self.assertEqual(out.returncode, 2)
        self.assertIn("cannot edit", out.stderr)

    def test_task_on_stdin(self):
        self.save(AUTHOR_TIERS)
        self.pirlo("ask", stdin='what does "hi" mean?')
        self.assertIn('what does "hi" mean?', self.calls()[0]["argv"][-1])

    def test_native_tier_hands_back(self):
        self.save({"cheap": {"cli": "native"}})
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
        self.save(AUTHOR_TIERS)
        out = self.pirlo("ask", "x", STUB_FAIL="1")
        self.assertEqual(out.returncode, 1)
        self.assertIn("PIRLO_FAILED", out.stdout)
        self.assertIn("quota exhausted", out.stdout)
        self.assertFalse(self.log()[0]["ok"])

    def test_long_reply_is_cut(self):
        self.save(AUTHOR_TIERS, maxReplyChars=100)
        out = self.pirlo("ask", "x", STUB_REPLY="word " * 200)
        self.assertIn("reply cut at 100 characters", out.stdout)
        self.assertLess(len(out.stdout), 400)

    def test_read_only_tripwire(self):
        self.save(AUTHOR_TIERS)
        out = self.pirlo("ask", "x", STUB_WRITE=str(self.repo / "intruder.txt"))
        self.assertIn("WARNING: the worker changed files although it was read-only: intruder.txt", out.stdout)
        self.assertEqual(self.log()[0]["filesChanged"], 1)

    def test_edit_mode_and_changed_files(self):
        self.save(AUTHOR_TIERS)
        out = self.pirlo("edit", "rename foo to bar", STUB_WRITE=str(self.repo / "app.rb"))
        argv = self.calls()[0]["argv"]
        self.assertEqual(argv[argv.index("--mode") + 1], "accept-edits")
        self.assertIn("Files changed: app.rb", out.stdout)
        self.assertEqual(self.log()[0]["kind"], "edit")

    def test_no_recursion_inside_a_worker(self):
        self.save(AUTHOR_TIERS)
        out = self.pirlo("ask", "x", PIRLO_WORKER="1")
        self.assertEqual(out.returncode, 2)
        self.assertEqual(self.calls(), [])


class Fessor(PirloCase):
    def enable_fessor(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.local.json").write_text(
            json.dumps({"enabledPlugins": {"fessor@fessor": True}}))

    def test_fessor_forces_read_only_and_no_solutions(self):
        self.enable_fessor()
        self.save(AUTHOR_TIERS)
        out = self.pirlo("edit", "fix the exercise")
        self.assertIn("PIRLO_RESTRICTED", out.stdout)
        argv = self.calls()[0]["argv"]
        self.assertEqual(argv[argv.index("--mode") + 1], "plan")
        self.assertIn("Never solve exercises", argv[-1])
        self.assertTrue(self.log()[0]["restricted"])

    def test_fessor_via_agents_md(self):
        (self.repo / "AGENTS.md").write_text("# project\n\n# fessor\n\nVocê é o fessor\n")
        self.save(AUTHOR_TIERS)
        self.pirlo("ask", "explain")
        self.assertIn("Never solve exercises", self.calls()[0]["argv"][-1])

    def test_disabled_fessor_is_ignored(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.local.json").write_text(
            json.dumps({"enabledPlugins": {"fessor@fessor": False}}))
        self.save(AUTHOR_TIERS)
        self.pirlo("ask", "explain")
        self.assertNotIn("Never solve exercises", self.calls()[0]["argv"][-1])

    def test_native_mentions_restriction(self):
        self.enable_fessor()
        self.save({"cheap": {"cli": "native"}})
        self.assertIn("student", self.pirlo("ask", "x").stdout)


class Exec(PirloCase):
    def test_short_output_skips_the_worker(self):
        self.save(AUTHOR_TIERS)
        out = self.pirlo("exec", "--", sys.executable, "-c", "print('3 tests, 0 failures')")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("3 tests, 0 failures", out.stdout)
        self.assertIn("exit 0", out.stdout)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.log()[0]["cli"], "none")

    def big_command(self, lines=400):
        script = (f"import sys\nfor i in range({lines}): print('ok line', i)\n"
                  "print('app/models/user.rb:42: Error: undefined method')\nsys.exit(1)")
        return [sys.executable, "-c", script]

    def test_long_output_goes_to_the_worker_with_a_saved_log(self):
        self.save(AUTHOR_TIERS)
        out = self.pirlo("exec", "--tier", "cheap", "--task", "list failures", "--", *self.big_command(),
                         STUB_REPLY="1 failure: app/models/user.rb:42 undefined method")
        self.assertIn("exit 1", out.stdout)
        self.assertIn("1 failure", out.stdout)
        logs = list((self.repo / ".pirlo" / "runs").glob("*.log"))
        self.assertEqual(len(logs), 1)
        self.assertEqual((self.repo / ".pirlo" / ".gitignore").read_text(), "*\n")
        prompt = self.calls()[0]["argv"][-1]
        self.assertIn("exited with 1", prompt)
        self.assertIn("list failures", prompt)
        self.assertIn("app/models/user.rb:42: Error", prompt)
        entry = self.log()[0]
        self.assertEqual(entry["kind"], "exec")
        self.assertGreater(entry["outputChars"], 4000)
        self.assertEqual(entry["exitCode"], 1)

    def test_huge_output_is_passed_as_a_file(self):
        self.save(AUTHOR_TIERS, embedOutputChars=1000)
        self.pirlo("exec", "--", *self.big_command())
        prompt = self.calls()[0]["argv"][-1]
        self.assertIn("saved in the file", prompt)
        self.assertNotIn("<output>", prompt)

    def test_worker_failure_falls_back_to_free_excerpt(self):
        self.save(AUTHOR_TIERS)
        out = self.pirlo("exec", "--", *self.big_command(), STUB_FAIL="1")
        self.assertIn("worker failed", out.stdout)
        self.assertRegex(out.stdout, r"\.pirlo/runs/[^:]+\.log:401: app/models/user.rb:42: Error")

    def test_native_exec_returns_excerpt(self):
        self.save({"cheap": {"cli": "native"}})
        out = self.pirlo("exec", "--", *self.big_command())
        self.assertIn("PIRLO_NATIVE", out.stdout)
        self.assertIn("Last 30 lines", out.stdout)
        self.assertLess(len(out.stdout), 4000)

    def test_shell_string_command(self):
        self.save(AUTHOR_TIERS)
        out = self.pirlo("exec", "--", "echo one && echo two")
        self.assertIn("one\ntwo", out.stdout)


class ScopeAndSavings(PirloCase):
    def test_local_scope_keeps_other_repos_inactive(self):
        self.save(AUTHOR_TIERS, scope="local")
        self.assertTrue((self.repo / ".pirlo" / "config.json").exists())
        self.assertEqual((self.repo / ".pirlo" / ".gitignore").read_text(), "*\n")
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        out = self.pirlo("ask", "x", cwd=other)
        self.assertEqual(out.returncode, 2)
        self.assertIn("not set up for this repository", out.stderr)
        self.assertEqual(self.pirlo("ask", "x").returncode, 0)

    def test_local_overrides_user(self):
        self.save(AUTHOR_TIERS)
        self.save({"cheap": {"cli": "codex", "model": "gpt-6-luna"}}, scope="local")
        self.pirlo("ask", "x")
        self.assertEqual(self.calls()[0]["cli"], "codex")
        shown = json.loads(self.pirlo("show").stdout)
        self.assertEqual(shown["source"], "local")
        self.assertEqual(shown["config"]["tiers"]["strong"]["cli"], "agy")

    def test_save_rejects_bad_config(self):
        bad = self.pirlo("save", "--scope", "user", stdin=json.dumps({"tiers": {"cheap": {"cli": "nope"}}}))
        self.assertEqual(bad.returncode, 2)
        self.assertIn("unknown cli", bad.stderr)

    def test_savings_report_is_an_explicit_estimate(self):
        self.save(AUTHOR_TIERS)
        self.pirlo("exec", "--", *Exec.big_command(self))
        self.pirlo("ask", "x")
        self.pirlo("exec", "--", "echo short")
        out = self.pirlo("savings")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("ESTIMATE", out.stdout)
        self.assertIn("estimate, not a measurement", out.stdout)
        self.assertIn("agy gemini-3.8-flash-low: 2 runs", out.stdout)
        data = json.loads(self.pirlo("savings", "--json").stdout)
        self.assertEqual(data["runs"], 3)
        self.assertEqual(data["skipped"], 1)
        self.assertGreater(data["savedLow"], 1000)
        self.assertGreaterEqual(data["savedHigh"], data["savedLow"] + 5000 - 200)

    def test_savings_with_empty_log(self):
        self.assertIn("No delegations", self.pirlo("savings").stdout)


class Hook(PirloCase):
    def context(self, **env):
        out = self.pirlo("hook", **env)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"] if out.stdout.strip() else None

    def test_reminds_the_lead_once_when_configured(self):
        self.save(AUTHOR_TIERS)
        self.assertIn("pirlo:worker", self.context())

    def test_silent_without_setup_outside_claude_code(self):
        self.assertIsNone(self.context())

    def test_on_by_default_inside_claude_code(self):
        self.assertIn("pirlo:worker", self.context(CLAUDECODE="1"))
        out = self.pirlo("hook", "--claude-code")
        self.assertIn("pirlo:worker", out.stdout)

    def test_silent_where_local_scope_does_not_apply(self):
        self.save(AUTHOR_TIERS, scope="local")
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        out = self.pirlo("hook", cwd=other, CLAUDECODE="1")
        self.assertEqual(out.stdout, "")

    def test_mentions_fessor(self):
        (self.repo / "AGENTS.md").write_text("# fessor\n")
        self.save(AUTHOR_TIERS)
        self.assertIn("fessor is active", self.context())

    def test_silent_inside_a_worker(self):
        self.save(AUTHOR_TIERS)
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
        for path in list((ROOT / "skills").glob("*/SKILL.md")) + list((ROOT / "codex" / "skills").glob("*/SKILL.md")):
            meta = self.frontmatter(path)
            self.assertTrue(meta.get("name") and meta.get("description"), path)

    def test_hook_calls_the_script(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())
        command = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        self.assertIn('"${CLAUDE_PLUGIN_ROOT}/bin/pirlo" hook --claude-code', command)
        self.assertNotIn("UserPromptSubmit", hooks["hooks"])

    def test_codex_skills_point_at_the_script(self):
        skill = ROOT / "codex" / "skills" / "pirlo"
        self.assertTrue((skill / "../../../bin/pirlo").resolve().is_file())


if __name__ == "__main__":
    unittest.main()
