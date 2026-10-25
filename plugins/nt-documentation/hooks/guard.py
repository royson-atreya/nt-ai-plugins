#!/usr/bin/env python3
"""PreToolUse guard for nt-documentation.

Scope: the guard acts only on Nadi Tarangini paths: anything inside a git repo whose origin
is github.com/Atreya-Innovations/* (https or ssh), or under the workspace (~/atreya-ai,
override with NT_WORKSPACE). Everything else passes untouched.

1. Secret files (in scope): never Read/Grep/Bash a .env*, *.jks, *.keystore,
   firebase-*.json, google-services.json or GoogleService-Info.plist.
2. Product repos are read-only: deny Write/Edit/NotebookEdit and modifying Bash commands in
   Atreya-origin repos and under $NT_REPOS_DIR. Not product repos: $NT_DOCS_DIR, and any repo
   with .claude-plugin/marketplace.json at its root (a plugin marketplace such as nt-ai-plugins).
   Single exception, shared with nt-dev-coding and nt-qa-testing through hooks/devgate.py: a
   Write/Edit under $NT_REPOS_DIR for the active nt-dev-coding task the user approved, in a repo
   named in its plan, on a branch other than master/main/production. Bash writes stay blocked,
   and the approval markers (nt-docs/dev/ACTIVE, dev/<id>/APPROVED) can never be written here.
3. Searches inside product repos must be limited to code file types (several secret
   files are committed, so an unrestricted search could print them).
4. git patch output (show/diff/log -p) inside product repos needs a code-file pathspec.

Deterministic, standard library only, no subprocesses. Denies with a reason Claude can act on.
"""
import fnmatch
import functools
import json
import os
import re
import shlex
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import devgate  # noqa: E402  (identical copy of nt-dev-coding/hooks/devgate.py)
except Exception as _e:  # fail closed: without the shared gate nothing may pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": f"nt-documentation guard: cannot load devgate.py "
                                             f"({type(_e).__name__}: {_e}); refusing to be safe."}}))
    sys.exit(0)

WORKSPACE = os.path.realpath(os.path.expanduser(os.environ.get("NT_WORKSPACE", "~/atreya-ai")))
REPOS = os.path.realpath(os.path.expanduser(os.environ.get("NT_REPOS_DIR", os.path.join(WORKSPACE, "repos"))))
ORG_ORIGIN = re.compile(r"github\.com[:/]+Atreya-Innovations/", re.I)

SECRET_GLOBS = (".env", ".env.*", "*.jks", "*.keystore", "firebase-*.json",
                "google-services.json", "GoogleService-Info.plist")
CODE_EXTS = {"php", "dart", "js", "mjs", "ts", "jsx", "tsx", "vue", "html", "css", "scss",
             "md", "sql", "yaml", "yml", "xml", "kt", "kts", "java", "swift", "gradle", "txt", "py", "sh"}
CODE_TYPES = {"php", "dart", "js", "ts", "html", "css", "md", "sql", "yaml", "xml",
              "kotlin", "java", "swift", "py", "sh", "vue"}

SEARCH_HINT = ("Inside the product repos, restrict searches to code files: Grep with type='php'/'dart'/'js' "
               "or glob='*.php' / '*.{php,blade.php}'; grep -r with --include='*.php'; rg with -t php or -g '*.dart'.")
GIT_HINT = ("Inside the product repos, git show/diff/log -p must end with a pathspec of code files, e.g. "
            "`git show <sha> -- 'app/**/*.php'` or `git diff A B -- lib/foo.dart`, or use --stat/--name-only.")

GIT_WRITE = {"commit", "push", "pull", "checkout", "switch", "reset", "restore", "clean", "stash", "merge",
             "rebase", "cherry-pick", "revert", "apply", "am", "add", "rm", "mv", "tag", "init", "gc",
             "prune", "update-index", "update-ref", "filter-branch", "worktree", "submodule"}
