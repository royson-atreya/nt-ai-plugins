#!/usr/bin/env python3
"""Credential placeholders for nt-qa-testing. Claude never sees a real test-account value.

Values come from the plugin's sensitive user config, which Claude Code exports only to hook
processes as CLAUDE_PLUGIN_OPTION_<ROLE>_<USERNAME|PASSWORD>.

  creds.py pre   (PreToolUse)
    - Playwright browser_type / browser_fill_form: replace {{nt-qa:<role>:username|password}}
      with the real value (updatedInput). Unknown or unconfigured role -> deny.
    - Any other Playwright tool carrying a placeholder -> deny (keeps values out of evaluate etc.).
    - Any Write/Edit/Bash/Playwright input containing a real configured value -> deny
      (credentials are never written to files, reports or CSV).
    - Injection happens only when the session runs inside the workspace (~/atreya-ai), where
      guard.py also disables browser_evaluate / browser_run_code_unsafe and file-saving snapshots.
  creds.py post  (PostToolUse: Playwright, Read, Bash, Grep)
    - Mask every configured value in the tool output as ●●●● (updatedToolOutput), so echoed
      Playwright code such as .fill('...'), request bodies or a file that captured a value never
      reach Claude. Image blocks are left as they are.

Standard library only. Fails closed.
"""
import base64
import json
import os
import re
import sys
from urllib.parse import quote, quote_plus

sys.dont_write_bytecode = True

WORKSPACE = os.path.realpath(os.path.expanduser(os.environ.get("NT_WORKSPACE", "~/atreya-ai")))
ROLES = ("doctor", "admin", "patient", "college")
WITHHELD = "[nt-qa-testing: output withheld because credential masking failed; take a new snapshot]"
KINDS = ("username", "password")
PLACEHOLDER = re.compile(r"\{\{\s*nt-qa:([a-z]+):([a-z]+)\s*\}\}")
MASK = "●●●●"
INJECT_TOOLS = ("browser_type", "browser_fill_form")


def creds():
    out = {}
    for role in ROLES:
        for kind in KINDS:
            v = os.environ.get(f"CLAUDE_PLUGIN_OPTION_{role.upper()}_{kind.upper()}", "")
            # an unresolved substitution is not a value
            if v and not v.startswith("${"):
                out[(role, kind)] = v
    return out


def bounded(value):
    """Match a value only when not glued to other letters/digits (avoids masking inside words)."""
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(value) + r"(?![A-Za-z0-9])")


def scannable(kind, value):
    """Values distinctive enough to scan for in written content without false positives."""
    if kind == "password":
        return len(value) >= 4
    return len(value) >= 6 and bool(re.search(r"[^A-Za-z]", value))


def walk(obj, fn):
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, dict):
        if obj.get("type") == "image" or "base64" in obj:
            return obj  # binary image data: masking would corrupt it, and it holds no typed text
        return {k: walk(v, fn) for k, v in obj.items()}
    if isinstance(obj, list):
        return [walk(v, fn) for v in obj]
    return obj


def strings_in(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings_in(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings_in(v)


def emit(event, **fields):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, **fields}}))
    sys.exit(0)


def deny(reason):
    emit("PreToolUse", permissionDecision="deny", permissionDecisionReason=f"nt-qa-testing creds: {reason}")


def is_playwright(tool):
    return tool.startswith("mcp__") and "playwright" in tool.lower()


def pre(data):
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    values = creds()
    text = "\n".join(strings_in(inp))
    name = tool.rsplit("__", 1)[-1]
    found = PLACEHOLDER.findall(text)

    # never let a real value be written anywhere by Claude
    if not (is_playwright(tool) and name in INJECT_TOOLS):
        for (role, kind), v in values.items():
            if scannable(kind, v) and bounded(v).search(text):
                deny(f"this input contains the real {role} {kind} from the plugin config. Use the placeholder "
                     f"{{{{nt-qa:{role}:{kind}}}}} and never write credentials into files, reports or CSV.")

    if not is_playwright(tool) or not found:
        return
    if name not in INJECT_TOOLS:
        deny(f"credential placeholders may only be used in browser_type or browser_fill_form, not {name}.")
    cwd = os.path.realpath(data.get("cwd") or os.getcwd())
    if not (cwd == WORKSPACE or cwd.startswith(WORKSPACE + os.sep)):
        deny("test credentials are injected only in sessions started under ~/atreya-ai (where the browser "
             "guards apply). Restart Claude Code from ~/atreya-ai.")
    for role, kind in found:
        if role not in ROLES or kind not in KINDS:
            deny(f"unknown placeholder {{{{nt-qa:{role}:{kind}}}}}; use role doctor|admin|patient|college and "
                 "kind username|password.")
        if (role, kind) not in values:
            deny(f"the {role} {kind} is not configured. Mark the case Blocked ('{role} account not configured'); "
                 "the user can add it via /plugin -> Installed -> nt-qa-testing -> Configure options.")

    def sub(s):
        return PLACEHOLDER.sub(lambda m: values[(m.group(1), m.group(2))], s)

    emit("PreToolUse", permissionDecision="allow",
         permissionDecisionReason="nt-qa-testing: test credential injected from secure config",
         updatedInput=walk(inp, sub))


def variants_of(values):
    """Plain value plus the escaped/encoded forms it takes in JS code, JSON, form bodies and Basic auth."""
    out = set()
    for v in values.values():
        if len(v) >= 3:
            out |= {v, json.dumps(v)[1:-1], v.replace("'", "\\'"), quote(v), quote_plus(v),
                    base64.b64encode(v.encode()).decode().rstrip("=")}
    for role in ROLES:
        u, p = values.get((role, "username")), values.get((role, "password"))
        if u and p:
            out.add(base64.b64encode(f"{u}:{p}".encode()).decode().rstrip("="))
    return out


def post(data):
    response = data.get("tool_response")
    if response is None:
        return
    patterns = [bounded(v) for v in sorted(variants_of(creds()), key=len, reverse=True)]
    if not patterns:
        return

    def mask(s):
        for p in patterns:
            s = p.sub(MASK, s)
        return s

    try:
        masked = walk(response, mask)
    except Exception:
        masked = walk(response, lambda s: WITHHELD)  # keep the output's shape so the replacement is used
    if masked != response:
        emit("PostToolUse", updatedToolOutput=masked)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = None
    if mode == "pre":
        if data is None:
            deny("hook input was not valid JSON; refusing to be safe.")
        pre(data)
    elif mode == "post":
        if data is None:
            raise ValueError("unparsable PostToolUse input")
        post(data)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # fail closed
        if mode == "pre":
            deny(f"creds hook error ({type(e).__name__}); refusing to be safe.")
        emit("PostToolUse", updatedToolOutput=[{"type": "text", "text": WITHHELD}])
