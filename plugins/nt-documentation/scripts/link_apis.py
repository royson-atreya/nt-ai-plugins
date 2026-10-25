#!/usr/bin/env python3
"""Cross-repo trace: client screen -> API call -> backend route -> controller@action -> DB tables.

Static and read-only. Clients:
  web (Nadi-Tarangini-Frontend): Blade view / page JS -> web route -> web controller method
       -> "$backendUrl/endpoint" | $backendUrl . '/endpoint' | config('app.backend_url') . '/endpoint'
  app (Nadi-Tarangini-App): screen -> BLoC -> ApiRepository method -> StringsConst().xxxUrl
       ('${AppEnvironment.baseUrl}/endpoint'), or a direct '${...baseUrl}/endpoint' string
Backend tables: models / DB::table used in the action body, plus one hop into the services and
repositories the action calls (interface bindings resolved from app/Providers); falls back to the
controller file (level "file").

Usage:
  link_apis.py [--out DIR]          write api-links.json, api-links.csv, api-links.md (default $NT_DOCS_DIR/api-links)
  link_apis.py --stdout-summary     print the summary only, write nothing

Manual fixes for calls that cannot be resolved statically go in <out>/overrides.json:
  [{"client": "web|app", "file": "<repo-relative path>", "symbol": "<method>", "line": 123 (optional),
    "method": "POST", "uri": "/resolved/uri", "note": "why"}]
"""
import argparse
import collections
import csv
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graph_query import repo_path, stamp  # noqa: E402
from laravel_data import models as load_models, read  # noqa: E402
from laravel_routes import match_brace, parse_file, strip_comments, use_map  # noqa: E402

BACKEND, WEB, APP = "Ashoka-World-Backend", "Nadi-Tarangini-Frontend", "Nadi-Tarangini-App"
SKIP_JS = re.compile(r"(\.min\.js$|/vendor/|/plugins?/|jquery|bootstrap|jspdf|chart)", re.I)
WRITE_CALL = r"(create|insert|insertGetId|update|updateOrCreate|updateOrInsert|firstOrCreate|upsert|destroy|delete|forceDelete|increment|decrement|save|truncate)"


# ---------------------------------------------------------------- helpers

def norm_uri(uri):
    uri = uri.split("?", 1)[0].split("#", 1)[0]
    uri = re.sub(r"\{\$[^}]*\}|\$\{[^}]*\}|\$[A-Za-z_][\w>-]*(\[[^\]]*\])?|\{[^}/]*\}", "{}", uri)
    uri = "/" + "/".join(s for s in uri.split("/") if s)
    return uri


def segs(uri):
    return [s for s in uri.split("/") if s]


def php_methods(code):
    """[(name, start, end)] for PHP functions in comment-stripped code."""
    out = []
    for m in re.finditer(r"function\s+(\w+)\s*\(", code):
        brace = code.find("{", m.end())
        semi = code.find(";", m.end())
        if brace == -1 or (semi != -1 and semi < brace):
            continue  # abstract / interface method
        out.append((m.group(1), m.start(), match_brace(code, brace)))
    return out


def enclosing(methods, pos):
    best = None
    for name, s, e in methods:
        if s <= pos <= e and (best is None or s > best[1]):
            best = (name, s, e)
    return best


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def docs_dir():
    return os.path.expanduser(os.environ.get("NT_DOCS_DIR", "~/atreya-ai/nt-docs"))


def load_owner(repo_name):
    p = os.path.join(docs_dir(), repo_name, "module-map.json")
    if not os.path.isfile(p):
        return lambda f: None
    from module_map import owner
    with open(p) as fh:
        mods = json.load(fh)["modules"]
    return lambda f: owner(mods, f)[0] if f else None


# ---------------------------------------------------------------- backend

