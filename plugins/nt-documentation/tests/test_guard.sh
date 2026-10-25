#!/usr/bin/env bash
# Regression tests for hooks/guard.py and hooks/zoho_confirm.py.
# Run: bash tests/test_guard.sh   (exit 1 on any failure)
# Uses the real repos under $NT_REPOS_DIR plus throwaway fixture repos in a temp dir.
set -u
cd "$(dirname "$0")/.."
WS="${NT_WORKSPACE:-$HOME/atreya-ai}"
R="${NT_REPOS_DIR:-$WS/repos}"; B="$R/Ashoka-World-Backend"; D="${NT_DOCS_DIR:-$WS/nt-docs}"; P="$WS/nt-ai-plugins"
fail=0; n=0

# ---------- fixtures ----------
FX=$(mktemp -d); trap 'rm -rf "$FX"' EXIT
mkrepo(){ git init -q "$FX/$1" && git -C "$FX/$1" remote add origin "$2" 2>/dev/null; mkdir -p "$FX/$1/app"; : > "$FX/$1/.env"; : > "$FX/$1/app/x.php"; }
mkrepo atreya-https https://github.com/Atreya-Innovations/Some-Repo.git
mkrepo atreya-ssh   git@github.com:atreya-innovations/other-repo.git
mkrepo other        https://github.com/someone-else/project.git
mkrepo atreya-market https://github.com/Atreya-Innovations/nt-ai-plugins.git
mkdir -p "$FX/atreya-market/.claude-plugin" && echo '{}' > "$FX/atreya-market/.claude-plugin/marketplace.json"
mkdir -p "$FX/plain" && : > "$FX/plain/.env"
git -C "$FX/atreya-https" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
git -C "$FX/atreya-https" worktree add -q "$FX/wt" 2>/dev/null; : > "$FX/wt/.env"
A="$FX/atreya-https"; S="$FX/atreya-ssh"; O="$FX/other"; M="$FX/atreya-market"; W="$FX/wt"; N="$FX/plain"

# ---------- helpers ----------
t(){ n=$((n+1)); out=$(jq -nc --arg t "$2" --argjson i "$3" --arg c "${4:-$P}" '{tool_name:$t,tool_input:$i,cwd:$c}' | python3 hooks/guard.py)
  got=$([ -n "$out" ] && echo deny || echo allow)
  if [ "$got" != "$1" ]; then fail=1; echo "FAIL expected $1: $2 $3 (cwd ${4:-$P})"; echo "   $out"; fi; }
bc(){ t "$1" Bash "$(jq -nc --arg c "$2" '{command:$c}')" "${3:-$P}"; }
f(){ t "$1" "$2" "$(jq -nc --arg p "$3" '{file_path:$p}')"; }
g(){ t "$1" Grep "$2"; }

# ---------- scope: secret files only in NT paths ----------
f deny  Read "$B/.env"; f deny Read "$B/config/firebase-admin-key.json"
f deny  Read "$R/Nadi-Tarangini-App/key/nt-guna-beta-keystore.jks"; f deny Read "$R/Nadi-Tarangini-App/ios/Runner/GoogleService-Info.plist"
f deny  Read "$WS/some-new-folder/.env.local"          # anywhere under the workspace
f deny  Read "$A/.env"; f deny Read "$S/.env"; f deny Read "$W/.env"   # Atreya origin: https, ssh (any case), worktree
f deny  Read "$M/.env"                                 # marketplace repo is still Atreya: secrets stay blocked
f allow Read "$O/.env"; f allow Read "$N/.env"; f allow Read "/tmp/x/.env.local"   # not NT: untouched
f allow Read "$B/routes/api.php"
bc allow "cp .env.example .env" "$O"; bc allow "cat .env" "$N"; bc allow "cat $O/.env" /tmp
bc deny  "cat .env" "$A"; bc deny "cat $A/.env" /tmp; bc deny "cat $B/.env"; bc deny "head config/*.json" "$B"
g allow "{\"pattern\":\"k\",\"path\":\"$O\",\"glob\":\".env\"}"; g deny "{\"pattern\":\"k\",\"path\":\"$A\",\"glob\":\".env\"}"
# NT_WORKSPACE override (no hardcoded home path)
mkdir -p "$FX/ws"; : > "$FX/ws/.env"
out=$(jq -nc --arg p "$FX/ws/.env" '{tool_name:"Read",tool_input:{file_path:$p},cwd:"/tmp"}' | NT_WORKSPACE="$FX/ws" python3 hooks/guard.py); n=$((n+1))
[ -n "$out" ] || { fail=1; echo "FAIL NT_WORKSPACE override should scope $FX/ws"; }

