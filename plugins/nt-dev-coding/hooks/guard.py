#!/usr/bin/env python3
"""PreToolUse guard for nt-dev-coding.

Scope: the Nadi Tarangini workspace (~/atreya-ai, override NT_WORKSPACE). Elsewhere calls pass,
except that Write/Edit into $NT_REPOS_DIR is always judged.

1. Repo writes: Write/Edit/MultiEdit/NotebookEdit inside $NT_REPOS_DIR only through devgate
   (active task approved by the user, repo in the approved plan, branch not master/main/production).
   Write may only create NEW files; existing files are changed with Edit (no whole-file rewrites).
   Bash never writes into the repos (redirects, rm/mv/cp/..., sed -i).
2. Approval markers (nt-docs/dev/ACTIVE, dev/<id>/APPROVED) are written only by the approve hook.
3. git: commit/push/pull/checkout/switch/branch/merge/rebase/reset/stash/tag and other writing
   subcommands are blocked in the workspace; read-only git (status, diff, log, show, ...) passes.
4. php artisan only route:list, list, about, --version (the backend .env points at PRODUCTION);
   php only -l / --version; phpunit, pest, sail, php -r/-f and other scripts are blocked.
5. composer/npm/yarn/pnpm/npx/pod/flutter/dart: no install, upgrade, publish or scripts; allowed
   checks are `flutter analyze --no-pub` and `dart format --output=none`.
6. Secret files (.env*, *.jks, *.keystore, firebase-*.json, google-services.json,
   GoogleService-Info.plist) are never read via Read, Grep, Glob or Bash.

Standard library only, no subprocesses, fails closed.
"""
import fnmatch
import json
import os
import re
import shlex
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import devgate  # noqa: E402
except Exception as _e:  # fail closed: without the gate nothing may pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": f"nt-dev-coding guard: cannot load devgate.py "
                                             f"({type(_e).__name__}: {_e}); refusing to be safe."}}))
    sys.exit(0)

WORKSPACE, REPOS, DOCS, DEV = devgate.WORKSPACE, devgate.REPOS, devgate.DOCS, devgate.DEV

SECRET_GLOBS = (".env", ".env.*", "*.jks", "*.keystore", "firebase-*.json",
                "google-services.json", "GoogleService-Info.plist")
SECRET_PROBES = (".env", ".env.production", "release.jks", "upload.keystore", "firebase-adminsdk.json",
                 "google-services.json", "GoogleService-Info.plist")
SECRET_PREFIXES = (".env", "*.env", "google-services", "GoogleService-Info")
SECRET_SUFFIXES = (".jks", ".keystore")

# git is allowlisted: only these read-only subcommands run in the workspace (plus listing forms below)
GIT_READ = {"status", "diff", "log", "show", "blame", "rev-parse", "ls-files", "ls-tree", "cat-file", "grep",
            "shortlog", "describe", "rev-list", "merge-base", "name-rev", "for-each-ref", "show-ref",
            "whatchanged", "range-diff", "version", "help", "annotate", "count-objects", "diff-tree",
            "diff-files", "diff-index", "check-ignore", "check-attr", "cherry", "show-branch", "--version", "--help"}
GIT_LISTING = {  # subcommand -> predicate on the remaining args (True = read-only use)
    "branch": lambda r: all(a in {"--show-current", "-a", "--all", "-r", "--remotes", "-v", "-vv", "--list", "-l",
                                  "--contains", "--merged", "--no-merged", "--no-color", "--color"}
                            or a.startswith("--format") for a in r),
    "tag": lambda r: all(a in ("-l", "--list", "-n") for a in r),
    "stash": lambda r: r[:1] in (["list"], ["show"]),
    "remote": lambda r: not r or r[0] in ("-v", "--verbose", "show", "get-url"),
    "config": lambda r: bool(set(r) & {"--get", "--get-all", "--get-regexp", "--list", "-l", "get", "list"})
                        and not set(r) & {"--add", "--unset", "--unset-all", "--replace-all", "--rename-section",
                                          "--remove-section", "-e", "--edit", "set", "unset"},
    "symbolic-ref": lambda r: len([a for a in r if not a.startswith("-")]) <= 1 and "-d" not in r and "--delete" not in r,
    "reflog": lambda r: not r or r[0] == "show" or r[0].startswith("-"),
    "worktree": lambda r: r[:1] == ["list"],
    "submodule": lambda r: r[:1] == ["status"],
}
FS_WRITE = {"rm", "rmdir", "mv", "cp", "touch", "mkdir", "chmod", "chown", "ln", "truncate", "tee",
            "install", "rsync", "dd", "unlink", "patch"}