class Backend:
    def __init__(self):
        self.name, self.dir = repo_path("backend")
        self.routes = [r for f in ("routes/api.php", "routes/web.php")
                       if os.path.isfile(os.path.join(self.dir, f)) for r in parse_file(self.dir, self.name, f)]
        self.models = load_models(self.dir)
        self.by_fqcn = {self.fqcn_of(m["file"]): m for m in self.models}
        self.by_short = collections.defaultdict(list)
        for m in self.models:
            self.by_short[m["model"]].append(m)
        self.bindings = self.load_bindings()
        self.cache = {}

    def fqcn_of(self, rel):
        return "App\\" + rel[len("app/"):-len(".php")].replace("/", "\\")

    def file_of(self, fqcn):
        if not fqcn or not fqcn.startswith("App\\"):
            return None
        rel = "app/" + fqcn[4:].replace("\\", "/") + ".php"
        return rel if os.path.isfile(os.path.join(self.dir, rel)) else None

    def load_bindings(self):
        b = {}
        pdir = os.path.join(self.dir, "app", "Providers")
        for fn in os.listdir(pdir) if os.path.isdir(pdir) else []:
            src = read(os.path.join(pdir, fn))
            uses = use_map(src)
            for a, c in re.findall(r"->(?:bind|singleton|scoped)\(\s*([\w\\]+)::class\s*,\s*([\w\\]+)::class", src):
                b[uses.get(a, a)] = uses.get(c, c)
        return b

    def parsed(self, rel):
        if rel not in self.cache:
            src = read(os.path.join(self.dir, rel))
            code = strip_comments(src)
            self.cache[rel] = (src, code, use_map(src), php_methods(code))
        return self.cache[rel]

    def body(self, rel, method):
        src, code, uses, methods = self.parsed(rel)
        for name, s, e in methods:
            if name == method:
                return code[s:e], uses, code
        return None, uses, code

    def tables_in(self, text, uses):
        found = {}
        for m in re.finditer(r"\b([A-Z]\w+)::|new\s+([A-Z]\w+)\s*\(", text):
            short = m.group(1) or m.group(2)
            model = self.by_fqcn.get(uses.get(short, "")) or (self.by_short[short][0] if len(self.by_short.get(short, [])) == 1 else None)
            if not model:
                continue
            stmt = text[m.start(): text.find(";", m.start()) + 1 or len(text)]
            write = bool(m.group(2)) or bool(re.search(rf"(::|->){WRITE_CALL}\s*\(", stmt))
            key = (model["table"], model["connection"])
            found[key] = found.get(key, False) or write
        for m in re.finditer(r"DB::(?:connection\(\s*['\"](\w+)['\"]\s*\)->)?table\(\s*['\"](\w+)['\"]", text):
            stmt = text[m.start(): text.find(";", m.start()) + 1 or len(text)]
            key = (m.group(2), m.group(1) or "mysql (default)")
            found[key] = found.get(key, False) or bool(re.search(rf"->{WRITE_CALL}\s*\(", stmt))
        return found

    def service_calls(self, body, uses, code):
        """(fqcn, method) pairs for services/repositories the action calls."""
        props = {}
        ctor = re.search(r"function\s+__construct\s*\(([^)]*)\)", code)
        if ctor:
            for typ, var in re.findall(r"([\w\\]+)\s+\$(\w+)", ctor.group(1)):
                props[var] = uses.get(typ, typ)
        for typ, var in re.findall(r"(?:protected|private|public)\s+(?:readonly\s+)?([\w\\]+)\s+\$(\w+)", code):
            props.setdefault(var, uses.get(typ, typ))
        calls = set()
        for var, meth in re.findall(r"\$this->(\w+)->(\w+)\s*\(", body):
            if var in props:
                calls.add((props[var], meth))
        for cls, meth in re.findall(r"\b([A-Z]\w+)::(\w+)\s*\(", body):
            if cls.endswith(("Service", "Repository", "Helper")) or "Service" in cls:
                calls.add((uses.get(cls, cls), meth))
        for cls, meth in re.findall(r"\(\s*new\s+([A-Z]\w+)(?:\([^)]*\))?\s*\)\s*->(\w+)\s*\(", body):
            calls.add((uses.get(cls, cls), meth))
        for cls, meth in re.findall(r"app\(\s*([\w\\]+)::class\s*\)->(\w+)\s*\(", body):
            calls.add((uses.get(cls, cls), meth))
        out = set()
        for fq, meth in calls:
            fq = self.bindings.get(fq, fq)
            if "\\" not in fq:
                fq = "App\\Services\\" + fq
            out.add((fq, meth))
        return out

    def route_tables(self, route):
        rel, action = route["controller_file"], route["action"]
        if not rel or not action or action == "closure":
            return []
        body, uses, code = self.body(rel, action)
        result = {}
        if body:
            for k, w in self.tables_in(body, uses).items():
                result[k] = {"level": "action", "write": w}
            for fq, meth in self.service_calls(body, uses, code):
                srel = self.file_of(fq)
                if not srel or srel.startswith("app/Models/"):
                    continue
                sbody, suses, scode = self.body(srel, meth)
                for k, w in self.tables_in(sbody or scode, suses).items():
                    if k not in result:
                        result[k] = {"level": "service" if sbody else "service-file", "write": w, "via": srel}
        if not result:
            _, code, uses, _ = self.parsed(rel)
            for k, w in self.tables_in(code, uses).items():
                result[k] = {"level": "file", "write": w}
        return [dict(table=t, connection=c, **v) for (t, c), v in sorted(result.items())]

    def match(self, method, uri):
        """Best backend route for a client call: exact > param > case-insensitive."""
        target = segs(uri)
        best = None
        for r in self.routes:
            rs = segs(norm_uri(r["uri"]))
            optional = sum(1 for s in segs(r["uri"]) if s.endswith("?}"))
            if not (len(rs) - optional <= len(target) <= len(rs)):
                continue
            kind = "exact"
            ok = True
            for a, b in zip(rs, target):
                if a == b:
                    continue
                if a == "{}" or b == "{}":
                    kind = "param" if kind == "exact" else kind
                elif a.lower() == b.lower():
                    kind = "case-mismatch"
                else:
                    ok = False
                    break
            if not ok:
                continue
            method_ok = not method or method in r["methods"] or "ANY" in r["methods"]
            score = {"exact": 3, "param": 2, "case-mismatch": 1}[kind] + (0.5 if method_ok else 0)
            if best is None or score > best[0]:
                best = (score, r, kind, method_ok)
        return best