# ---------- product repos are read-only ----------
f deny  Write "$B/app/x.php"; f deny Edit "$B/routes/api.php"; f deny Write "$A/app/new.php"; f deny Edit "$S/app/x.php"; f deny Write "$W/app/x.php"
f allow Write "$O/app/x.php"; f allow Write "$N/notes.md"          # other repos / non-repos: untouched
f allow Write "$M/plugins/p/README.md"                              # Atreya marketplace repo is not a product repo
f allow Write "$D/x.md"; f allow Write "$P/plugins/nt-documentation/README.md"
bc deny "echo hi > $B/x.txt"; bc deny "echo hi > $A/x.txt" /tmp; bc allow "echo hi > $O/x.txt" /tmp; bc allow "echo hi > /tmp/x.txt" "$B"
bc deny "rm -rf $B/storage"; bc deny "rm app/x.php" "$A"; bc allow "rm app/x.php" "$O"; bc deny "sed -i '' s/a/b/ routes/api.php" "$B"
bc allow "cp $B/routes/api.php /tmp/api.php"; bc deny "cp /tmp/a.php $B/app/a.php"; bc deny "cd $B && graphify update ."
bc deny "git -C $B checkout main"; bc deny "git commit -m x" "$B"; bc deny "git commit -m x" "$A"; bc allow "git commit -m x" "$O"
bc allow "git commit -m x" "$M"; bc allow "mkdir -p $D/Ashoka-World-Backend/modules"; bc allow "git status" "$P"; bc allow "npm test" /tmp

# ---------- searches inside product repos ----------
g deny  "{\"pattern\":\"k\",\"path\":\"$B\"}"; g deny "{\"pattern\":\"k\",\"path\":\"$WS\"}"; g deny "{\"pattern\":\"k\",\"path\":\"$A\"}"
g allow "{\"pattern\":\"k\",\"path\":\"$B\",\"type\":\"php\"}"; g allow "{\"pattern\":\"k\",\"path\":\"$B\",\"glob\":\"*.{php,blade.php}\"}"
g deny  "{\"pattern\":\"k\",\"path\":\"$B\",\"glob\":\"*.json\"}"; g allow "{\"pattern\":\"k\",\"path\":\"$P\"}"; g allow "{\"pattern\":\"k\",\"path\":\"$O\"}"
bc allow "head -50 routes/api.php" "$B"; bc allow "grep -rn --include='*.php' Razorpay $B/app"; bc deny "grep -rn Razorpay $B"
bc deny "grep -rln foo ." "$B"; bc deny "grep -rln foo ." "$A"; bc allow "grep -rln foo ." "$O"
bc allow "grep -n 'foo.*bar' routes/api.php" "$B"; bc allow "grep -rilE --exclude='.env*' --include='*.php' x $R"
bc deny "rg secret $R"; bc allow "rg -t php secret $R"; bc deny "rg -t php --hidden secret $R"
bc deny "find $B -type f | xargs cat"; bc deny "find $B -name '*.json' -exec cat {} +"; bc allow "find $B -name '*.php' -exec grep -l Enach {} +"

# ---------- git history inside product repos ----------
bc allow "git -C $B log --oneline -5"; bc deny "git -C $B show HEAD"; bc allow "git -C $B show HEAD --stat"
bc allow "git -C $B show HEAD -- 'app/**/*.php'"; bc deny "git -C $B show HEAD -- config/"; bc deny "git -C $B show HEAD:.env"
bc allow "git -C $B show HEAD:routes/api.php"; bc deny "git -C $B log -p"; bc deny "git diff" "$B"; bc allow "git diff" "$O"

# ---------- secret content into docs ----------
t deny  Write "$(jq -nc --arg p "$D/a.md" '{file_path:$p,content:"rzp_live_ABCDEFGH1234"}')"
t allow Write "$(jq -nc --arg p "$D/a.md" '{file_path:$p,content:"Razorpay key is configured in services.razorpay.key"}')"

# ---------- fail closed ----------
n=$((n+2))
[ -n "$(echo 'not json' | python3 hooks/guard.py)" ] || { fail=1; echo "FAIL non-JSON input should deny"; }
[ -n "$(echo '{"tool_name":"Bash","tool_input":["x"]}' | python3 hooks/guard.py)" ] || { fail=1; echo "FAIL list tool_input should deny"; }

# ---------- zoho ----------
n=$((n+2))
[ "$(echo '{"tool_name":"mcp__x_Zoho__ZohoSprints_CreateItem"}' | python3 hooks/zoho_confirm.py | jq -r .hookSpecificOutput.permissionDecision)" = ask ] || { fail=1; echo "FAIL zoho write should ask"; }
[ -z "$(echo '{"tool_name":"mcp__x_Zoho__ZohoSprints_GetItems"}' | python3 hooks/zoho_confirm.py)" ] || { fail=1; echo "FAIL zoho read should pass"; }

[ "$fail" = 0 ] && echo "all $n guard tests passed"; exit $fail
