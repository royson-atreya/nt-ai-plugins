#!/usr/bin/env bash
# Tests for nt-dev-coding scripts: devtask.py (id, specs, status, start) and diffstat.py.
# Throwaway workspace in a temp dir; never touches the real repos or nt-docs. Run: bash tests/test_scripts.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export ROOT TMP NT_WORKSPACE="$TMP/ws"
python3 -I - <<'EOF'
import json, os, subprocess, sys

ROOT, TMP = os.environ["ROOT"], os.environ["TMP"]
WS = f"{TMP}/ws"; R = f"{WS}/repos"; D = f"{WS}/nt-docs"; DEV = f"{D}/dev"
B = f"{R}/Ashoka-World-Backend"
fails = total = 0


def check(label, got, want):
    global fails, total
    total += 1
    if got != want:
        fails += 1
        print(f"FAIL  {label}   (got {got!r}, want {want!r})")


def sh(*args, cwd=None):
    subprocess.run(args, check=True, capture_output=True, cwd=cwd)


def script(name, *args):
    r = subprocess.run([sys.executable, f"{ROOT}/scripts/{name}", *args], capture_output=True, text=True, timeout=60)
    try:
        return r.returncode, json.loads(r.stdout)
    except ValueError:
        print(r.stdout, r.stderr)
        return r.returncode, {}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