FS_WRITE = {"rm", "rmdir", "mv", "cp", "touch", "mkdir", "chmod", "chown", "ln", "truncate", "tee",
            "install", "rsync", "dd", "unlink", "patch"}
INPLACE = {"sed": ("-i", "--in-place"), "perl": ("-i", "-pi"), "ruby": ("-i",)}
DOCS = os.path.realpath(os.path.expanduser(os.environ.get("NT_DOCS_DIR", os.path.join(WORKSPACE, "nt-docs"))))
# secrets also live inside ordinary source files; never let them reach the docs
SECRET_CONTENT = re.compile(
    r"AIza[0-9A-Za-z_\-]{35}"
    r"|rzp_(?:live|test)_[A-Za-z0-9]{8,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\"private_key\"\s*:"
    r"|(?:sk|pk)_live_[A-Za-z0-9]{10,}|gh[pousr]_[A-Za-z0-9]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|[?&](?:key|token|secret|api_key|apikey|access_token|signature)=[A-Za-z0-9_\-%.]{16,}"
    r"|Bearer\s+[A-Za-z0-9\-_.=]{24,}"
    r"|(?:password|passwd|secret|api_key|auth_key)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]",
    re.I,
)

PATCH_FREE_FLAGS = {"--stat", "--name-only", "--name-status", "--numstat", "--shortstat", "--no-patch",
                    "-s", "--summary", "--dirstat", "--raw"}


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": f"nt-documentation guard: {reason}",
    }}))
    sys.exit(0)


def is_secret(path):
    base = os.path.basename(str(path).rstrip("/").strip("'\""))
    return any(fnmatch.fnmatch(base, g) for g in SECRET_GLOBS)


def resolve(path, cwd):
    path = os.path.expanduser(os.path.expandvars(str(path)))
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return os.path.realpath(path)


def under(p, root):
    return p == root or p.startswith(root.rstrip(os.sep) + os.sep)


@functools.lru_cache(maxsize=512)
def git_top(d):
    """Nearest ancestor of directory d holding a .git dir or file (worktree), or None."""
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


@functools.lru_cache(maxsize=128)
def origin_url(top):
    """remote.origin.url read from the repo's config file (handles worktree .git files)."""
    gitdir = os.path.join(top, ".git")
    try:
        if os.path.isfile(gitdir):
            with open(gitdir) as f:
                ref = f.read().split("gitdir:", 1)[1].strip()
            gitdir = os.path.normpath(os.path.join(top, ref))
            common = os.path.join(gitdir, "commondir")
            if os.path.isfile(common):
                with open(common) as f:
                    gitdir = os.path.normpath(os.path.join(gitdir, f.read().strip()))
        with open(os.path.join(gitdir, "config"), errors="ignore") as f:
            cfg = f.read()
    except (OSError, IndexError):
        return None
    sec = re.search(r'^\s*\[remote\s+"origin"\]([^\[]*)', cfg, re.M)
    url = sec and re.search(r"^\s*url\s*=\s*(\S+)", sec.group(1), re.M)
    return url.group(1) if url else None


def atreya_repo(p):
    """Top of the Atreya-Innovations git repo containing resolved path p, or None."""
    top = git_top(p if os.path.isdir(p) else os.path.dirname(p))
    return top if top and ORG_ORIGIN.search(origin_url(top) or "") else None


def in_scope(path, cwd):
    """The guard only acts on NT paths: the workspace, or any Atreya-origin repo."""
    p = resolve(path, cwd)
    return under(p, WORKSPACE) or atreya_repo(p) is not None


def in_repos(path, cwd):
    """True if path is inside a read-only product repo."""
    p = resolve(path, cwd)
    if under(p, DOCS):
        return False
    top = atreya_repo(p) or (git_top(p if os.path.isdir(p) else os.path.dirname(p)) if under(p, REPOS) else None)
    if top and os.path.isfile(os.path.join(top, ".claude-plugin", "marketplace.json")):
        return False  # a plugin marketplace repo (e.g. nt-ai-plugins) is not a product repo
    return under(p, REPOS) or top is not None


