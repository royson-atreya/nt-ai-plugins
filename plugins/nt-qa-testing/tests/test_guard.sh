#!/usr/bin/env bash
# Tests for nt-qa-testing hooks: guard.py, creds.py (pre/post), session_banner.py.
# Uses a temporary fake workspace and FAKE credentials only. Run: bash tests/test_guard.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/ws/repos/Nadi-Tarangini-Frontend" "$TMP/ws/nt-docs/qa" "$TMP/elsewhere"

export ROOT TMP
export NT_WORKSPACE="$TMP/ws"
export CLAUDE_PLUGIN_OPTION_DOCTOR_USERNAME="qa.doctor+fake01@example.com"
export CLAUDE_PLUGIN_OPTION_DOCTOR_PASSWORD="Fake-Pass-123"
export CLAUDE_PLUGIN_OPTION_STAGING_BASE_URL="https://staging-dashboard.naditarangini.com"

python3 -I - <<'EOF'
import json, os, subprocess, sys

ROOT, TMP = os.environ["ROOT"], os.environ["TMP"]
WS = f"{TMP}/ws"; REPO = f"{WS}/repos/Nadi-Tarangini-Frontend"; DOCS = f"{WS}/nt-docs"; OUT = f"{TMP}/elsewhere"
PW = "mcp__plugin_playwright_playwright__"
fails = 0

def run(script, payload, *args):
    r = subprocess.run([sys.executable, f"{ROOT}/hooks/{script}", *args], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=20)
    return json.loads(r.stdout) if r.stdout.strip() else {}

def decision(out):
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision", "allow")

def check(label, got, want):
    global fails
    ok = got == want
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"   (got {got!r}, want {want!r})"))

def guard(tool, inp, cwd=DOCS, want="allow"):
    check(f"guard {want:5} {tool.replace(PW, 'pw:')} {json.dumps(inp)[:70]}", decision(run("guard.py",
          {"tool_name": tool, "tool_input": inp, "cwd": cwd})), want)

# --- production hosts: blocked everywhere ---
for url in ["https://dashboard.naditarangini.com/login", "https://naditarangini.com", "http://www.naditarangini.com",
            "https://api.ashoka.world/api/v1/x", "dashboard.naditarangini.com"]:
    guard(PW + "browser_navigate", {"url": url}, want="deny")
    guard(PW + "browser_navigate", {"url": url}, cwd=OUT, want="deny")
guard("WebFetch", {"url": "https://api.ashoka.world/health", "prompt": "x"}, cwd=OUT, want="deny")
guard("Bash", {"command": "curl -s https://api.ashoka.world/api/login"}, cwd=OUT, want="deny")
guard("Bash", {"command": "wget dashboard.naditarangini.com"}, want="deny")
guard("Bash", {"command": "python3 -c \"import urllib.request;urllib.request.urlopen('https://api.ashoka.world')\""}, want="deny")
guard(PW + "browser_evaluate", {"function": "() => fetch('https://api.ashoka.world/api/x')"}, want="deny")
guard(PW + "browser_tabs", {"action": "new", "url": "https://dashboard.naditarangini.com"}, want="deny")

# --- staging allowed ---
guard(PW + "browser_navigate", {"url": "https://staging-dashboard.naditarangini.com/login"})
guard(PW + "browser_navigate", {"url": "staging-dashboard.naditarangini.com"})
guard(PW + "browser_navigate", {"url": "about:blank"})
guard("Bash", {"command": "curl -s https://staging-api.ashoka.world/api/health"})
guard("WebFetch", {"url": "https://code.claude.com/docs/en/hooks", "prompt": "x"})
guard("Bash", {"command": "grep -n 'dashboard.naditarangini.com' notes.md"})  # mentioning a host is not a call

