#!/usr/bin/env python3
"""PreToolUse guard for nt-qa-testing.

1. Production hosts are blocked in every session: any *.naditarangini.com or *.ashoka.world
   host that is not a staging host (naditarangini.com, www., dashboard., api.ashoka.world, ...).
   Checked in Playwright tool inputs, WebFetch, and network commands in Bash.
2. Inside the workspace (~/atreya-ai, override NT_WORKSPACE) Playwright may open only the
   staging hosts (and about:blank); file:/javascript:/data: URLs and browser_run_code_unsafe
   are refused.
3. Inside the workspace: no git commit/push/pull; no reading secret files (.env*, *.jks,
   *.keystore, firebase-*.json, google-services.json, GoogleService-Info.plist) via Read,
   Grep, Glob or Bash; nothing writes into the product repos ($NT_REPOS_DIR). Single exception,
   shared with nt-dev-coding and nt-documentation through hooks/devgate.py: a Write/Edit for the
   active nt-dev-coding task the user approved, in a repo named in its plan, on a branch other than
   master/main/production. Bash writes stay blocked; the approval markers (nt-docs/dev/ACTIVE,
   dev/<id>/APPROVED) can never be written here.

Reading the product repos is not blocked here (nt-documentation needs it); the skills forbid
using code for test design. Standard library only, no subprocesses, fails closed.
"""
import fnmatch
import json
import os
import re
import shlex
import sys
from urllib.parse import unquote

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import devgate  # noqa: E402  (identical copy of nt-dev-coding/hooks/devgate.py)
except Exception as _e:  # fail closed: without the shared gate nothing may pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": f"nt-qa-testing guard: cannot load devgate.py "
                                             f"({type(_e).__name__}: {_e}); refusing to be safe."}}))
    sys.exit(0)

WORKSPACE = os.path.realpath(os.path.expanduser(os.environ.get("NT_WORKSPACE", "~/atreya-ai")))
REPOS = os.path.realpath(os.path.expanduser(os.environ.get("NT_REPOS_DIR", os.path.join(WORKSPACE, "repos"))))

STAGING = {"staging-dashboard.naditarangini.com", "staging-api.ashoka.world"}
NT_DOMAINS = ("naditarangini.com", "ashoka.world")

SECRET_GLOBS = (".env", ".env.*", "*.jks", "*.keystore", "firebase-*.json",
                "google-services.json", "GoogleService-Info.plist")
SECRET_PROBES = (".env", ".env.production", "release.jks", "upload.keystore", "firebase-adminsdk.json",
                 "google-services.json", "GoogleService-Info.plist")
# prefix/suffix (not substring) so code such as `process.env` or `app.env` is not mistaken for a file
SECRET_PREFIXES = (".env", "*.env", "google-services", "GoogleService-Info")
SECRET_SUFFIXES = (".jks", ".keystore")

URL_RE = re.compile(r"(?i)\b(https?|wss?|ftp|file)://([^\s'\"<>`/?#\\)]*)")
NT_HOST_RE = re.compile(r"(?i)(?<![a-z0-9.-])((?:[a-z0-9-]+\.)*(?:naditarangini\.com|ashoka\.world))(?![a-z0-9-])")

NET_PROGS = {"curl", "wget", "http", "https", "xh", "httpie", "aria2c", "lynx", "w3m", "links", "open",
             "ab", "hey", "siege", "playwright", "chromium", "google-chrome", "firefox",
             "nc", "ncat", "netcat", "socat", "telnet", "ssh", "scp", "sftp", "openssl", "dig", "nslookup"}
INTERPRETERS = {"python", "python3", "node", "ruby", "perl", "php", "deno", "bun", "osascript"}
GIT_BLOCKED = {"commit", "push", "pull"}
GIT_WRITE = GIT_BLOCKED | {"checkout", "switch", "reset", "restore", "clean", "stash", "merge", "rebase",
                           "cherry-pick", "revert", "apply", "am", "add", "rm", "mv", "tag", "init", "gc",
                           "worktree", "submodule", "update-index", "update-ref", "filter-branch"}
FS_WRITE = {"rm", "rmdir", "mv", "cp", "touch", "mkdir", "chmod", "chown", "ln", "truncate", "tee",
            "install", "rsync", "dd", "unlink", "patch"}
INPLACE = {"sed": ("-i", "--in-place"), "perl": ("-i", "-pi"), "ruby": ("-i",)}
READERS = {"cat", "head", "tail", "less", "more", "strings", "xxd", "od", "hexdump", "base64", "bat", "nl",
           "awk", "sed", "cut", "sort", "uniq", "grep", "egrep", "fgrep", "jq", "rg", "source", "."}
SPLIT = re.compile(r"\s*(?:&&|\|\||;|\||\n)\s*")


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": f"nt-qa-testing guard: {reason}",
    }}))
    sys.exit(0)


# ---------- helpers ----------