# ---------------------------------------------------------------- web client

def web_calls(overrides):
    name, wdir = repo_path("web")
    routes = [r for f in ("routes/web.php", "routes/api.php") if os.path.isfile(os.path.join(wdir, f))
              for r in parse_file(wdir, name, f)]
    route_by_action = collections.defaultdict(list)
    for r in routes:
        if r["controller_file"]:
            route_by_action[(r["controller_file"], r["action"])].append(r)
    callers = index_web_callers(wdir)
    calls = []
    pat = re.compile(
        r"\"\{?\$backendUrl\}?(/[^\"]*)\""                                   # "$backendUrl/x"
        r"|\$backendUrl\s*\.\s*(['\"])(/[^'\"]*)\2"                          # $backendUrl . '/x'
        r"|config\(\s*['\"]app\.backend_url['\"]\s*\)\s*\.\s*(['\"])(/[^'\"]*)\4"
        r"|(\$backendUrl\s*\.\s*\$\w+|config\(\s*['\"]app\.backend_url['\"]\s*\)\s*\.\s*\$\w+)"  # fully dynamic
    )
    for root, _, files in os.walk(os.path.join(wdir, "app")):
        for fn in files:
            if not fn.endswith(".php"):
                continue
            rel = os.path.relpath(os.path.join(root, fn), wdir)
            src = read(os.path.join(root, fn))
            code = strip_comments(src)
            if "backend" not in code:
                continue
            methods = php_methods(code)
            for m in pat.finditer(code):
                literal = m.group(1) or m.group(3) or m.group(5)
                dynamic = m.group(6)
                after = code[m.end(): m.end() + 6]
                uri = None
                if literal is not None:
                    uri = literal + ("{}" if literal.endswith("/") and re.match(r"\s*\.", after) else "")
                enc = enclosing(methods, m.start())
                back = code[max(enc[1] if enc else 0, m.start() - 300): m.start()]
                verbs = re.findall(r"(?:->|Http::)(get|post|put|patch|delete)\s*\(", back)
                call = {
                    "client": "web", "file": rel, "line": line_of(code, m.start()),
                    "symbol": enc[0] if enc else None,
                    "method": verbs[-1].upper() if verbs else None,
                    "uri": norm_uri(uri) if uri else None,
                    "raw": None if uri else dynamic,
                }
                apply_override(call, overrides)
                wr = route_by_action.get((rel, call["symbol"]), [])
                call["client_routes"] = [f"{','.join(r['methods'])} {r['uri']}" for r in wr]
                screens = set()
                if enc:
                    for v in re.findall(r"view\(\s*['\"]([\w.\-/]+)['\"]", code[enc[1]:enc[2]]):
                        screens.add("resources/views/" + v.replace(".", "/") + ".blade.php")
                for r in wr:
                    screens |= callers["uri"].get(r["uri"].split("{")[0].rstrip("/") or "/", set())
                    if r["name"]:
                        screens |= callers["name"].get(r["name"], set())
                call["screens"] = sorted(s for s in screens if not re.search(r"resources/views/(errors|layouts|emails?)/", s))
                calls.append(call)
    return calls