# --- strict allowlist only inside the workspace ---
guard(PW + "browser_navigate", {"url": "https://example.com"}, want="deny")
guard(PW + "browser_navigate", {"url": "https://example.com"}, cwd=OUT)
guard(PW + "browser_navigate", {"url": "file:///etc/hosts"}, want="deny")
guard(PW + "browser_navigate", {"url": "javascript:alert(1)"}, want="deny")
guard(PW + "browser_run_code_unsafe", {"code": "async (page) => page.title()"}, want="deny")
guard(PW + "browser_run_code_unsafe", {"code": "async (page) => page.title()"}, cwd=OUT)
guard(PW + "browser_click", {"element": "Login button", "target": "e12"})
guard(PW + "browser_file_upload", {"paths": [f"{REPO}/.env"]}, want="deny")
guard(PW + "browser_take_screenshot", {"filename": f"{REPO}/shot.png"}, want="deny")
guard(PW + "browser_take_screenshot", {"filename": f"{DOCS}/qa/NT-BUG-1/screenshots/TC-NT-BUG-1-01-s01.png"})

# --- git ---
for sub in ("commit -m x", "push origin main", "pull"):
    guard("Bash", {"command": f"git {sub}"}, cwd=f"{WS}/nt-ai-plugins", want="deny")
guard("Bash", {"command": f"git -C {REPO} push"}, cwd=OUT, want="deny")
guard("Bash", {"command": "git commit -m x"}, cwd=OUT)
guard("Bash", {"command": "git status && git log --oneline -5"}, cwd=REPO)
guard("Bash", {"command": "git checkout -b x"}, cwd=REPO, want="deny")

# --- secret files ---
guard("Read", {"file_path": f"{REPO}/.env"}, want="deny")
guard("Read", {"file_path": f"{REPO}/android/app/google-services.json"}, want="deny")
guard("Read", {"file_path": f"{REPO}/upload.keystore"}, want="deny")
guard("Read", {"file_path": f"{OUT}/.env"})
guard("Read", {"file_path": f"{DOCS}/api-links/api-links.json"})
guard("Grep", {"pattern": "KEY", "path": f"{REPO}/.env.production"}, want="deny")
guard("Grep", {"pattern": "KEY", "path": REPO, "glob": "firebase-*.json"}, want="deny")
guard("Grep", {"pattern": "KEY", "path": REPO, "glob": "*.json"}, want="deny")
guard("Grep", {"pattern": "KEY", "path": REPO}, want="deny")
guard("Grep", {"pattern": "Route::", "path": REPO, "type": "php"})
guard("Grep", {"pattern": "patient", "path": DOCS})
guard("Glob", {"pattern": "**/.env*", "path": REPO}, want="deny")
guard("Glob", {"pattern": "**/GoogleService-Info.plist"}, want="deny")
guard("Glob", {"pattern": "**/*.md", "path": DOCS})
guard("Bash", {"command": f"cat {REPO}/.env"}, want="deny")
guard("Bash", {"command": "cat .env"}, cwd=REPO, want="deny")
guard("Bash", {"command": "cat config/*.json"}, cwd=REPO, want="deny")
guard("Bash", {"command": "grep -rn KEY --include='*.php' ."}, cwd=REPO)
guard("Bash", {"command": "grep -rn KEY ."}, cwd=REPO, want="deny")
guard("Bash", {"command": "grep -n 'process.env' notes.md"})  # code mention, not a file

# --- product repos are never modified ---
guard("Write", {"file_path": f"{REPO}/tests/login.spec.js", "content": "x"}, want="deny")
guard("Edit", {"file_path": f"{REPO}/app.php", "old_string": "a", "new_string": "b"}, want="deny")
guard("Write", {"file_path": f"{DOCS}/qa/NT-BUG-1/plan.md", "content": "x"})
guard("Bash", {"command": f"echo x > {REPO}/x.txt"}, want="deny")
guard("Bash", {"command": f"cp a.png {REPO}/"}, want="deny")
guard("Bash", {"command": "sed -i '' s/a/b/ app.php"}, cwd=REPO, want="deny")
guard("Bash", {"command": f"mkdir -p {DOCS}/qa/NT-BUG-1/screenshots && mv shot.png {DOCS}/qa/NT-BUG-1/screenshots/"})