def contains_repos(path, cwd):
    """True if the path is inside a product repo or is an ancestor of $NT_REPOS_DIR (a search root covering them)."""
    p = resolve(path, cwd)
    return in_repos(p, cwd) or REPOS.startswith(p.rstrip(os.sep) + os.sep)


def code_glob(glob):
    """True if every alternative in a glob targets an allowed code extension."""
    if not glob or glob.startswith("!"):
        return False
    m = re.search(r"\.\{([^}]*)\}$", glob)
    exts = m.group(1).split(",") if m else [glob.rsplit(".", 1)[-1] if "." in glob else ""]
    return all(e.strip().split(".")[-1] in CODE_EXTS for e in exts)


# ---------- file tools ----------

def check_file_tool(tool, inp, cwd):
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    if not path:
        return
    if is_secret(path) and in_scope(path, cwd):
        deny(f"'{os.path.basename(path)}' is a secret file in a Nadi Tarangini repo and must never be read or written.")
    if tool != "Read" and devgate.is_marker(path, cwd):
        deny(devgate.MARKER_MSG)
    if tool != "Read" and in_repos(path, cwd):
        ok, why = devgate.check_write(path, cwd)
        if not ok:
            deny(f"{tool} of {path} is not allowed; the Nadi Tarangini product repos are read-only"
                 f"{' (' + why + ')' if why else ''}. Write output to {DOCS}.")
    if tool != "Read" and path:
        p = resolve(path, cwd)
        if p.startswith(DOCS + os.sep):
            texts = [inp.get("content", ""), inp.get("new_string", ""), inp.get("new_source", "")]
            texts += [e.get("new_string", "") for e in inp.get("edits", []) or []]
            m = SECRET_CONTENT.search("\n".join(t for t in texts if t))
            if m:
                deny("the text being written to nt-docs contains something that looks like a secret "
                     f"(matched '{m.group(0)[:12]}…'). Describe it instead, e.g. 'Google Chat webhook URL (key redacted)'.")


def check_grep(inp, cwd):
    path = inp.get("path") or cwd
    glob = inp.get("glob") or ""
    if (is_secret(path) or (glob and is_secret(glob.lstrip("*/")))) and in_scope(path, cwd):
        deny("searching secret files in a Nadi Tarangini repo is not allowed.")
    if not contains_repos(path, cwd):
        return
    if os.path.isfile(resolve(path, cwd)):
        return  # single non-secret file
    if inp.get("type") in CODE_TYPES or code_glob(glob):
        return
    deny("unrestricted search inside the product repos. " + SEARCH_HINT)


# ---------- bash ----------

SPLIT = re.compile(r"\s*(?:&&|\|\||;|\||\n)\s*")


def tokens(segment):
    try:
        return shlex.split(segment, comments=True)
    except ValueError:
        return segment.split()


def strip_excludes(toks):
    """Drop tokens that exclude files from a search (they legitimately name secret patterns)."""
    out, skip = [], False
    for t in toks:
        if skip:
            skip = False
            continue
        if t.startswith(("--exclude", "--exclude-dir")) or t.startswith(("--glob=!", "-g!", ":!", ":(exclude")) \
                or t.startswith("!"):
            continue
        if t in ("-g", "--glob", "--exclude", "--exclude-dir"):
            skip = True  # value follows; checked separately for -g
            continue
        out.append(t)
    return out


def path_tokens(toks):
    """Tokens that look like paths (also the part after '=' in --opt=path), for scope checks."""
    for t in toks:
        for part in (t, t.split("=", 1)[-1]):
            if part and (part[0] in "/~.$" or "/" in part) and not part.startswith(("-", "http://", "https://")):
                yield part