INPLACE = {"sed", "gsed", "perl", "ruby"}
SAFE_EXEC = {"grep", "egrep", "fgrep", "wc", "ls", "stat", "file"}  # find -exec / xargs targets
ARCHIVERS = {"tar", "unzip", "gunzip", "gzip", "bzip2", "bunzip2", "xz", "unxz", "zip", "7z", "ar", "cpio", "jar"}
FETCHERS = {"curl", "wget", "aria2c", "http", "xh"}
REDIRECT = re.compile(r"(?<![<>=-])\d*>{1,2}\|?(?!&)\s*([^\s;&|<>]+)")
READERS = {"cat", "head", "tail", "less", "more", "strings", "xxd", "od", "hexdump", "base64", "bat", "nl",
           "awk", "sed", "cut", "sort", "uniq", "grep", "egrep", "fgrep", "jq", "rg", "source", "."}
INTERPRETERS = {"python", "python3", "node", "ruby", "perl", "deno", "bun", "osascript"}
SHELLS = {"bash", "sh", "zsh", "dash"}
PREFIXES = {"sudo", "command", "nohup", "time", "env", "exec", "builtin"}

ARTISAN_OK = {"route:list", "list", "about", "--version", "-V"}
COMPOSER_OK = {"show", "info", "validate", "diagnose", "licenses", "outdated", "depends", "why", "why-not",
               "prohibits", "check-platform-reqs", "about", "list", "help", "--version", "-V", "audit"}
NPM_OK = {"ls", "list", "ll", "la", "view", "info", "show", "outdated", "explain", "why", "help",
          "--version", "-v", "version"}
FLUTTER_OK = {"analyze", "--version", "doctor", "devices"}
DART_OK = {"format", "analyze", "--version", "info"}

SPLIT = re.compile(r"\s*(?:&&|\|\||;|(?<!>)\||\n)\s*")


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": f"nt-dev-coding guard: {reason}",
    }}))
    sys.exit(0)


# ---------- helpers ----------

def resolve(path, cwd):
    return devgate._resolve(path, cwd)


def under(p, root):
    return devgate._under(p, root)


def in_ws(path, cwd):
    return under(resolve(path, cwd), WORKSPACE)


def in_repos(path, cwd):
    return under(resolve(path, cwd), REPOS)


def is_secret(name):
    base = os.path.basename(str(name).rstrip("/").strip("'\""))
    return any(fnmatch.fnmatch(base, g) for g in SECRET_GLOBS)


def secret_named(name):
    """Names or patterns that explicitly target a secret file (.env*, *.keystore, google-services*...)."""
    base = os.path.basename(str(name).rstrip("/").strip("'\"")).rstrip("*?")
    return (is_secret(base) or base == "firebase-" or base.startswith(SECRET_PREFIXES)
            or base.endswith(SECRET_SUFFIXES))


def glob_hits_secret(pattern):
    base = os.path.basename(str(pattern).strip("'\""))
    return bool(re.search(r"[*?\[]", base)) and any(fnmatch.fnmatch(p, base) for p in SECRET_PROBES)


QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")


def unquoted(segment):
    """segment with quoted strings blanked, so `grep '$q->where('` is not mistaken for a redirect."""
    return QUOTED.sub("''", segment)