# --- creds: injection ---
PH_U, PH_P = "{{nt-qa:doctor:username}}", "{{nt-qa:doctor:password}}"
out = run("creds.py", {"tool_name": PW + "browser_type",
          "tool_input": {"element": "Password", "target": "e7", "text": PH_P}, "cwd": DOCS}, "pre")
check("creds inject: decision allow", decision(out), "allow")
check("creds inject: password substituted", out["hookSpecificOutput"]["updatedInput"]["text"], "Fake-Pass-123")
check("creds inject: other fields kept", out["hookSpecificOutput"]["updatedInput"]["target"], "e7")
out = run("creds.py", {"tool_name": PW + "browser_fill_form", "tool_input": {"fields": [
          {"name": "Email", "type": "textbox", "target": "e5", "value": PH_U},
          {"name": "Password", "type": "textbox", "target": "e7", "value": PH_P}]}, "cwd": DOCS}, "pre")
vals = [f["value"] for f in out["hookSpecificOutput"]["updatedInput"]["fields"]]
check("creds inject: fill_form both fields", vals, ["qa.doctor+fake01@example.com", "Fake-Pass-123"])

def creds_pre(tool, inp, want):
    check(f"creds {want:5} {tool.replace(PW, 'pw:')} {json.dumps(inp)[:60]}",
          decision(run("creds.py", {"tool_name": tool, "tool_input": inp, "cwd": DOCS}, "pre")), want)

creds_pre(PW + "browser_type", {"target": "e7", "text": "{{nt-qa:college:password}}"}, "deny")  # not configured
creds_pre(PW + "browser_type", {"target": "e7", "text": "{{nt-qa:root:password}}"}, "deny")     # unknown role
creds_pre(PW + "browser_evaluate", {"function": f"() => '{PH_P}'"}, "deny")
creds_pre(PW + "browser_navigate", {"url": "https://staging-dashboard.naditarangini.com/login"}, "allow")
creds_pre("Write", {"file_path": f"{DOCS}/qa/x/cases.md", "content": f"Login as {PH_U} / {PH_P}"}, "allow")
creds_pre("Write", {"file_path": f"{DOCS}/qa/x/report.md", "content": "password was Fake-Pass-123"}, "deny")
creds_pre("Write", {"file_path": f"{DOCS}/qa/x/results.csv", "content": "qa.doctor+fake01@example.com,Pass"}, "deny")
creds_pre("Bash", {"command": "echo Fake-Pass-123 >> notes.txt"}, "deny")

# --- creds: masking ---
resp = [{"type": "text", "text": "### Ran Playwright code\nawait page.getByRole('textbox', { name: 'Password' })"
         ".fill('Fake-Pass-123');\nbody: email=qa.doctor%2Bfake01%40example.com&password=Fake-Pass-123"}]
out = run("creds.py", {"tool_name": PW + "browser_type", "tool_response": resp}, "post")
masked = json.dumps(out.get("hookSpecificOutput", {}).get("updatedToolOutput"))
check("creds mask: password removed", "Fake-Pass-123" in masked, False)
check("creds mask: url-encoded username removed", "fake01" in masked, False)
check("creds mask: mask present", "●●●●" in json.loads(masked)[0]["text"], True)
out = run("creds.py", {"tool_name": PW + "browser_snapshot", "tool_response": [{"type": "text", "text": "Doctor Dashboard"}]}, "post")
check("creds mask: unchanged output passes through", out, {})

