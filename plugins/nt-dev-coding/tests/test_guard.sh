#!/usr/bin/env bash
# Tests for nt-dev-coding hooks: guard.py, approve.py, session_banner.py, devgate.py.
# Builds a throwaway workspace (fixture git repos, nt-docs/dev) in a temp dir; never touches the real repos.
# Run: bash tests/test_guard.sh   (exit 1 on any failure)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
WS="$TMP/ws"; R="$WS/repos"
mkdir -p "$WS/nt-docs/dev" "$TMP/elsewhere"
for r in Ashoka-World-Backend Nadi-Tarangini-Frontend Nadi-Tarangini-App; do
  git init -q -b master "$R/$r"
  mkdir -p "$R/$r/app" "$R/$r/lib"
  printf '<?php\necho 1;\n' > "$R/$r/app/x.php"; : > "$R/$r/.env"; : > "$R/$r/lib/main.dart"
  git -C "$R/$r" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
done
git -C "$R/Nadi-Tarangini-App" checkout -q -b production

export ROOT TMP NT_WORKSPACE="$WS"
python3 -I - <<'EOF'
import json, os, subprocess, sys

ROOT, TMP = os.environ["ROOT"], os.environ["TMP"]
WS = f"{TMP}/ws"; R = f"{WS}/repos"; DEV = f"{WS}/nt-docs/dev"; OUT = f"{TMP}/elsewhere"
B, F, A = f"{R}/Ashoka-World-Backend", f"{R}/Nadi-Tarangini-Frontend", f"{R}/Nadi-Tarangini-App"
P = f"{WS}/nt-ai-plugins"; os.makedirs(P, exist_ok=True)
fails = 0
total = 0


def run(script, payload):
    r = subprocess.run([sys.executable, f"{ROOT}/hooks/{script}"], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=20)
    if r.returncode:
        print(r.stderr)
    return json.loads(r.stdout) if r.stdout.strip() else {}


def check(label, got, want):
    global fails, total
    total += 1
    ok = got == want
    fails += not ok
    if not ok:
        print(f"FAIL  {label}   (got {got!r}, want {want!r})")


def guard(want, tool, inp, cwd=P):
    out = run("guard.py", {"tool_name": tool, "tool_input": inp, "cwd": cwd})
    got = (out.get("hookSpecificOutput") or {}).get("permissionDecision", "allow")
    check(f"{want:5} {tool} {json.dumps(inp)[:90]} (cwd {cwd.replace(TMP, '$TMP')})", got, want)
    return out


def bash(want, cmd, cwd=P):
    return guard(want, "Bash", {"command": cmd}, cwd)


def edit(want, path, tool="Edit"):
    inp = {"file_path": path, "old_string": "a", "new_string": "b"} if tool == "Edit" else {"file_path": path, "content": "x"}
    return guard(want, tool, inp)


def prompt(text):
    return run("approve.py", {"prompt": text, "cwd": WS, "hook_event_name": "UserPromptSubmit"})


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def write_plan(tid, repos):
    os.makedirs(f"{DEV}/{tid}", exist_ok=True)
    with open(f"{DEV}/{tid}/plan.md", "w") as f:
        f.write(f"---\nid: {tid}\nrepos: [{', '.join(repos)}]\n---\n# plan\n")


# ---------- no task: repos are read-only ----------
edit("deny", f"{B}/app/x.php"); edit("deny", f"{B}/app/new.php", "Write")
guard("allow", "Read", {"file_path": f"{B}/app/x.php"})
guard("allow", "Write", {"file_path": f"{DEV}/T-1/ticket.md", "content": "x"})
edit("allow", f"{OUT}/x.php")

# ---------- approval: only via the user's prompt ----------
write_plan("T-1", ["Ashoka-World-Backend", "Nadi-Tarangini-App"])
for path in (f"{DEV}/T-1/APPROVED", f"{DEV}/ACTIVE"):
    guard("deny", "Write", {"file_path": path, "content": "{}"})
    guard("deny", "Edit", {"file_path": path, "old_string": "a", "new_string": "b"})
bash("deny", f"echo T-1 > {DEV}/ACTIVE"); bash("deny", "printf x >APPROVED", f"{DEV}/T-1")
bash("deny", f"cp /tmp/a {DEV}/T-1/APPROVED"); bash("deny", f"touch {DEV}/T-1/APPROVED"); bash("deny", f"rm {DEV}/ACTIVE")
bash("deny", f"python3 -c \"open('{DEV}/T-1/APPROVED','w').write('x')\"")
bash("deny", f"bash -c 'echo T-1 > {DEV}/ACTIVE'")
bash("deny", f"python3 - <<'X'\nopen('{DEV}/T-1/APPROVED','w').write('x')\nX")
bash("deny", "node -e \"require('fs').writeFileSync('APPROVED','x')\"", f"{DEV}/T-1")
bash("allow", f"python3 {ROOT}/scripts/devtask.py id \"show APPROVED status on ENACH\"")
bash("allow", f"cat {DEV}/ACTIVE"); bash("allow", f"ls {DEV}/T-1/APPROVED"); bash("allow", f"test -f {DEV}/T-1/APPROVED")

