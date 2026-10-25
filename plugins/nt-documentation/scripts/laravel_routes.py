#!/usr/bin/env python3
"""Static, read-only parser for Laravel route files (no PHP, no app boot, no .env).

Handles Route::group([...], fn), Route::middleware()/prefix()/controller()->group(fn),
Route::get|post|put|patch|delete|options|any|match, [Ctrl::class, 'method'],
'Ctrl@method', closures, ->name(), ->middleware(), and skips commented-out routes.

Usage:
  laravel_routes.py <repo> [--file routes/api.php ...] [--format json|tsv]
  laravel_routes.py <repo> --by-controller            controllers with route counts and URI prefixes
  laravel_routes.py <repo> --grep <text>              routes whose uri/controller/action contains text

<repo>: backend | web | repo directory name. Env: NT_REPOS_DIR (default ~/atreya-ai/repos).
"""
import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graph_query import repo_path  # noqa: E402

# file -> URI prefix applied by RouteServiceProvider (checked against both repos)
FILE_PREFIX = {
    "Ashoka-World-Backend": {"routes/api.php": "", "routes/web.php": ""},
    "Nadi-Tarangini-Frontend": {"routes/api.php": "api", "routes/web.php": ""},
}
VERBS = ("get", "post", "put", "patch", "delete", "options", "any", "match")


def strip_comments(src):
    """Blank out comments, keeping offsets and newlines so line numbers stay correct."""
    out, i, n = list(src), 0, len(src)
    while i < n:
        c = src[i]
        if c in "'\"":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            i = j + 1
        elif src.startswith("//", i) or c == "#":
            j = src.find("\n", i)
            j = n if j == -1 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j == -1 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


def use_map(src):
    m = {}
    for full, alias in re.findall(r"^use\s+([\w\\]+)(?:\s+as\s+(\w+))?\s*;", src, re.M):
        m[alias or full.rsplit("\\", 1)[-1]] = full
    return m


def scan_statement(code, i):
    """From Route:: at i, return (end, kind) where kind is ';' or '{' (closure body start)."""
    depth, n = 0, len(code)
    while i < n:
        c = code[i]
        if c in "'\"":
            j = i + 1
            while j < n and code[j] != c:
                j += 2 if code[j] == "\\" else 1
            i = j + 1
            continue
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif c == "{":
            return i, "{"
        elif c == ";" and depth <= 0:
            return i, ";"
        i += 1
    return n, ";"


def match_brace(code, i):
    depth, n = 0, len(code)
    while i < n:
        c = code[i]
        if c in "'\"":
            j = i + 1
            while j < n and code[j] != c:
                j += 2 if code[j] == "\\" else 1
            i = j + 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


def strs(text):
    return re.findall(r"'([^']*)'|\"([^\"]*)\"", text)


def first_str(text):
    s = strs(text)
    return (s[0][0] or s[0][1]) if s else None


def group_attrs(stmt):
    attrs = {"prefix": None, "middleware": [], "controller": None, "name": None}
    m = re.search(r"['\"]prefix['\"]\s*=>\s*['\"]([^'\"]*)['\"]", stmt) or re.search(r"prefix\(\s*['\"]([^'\"]*)['\"]", stmt)
    if m:
        attrs["prefix"] = m.group(1)
    for mm in re.finditer(r"['\"]middleware['\"]\s*=>\s*(\[[^\]]*\]|['\"][^'\"]*['\"])|middleware\(\s*(\[[^\]]*\]|['\"][^'\"]*['\"])", stmt):
        attrs["middleware"] += [a or b for a, b in strs(mm.group(1) or mm.group(2))]
    m = re.search(r"controller\(\s*([\w\\]+)::class", stmt)
    if m:
        attrs["controller"] = m.group(1)
    m = re.search(r"['\"]as['\"]\s*=>\s*['\"]([^'\"]*)['\"]|->name\(\s*['\"]([^'\"]*)['\"]", stmt)
    if m:
        attrs["name"] = m.group(1) or m.group(2)
    return attrs


def join_uri(*parts):
    segs = [p.strip("/") for p in parts if p and p.strip("/")]
    return "/" + "/".join(segs)