# --- review hardening ---
guard(PW + "browser_evaluate", {"function": "() => document.title"}, want="deny")
guard(PW + "browser_evaluate", {"function": "() => document.title"}, cwd=OUT)
guard(PW + "browser_snapshot", {"filename": f"{DOCS}/qa/x/snap.md"}, want="deny")
guard(PW + "browser_console_messages", {"level": "error", "filename": "console.log"}, want="deny")
guard(PW + "browser_navigate", {"url": "https://dashboard%2enaditarangini%2ecom/"}, cwd=OUT, want="deny")
guard("WebFetch", {"url": "https://api%2Eashoka%2Eworld/x", "prompt": "x"}, cwd=OUT, want="deny")
guard("Bash", {"command": "nc api.ashoka.world 443"}, cwd=OUT, want="deny")
guard("Bash", {"command": "openssl s_client -connect api.ashoka.world:443"}, cwd=OUT, want="deny")
guard("Bash", {"command": "python3 -c \"import http.client;http.client.HTTPSConnection('api.ashoka.world')\""}, cwd=OUT, want="deny")
check("creds inject: refused outside workspace", decision(run("creds.py", {"tool_name": PW + "browser_type",
      "tool_input": {"target": "e7", "text": PH_P}, "cwd": OUT}, "pre")), "deny")
import base64 as b64
basic = b64.b64encode(b"qa.doctor+fake01@example.com:Fake-Pass-123").decode()
out = run("creds.py", {"tool_name": PW + "browser_network_request", "tool_response":
          [{"type": "text", "text": f"authorization: Basic {basic}"}]}, "post")
check("creds mask: Basic auth header masked", basic.rstrip("=") in json.dumps(out), False)
out = run("creds.py", {"tool_name": "Read", "tool_response": {"type": "text", "file": {"filePath": "/x/snap.md",
          "content": "textbox \"Email\": qa.doctor+fake01@example.com", "numLines": 1}}}, "post")
check("creds mask: Read output masked, shape kept",
      out["hookSpecificOutput"]["updatedToolOutput"]["file"]["content"], 'textbox "Email": ●●●●')
img = [{"type": "image", "data": "Fake-Pass-123" + "A" * 50, "mimeType": "image/png"}]
check("creds mask: image block untouched", run("creds.py", {"tool_name": PW + "browser_take_screenshot",
      "tool_response": img}, "post"), {})

# --- results_csv: sections after the last case are not part of it ---
import tempfile
rd = tempfile.mkdtemp(dir=TMP) + "/NT-BUG-7"
os.makedirs(rd)
open(f"{rd}/cases.md", "w").write("""## TC-NT-BUG-7-01 · Last case [bug-repro]
- Module: patients
- Sub-module: Add
- Priority: P1
- Role: doctor
- Spec: bug report
- Status: Ready
- Preconditions: none
- Test data: none

Steps:
1. Open list → Expected: list shown

Expected result: ok

## Traceability
- Module: WRONG
1. not a step

**Open questions**
2. also not a step
""")
json.dump({"cases": [{"id": "TC-NT-BUG-7-01", "verdict": "Pass", "actual": "list shown"}]}, open(f"{rd}/check.json", "w"))
json.dump({"cases": []}, open(f"{rd}/run.json", "w"))
subprocess.run([sys.executable, f"{ROOT}/scripts/results_csv.py", rd], capture_output=True, check=True)
import csv
row = list(csv.reader(open(f"{rd}/results.csv", encoding="utf-8-sig")))[1]
check("csv: trailing sections ignored (module, steps)", (row[1], row[5]), ("patients", "1. Open list"))
check("csv: bug id from run id", "bug repro (NT-BUG-7)" in row[11], True)

# --- banner ---
r = subprocess.run([sys.executable, f"{ROOT}/hooks/session_banner.py"], input=json.dumps({"cwd": DOCS}),
                   capture_output=True, text=True)
b = json.loads(r.stdout)["systemMessage"]
check("banner: lists run-web", "/nt-qa-testing:run-web" in b, True)
check("banner: doctor configured, college missing", "configured: doctor" in b and "college" in b, True)
check("banner: no credential values", "Fake-Pass-123" in r.stdout or "fake01" in r.stdout, False)
r = subprocess.run([sys.executable, f"{ROOT}/hooks/session_banner.py"], input=json.dumps({"cwd": OUT}),
                   capture_output=True, text=True)
check("banner: silent outside workspace", r.stdout.strip(), "")

print(f"\n{'ALL PASS' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
EOF