READERS = {"cat", "head", "tail", "less", "more", "strings", "xxd", "od", "hexdump", "base64", "bat",
           "nl", "awk", "sed", "cut", "sort", "uniq", "grep", "egrep", "fgrep", "jq", "python", "python3"}
PATTERN_FIRST = {"grep", "egrep", "fgrep", "awk", "sed", "jq"}


def check_bash(cmd, cwd):
    if devgate.bash_writes_marker(cmd, cwd):
        deny(devgate.MARKER_MSG)
    segments = [s for s in SPLIT.split(cmd) if s.strip()]
    # a pipeline is judged as a whole: `find <repo> ... | xargs cat` must count as touching the repos
    whole = REPOS in cmd or any(in_repos(p, cwd) for s in segments for p in path_tokens(tokens(s)))
    for segment in segments:
        toks = tokens(segment)
        if not toks:
            continue
        # follow `cd` so later segments are evaluated in the right directory
        if toks[0] == "cd" and len(toks) > 1:
            cwd = resolve(toks[1], cwd)
            continue
        # env assignments / sudo prefixes
        while toks and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]) or toks[0] in ("sudo", "command", "nohup", "time")):
            toks = toks[1:]
        if not toks:
            continue

        # 1. secret names (outside exclusion flags) that resolve to a Nadi Tarangini path
        for t in strip_excludes(toks):
            for part in re.split(r"[\s=:]", t):
                if part and is_secret(part) and in_scope(part, cwd):
                    deny(f"command references secret file '{os.path.basename(part)}' in a Nadi Tarangini repo.")
        for redir in re.findall(r"<\s*(\S+)", segment):
            if is_secret(redir) and in_scope(redir, cwd):
                deny(f"command reads secret file '{redir}' in a Nadi Tarangini repo.")

        if not (whole or in_repos(cwd, cwd)):
            continue
        prog = os.path.basename(toks[0])

        # shell globs expand to file names the name check never sees (config/*.json -> firebase keys)
        if prog in READERS:
            positional = [a for a in toks[1:] if not a.startswith("-")]
            if prog in PATTERN_FIRST and positional and not any(a in ("-e", "-f", "--file") for a in toks):
                positional = positional[1:]
            for a in positional:
                if re.search(r"[*?\[]", a) and not code_glob(os.path.basename(a)):
                    deny(f"`{prog} {a}` could expand to secret files; name code files explicitly (e.g. *.php).")

        # 2. writes into the repos
        for target in re.findall(r"(?<![<0-9&])>{1,2}\s*([^\s;&|]+)", segment):
            if target != "/dev/null" and not target.startswith("&") and in_repos(target, cwd):
                deny(f"redirect writes into a product repo ({target}). Write output to {DOCS}.")
        if prog in FS_WRITE:
            args = [a for a in toks[1:] if not a.startswith("-")]
            targets = args[-1:] if prog in ("cp", "install", "rsync", "ln") else args
            if any(in_repos(a, cwd) for a in targets):
                deny(f"`{prog}` would modify the product repos; they are read-only.")
        if prog in INPLACE and any(a.startswith(INPLACE[prog]) for a in toks[1:]):
            deny(f"in-place `{prog}` edit inside the product repos is not allowed.")
        if prog in ("graphify",):
            deny("graphify writes into the repo; ask the user to run `graphify update .` themselves.")

        if prog == "git":
            check_git(toks)

        # 3. recursive searches must be limited to code files
        if prog in ("grep", "egrep", "fgrep"):
            recursive = any(a in ("-r", "-R", "--recursive", "--dereference-recursive")
                            or (re.match(r"^-[A-Za-z]+$", a) and ("r" in a or "R" in a)) for a in toks[1:])
            includes = [a.split("=", 1)[1] if "=" in a else "" for a in toks if a.startswith("--include")]
            if recursive and not (includes and all(code_glob(i.strip("'\"")) for i in includes)):
                deny("recursive grep without --include of code files. " + SEARCH_HINT)
        if prog in ("rg", "ag", "ack"):
            types = [toks[i + 1] for i, a in enumerate(toks[:-1]) if a in ("-t", "--type")] + \
                    [a.split("=", 1)[1] for a in toks if a.startswith("--type=")]
            globs = [toks[i + 1] for i, a in enumerate(toks[:-1]) if a in ("-g", "--glob")] + \
                    [a.split("=", 1)[1] for a in toks if a.startswith("--glob=")]
            pos_globs = [g for g in globs if not g.startswith("!")]
            ok = (types and all(t in CODE_TYPES for t in types)) or (pos_globs and all(code_glob(g) for g in pos_globs))
            if not ok or any(a in ("-u", "-uu", "-uuu", "--hidden", "--no-ignore") for a in toks):
                deny(f"`{prog}` inside the product repos must be limited to code types. " + SEARCH_HINT)
        if prog == "find" and any(a in ("-exec", "-execdir", "-ok") for a in toks) or \
                ("xargs" in segment and prog == "find"):
            names = [toks[i + 1] for i, a in enumerate(toks[:-1]) if a in ("-name", "-iname")]
            if not (names and all(code_glob(n) for n in names)):
                deny("find -exec/xargs inside the product repos must filter with -name '*.php' (or another code type).")
        if prog == "xargs" and any(a in ("cat", "grep", "head", "tail", "less", "more") for a in toks):
            deny("xargs over repo files can print secret files; use Grep/rg with a code type instead.")


