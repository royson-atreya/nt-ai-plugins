#!/usr/bin/env python3
"""Shared repo-write gate for the Nadi Tarangini plugins (nt-dev-coding, nt-documentation, nt-qa-testing).

The SAME file is copied into each plugin's hooks/ folder so every guard applies one rule:
a Write/Edit inside $NT_REPOS_DIR (~/atreya-ai/repos) is allowed only when

  1. $NT_DOCS_DIR/dev/ACTIVE names a task id,
  2. $NT_DOCS_DIR/dev/<id>/APPROVED exists, is valid JSON for that id, and was written by the
     nt-dev-coding approve hook after the user typed `approve <id>`,
  3. dev/<id>/plan.md is unchanged since approval (sha256 recorded in APPROVED),
  4. the file is inside a repo listed in APPROVED["repos"] (snapshot of the plan at approval time),
  5. that repo's HEAD is a branch, and not master, main or production,
  6. the file is not inside the repo's .git directory.

Anything else (unreadable marker, detached HEAD, odd path) is refused: the gate fails closed.
Standard library only, no subprocesses. Edit only in nt-dev-coding; copy to the other plugins.
"""
import hashlib
import json
import os
import re

WORKSPACE = os.path.realpath(os.path.expanduser(os.environ.get("NT_WORKSPACE", "~/atreya-ai")))
REPOS = os.path.realpath(os.path.expanduser(os.environ.get("NT_REPOS_DIR", os.path.join(WORKSPACE, "repos"))))
DOCS = os.path.realpath(os.path.expanduser(os.environ.get("NT_DOCS_DIR", os.path.join(WORKSPACE, "nt-docs"))))
DEV = os.path.join(DOCS, "dev")
PROTECTED = ("master", "main", "production")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
MARKERS = ("APPROVED", "ACTIVE")


def _under(p, root):
    return p == root or p.startswith(root.rstrip(os.sep) + os.sep)


def _resolve(path, cwd):
    path = os.path.expanduser(os.path.expandvars(str(path).strip("'\"")))
    if not os.path.isabs(path):
        path = os.path.join(cwd or os.getcwd(), path)
    return os.path.realpath(path)


def repo_of(path, cwd=None):
    """(name, root) of the repo under $NT_REPOS_DIR that contains path, or (None, None)."""
    p = _resolve(path, cwd)
    if not _under(p, REPOS) or p == REPOS:
        return None, None
    name = os.path.relpath(p, REPOS).split(os.sep)[0]
    root = os.path.join(REPOS, name)
    return (name, root) if os.path.isdir(root) else (None, None)


def branch(root):
    """Current branch of the repo at root, read from .git/HEAD; None when detached, unreadable, or when HEAD
    names a branch that does not exist (e.g. set with `git symbolic-ref`)."""
    gitdir = os.path.join(root, ".git")
    try:
        if os.path.isfile(gitdir):  # worktree or submodule: .git is a file pointing at the real dir
            with open(gitdir) as f:
                ref = f.read().split("gitdir:", 1)[1].strip()
            gitdir = os.path.normpath(os.path.join(root, ref))
        with open(os.path.join(gitdir, "HEAD")) as f:
            head = f.read().strip()
    except (OSError, IndexError):
        return None
    if not head.startswith("ref: refs/heads/"):
        return None
    br = head[len("ref: refs/heads/"):]
    return br if _ref_exists(gitdir, "refs/heads/" + br) else None  # HEAD pointed at a missing branch: refuse


def _ref_exists(gitdir, ref):
    common = gitdir
    try:
        with open(os.path.join(gitdir, "commondir")) as f:
            common = os.path.normpath(os.path.join(gitdir, f.read().strip()))
    except OSError:
        pass
    if os.path.isfile(os.path.join(common, ref)):
        return True
    try:
        with open(os.path.join(common, "packed-refs")) as f:
            return any(line.rstrip("\n").endswith(" " + ref) for line in f)
    except OSError:
        return False


def active_id():
    try:
        with open(os.path.join(DEV, "ACTIVE")) as f:
            tid = f.read().strip()
    except OSError:
        return None
    return tid if ID_RE.match(tid) else None