# fixture repo with one commit
os.makedirs(f"{B}/app", exist_ok=True)
write(f"{B}/app/Enach.php", "<?php\n" + "".join(f"// line {i}\n" for i in range(1, 21)))
write(f"{B}/app/Other.php", "<?php\n")
sh("git", "init", "-q", "-b", "master", B)
sh("git", "-C", B, "add", ".")
sh("git", "-C", B, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init")

# nt-docs fixture: one backend module with an analysis, one web module map-only
write(f"{D}/Ashoka-World-Backend/module-map.json", json.dumps({"status": "confirmed", "modules": [
    {"id": "enach", "name": "ENACH mandates", "summary": "Razorpay e-mandate registration and debit"}]}))
write(f"{D}/Ashoka-World-Backend/modules/enach.md", "---\ngenerated_at: 2026-10-20\ngraph_stale: false\n---\n# enach\n")
write(f"{D}/Nadi-Tarangini-Frontend/module-map.json", json.dumps({"status": "draft", "modules": [
    {"id": "inventory", "name": "Medical inventory", "summary": "stock"}]}))

# ---------- id ----------
_, o = script("devtask.py", "id", "ZS-1234: ENACH retry fails for doctors")
check("ticket id kept", o["id"], "ZS-1234")
_, o = script("devtask.py", "id", "Add the expiry alert to medical inventory")
check("slug id", o["id"].split("-", 1)[1], "expiry-alert-medical-inventory")
check("slug id date prefix", len(o["id"].split("-", 1)[0]), 8)
_, o = script("devtask.py", "id", "Save report fails with HTTP-500 on staging")
check("HTTP-500 is not a ticket id", (o["id_source"], o["id"].endswith("save-report-fails-http-500-staging")), ("slug", True))
_, o = script("devtask.py", "id", "Login broken on Android\nseen with UTF-8 names, see ZS-77")
check("only the first line is scanned", (o["id_source"], o["id"].split("-", 1)[1]), ("slug", "login-broken-android"))
_, o = script("devtask.py", "id", "NT-BUG-142 ENACH retry")
check("NT-BUG id kept", (o["id"], o["id_source"]), ("NT-BUG-142", "ticket-in-text"))

# ---------- specs gate ----------
_, o = script("devtask.py", "specs", "enach", "mandate")
check("analysis found", o["spec_level"], "analysis"); check("gate pass", o["gate"], "pass")
_, o = script("devtask.py", "specs", "inventory")
check("map-only stops", (o["spec_level"], o["gate"]), ("map-only", "stop"))
_, o = script("devtask.py", "specs", "zzzunknown")
check("nothing stops", (o["spec_level"], o["gate"]), ("none", "stop"))
write(f"{D}/impact/2026-10-25-inventory-expiry.md", "---\ngenerated_at: 2026-10-25\n---\ninventory expiry alerts\n")
_, o = script("devtask.py", "specs", "inventory")
check("impact report passes", (o["spec_level"], o["gate"]), ("impact", "pass"))

# ---------- status / start ----------
tid = "ZS-1234"
write(f"{DEV}/{tid}/plan.md", "---\nid: ZS-1234\nkind: bug\nrepos:\n  - Ashoka-World-Backend\nfiles:\n"
      "  - Ashoka-World-Backend/app/Enach.php\n  - Ashoka-World-Backend/app/Jobs/\n---\n# plan\n")
code, o = script("devtask.py", "status", tid)
check("unapproved is blocked", (code, o["ready"]), (1, False))
check("plan files parsed", o["plan_files"], ["Ashoka-World-Backend/app/Enach.php", "Ashoka-World-Backend/app/Jobs/"])
check("kind from plan", o["kind"], "bug")
check("missing planned file flagged", o["missing_files"], [])
check("no plan files outside plan repos", o["files_outside_repos"], [])
subprocess.run([sys.executable, f"{ROOT}/hooks/approve.py"], input=json.dumps({"prompt": f"approve {tid}"}),
               text=True, capture_output=True)
code, o = script("devtask.py", "start", tid)
check("master is blocked at start", code, 1)
check("blocker names checkout -b", any("checkout -b feature/ZS-1234" in b for b in o["blockers"]), True)
check("no base.json while blocked", os.path.exists(f"{DEV}/{tid}/base.json"), False)
sh("git", "-C", B, "checkout", "-q", "-b", "feature/ZS-1234")
write(f"{B}/app/Other.php", "<?php\n// user's own unrelated work\n")       # dirty before implement
code, o = script("devtask.py", "start", tid)
check("ready on feature branch", (code, o["ready"]), (0, True))
check("pre-existing change recorded", o["base_json"]["repos"]["Ashoka-World-Backend"]["dirty_before"], ["app/Other.php"])
check("start warns about it", len(o["warnings"]), 1)
base_commit = o["base_json"]["repos"]["Ashoka-World-Backend"]["commit"]
_, o = script("devtask.py", "start", tid)
check("base.json kept on re-run", o["base"].startswith("kept"), True)

# ---------- the "implementation" ----------
lines = open(f"{B}/app/Enach.php").read().splitlines()
lines[5] = "// line 5 fixed"; lines.insert(10, "// added A"); lines.insert(11, "// added B"); del lines[18]
write(f"{B}/app/Enach.php", "\n".join(lines) + "\n")
write(f"{B}/app/Jobs/RetryEnach.php", "<?php\nclass RetryEnach {}\n")       # new file under a planned folder
write(f"{B}/app/Unplanned.php", "<?php\n$k = 'rzp_live_ABCDEFGH12345678';\n")
sh("git", "-C", B, "add", "app/Jobs/RetryEnach.php")                         # tracked (A) vs untracked mix
sh("git", "-C", B, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "user commit mid-way")

code, o = script("diffstat.py", tid)
check("diffstat ok", code, 0)
by = {f["path"]: f for f in o["files"]}
check("Enach counts", (by["app/Enach.php"]["plus"], by["app/Enach.php"]["minus"]), (3, 2))
check("committed new file still counted vs base", (by["app/Jobs/RetryEnach.php"]["status"], by["app/Jobs/RetryEnach.php"]["plus"]), ("A", 2))
check("folder entry makes it planned", "unplanned" in by["app/Jobs/RetryEnach.php"]["flags"], False)
check("unplanned flagged", o["unplanned"], ["Ashoka-World-Backend/app/Other.php", "Ashoka-World-Backend/app/Unplanned.php"])
check("pre-existing flagged", o["pre_existing"], ["Ashoka-World-Backend/app/Other.php"])
check("no mixed files yet", o["mixed"], [])
check("credential redacted", "redacted" in by["app/Unplanned.php"]["flags"], True)
check("totals", (o["plus"], o["minus"]), (3 + 2 + 2 + 1, 2))
md = open(f"{DEV}/{tid}/diff.md").read()
check("diff.md never contains the key", "rzp_live_ABCDEFGH" in md, False)
check("diff.md has removed line", "-// line 5" in md, True)
check("diff.md has added line", "+// added A" in md, True)
check("diff.md records base", f"base: {base_commit}" in md, True)
check("table header", "| # | File | Status | + | − | Flags |" in md, True)
sha = o["diff_sha256"]
os.remove(f"{DEV}/{tid}/diff.md")
code, j = script("diffstat.py", tid, "--json")
check("--json writes nothing", os.path.exists(f"{DEV}/{tid}/diff.md"), False)
check("hash is stable across runs", j["diff_sha256"], sha)
check("diff.md front-matter carries the hash", f"diff_sha256: {sha}" in md, True)
lines = open(f"{B}/app/Enach.php").read().replace("// line 5 fixed", "// line 5 FIXED")   # same +/- counts
write(f"{B}/app/Enach.php", lines)
_, j = script("diffstat.py", tid, "--json")
check("same-count edit changes the hash", j["diff_sha256"] != sha, True)
check("same-count edit keeps totals", (j["plus"], j["minus"]), (o["plus"], o["minus"]))
check("kind in diff.md front-matter", "kind: bug" in md, True)
# re-plan adds a repo: start records its base without --reset
F = f"{R}/Nadi-Tarangini-Frontend"
os.makedirs(f"{F}/app", exist_ok=True); write(f"{F}/app/y.php", "<?php\n")
sh("git", "init", "-q", "-b", "master", F); sh("git", "-C", F, "add", ".")
sh("git", "-C", F, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "i")
sh("git", "-C", F, "checkout", "-q", "-b", "feature/ZS-1234")
plan_text = open(f"{DEV}/{tid}/plan.md").read()
plan_text = plan_text.replace("  - Ashoka-World-Backend\n", "  - Ashoka-World-Backend\n  - Nadi-Tarangini-Frontend\n", 1)
plan_text = plan_text.replace("files:\n", "files:\n  - Nadi-Tarangini-Frontend/app/y.php\n", 1)
write(f"{DEV}/{tid}/plan.md", plan_text)
subprocess.run([sys.executable, f"{ROOT}/hooks/approve.py"], input=json.dumps({"prompt": f"approve {tid}", "cwd": WS}),
               text=True, capture_output=True)
code, o = script("devtask.py", "start", tid)
check("re-plan: start ok", code, 0)
bj = json.load(open(f"{DEV}/{tid}/base.json"))
check("re-plan: new repo base recorded", "Nadi-Tarangini-Frontend" in bj["repos"], True)
check("re-plan: old base kept", bj["repos"]["Ashoka-World-Backend"]["commit"], base_commit)
sys.dont_write_bytecode = True; sys.path.insert(0, f"{ROOT}/scripts"); import diffstat
check("dot-folder plan entry is planned", diffstat.planned(".github/workflows/ci.yml", [".github/workflows/ci.yml"]), True)

print(("all %d nt-dev-coding script tests passed" % total) if not fails else ("%d of %d tests FAILED" % (fails, total)))
sys.exit(1 if fails else 0)
EOF