def check_git(toks):
    args = toks[1:]
    # skip global options like -C <dir>, -c k=v, --no-pager
    while args and args[0].startswith("-"):
        args = args[2:] if args[0] in ("-C", "-c") else args[1:]
    if not args:
        return
    sub, rest = args[0], args[1:]
    if sub in GIT_WRITE or (sub == "branch" and any(a in ("-d", "-D", "-m", "-M", "--delete") for a in rest)):
        deny(f"`git {sub}` would modify a product repo; only read-only git is allowed.")
    if sub in ("archive", "bundle", "fast-export", "format-patch"):
        deny(f"`git {sub}` can export secret files; not allowed in the product repos.")
    if sub == "cat-file" or sub == "grep":
        if "--" not in rest or not pathspec_ok(rest[rest.index("--") + 1:]):
            deny(f"`git {sub}` needs a code-file pathspec after `--`. " + GIT_HINT)
        return
    if sub not in ("show", "diff", "log", "whatchanged", "stash"):
        return
    patchy = sub in ("show", "diff") or any(a in ("-p", "-u", "--patch", "-L") or a.startswith("-L") for a in rest)
    if not patchy or any(a in PATCH_FREE_FLAGS for a in rest):
        return
    # git show <rev>:<path>
    for a in rest:
        if ":" in a and not a.startswith("-") and not a.startswith(":"):
            path = a.split(":", 1)[1]
            if path and not pathspec_ok([path]):
                deny(f"`git {sub} {a}` targets a non-code file. " + GIT_HINT)
            if path:
                return
    if "--" not in rest or not pathspec_ok(rest[rest.index("--") + 1:]):
        deny(f"`git {sub}` with patch output needs a code-file pathspec. " + GIT_HINT)


def pathspec_ok(specs):
    positive = [s for s in specs if not s.startswith((":!", ":^", ":(exclude"))]
    return bool(positive) and all(not is_secret(s) and code_glob(s.split("/")[-1]) for s in positive)


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
        check_file_tool(tool, inp, cwd)
    elif tool == "Grep":
        check_grep(inp, cwd)
    elif tool == "Bash":
        check_bash(inp.get("command", ""), cwd)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # fail closed: a crashing guard must not let the call through
        deny(f"guard error ({type(e).__name__}: {e}); refusing to be safe. Rephrase the call or report this hook bug.")
