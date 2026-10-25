"""Stand-in for agy, codex and claude in tests.

It mimics the non-interactive output of each CLI. Environment variables steer it:
  STUB_RECORD     file where each call appends {"cli", "argv", "stdin"} as one JSON line
  STUB_REPLY      reply text (default: "stub reply from <cli>")
  STUB_FAIL       exit with status 1 and an error
  STUB_LOGGED_OUT report "not logged in"
  STUB_WRITE      path of a file the worker creates, to trip the read-only check
"""

import json
import os
import sys


def record(cli, argv, stdin):
    path = os.environ.get("STUB_RECORD")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"cli": cli, "argv": argv, "stdin": stdin}) + "\n")


def main():
    cli, argv = sys.argv[1], sys.argv[2:]
    logged_out = bool(os.environ.get("STUB_LOGGED_OUT"))
    if argv == ["--version"]:
        print({"agy": "agy 2.3.0", "codex": "codex-cli 0.164.0", "claude": "2.1.310 (Claude Code)"}[cli])
        return 0
    if cli == "claude" and argv[:2] == ["auth", "status"]:
        print(json.dumps({"loggedIn": not logged_out, "authMethod": "oauth_token"}))
        return 0
    if cli == "codex" and argv[:2] == ["login", "status"]:
        print("Not logged in" if logged_out else "Logged in using ChatGPT")
        return 1 if logged_out else 0
    if cli == "codex" and argv[:2] == ["debug", "models"]:
        levels = [{"effort": e} for e in ("low", "medium", "high", "xhigh")]
        models = [{"slug": s, "visibility": v, "supported_reasoning_levels": levels}
                  for s, v in (("gpt-6-astra", "list"), ("gpt-6-sol", "list"), ("gpt-6-luna", "list"),
                               ("gpt-5.6-terra", "list"), ("gpt-5.6-luna", "list"),
                               ("codex-auto-review", "hide"))]
        print(json.dumps({"models": models}))
        return 0
    if cli == "agy" and argv[:1] == ["models"]:
        if logged_out:
            print("Error: not logged in. Run agy login.", file=sys.stderr)
            return 1
        print("Available models:")
        for model in ("gemini-3.8-flash-low", "gemini-3.8-flash-medium", "gemini-3.8-flash-high",
                      "gemini-4-argon-low", "gemini-4-argon-medium", "gemini-4-argon-high",
                      "claude-opus-5-5-high", "claude-sonnet-5-5-medium", "gpt-oss-120b-medium"):
            print(f"  {model}")
        return 0

    stdin = None if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
    record(cli, argv, stdin)
    if os.environ.get("STUB_WRITE"):
        with open(os.environ["STUB_WRITE"], "w", encoding="utf-8") as handle:
            handle.write("written by the worker\n")
    reply = os.environ.get("STUB_REPLY", f"stub reply from {cli}")
    if os.environ.get("STUB_FAIL"):
        print("Error: quota exhausted", file=sys.stderr)
        return 1
    if cli == "agy":
        print(json.dumps({"response": reply, "conversationId": "c1",
                          "usage": {"inputTokens": 5200, "outputTokens": 140}}))
    elif cli == "codex":
        events = [
            {"type": "thread.started", "thread_id": "t1"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": reply}},
            {"type": "turn.completed", "usage": {"input_tokens": 9000, "cached_input_tokens": 6000,
                                                  "output_tokens": 210}},
        ]
        for event in events:
            print(json.dumps(event))
    else:
        print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": reply,
                          "usage": {"input_tokens": 3, "cache_creation_input_tokens": 1000,
                                    "cache_read_input_tokens": 30000, "output_tokens": 50}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