def tokens(segment):
    try:
        return shlex.split(segment, comments=True)
    except ValueError:
        return segment.split()


def strip_excludes(toks):
    out, skip = [], False
    for t in toks:
        if skip:
            skip = False
            continue
        if t.startswith(("--exclude=", "--exclude-dir=", "--glob=!", "-g!", ":!", ":(exclude", "!")):
            continue
        if t in ("--exclude", "--exclude-dir"):
            skip = True
            continue
        out.append(t)
    return out


def subcommand(args):
    """First argument that is not an option (skips -C <dir> / -c <k=v> style pairs)."""
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-C", "-c", "--git-dir", "--work-tree", "-d", "--working-dir", "--directory", "-p", "--prefix"):
            i += 2
            continue
        if a.startswith("-") and a not in ("--version", "-V", "-v"):
            i += 1
            continue
        return a, args[i + 1:]
    return None, []


# ---------- file tools ----------

def check_file(tool, inp, cwd):
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    if not path:
        return
    if is_secret(path) and in_ws(path, cwd):
        deny(f"'{os.path.basename(path)}' is a secret file and must never be read or written.")
    if tool == "Read":
        return
    if devgate.is_marker(path, cwd):
        deny(devgate.MARKER_MSG)
    if not in_repos(path, cwd):
        return
    ok, reason = devgate.check_write(path, cwd)
    if not ok:
        deny(f"{tool} of {path} is not allowed: {reason or 'the product repos are read-only.'}")
    if tool == "Write" and os.path.exists(resolve(path, cwd)):
        deny(f"Write would replace the whole of {path}. Change existing files only with Edit (small, "
             "surgical old_string/new_string edits); Write is for new files only.")


def check_grep(inp, cwd):
    path = inp.get("path") or cwd
    glob = inp.get("glob") or ""
    if not in_ws(path, cwd):
        return
    if is_secret(path) or (glob and (secret_named(glob) or glob_hits_secret(glob))):
        deny("searching secret files (.env, keystores, Firebase/Google config) is not allowed.")
    if in_repos(path, cwd) and os.path.isdir(resolve(path, cwd)) and not (inp.get("type") or glob):
        deny("unrestricted search inside the product repos can print secret files; give type='php'/'dart' "
             "or glob='*.php' / '*.{php,blade.php}'.")


def check_glob(inp, cwd):
    pattern = inp.get("pattern") or ""
    if in_ws(inp.get("path") or cwd, cwd) and pattern and secret_named(pattern):
        deny("globbing for secret files (.env, keystores, Firebase/Google config) is not allowed.")


# ---------- bash ----------

def check_git(toks, cwd, envs=()):
    args = toks[1:]
    gdir, i = cwd, 0
    while i < len(args) and args[i].startswith("-"):  # global options before the subcommand
        a = args[i]
        if a == "-C" and i + 1 < len(args):
            gdir = resolve(args[i + 1], gdir)
            i += 2
            continue
        if a == "-c" or a.startswith(("--config-env", "--exec-path", "--git-dir", "--work-tree", "--namespace")):
            if in_ws(gdir, cwd) or in_ws(cwd, cwd):
                deny(f"`git {a}` is not allowed in the Nadi Tarangini workspace (inline config can run commands "
                     "or redirect git). Use plain read-only git.")
        i += 2 if a in ("-c", "--git-dir", "--work-tree", "--namespace", "--config-env") else 1
    if not in_ws(gdir, cwd):
        return
    if any(e.startswith("GIT_") for e in envs):
        deny("GIT_* environment overrides are not allowed with git in the Nadi Tarangini workspace.")
    sub, rest = (args[i], args[i + 1:]) if i < len(args) else (None, [])
    if sub is None:
        return
    if any(a == "--output" or a.startswith(("--output=", "--ext-diff", "--textconv")) for a in rest) or \
            (sub in ("diff", "log", "show") and "-o" in rest):
        deny(f"`git {sub}` with --output/--ext-diff/--textconv can write files or run tools; not allowed here.")
    if sub in GIT_READ or (sub in GIT_LISTING and GIT_LISTING[sub](rest)):
        return
    hint = ""
    if sub in ("checkout", "switch", "branch", "symbolic-ref"):
        hint = " To start work, the user runs e.g. `git -C <repo> checkout -b feature/<id>` themselves."
    deny(f"`git {sub}` is blocked: the user does all git actions (commit, push, pull, branch, config, ...). "
         f"Only read-only git (status, diff, log, show, blame, rev-parse, listing branches) is allowed.{hint}")