def index_web_callers(wdir):
    """Which Blade/JS files reference a web URI ('/storePatient') or route name (route('x'))."""
    idx = {"uri": collections.defaultdict(set), "name": collections.defaultdict(set)}
    for sub in ("resources/views", "public/js"):
        for root, _, files in os.walk(os.path.join(wdir, sub)):
            for fn in files:
                rel = os.path.relpath(os.path.join(root, fn), wdir)
                if not fn.endswith((".js", ".blade.php")) or SKIP_JS.search(rel):
                    continue
                src = read(os.path.join(root, fn))
                for q in re.findall(r"['\"`](/[A-Za-z][\w\-/]*)", src):
                    idx["uri"][q.rstrip("/")].add(rel)
                for q in re.findall(r"(?:url|to)\(\s*['\"]/?([A-Za-z][\w\-/]*)", src):
                    idx["uri"]["/" + q.rstrip("/")].add(rel)
                for q in re.findall(r"route\(\s*['\"]([\w.\-]+)['\"]", src):
                    idx["name"][q].add(rel)
    return idx


# ---------------------------------------------------------------- app client

DART_METHOD = re.compile(r"^\s{0,4}(?:static\s+)?(?:Future|Stream|void|[A-Z]\w*|int|bool|String|dynamic)(?:<[^\n{]*>)?\??\s+(\w+)\s*\(", re.M)


def app_calls(overrides):
    name, adir = repo_path("app")
    lib = os.path.join(adir, "lib")
    files = {}
    for root, _, fns in os.walk(lib):
        for fn in fns:
            if fn.endswith(".dart"):
                rel = os.path.relpath(os.path.join(root, fn), adir)
                files[rel] = read(os.path.join(root, fn))
    const_re = re.compile(r"(\w+)\s*(?:=|=>)\s*['\"]\$\{?(?:AppEnvironment|FlavorConfig)\.baseUrl\}?(/[^'\"]*)['\"]")
    direct_re = re.compile(r"['\"]\$\{?[\w.]*[bB]aseUrl\}?(/[^'\"]*)['\"]")
    dyn_re = re.compile(r"['\"]\$\{?[\w.]*[bB]aseUrl\}?/\$\{?(\w+)\}?")
    consts, calls = {}, []
    for rel, src in files.items():
        for m in const_re.finditer(src):
            consts[m.group(1)] = (norm_uri(m.group(2)), rel, line_of(src, m.start()))
    importers = collections.defaultdict(set)
    for rel, src in files.items():
        for imp in re.findall(r"import\s+['\"][^'\"]*?([\w]+\.dart)['\"]", src):
            importers[imp].add(rel)
    is_logic = re.compile(r"_(bloc|event|state|cubit|repository|service|model)\.dart$|/models?/|/api_services/")

    def screens_for(rel, depth=0):
        if not is_logic.search(rel):
            return {rel}
        if depth > 1:
            return set()
        out = set()
        for imp in importers.get(os.path.basename(rel), ()):
            out |= screens_for(imp, depth + 1) if is_logic.search(imp) else {imp}
        return out

    repo_methods = {}
    for rel, src in files.items():
        if "repository" in rel or "api_services" in rel:
            repo_methods[rel] = [(m.group(1), m.start()) for m in DART_METHOD.finditer(src)]

    def callers_of(meth, exclude):
        pat = re.compile(rf"\.{re.escape(meth)}\s*\(")
        return sorted(r for r, s in files.items() if r != exclude and pat.search(s))

    def add(rel, line, uri, symbol, via, raw=None):
        call = {"client": "app", "file": rel, "line": line, "symbol": symbol, "method": None,
                "uri": uri, "raw": raw, "via": via, "client_routes": []}
        apply_override(call, overrides)
        sc = set()
        if rel in repo_methods and symbol:
            for c in callers_of(symbol, rel):
                sc |= screens_for(c)
        else:
            sc |= screens_for(rel)
        call["screens"] = sorted(s for s in sc if not re.search(r"(^|/)(route|routes)/|router\.dart$|main(_\w+)?\.dart$", s))
        calls.append(call)

    for rel, src in files.items():
        verbs = None
        for m in re.finditer(r"StringsConst\(\)\.(\w+)", src):
            if m.group(1) not in consts:
                continue
            uri = consts[m.group(1)][0]
            sym = enclosing_dart(repo_methods.get(rel), m.start())
            win = src[m.start(): m.start() + 200]
            verbs = re.search(r"MethodType\.(get|post|put|patch|delete)", win)
            add(rel, line_of(src, m.start()), uri, sym, f"StringsConst.{m.group(1)}")
            if verbs:
                calls[-1]["method"] = verbs.group(1).upper()
        for m in direct_re.finditer(src):
            if const_re.match(src, max(0, src.rfind("\n", 0, m.start()) + 1)) or src[max(0, m.start() - 80): m.start()].rstrip().endswith(("=", "=>")) and rel.endswith("strings_const.dart"):
                continue
            uri = norm_uri(m.group(1))
            if uri == "/{}":
                continue
            add(rel, line_of(src, m.start()), uri, enclosing_dart(repo_methods.get(rel), m.start()), "direct")
        for m in dyn_re.finditer(src):
            add(rel, line_of(src, m.start()), None, enclosing_dart(repo_methods.get(rel), m.start()), "dynamic",
                raw=f"baseUrl/${m.group(1)}")
    return calls