out = prompt("approve T-9")
check("approve unknown id records nothing", os.path.exists(f"{DEV}/T-9/APPROVED"), False)
check("approve unknown id tells Claude", "no such task" in json.dumps(out), True)
check("ordinary prompt is ignored", prompt("please approve the plan for T-1 later"), {})
check("no APPROVED yet", os.path.exists(f"{DEV}/T-1/APPROVED"), False)
write_plan("T-bad", ["Not-A-Repo"]); prompt("approve T-bad")
check("plan with unknown repo is not approved", os.path.exists(f"{DEV}/T-bad/APPROVED"), False)
os.makedirs(f"{DEV}/T-noplan"); prompt("approve T-noplan")
check("missing plan is not approved", os.path.exists(f"{DEV}/T-noplan/APPROVED"), False)

out = prompt("Approve T-1.")
rec = json.load(open(f"{DEV}/T-1/APPROVED"))
check("APPROVED records repos", rec["repos"], ["Ashoka-World-Backend", "Nadi-Tarangini-App"])
check("ACTIVE set", open(f"{DEV}/ACTIVE").read().strip(), "T-1")
check("approve reports protected branch", "protected" in out.get("systemMessage", ""), True)

# ---------- approved, but protected branches ----------
r = edit("deny", f"{B}/app/x.php")
check("protected-branch hint names checkout -b", "checkout -b feature/T-1" in json.dumps(r), True)
edit("deny", f"{A}/lib/main.dart")                     # production
git(A, "checkout", "-q", "--detach"); edit("deny", f"{A}/lib/main.dart"); git(A, "checkout", "-q", "production")

# ---------- feature branch: edits allowed in planned repos only ----------
git(B, "checkout", "-q", "-b", "feature/T-1")
edit("allow", f"{B}/app/x.php"); edit("allow", f"{B}/app/New.php", "Write")
guard("allow", "MultiEdit", {"file_path": f"{B}/app/x.php", "edits": []})
edit("deny", f"{B}/app/x.php", "Write")                # existing file: Write would rewrite it all
edit("deny", f"{B}/.env"); guard("deny", "Read", {"file_path": f"{B}/.env"})
edit("deny", f"{B}/.git/config"); edit("deny", f"{B}/.git/hooks/pre-commit", "Write")
git(F, "checkout", "-q", "-b", "feature/T-1"); edit("deny", f"{F}/app/x.php")    # repo not in plan
edit("deny", f"{A}/lib/main.dart")                     # in plan but still on production
git(A, "checkout", "-q", "-b", "feature/T-1"); edit("allow", f"{A}/lib/main.dart")
edit("allow", f"{B}/app/../app/x.php")
os.symlink(f"{F}/app/x.php", f"{B}/app/link.php"); edit("deny", f"{B}/app/link.php")   # symlink into other repo

# Bash never writes into the repos, even when approved
bash("deny", f"echo x > {B}/app/x.php"); bash("deny", "sed -i '' s/a/b/ app/x.php", B); bash("deny", f"rm {B}/app/x.php")
bash("deny", f"cp /tmp/a.php {B}/app/a.php"); bash("deny", f"mv {B}/app/x.php /tmp/"); bash("deny", f"tee {B}/a.php")
bash("allow", f"cp {B}/app/x.php {OUT}/x.php"); bash("allow", "grep -n '$q->where(' app/x.php", B)
bash("allow", f"echo hi > {OUT}/x.txt", B)
for c in ["sed -Ei s/a/b/ app/x.php", "perl -0pi -e s/a/b/ app/x.php", "find . -name x.php -delete",
          "find . -name '*.json' -exec cat {} +", f"find {B} -type f | xargs rm", "xargs rm < /tmp/list.txt",
          "curl -o app/x.php http://x", "curl -sO http://x/a.php", "wget http://x", f"tar -C {B} -xf /tmp/a.tar",
          "tar --extract -f /tmp/a.tar", "unzip /tmp/a.zip", f"cp -t {B}/app /tmp/a.php", f"dd if=/tmp/a of={B}/app/x.php",
          "exec 3>app/x.php", "echo x &>app/x.php", "echo x >|app/x.php", f"python3 -c \"open('{B}/app/x.php','w')\"",
          "python3 - <<X\nopen('app/x.php','w')\nX", "node -e \"require('fs').writeFileSync('app/x.php','')\""]:
    bash("deny", c, B)