def parse_route(stmt, stack, uses):
    m = re.match(r"Route::(\w+)\s*\(", stmt)
    verb = m.group(1).lower()
    body = stmt[m.end():]
    if verb == "match":
        mm = re.match(r"\s*\[([^\]]*)\]\s*,", body)
        methods = [a or b for a, b in strs(mm.group(1))] if mm else ["?"]
        body = body[mm.end():] if mm else body
    else:
        methods = ["ANY" if verb == "any" else verb]
    uri = first_str(body) or ""
    rest = body[body.find(uri) + len(uri) + 1:] if uri else body
    ctrl = action = None
    m = re.search(r"\[\s*([\w\\]+)::class\s*,\s*['\"](\w+)['\"]\s*\]", rest)
    if m:
        ctrl, action = m.group(1), m.group(2)
    else:
        m = re.match(r"\s*,\s*['\"]([\w\\]+)@(\w+)['\"]", rest)
        if m:
            ctrl, action = m.group(1), m.group(2)
        else:
            m = re.match(r"\s*,\s*([\w\\]+)::class", rest)  # invokable controller
            if m:
                ctrl, action = m.group(1), "__invoke"
            else:
                m = re.match(r"\s*,\s*['\"](\w+)['\"]", rest)  # inside Route::controller()->group
                group_ctrl = next((g["controller"] for g in reversed(stack) if g["controller"]), None)
                if m and group_ctrl:
                    ctrl, action = group_ctrl, m.group(1)
                elif re.match(r"\s*,\s*(static\s+)?(function|fn)\b", rest):
                    action = "closure"
    name = None
    mm = re.search(r"->name\(\s*['\"]([^'\"]*)['\"]", stmt)
    if mm:
        name = "".join(g["name"] or "" for g in stack) + mm.group(1)
    mw = [x for g in stack for x in g["middleware"]]
    for mm in re.finditer(r"->middleware\(\s*(\[[^\]]*\]|['\"][^'\"]*['\"])", stmt):
        mw += [a or b for a, b in strs(mm.group(1))]
    fqcn = uses.get(ctrl, ctrl) if ctrl else None
    if fqcn and "\\" not in fqcn:
        fqcn = "App\\Http\\Controllers\\" + fqcn
    return methods, uri, name, mw, fqcn, action


def parse_file(repo_dir, repo_name, rel):
    path = os.path.join(repo_dir, rel)
    with open(path, encoding="utf-8", errors="ignore") as f:
        src = f.read()
    uses = use_map(src)
    code = strip_comments(src)
    base = FILE_PREFIX.get(repo_name, {}).get(rel, "")
    routes, stack, closers = [], [], []  # closers: positions of '}' that pop the stack
    i = 0
    for m in re.finditer(r"Route::\w+\s*\(|\}", code):
        if m.start() < i:
            continue
        if m.group(0) == "}":
            if closers and m.start() == closers[-1]:
                closers.pop()
                stack.pop()
            continue
        end, kind = scan_statement(code, m.start())
        stmt = code[m.start():end]
        verb = re.match(r"Route::(\w+)", stmt).group(1).lower()
        if kind == "{" and "group(" in stmt:
            stack.append(group_attrs(stmt))
            closers.append(match_brace(code, end))
            i = end + 1
            continue
        if verb in VERBS:
            methods, uri, name, mw, fqcn, action = parse_route(stmt, stack, uses)
            prefix = join_uri(base, *[g["prefix"] for g in stack])
            ctrl_file = None
            if fqcn and fqcn.startswith("App\\"):
                cand = "app/" + fqcn[4:].replace("\\", "/") + ".php"
                ctrl_file = cand if os.path.isfile(os.path.join(repo_dir, cand)) else None
            routes.append({
                "methods": [x.upper() for x in methods],
                "uri": join_uri(prefix, uri),
                "name": name,
                "controller": fqcn,
                "action": action,
                "controller_file": ctrl_file,
                "middleware": sorted(set(mw)),
                "route_file": rel,
                "line": code.count("\n", 0, m.start()) + 1,
            })
        if kind == "{":  # closure handler: skip its body
            i = match_brace(code, end) + 1
        else:
            i = end + 1
    return routes


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("repo")
    p.add_argument("--file", action="append", help="route file(s) relative to repo (default: routes/api.php, routes/web.php)")
    p.add_argument("--format", choices=("json", "tsv"), default="tsv")
    p.add_argument("--by-controller", action="store_true")
    p.add_argument("--grep")
    a = p.parse_args()
    name, path = repo_path(a.repo)
    files = a.file or [f for f in ("routes/api.php", "routes/web.php") if os.path.isfile(os.path.join(path, f))]
    routes = [r for f in files for r in parse_file(path, name, f)]
    if a.grep:
        g = a.grep.lower()
        routes = [r for r in routes if g in r["uri"].lower() or g in (r["controller"] or "").lower() or g in (r["action"] or "").lower()]
    if a.by_controller:
        by = collections.defaultdict(list)
        for r in routes:
            by[r["controller"] or "(closure)"].append(r)
        print(f"# {name}: {len(routes)} routes, {len(by)} controllers")
        for ctrl, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
            prefixes = collections.Counter("/".join(r["uri"].split("/")[:3]) for r in rs)
            missing = "" if ctrl == "(closure)" or rs[0]["controller_file"] else "  [controller file not found]"
            print(f"{len(rs):4d}  {ctrl}{missing}\n      prefixes: " + ", ".join(f"{k} ({v})" for k, v in prefixes.most_common(4)))
        return
    if a.format == "json":
        print(json.dumps(routes, indent=1))
    else:
        for r in routes:
            print("\t".join([",".join(r["methods"]), r["uri"], f"{(r['controller'] or '').rsplit(chr(92), 1)[-1]}@{r['action']}",
                             ",".join(r["middleware"]), f"{r['route_file']}:{r['line']}"]))
        print(f"# {len(routes)} routes", file=sys.stderr)


if __name__ == "__main__":
    main()