def enclosing_dart(methods, pos):
    if not methods:
        return None
    best = None
    for name, s in methods:
        if s <= pos:
            best = name
    return best


# ---------------------------------------------------------------- overrides / main

def load_overrides(out):
    p = os.path.join(out, "overrides.json")
    if not os.path.isfile(p):
        return []
    with open(p) as f:
        return json.load(f)


def apply_override(call, overrides):
    for o in overrides:
        if o.get("client") == call["client"] and o.get("file") == call["file"] and \
                (o.get("symbol") in (None, call["symbol"])) and (o.get("line") in (None, call["line"])):
            call["uri"] = norm_uri(o["uri"])
            call["method"] = o.get("method") or call["method"]
            call["override"] = o.get("note", True)
            return


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(docs_dir(), "api-links"))
    ap.add_argument("--stdout-summary", action="store_true")
    a = ap.parse_args()
    overrides = load_overrides(a.out)

    be = Backend()
    own_b, own_w, own_a = load_owner(BACKEND), load_owner(WEB), load_owner(APP)
    calls = web_calls(overrides) + app_calls(overrides)
    links, unmatched, hit = [], [], set()
    table_cache = {}
    for c in calls:
        res = be.match(c["method"], c["uri"]) if c["uri"] else None
        if not res:
            unmatched.append({k: c.get(k) for k in ("client", "file", "line", "symbol", "method", "uri", "raw", "via")})
            continue
        _, r, kind, method_ok = res
        rk = (r["route_file"], r["line"])
        hit.add(rk)
        if rk not in table_cache:
            table_cache[rk] = be.route_tables(r)
        owner = own_w if c["client"] == "web" else own_a
        links.append({
            "client": c["client"],
            "client_module": owner(c["file"]),
            "screens": c["screens"],
            "client_entry": {"file": c["file"], "line": c["line"], "symbol": c["symbol"],
                             "via": c.get("via"), "client_routes": c.get("client_routes", [])},
            "method": c["method"], "uri": c["uri"],
            "match": "override" if c.get("override") else kind,
            "method_ok": method_ok,
            "backend": {"methods": r["methods"], "uri": r["uri"], "controller": r["controller"], "action": r["action"],
                        "controller_file": r["controller_file"], "route": f"{r['route_file']}:{r['line']}",
                        "middleware": r["middleware"], "module": own_b(r["controller_file"])},
            "tables": table_cache[rk],
        })
    orphans = []
    for r in be.routes:
        if (r["route_file"], r["line"]) in hit:
            continue
        u = r["uri"].lower()
        hint = next((h for k, h in (("webhook", "webhook"), ("cron", "cron"), ("public", "public/partner"),
                                    ("external", "external partner"), ("test", "test"), ("ashokadashboard", "Ashoka dashboard"),
                                    ("research", "research dashboard"), ("turyaa", "Turyaa app"), ("reception", "receptionist"))
                     if k in u), "")
        orphans.append({"methods": r["methods"], "uri": r["uri"], "controller": r["controller"], "action": r["action"],
                        "route": f"{r['route_file']}:{r['line']}", "module": own_b(r["controller_file"]), "hint": hint})

    stamps = [stamp(x) for x in ("backend", "web", "app")]
    summary = {
        "client_calls": len(calls),
        "linked": len(links),
        "unmatched_client_calls": len(unmatched),
        "backend_routes": len(be.routes),
        "backend_routes_with_client": len(hit),
        "orphan_routes": len(orphans),
        "by_client": dict(collections.Counter(l["client"] for l in links)),
        "by_match": dict(collections.Counter(l["match"] for l in links)),
        "method_mismatches": sum(1 for l in links if not l["method_ok"]),
        "overrides_applied": sum(1 for l in links if l["match"] == "override"),
    }
    if a.stdout_summary:
        print(json.dumps(summary, indent=2))
        return
    os.makedirs(a.out, exist_ok=True)
    doc = {"schema_version": 1, "generated_by": "nt-documentation/link-apis",
           "generated_at": datetime.date.today().isoformat(), "sources": stamps, "summary": summary,
           "links": links, "unmatched_client_calls": unmatched, "orphan_routes": orphans}
    with open(os.path.join(a.out, "api-links.json"), "w") as f:
        json.dump(doc, f, indent=1)
    with open(os.path.join(a.out, "api-links.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["client", "client_module", "screens", "client_file", "client_symbol", "client_route", "method", "uri",
                    "match", "backend_route", "controller", "action", "backend_module", "tables"])
        for l in links:
            w.writerow([l["client"], l["client_module"] or "", ";".join(l["screens"]),
                        f"{l['client_entry']['file']}:{l['client_entry']['line']}", l["client_entry"]["symbol"] or "",
                        ";".join(l["client_entry"]["client_routes"]), l["method"] or "", l["uri"], l["match"],
                        l["backend"]["route"], (l["backend"]["controller"] or "").rsplit("\\", 1)[-1], l["backend"]["action"],
                        l["backend"]["module"] or "",
                        ";".join(f"{t['table']}[{t['connection'].split(' ')[0]}]{'(W)' if t['write'] else ''}@{t['level']}" for t in l["tables"])])
    write_md(a.out, doc)
    print(json.dumps(summary, indent=2))
    print(f"wrote {a.out}/api-links.json, api-links.csv, api-links.md")