for c in ["find . -name '*.php' -exec grep -l Enach {} +", f"find {B} -name '*.php' | xargs grep -l x", "tar -tf /tmp/a.tar",
          "curl -s https://staging-api.ashoka.world/health", "grep -n 'a => b' app/x.php", "php -l app/x.php 2>&1",
          "ls app >/dev/null", "wc -l app/x.php"]:
    bash("allow", c, B)
git(A, "symbolic-ref", "HEAD", "refs/heads/ghost"); edit("deny", f"{A}/lib/main.dart")   # HEAD -> missing branch
git(A, "symbolic-ref", "HEAD", "refs/heads/feature/T-1"); edit("allow", f"{A}/lib/main.dart")
# fail closed when devgate.py cannot be loaded
os.makedirs(f"{TMP}/broken", exist_ok=True); shutil_copy = __import__("shutil").copy
shutil_copy(f"{ROOT}/hooks/guard.py", f"{TMP}/broken/guard.py")
r = subprocess.run([sys.executable, f"{TMP}/broken/guard.py"], input=json.dumps({"tool_name": "Read", "tool_input": {}}),
                   capture_output=True, text=True)
check("guard without devgate denies", "deny" in r.stdout, True)

# plan edited after approval -> blocked until re-approved
with open(f"{DEV}/T-1/plan.md", "a") as f:
    f.write("\nrepos widened\n")
r = edit("deny", f"{B}/app/x.php"); check("changed plan explains re-approve", "re-approve" in json.dumps(r), True)
prompt("approve T-1"); edit("allow", f"{B}/app/x.php")

# ACTIVE pointing at another task, forged APPROVED copied between tasks
write_plan("T-2", ["Nadi-Tarangini-Frontend"])
prompt("approve T-2"); edit("allow", f"{F}/app/x.php"); edit("deny", f"{B}/app/x.php")
prompt("approve T-1"); edit("deny", f"{F}/app/x.php")
import shutil; shutil.copy(f"{DEV}/T-1/APPROVED", f"{DEV}/T-2/APPROVED")
with open(f"{DEV}/ACTIVE", "w") as f:
    f.write("T-2\n")
edit("deny", f"{F}/app/x.php")                         # APPROVED id != T-2
prompt("approve T-1")

# revoke
prompt("revoke T-1")
check("revoke removes APPROVED", os.path.exists(f"{DEV}/T-1/APPROVED"), False)
check("revoke clears ACTIVE", os.path.exists(f"{DEV}/ACTIVE"), False)
edit("deny", f"{B}/app/x.php")
prompt("approve T-1")

# ---------- git ----------
for c in ["git commit -m x", "git push", "git pull", "git checkout -b x", "git switch main", "git branch x",
          "git branch -D x", "git merge x", "git rebase main", "git reset --hard", "git stash", "git tag v1",
          "git add .", "git restore app/x.php", "git -C {B} checkout master", "git -c user.name=x commit -m y"]:
    bash("deny", c.format(B=B), B)
bash("deny", "git commit -m x", P)                     # whole workspace, incl. nt-ai-plugins
bash("deny", f"cd {B} && git push", OUT); bash("deny", "env GIT_X=1 git push", B); bash("deny", f"git -C {B} reset --hard", OUT)
bash("allow", f"git -C {B} status --short", OUT); bash("allow", f"git -C {B} diff --numstat -- app/x.php", OUT)
for c in ["git status", "git diff -- app/x.php", "git log --oneline -5", "git show HEAD --stat",
          "git branch --show-current", "git branch", "git branch -a", "git rev-parse HEAD", "git stash list",
          "git blame app/x.php", "git tag"]:
    bash("allow", c, B)
bash("allow", "git commit -m x", OUT)                  # outside the workspace: not ours
for c in ["git symbolic-ref HEAD refs/heads/feature/x", "git config core.hooksPath /tmp", "git config --global user.name x",
          "git remote add x y", "git checkout-index -f -a", "git read-tree HEAD", "git diff --output=app/x.php",
          "git -c core.pager=less log", "GIT_EXTERNAL_DIFF=x git diff", "git notes add -m x", "git hash-object -w app/x.php",
          "git update-ref refs/heads/x HEAD", "git format-patch -1", "git diff --ext-diff"]:
    bash("deny", c, B)