def check_php(prog, toks):
    args = toks[1:]
    if prog in ("phpunit", "pest", "sail", "paratest", "dusk"):
        deny(f"`{prog}` is blocked: tests and containers may reach the backend's PRODUCTION database (.env). "
             "Allowed: php -l <file>, php artisan route:list|list|about|--version.")
    if prog == "artisan":
        args = ["artisan"] + args
    if not args or args[0] in ("-v", "--version", "-i", "-m"):
        return
    if args[0] == "-l" or args[0] == "--syntax-check":
        if all(not a.startswith("-") or a in ("-l", "--syntax-check") for a in args):
            return
    if os.path.basename(args[0]) == "artisan":
        sub = next((a for a in args[1:] if not a.startswith("-") or a in ("--version", "-V")), None)
        if sub is None or sub in ARTISAN_OK:
            return
        deny(f"`php artisan {sub or ''}` is blocked: the backend .env points at the PRODUCTION database. "
             "Never run migrate, db:*, tinker, seed, queue, schedule, test, cache or any other artisan "
             "command. Allowed: route:list, list, about, --version.")
    deny("only `php -l <files>` and `php -v` may run in the Nadi Tarangini workspace (scripts could reach "
         "the PRODUCTION database through the backend .env).")


def check_packages(prog, toks):
    args = toks[1:]
    sub, rest = subcommand(args)
    if prog == "npx" or prog in ("pnpx", "bunx"):
        deny(f"`{prog}` downloads and runs packages; not allowed. Ask the user to install tools themselves.")
    if prog == "composer":
        if sub is None or sub in COMPOSER_OK:
            return
        deny(f"`composer {sub}` is blocked (no install, update, require, remove, scripts or publishing). "
             "New dependencies need the user's go-ahead; the user installs them.")
    if prog in ("npm", "yarn", "pnpm"):
        if sub is None or sub in NPM_OK:
            return
        deny(f"`{prog} {sub}` is blocked (no install, update, scripts/build or publishing). "
             "The user installs dependencies themselves.")
    if prog == "pod":
        if sub is None or sub in ("--version", "list", "search", "env"):
            return
        deny(f"`pod {sub}` is blocked (no install, update or publishing).")
    if prog == "flutter":
        if sub is None or sub not in FLUTTER_OK:
            deny(f"`flutter {sub or ''}` is blocked (no pub get/add/upgrade, upgrade, build, run, test, clean "
                 "or publishing). Allowed check: `flutter analyze --no-pub <files>`.")
        if sub == "analyze" and "--no-pub" not in rest:
            deny("use `flutter analyze --no-pub <files>`; without --no-pub flutter may run `pub get` and "
                 "change pubspec.lock / .dart_tool.")
        return
    if prog == "dart":
        if sub is None or sub not in DART_OK:
            deny(f"`dart {sub or ''}` is blocked (no pub, fix, run, compile or publishing). Allowed checks: "
                 "`dart format --output=none --set-exit-if-changed <files>`, `dart analyze <files>`.")
        if sub == "format":
            joined = " ".join(rest)
            if not re.search(r"(?:--output[= ]none|-o\s*none)\b", joined):
                deny("`dart format` rewrites files; use the check-only form "
                     "`dart format --output=none --set-exit-if-changed <files>`.")
        return