def write_md(out, doc):
    s = doc["summary"]
    L = ["---", "generated_by: nt-documentation/link-apis", f"generated_at: {doc['generated_at']}", "sources:"]
    for st in doc["sources"]:
        L += [f"  - repo: {st['repo']}", f"    commit: {st['commit']}", f"    graph_stale: {str(st['graph_stale']).lower()}"]
    L += ["---", "", "# API links: screen → API → route → controller → tables", "",
          "> Generated by `scripts/link_apis.py` (static analysis). The full rows are in `api-links.csv` and `api-links.json`. "
          "Manual fixes go in `overrides.json`.", "",
          "## Summary", "", "| Metric | Value |", "|---|---|"]
    L += [f"| {k.replace('_', ' ')} | {v} |" for k, v in s.items()]
    by_mod = collections.defaultdict(lambda: collections.Counter())
    for l in doc["links"]:
        by_mod[l["backend"]["module"] or "(no module map)"][l["client"]] += 1
    L += ["", "## Client calls per backend module", "", "| Backend module | web | app |", "|---|---|---|"]
    for m, c in sorted(by_mod.items(), key=lambda kv: -sum(kv[1].values())):
        L.append(f"| `{m}` | {c.get('web', 0)} | {c.get('app', 0)} |")
    L += ["", f"## Unmatched client calls ({len(doc['unmatched_client_calls'])})", "",
          "Calls whose URI could not be resolved, or that match no backend route. The api-linker resolves these into `overrides.json`.", "",
          "| Client | File:line | Symbol | Method | URI / raw |", "|---|---|---|---|---|"]
    for u in doc["unmatched_client_calls"]:
        L.append(f"| {u['client']} | `{u['file']}:{u['line']}` | {u['symbol'] or ''} | {u['method'] or ''} | `{u['uri'] or u['raw']}` |")
    L += ["", f"## Backend routes with no known NT client ({len(doc['orphan_routes'])})", "",
          "These may be used by partners, crons, webhooks or the Turyaa or Ashoka dashboards, or they may be dead code. Check before treating any as unused.", ""]
    by = collections.defaultdict(list)
    for o in doc["orphan_routes"]:
        by[o["module"] or "(no module map)"].append(o)
    for m, rows in sorted(by.items(), key=lambda kv: -len(kv[1])):
        L += [f"### `{m}` ({len(rows)})", "", "| Method | URI | Controller@action | Hint | Route |", "|---|---|---|---|---|"]
        for o in rows:
            L.append(f"| {','.join(o['methods'])} | `{o['uri']}` | {(o['controller'] or '').rsplit(chr(92), 1)[-1]}@{o['action']} | {o['hint']} | `{o['route']}` |")
        L.append("")
    with open(os.path.join(out, "api-links.md"), "w") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