for c in ["git symbolic-ref HEAD", "git symbolic-ref --short HEAD", "git config --get user.name", "git config --list",
          "git remote -v", "git ls-files", "git diff --stat", "git log -p -- app/x.php", "git show-ref"]:
    bash("allow", c, B)

# ---------- php / artisan ----------
for c in ["php artisan route:list", "php artisan route:list --path=api", "php artisan list", "php artisan about",
          "php artisan --version", "php -l app/x.php", "php -v", "php8.2 -l app/x.php"]:
    bash("allow", c, B)
for c in ["php artisan migrate", "php artisan migrate:status", "php artisan db:seed", "php artisan db:show",
          "php artisan tinker", "php artisan queue:work", "php artisan schedule:run", "php artisan test",
          "php artisan cache:clear", "php -r 'echo 1;'", "php app/x.php", "vendor/bin/phpunit", "./vendor/bin/pest",
          "./vendor/bin/sail up", "php -d x=1 artisan migrate", "bash -c 'php artisan migrate'",
          "sh -c \"cd x && php artisan tinker\""]:
    bash("deny", c, B)

# ---------- package managers ----------
for c in ["composer install", "composer update", "composer require foo/bar", "composer remove foo", "composer run test",
          "composer dump-autoload", "npm install", "npm i", "npm ci", "npm install -g x", "npm run prod", "npm publish",
          "npx something", "yarn add x", "pnpm install", "pod install",
          "flutter pub get", "flutter pub add http", "flutter upgrade", "flutter build apk", "flutter test",
          "flutter analyze", "flutter clean", "dart pub get", "dart fix --apply", "dart format lib/main.dart",
          "dart format --set-exit-if-changed lib/main.dart", "dart pub publish"]:
    bash("deny", c, A if c.split()[0] in ("flutter", "dart", "pod") else B)
for c in ["composer show", "composer --version", "composer validate", "npm ls", "npm --version"]:
    bash("allow", c, B)
for c in ["flutter analyze --no-pub lib/main.dart", "flutter --version",
          "dart format --output=none --set-exit-if-changed lib/main.dart", "dart format -o none lib/main.dart",
          "dart analyze lib/main.dart"]:
    bash("allow", c, A)
bash("allow", "npm install", OUT)                      # outside the workspace

# ---------- secrets ----------
bash("deny", "cat .env", B); bash("deny", f"cat {B}/.env", OUT); bash("deny", "head config/*.json", B)
bash("deny", "grep -n KEY .env.production", B); bash("deny", "source .env", B)
bash("deny", "cat android/app/google-services.json", A); bash("deny", "ls key/upload.keystore", A)
guard("deny", "Read", {"file_path": f"{A}/ios/Runner/GoogleService-Info.plist"})
guard("deny", "Read", {"file_path": f"{B}/config/firebase-adminsdk.json"})
guard("deny", "Grep", {"pattern": "k", "path": B, "glob": ".env*"}); guard("deny", "Grep", {"pattern": "k", "path": B})
guard("allow", "Grep", {"pattern": "k", "path": B, "type": "php"}); guard("allow", "Grep", {"pattern": "k", "path": B, "glob": "*.php"})
guard("deny", "Glob", {"pattern": "**/.env*", "path": B}); guard("deny", "Glob", {"pattern": "**/*.jks", "path": WS})
guard("allow", "Glob", {"pattern": "app/**/*.php", "path": B})
bash("deny", "grep -rn Razorpay .", B); bash("allow", "grep -rn --include='*.php' Razorpay .", B)
bash("deny", "rg Razorpay", B); bash("allow", "rg -t php Razorpay", B)
guard("allow", "Read", {"file_path": f"{OUT}/.env"})   # not NT
bash("allow", "grep -n 'process.env' app/x.php", B)

# ---------- fail closed ----------
total += 2
r = subprocess.run([sys.executable, f"{ROOT}/hooks/guard.py"], input="not json", capture_output=True, text=True)
fails += "deny" not in r.stdout
r = subprocess.run([sys.executable, f"{ROOT}/hooks/guard.py"], input='{"tool_name":"Bash","tool_input":["x"]}',
                   capture_output=True, text=True)
fails += "deny" not in r.stdout

# ---------- banner ----------
b = run("session_banner.py", {"cwd": WS})
check("banner lists commands", "/nt-dev-coding:implement" in b.get("systemMessage", ""), True)
check("banner shows active task", "T-1" in b.get("systemMessage", ""), True)
check("banner silent outside workspace", run("session_banner.py", {"cwd": OUT}), {})

print(("all %d nt-dev-coding hook tests passed" % total) if not fails else ("%d of %d tests FAILED" % (fails, total)))
sys.exit(1 if fails else 0)
EOF