def check_bash(cmd, cwd, depth=0):
    if depth > 3:
        deny("nested shell commands are too deep to check; run the commands directly.")
    if depth == 0 and devgate.bash_writes_marker(cmd, cwd):
        deny(devgate.MARKER_MSG)
    # a pipeline that touches the repos anywhere is judged as a whole (`find <repo> ... | xargs rm`)
    whole, c = REPOS in cmd, cwd
    for s in (s for s in SPLIT.split(cmd) if s.strip()):
        t = tokens(s)
        if t and t[0] == "cd" and len(t) > 1:
            c = resolve(t[1], c)
        whole = whole or in_repos(c, c) or any(in_repos(x, c) for x in t[1:] if "/" in x or x.startswith(("~", ".")))
    if whole and devgate._INLINE_CODE.search(cmd):
        deny("inline interpreter code (python -c, node -e, heredocs) is not allowed against the product repos: it "
             "could write files. Use Edit for changes, Read/Grep for reading, or the plugin scripts.")
    for segment in (s for s in SPLIT.split(cmd) if s.strip()):
        toks = tokens(segment)
        if not toks:
            continue
        if toks[0] == "cd" and len(toks) > 1:
            cwd = resolve(toks[1], cwd)
            continue
        envs = []
        while toks and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]) or toks[0] in PREFIXES):
            if "=" in toks[0]:
                envs.append(toks[0])
            toks = toks[1:]
        if not toks:
            continue
        prog = os.path.basename(toks[0])

        # nested shells: check the inner command too
        if prog in SHELLS and "-c" in toks[1:-1]:
            check_bash(toks[toks.index("-c") + 1], cwd, depth + 1)
            continue
        if prog == "eval":
            check_bash(" ".join(toks[1:]), cwd, depth + 1)
            continue

        path_toks = [t for t in toks[1:] if not t.startswith("-") and ("/" in t or t.startswith(("~", ".")))]
        ws = in_ws(cwd, cwd) or any(in_ws(t, cwd) for t in path_toks)

        redirects = REDIRECT.findall(unquoted(segment))
        repo_ctx = whole or in_repos(cwd, cwd)
        no_bash_write = "Use Edit (or Write for a new file) under an approved task."

        # writes into the product repos (always, from any cwd)
        for target in redirects:
            if target != "/dev/null" and in_repos(target, cwd):
                deny(f"redirect writes into a product repo ({target}). {no_bash_write}")
        if prog in FS_WRITE:
            args = [a for a in toks[1:] if not a.startswith("-")]
            targets = args if prog in ("mv", "rm", "rmdir", "touch", "mkdir", "chmod", "chown", "truncate",
                                       "unlink", "tee", "patch") else args[-1:]
            for i, a in enumerate(toks[1:-1], 1):
                if a in ("-t", "--target-directory"):
                    targets.append(toks[i + 1])
            targets += [a.split("=", 1)[1] for a in toks[1:] if a.startswith(("--target-directory=", "of="))]
            if any(in_repos(a, cwd) for a in targets):
                deny(f"`{prog}` would modify the product repos from Bash. {no_bash_write}")
        if prog in INPLACE and repo_ctx and any(re.match(r"^-[A-Za-z0-9]*i", a) or a.startswith("--in-place")
                                                for a in toks[1:]):
            deny(f"in-place `{prog}` edit inside the product repos is not allowed. {no_bash_write}")
        if prog == "find" and repo_ctx:
            if any(a in ("-delete", "-fprint", "-fprint0", "-fprintf", "-fls") for a in toks):
                deny(f"`find` with -delete/-fprint would modify the product repos. {no_bash_write}")
            for i, a in enumerate(toks[:-1]):
                if a in ("-exec", "-execdir", "-ok", "-okdir") and os.path.basename(toks[i + 1]) not in SAFE_EXEC:
                    deny(f"`find {a} {toks[i + 1]}` in the product repos is not allowed (only grep, wc, ls, stat, "
                         "file).")
        if prog == "xargs" and repo_ctx:
            rest, i = toks[1:], 0
            while i < len(rest) and rest[i].startswith("-"):
                i += 2 if rest[i] in ("-n", "-I", "-P", "-L", "-d", "-s", "-E", "-a", "--max-args", "--delimiter") else 1
            if i >= len(rest) or os.path.basename(rest[i]) not in SAFE_EXEC:
                deny(f"`xargs {rest[i] if i < len(rest) else ''}` over repo files is not allowed (only grep, wc, ls, "
                     "stat, file).")
        if prog in FETCHERS and repo_ctx:
            if prog == "wget" or any(a in ("-o", "-O", "--output", "--remote-name", "--output-dir", "-D",
                                          "--dump-header", "-c", "--cookie-jar", "--trace", "--trace-ascii")
                                     or a.startswith(("--output", "-o", "-O"))
                                     or (re.fullmatch(r"-[A-Za-z]+", a) and set(a[1:]) & set("oODc")) for a in toks[1:]):
                deny(f"`{prog}` writing files is not allowed in the product repos.")
        listing = (prog == "tar" and len(toks) > 1 and (toks[1] == "--list" or re.fullmatch(r"-?t[vzjJf]*", toks[1]))) \
            or (prog == "unzip" and "-l" in toks)
        if prog in ARCHIVERS and repo_ctx and not listing:
            deny(f"`{prog}` would write or extract files in the product repos.")

        if prog == "git":
            check_git(toks, cwd, envs)
        if not ws:
            continue

        # secret files
        for t in strip_excludes(toks[1:]):
            for part in re.split(r"[=:]", t):
                if part and secret_named(part):
                    deny(f"command references secret file '{os.path.basename(part)}'; never read secrets.")
            if prog in READERS and glob_hits_secret(t):
                deny(f"`{prog} {t}` could expand to a secret file; name the files explicitly.")
        for redir in re.findall(r"<\s*([^\s<>|;&]+)", unquoted(segment)):
            if secret_named(redir):
                deny(f"command reads secret file '{redir}'.")

        # production database, package managers
        if re.match(r"^php[0-9.]*$", prog) or prog in ("artisan", "phpunit", "pest", "sail", "paratest", "dusk"):
            check_php(prog, toks)
        if prog in ("composer", "npm", "yarn", "pnpm", "npx", "pnpx", "bunx", "pod", "flutter", "dart"):
            check_packages(prog, toks)

        # unrestricted recursive search inside the repos (committed secrets could print)
        if in_repos(cwd, cwd) or any(in_repos(t, cwd) for t in path_toks):
            if prog in ("grep", "egrep", "fgrep") and any(
                    a in ("-r", "-R", "--recursive") or re.match(r"^-[A-Za-z]*[rR][A-Za-z]*$", a) for a in toks):
                if not any(a.startswith("--include") for a in toks):
                    deny("recursive grep in the product repos needs --include='*.php' (or another code type).")
            if prog in ("rg", "ag", "ack") and not any(a in ("-t", "--type", "-g", "--glob") or
                                                       a.startswith(("--type=", "--glob=")) for a in toks):
                deny(f"`{prog}` in the product repos needs -t <code type> or -g '*.php'.")


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        deny("hook input was not valid JSON; refusing to be safe.")
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    if not isinstance(inp, dict):
        deny("unexpected tool_input shape; refusing to be safe.")
    cwd = data.get("cwd") or os.getcwd()
    if tool in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit"):
        check_file(tool, inp, cwd)
    elif tool == "Grep":
        check_grep(inp, cwd)
    elif tool == "Glob":
        check_glob(inp, cwd)
    elif tool == "Bash":
        check_bash(inp.get("command", ""), cwd)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # fail closed
        deny(f"guard error ({type(e).__name__}: {e}); refusing to be safe. Rephrase the call or report this hook bug.")