def plan_sha(tid):
    try:
        with open(os.path.join(DEV, tid, "plan.md"), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def approval(tid):
    """The APPROVED record of a task as a dict, or None."""
    try:
        with open(os.path.join(DEV, tid, "APPROVED")) as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(rec, dict) or rec.get("id") != tid or not isinstance(rec.get("repos"), list):
        return None
    return rec


def plan_repos(text, key="repos"):
    """A list key (default `repos:`) from a plan.md YAML front-matter (inline [a, b] or block '- a' form)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.S)
    if not m:
        return []
    lines = m.group(1).splitlines()
    for i, line in enumerate(lines):
        km = re.match(rf"^{re.escape(key)}\s*:\s*(.*)$", line)
        if not km:
            continue
        rest = km.group(1).strip()
        if rest.startswith("["):
            items = rest.strip("[]").split(",")
        elif rest:
            items = [rest]
        else:
            items = []
            for nxt in lines[i + 1:]:
                im = re.match(r"^\s+-\s*(.+)$", nxt)
                if not im:
                    break
                items.append(im.group(1))
        return [x.strip().strip("'\"") for x in items if x.strip().strip("'\"")]
    return []


def protected_hint(name, root, br, tid):
    where = "detached HEAD" if br is None else f"branch '{br}'"
    return (f"{name} is on {where}, which is protected. The user creates the branch themselves, e.g. "
            f"`git -C {root} checkout -b feature/{tid or '<id>'}`.")


def check_write(path, cwd=None):
    """(allowed, reason) for writing path inside $NT_REPOS_DIR. Paths outside the repos return (False, '')."""
    try:
        name, root = repo_of(path, cwd)
        if not name:
            return False, ""
        p = _resolve(path, cwd)
        if _under(p, os.path.join(root, ".git")):
            return False, "writing inside a repo's .git directory is never allowed."
        tid = active_id()
        if not tid:
            return False, ("there is no active approved nt-dev-coding task. Plan it with /nt-dev-coding:task "
                           "or /nt-dev-coding:bug; the user then types `approve <id>`.")
        rec = approval(tid)
        if not rec:
            return False, (f"task {tid} has no valid APPROVED marker. Only the user can approve, by typing "
                           f"`approve {tid}`.")
        if rec.get("plan_sha256") != plan_sha(tid):
            return False, (f"dev/{tid}/plan.md changed after approval. Show the user the change; they re-approve "
                           f"with `approve {tid}`.")
        if name not in rec["repos"]:
            return False, (f"{name} is not in the approved plan of {tid} (approved repos: "
                           f"{', '.join(rec['repos']) or 'none'}). Update the plan and ask the user to re-approve.")
        br = branch(root)
        if br is None or br in PROTECTED:
            return False, protected_hint(name, root, br, tid)
        return True, ""
    except Exception as e:  # fail closed
        return False, f"repo-write gate error ({type(e).__name__}: {e})."


def is_marker(path, cwd=None):
    """True if path is dev/ACTIVE or dev/<id>/APPROVED (only the approve hook may write these)."""
    p = _resolve(path, cwd)
    base = os.path.basename(p)
    if base not in MARKERS or not _under(p, DEV):
        return False
    return os.path.dirname(p) == DEV if base == "ACTIVE" else os.path.dirname(os.path.dirname(p)) == DEV


MARKER_MSG = ("APPROVED and ACTIVE are written only by the nt-dev-coding approve hook when the user types "
              "`approve <id>`; never create, change or delete them.")
_MARKER_READERS = {"ls", "cat", "head", "tail", "test", "[", "stat", "jq", "shasum", "sha256sum", "wc", "file",
                   "grep", "echo", "printf", "find", "diff", "cmp"}
_COPIERS = {"cp", "install", "rsync", "ln", "scp"}  # only the last argument is written
_INLINE_CODE = re.compile(r"(?:^|[\s;&|(])(?:python3?|node|ruby|perl|deno|bun|osascript)\b[^\n]*?"
                          r"(?:\s-[ce]\b|\s-\s|\s-$|<<|--eval\b)", re.M)
_SPLIT = re.compile(r"\s*(?:&&|\|\||;|(?<!>)\||\n)\s*")
_QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")


def bash_writes_marker(cmd, cwd=None, depth=0):
    """True if a shell command could create, change or delete an approval marker."""
    import shlex
    cwd = cwd or os.getcwd()
    if depth > 3:
        return True
    if _INLINE_CODE.search(cmd) and re.search(r"\b(APPROVED|ACTIVE)\b", cmd) and \
            (_under(_resolve(cwd, cwd), WORKSPACE) or DEV in cmd or "nt-docs" in cmd):
        return True
    for segment in (s for s in _SPLIT.split(cmd) if s.strip()):
        try:
            toks = shlex.split(segment, comments=True)
        except ValueError:
            toks = segment.split()
        if toks and toks[0] == "cd" and len(toks) > 1:
            cwd = _resolve(toks[1], cwd)
            continue
        while toks and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]) or
                        toks[0] in ("sudo", "command", "nohup", "time", "env", "exec", "builtin")):
            toks = toks[1:]
        if not toks:
            continue
        prog = os.path.basename(toks[0])
        if prog in ("bash", "sh", "zsh", "dash") and "-c" in toks[1:-1]:
            if bash_writes_marker(toks[toks.index("-c") + 1], cwd, depth + 1):
                return True
            continue
        if prog == "eval" and bash_writes_marker(" ".join(toks[1:]), cwd, depth + 1):
            return True
        redirects = re.findall(r"(?<![<>=-])\d*>{1,2}\|?(?!&)\s*([^\s;&|<>]+)", _QUOTED.sub("''", segment))
        if any(is_marker(r, cwd) for r in redirects):
            return True
        args = [t for t in toks[1:] if not t.startswith("-")]
        if prog in _COPIERS:
            args = args[-1:]
        if prog not in _MARKER_READERS and any(is_marker(part, cwd) for a in args for part in re.split(r"[=:]", a) if part):
            return True
    return False