def resolve(path, cwd):
    path = os.path.expanduser(os.path.expandvars(str(path).strip("'\"")))
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return os.path.realpath(path)


def under(p, root):
    return p == root or p.startswith(root.rstrip(os.sep) + os.sep)


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
    """A shell/file glob such as *.json or config/* that would expand to a secret file name."""
    base = os.path.basename(str(pattern).strip("'\""))
    return bool(re.search(r"[*?\[]", base)) and any(fnmatch.fnmatch(p, base) for p in SECRET_PROBES)


def host_class(host):
    h = host.lower().strip(".").rsplit("@", 1)[-1].split(":", 1)[0]
    if h in STAGING:
        return "staging"
    if any(h == d or h.endswith("." + d) for d in NT_DOMAINS):
        return "prod"
    return "other"


def strings_in(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings_in(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings_in(v)


def normal(text):
    """Undo URL-encoding and odd dots so dashboard%2enaditarangini%2ecom is still recognised."""
    return unquote(unquote(text)).translate({ord(c): "." for c in "\u3002\uff0e\uff61"})


def prod_hosts(text):
    text = normal(text)
    hosts = [m.group(2) for m in URL_RE.finditer(text)] + [m.group(1) for m in NT_HOST_RE.finditer(text)]
    return [h for h in hosts if host_class(h) == "prod"]


PROD_MSG = ("{h} is a Nadi Tarangini PRODUCTION host and is blocked. nt-qa-testing runs on staging only: "
            "https://staging-dashboard.naditarangini.com (API staging-api.ashoka.world).")


# ---------- Playwright ----------

def check_playwright(tool, inp, cwd):
    name = tool.rsplit("__", 1)[-1]
    ws = in_ws(cwd, cwd)
    for s in strings_in(inp):
        for h in prod_hosts(s):
            deny(PROD_MSG.format(h=h))
    for p in (inp.get("paths") or []) + [inp.get("filename") or ""]:
        if p and (is_secret(p) or secret_named(p)):
            deny(f"'{os.path.basename(p)}' is a secret file; it must never be uploaded or written by the browser.")
        if p and name != "browser_file_upload" and in_repos(p, cwd):
            deny(f"{name} would write into the product repos ({p}); save under ~/atreya-ai/nt-docs/qa/<run-id>/.")
    if not ws:
        return
    if name in ("browser_run_code_unsafe", "browser_evaluate"):
        deny(f"{name} is disabled for Nadi Tarangini work (it could read typed credentials); use the regular browser_* tools.")
    if inp.get("filename") and name != "browser_take_screenshot":
        deny(f"saving {name} output to a file is disabled for Nadi Tarangini work (files are not masked); "
             "only browser_take_screenshot may save, under nt-docs/qa/<run-id>/screenshots/.")
    for s in strings_in(inp):
        for m in URL_RE.finditer(normal(s)):
            scheme, host = m.group(1).lower(), m.group(2)
            if scheme == "file":
                deny("file:// URLs are not allowed in the browser during Nadi Tarangini QA.")
            if host_class(host) != "staging":
                deny(f"'{host}' is not a staging host. During Nadi Tarangini QA the browser may open only "
                     f"{', '.join(sorted(STAGING))}.")
    url = (inp.get("url") or "").strip()
    if url and name in ("browser_navigate", "browser_tabs"):
        if url == "about:blank":
            return
        if re.match(r"(?i)^[a-z][a-z0-9+.-]*:", url) and not re.match(r"(?i)^https?://", url):
            deny(f"'{url.split(':', 1)[0]}:' URLs are not allowed; only https://staging-dashboard.naditarangini.com.")
        host = re.sub(r"(?i)^https?://", "", normal(url)).split("/", 1)[0]
        if host_class(host) != "staging":
            deny(f"'{host}' is not a staging host. Navigate only to https://staging-dashboard.naditarangini.com.")


# ---------- file tools ----------

def check_file(tool, inp, cwd):
    path = inp.get("file_path") or inp.get("notebook_path") or ""
    if not path:
        return
    if is_secret(path) and in_ws(path, cwd):
        deny(f"'{os.path.basename(path)}' is a secret file and must never be read or written.")
    if tool != "Read" and devgate.is_marker(path, cwd):
        deny(devgate.MARKER_MSG)
    if tool != "Read" and in_repos(path, cwd):
        ok, why = devgate.check_write(path, cwd)
        if not ok:
            deny(f"{tool} of {path} is not allowed; the product repos are never modified by nt-qa-testing"
                 f"{' (' + why + ')' if why else ''}. QA output goes to ~/atreya-ai/nt-docs/qa/<run-id>/.")


def check_grep(inp, cwd):
    path = inp.get("path") or cwd
    glob = inp.get("glob") or ""
    if not in_ws(path, cwd):
        return
    if is_secret(path) or (glob and (secret_named(glob) or glob_hits_secret(glob))):
        deny("searching secret files (.env, keystores, Firebase/Google config) is not allowed.")
    if in_repos(path, cwd) and os.path.isdir(resolve(path, cwd)) and not (inp.get("type") or glob):
        deny("unrestricted search inside the product repos can print secret files; give type= or glob= "
             "for code files. (nt-qa-testing designs tests from nt-docs specs, not code.)")


def check_glob(inp, cwd):
    pattern = inp.get("pattern") or ""
    if in_ws(inp.get("path") or cwd, cwd) and pattern and secret_named(pattern):
        deny("globbing for secret files (.env, keystores, Firebase/Google config) is not allowed.")


def check_webfetch(inp):
    for h in prod_hosts(inp.get("url") or ""):
        deny(PROD_MSG.format(h=h))


# ---------- bash ----------

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


def check_git(toks, cwd):
    args = toks[1:]
    gdir = cwd
    while args and args[0].startswith("-"):
        if args[0] == "-C" and len(args) > 1:
            gdir = resolve(args[1], cwd)
        args = args[2:] if args[0] in ("-C", "-c") else args[1:]
    if not args:
        return
    sub = args[0]
    if sub in GIT_BLOCKED and in_ws(gdir, cwd):
        deny(f"`git {sub}` is blocked in the Nadi Tarangini workspace. The user commits, pushes and pulls themselves.")
    if sub in GIT_WRITE and in_repos(gdir, cwd):
        deny(f"`git {sub}` would modify a product repo; they are never modified by nt-qa-testing.")


def check_bash(cmd, cwd):
    if devgate.bash_writes_marker(cmd, cwd):
        deny(devgate.MARKER_MSG)
    # 1. production hosts (everywhere), judged on the whole command: quoted scripts contain ; and |
    words = {os.path.basename(w) for w in re.findall(r"[A-Za-z0-9_./-]+", cmd)}
    if words & (NET_PROGS | INTERPRETERS):
        for h in prod_hosts(cmd):
            deny(PROD_MSG.format(h=h))
    for segment in (s for s in SPLIT.split(cmd) if s.strip()):
        toks = tokens(segment)
        if not toks:
            continue
        if toks[0] == "cd" and len(toks) > 1:
            cwd = resolve(toks[1], cwd)
            continue
        while toks and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]) or
                        toks[0] in ("sudo", "command", "nohup", "time", "env", "exec")):
            toks = toks[1:]
        if not toks:
            continue
        prog = os.path.basename(toks[0])
        if prog == "git":
            check_git(toks, cwd)

        ws = in_ws(cwd, cwd) or any(in_ws(t, cwd) for t in toks if "/" in t or t.startswith(("~", ".")))
        if not ws:
            continue

        # 2. secret files
        for t in strip_excludes(toks[1:]):
            for part in re.split(r"[=:]", t):
                if part and secret_named(part):
                    deny(f"command references secret file '{os.path.basename(part)}'; never read secrets.")
            if prog in READERS and glob_hits_secret(t):
                deny(f"`{prog} {t}` could expand to a secret file; name the files explicitly.")
        for redir in re.findall(r"<\s*([^\s<>|;&]+)", segment):
            if secret_named(redir):
                deny(f"command reads secret file '{redir}'.")

        # 3. writes into the product repos
        for target in re.findall(r"(?<![<0-9&])>{1,2}\s*([^\s;&|]+)", segment):
            if target != "/dev/null" and in_repos(target, cwd):
                deny(f"redirect writes into a product repo ({target}); QA output goes to nt-docs/qa/.")
        if prog in FS_WRITE:
            args = [a for a in toks[1:] if not a.startswith("-")]
            targets = args[-1:] if prog in ("cp", "install", "rsync", "ln", "mv") else args
            if prog == "mv":
                targets = args  # moving a file out of a repo also modifies it
            if any(in_repos(a, cwd) for a in targets):
                deny(f"`{prog}` would modify the product repos; they are never modified by nt-qa-testing.")
        if prog in INPLACE and any(a.startswith(INPLACE[prog]) for a in toks[1:]) and \
                (in_repos(cwd, cwd) or any(in_repos(a, cwd) for a in toks[1:] if not a.startswith("-"))):
            deny(f"in-place `{prog}` edit inside the product repos is not allowed.")

        # 4. unrestricted recursive search inside the repos (could print committed secrets)
        if in_repos(cwd, cwd) or any(in_repos(t, cwd) for t in toks[1:] if not t.startswith("-")):
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
    if tool.startswith("mcp__") and "playwright" in tool.lower():
        check_playwright(tool, inp, cwd)
    elif tool in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit"):
        check_file(tool, inp, cwd)
    elif tool == "Grep":
        check_grep(inp, cwd)
    elif tool == "Glob":
        check_glob(inp, cwd)
    elif tool == "WebFetch":
        check_webfetch(inp)
    elif tool == "Bash":
        check_bash(inp.get("command", ""), cwd)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # fail closed
        deny(f"guard error ({type(e).__name__}: {e}); refusing to be safe. Rephrase the call or report this hook bug.")
