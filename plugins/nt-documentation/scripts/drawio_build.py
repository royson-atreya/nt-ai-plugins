#!/usr/bin/env python3
"""Build draw.io diagrams from a small JSON spec, and generate specs from nt-docs data.

Usage:
  drawio_build.py build <spec.json> <out.drawio>       render a spec (validates it first)
  drawio_build.py spec-system [--out spec.json]         system diagram spec from module maps + api-links
  drawio_build.py spec-module <repo> <module-id> [--out spec.json]
                                                        module overview page spec (Screens -> APIs -> Services -> Tables -> External)
  drawio_build.py inspect <file.drawio>                 list pages, nodes (kind, label, source) and edges (for diagram-checker)

Spec format:
  {"title": str, "repos": ["backend", ...],               # repos stamped on every page
   "pages": [{"name": str, "rows": "stack"|"sequence",    # stack: nodes stack per lane; sequence: one row per node (flows)
              "lanes": [{"id": str, "label": str}],
              "nodes": [{"id", "label", "lane", "kind", "source"?, "status"?}],
              "edges": [{"from", "to", "label"?, "style"?: "call"|"data"|"async"}]}]}
  kind: client screen api controller service table db external area device step note
  status: "not-in-use" draws the node faded and dashed.
Env: NT_DOCS_DIR, NT_REPOS_DIR.
"""
import collections
import datetime
import json
import os
import re
import sys
from xml.sax.saxutils import escape, quoteattr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graph_query import stamp  # noqa: E402

KIND_STYLE = {
    "client": "rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;fontStyle=1;",
    "screen": "rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;",
    "api": "whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;",
    "controller": "whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;",
    "service": "whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;",
    "table": "shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=8;fillColor=#f5f5f5;strokeColor=#666666;",
    "db": "shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=12;fillColor=#f5f5f5;strokeColor=#666666;fontStyle=1;",
    "external": "rounded=1;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;dashed=1;",
    "area": "rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;fontStyle=1;",
    "device": "rounded=1;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;",
    "step": "rounded=1;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#333333;align=left;spacingLeft=8;",
    "note": "shape=note;whiteSpace=wrap;html=1;size=14;fillColor=#fff9c4;strokeColor=#c9b458;align=left;spacingLeft=6;",
}
EDGE_STYLE = {
    "call": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;",
    "data": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;dashed=1;endArrow=block;endFill=0;",
    "async": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;dashed=1;dashPattern=1 3;endArrow=open;",
}
LANE_W, NODE_W, NODE_H, GAP_X, GAP_Y, TOP = 240, 200, 54, 70, 18, 140
REPO_KEYS = {"backend": "Ashoka-World-Backend", "web": "Nadi-Tarangini-Frontend", "app": "Nadi-Tarangini-App"}


def docs_dir():
    return os.path.expanduser(os.environ.get("NT_DOCS_DIR", "~/atreya-ai/nt-docs"))


# ------------------------------------------------------------------ render

def validate(spec):
    errs = []
    if not spec.get("pages"):
        errs.append("spec has no pages")
    for p in spec.get("pages", []):
        lanes = {l["id"] for l in p.get("lanes", [])}
        ids = collections.Counter(n["id"] for n in p.get("nodes", []))
        errs += [f"page '{p.get('name')}': duplicate node id {i}" for i, c in ids.items() if c > 1]
        for n in p.get("nodes", []):
            if n.get("lane") not in lanes:
                errs.append(f"page '{p.get('name')}': node {n['id']} has unknown lane {n.get('lane')}")
            if n.get("kind") not in KIND_STYLE:
                errs.append(f"page '{p.get('name')}': node {n['id']} has unknown kind {n.get('kind')}")
        for e in p.get("edges", []):
            for end in ("from", "to"):
                if e.get(end) not in ids:
                    errs.append(f"page '{p.get('name')}': edge {e.get('from')}->{e.get('to')} references unknown node {e.get(end)}")
            if e.get("style", "call") not in EDGE_STYLE:
                errs.append(f"page '{p.get('name')}': edge style {e.get('style')} unknown")
    return errs


def label_html(text):
    return escape(str(text)).replace("\n", "<br>")


def render(spec):
    stamps = [stamp(r) for r in spec.get("repos", [])]
    stamp_txt = " | ".join(f"{s['repo']} @ {str(s['commit'])[:9]}" + (" (graph STALE)" if s["graph_stale"] else "") for s in stamps)
    gen = datetime.date.today().isoformat()
    out = ['<mxfile host="nt-documentation" agent="nt-documentation/diagram" type="device">']
    for pi, page in enumerate(spec["pages"]):
        pid = f"p{pi}"
        cells = [f'<mxCell id="{pid}-0"/>', f'<mxCell id="{pid}-1" parent="{pid}-0"/>']
        title = f"{spec.get('title', '')}: {page['name']}" if spec.get("title") else page["name"]
        cells.append(cell(f"{pid}-title", label_html(title), "text;html=1;fontSize=20;fontStyle=1;align=left;verticalAlign=middle;",
                          f"{pid}-1", 20, 10, 900, 36, attrs={"nt_kind": "title"}))
        stamp_attrs = {"nt_kind": "stamp", "nt_generated_at": gen,
                       "nt_sources": json.dumps([{k: s[k] for k in ("repo", "commit", "graph_commit", "graph_stale")} for s in stamps])}
        cells.append(cell(f"{pid}-nt-stamp", label_html(f"Source: {stamp_txt or 'n/a'} | generated {gen} by nt-documentation"),
                          "text;html=1;fontSize=11;fontColor=#666666;align=left;verticalAlign=middle;",
                          f"{pid}-1", 20, 46, 1100, 24, attrs=stamp_attrs))
        lanes = page["lanes"]
        by_lane = collections.defaultdict(list)
        for n in page["nodes"]:
            by_lane[n["lane"]].append(n)
        sequence = page.get("rows") == "sequence"
        rows = len(page["nodes"]) if sequence else max((len(v) for v in by_lane.values()), default=1)
        lane_h = 50 + rows * (NODE_H + (GAP_Y + 14 if sequence else GAP_Y)) + 20
        for li, lane in enumerate(lanes):
            lx = 20 + li * (LANE_W + GAP_X)
            lid = f"{pid}-lane-{lane['id']}"
            cells.append(cell(lid, label_html(lane["label"]),
                              "swimlane;startSize=30;html=1;fillColor=#f7f7f7;strokeColor=#bbbbbb;fontStyle=1;collapsible=0;",
                              f"{pid}-1", lx, TOP - 50, LANE_W, lane_h, attrs={"nt_kind": "lane"}))
        lane_index = {l["id"]: i for i, l in enumerate(lanes)}
        for row, n in enumerate(page["nodes"]):
            k = row if sequence else by_lane[n["lane"]].index(n)
            y = 40 + k * (NODE_H + (GAP_Y + 14 if sequence else GAP_Y))
            style = KIND_STYLE[n["kind"]]
            if n.get("status") == "not-in-use":
                style += "opacity=45;dashed=1;"
            attrs = {"nt_id": n["id"], "nt_kind": n["kind"]}
            if n.get("source"):
                attrs["nt_source"] = n["source"]
                attrs["tooltip"] = n["source"]
            if n.get("status"):
                attrs["nt_status"] = n["status"]
            cells.append(cell(f"{pid}-{n['id']}", label_html(n["label"]), style,
                              f"{pid}-lane-{n['lane']}", (LANE_W - NODE_W) / 2, y, NODE_W, NODE_H, attrs=attrs))
        for ei, e in enumerate(page.get("edges", [])):
            cells.append(
                f'<mxCell id="{pid}-e{ei}" value={quoteattr(label_html(e.get("label", "")))} '
                f'style={quoteattr(EDGE_STYLE[e.get("style", "call")] + "fontSize=10;labelBackgroundColor=#ffffff;")} '
                f'edge="1" parent="{pid}-1" source="{pid}-{e["from"]}" target="{pid}-{e["to"]}">'
                '<mxGeometry relative="1" as="geometry"/></mxCell>')
        legend_x = 20 + len(lanes) * (LANE_W + GAP_X)
        ly = TOP - 50
        cells.append(cell(f"{pid}-legend", "Legend", "text;html=1;fontStyle=1;align=left;", f"{pid}-1", legend_x, ly, 160, 20,
                          attrs={"nt_kind": "legend"}))
        used = sorted({n["kind"] for n in page["nodes"]})
        for i, kind in enumerate(used):
            cells.append(cell(f"{pid}-legend-{kind}", kind, KIND_STYLE[kind] + "fontSize=10;", f"{pid}-1",
                              legend_x, ly + 26 + i * 34, 120, 26, attrs={"nt_kind": "legend"}))
        w = legend_x + 200
        h = TOP + lane_h + 40
        out.append(f'<diagram id="{pid}" name={quoteattr(page["name"])}>'
                   f'<mxGraphModel dx="{w}" dy="{h}" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" '
                   f'fold="1" page="1" pageScale="1" pageWidth="{w}" pageHeight="{h}" math="0" shadow="0"><root>'
                   + "".join(cells) + "</root></mxGraphModel></diagram>")
    out.append("</mxfile>")
    return "\n".join(out)


def cell(cid, value, style, parent, x, y, w, h, attrs=None):
    geo = f'<mxGeometry x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" as="geometry"/>'
    if attrs:
        a = " ".join(f"{k}={quoteattr(str(v))}" for k, v in attrs.items())
        return (f'<UserObject id="{cid}" label={quoteattr(value)} {a}>'
                f'<mxCell style={quoteattr(style)} vertex="1" parent="{parent}">{geo}</mxCell></UserObject>')
    return f'<mxCell id="{cid}" value={quoteattr(value)} style={quoteattr(style)} vertex="1" parent="{parent}">{geo}</mxCell>'


# ------------------------------------------------------------------ spec generators

def load_json(path, what):
    if not os.path.isfile(path):
        sys.exit(f"error: {what} not found at {path}")
    with open(path) as f:
        return json.load(f)


def short(fqcn):
    return (fqcn or "").rsplit("\\", 1)[-1]


def spec_module(repo, module_id):
    from link_apis import Backend
    rname = REPO_KEYS.get(repo, repo)
    mm = load_json(os.path.join(docs_dir(), rname, "module-map.json"), f"{rname} module map (run map)")
    mod = next((m for m in mm["modules"] if m["id"] == module_id), None)
    if not mod:
        sys.exit(f"error: module '{module_id}' not in {rname} map; ids: {', '.join(m['id'] for m in mm['modules'])}")
    links_doc = load_json(os.path.join(docs_dir(), "api-links", "api-links.json"), "api-links.json (run link-apis)")
    links = links_doc["links"]
    nodes, edges = [], []

    def add(nid, label, lane, kind, source=None, status=None):
        if not any(n["id"] == nid for n in nodes):
            nodes.append({k: v for k, v in dict(id=nid, label=label, lane=lane, kind=kind, source=source, status=status).items() if v})
        return nid

    def cap(items, n):
        return items[:n], max(0, len(items) - n)

    if rname == "Ashoka-World-Backend":
        lanes = [{"id": "screens", "label": "Screens (web / app)"}, {"id": "apis", "label": "APIs by controller"},
                 {"id": "services", "label": "Services / repositories"}, {"id": "tables", "label": "Tables"},
                 {"id": "external", "label": "External systems"}]
        be = Backend()
        from module_map import owner
        routes = [r for r in be.routes if r["controller_file"] and owner(mm["modules"], r["controller_file"])[0] == module_id]
        mlinks = [l for l in links if l["backend"]["module"] == module_id]
        by_ctrl = collections.defaultdict(list)
        for r in routes:
            by_ctrl[r["controller"]].append(r)
        called = collections.Counter(l["backend"]["controller"] for l in mlinks)
        for ctrl, rs in sorted(by_ctrl.items(), key=lambda kv: -len(kv[1])):
            add("c-" + short(ctrl), f"{short(ctrl)}\n{len(rs)} routes, {called.get(ctrl, 0)} client calls", "apis", "controller",
                source=rs[0]["controller_file"])
        scr = collections.Counter()
        scr_ctrl = collections.defaultdict(collections.Counter)
        for l in mlinks:
            for s in l["screens"][:3]:
                key = (l["client"], s)
                scr[key] += 1
                scr_ctrl[key][l["backend"]["controller"]] += 1
        top, more = cap([k for k, _ in scr.most_common()], 18)
        for client, s in top:
            sid = "s-" + re.sub(r"\W+", "-", s)[-60:]
            add(sid, f"{client}: {os.path.basename(s).replace('.blade.php', '').replace('.dart', '')}", "screens", "screen", source=s)
            for ctrl, c in scr_ctrl[(client, s)].most_common(3):
                edges.append({"from": sid, "to": "c-" + short(ctrl), "label": f"{c} call{'s' if c > 1 else ''}"})
        if more:
            add("s-more", f"+{more} more screens\n(see api-links.csv)", "screens", "note")
        tables = collections.defaultdict(lambda: {"write": False, "ctrls": set(), "level": set()})
        services = collections.defaultdict(set)
        for r in routes:
            for t in be.route_tables(r):
                key = (t["table"], t["connection"])
                tables[key]["write"] |= t["write"]
                tables[key]["level"].add(t["level"])
                tables[key]["ctrls"].add(r["controller"])
                if t.get("via"):
                    services[t["via"]].add(r["controller"])
        for srel, ctrls in sorted(services.items())[:12]:
            sid = "v-" + os.path.basename(srel)[:-4]
            add(sid, os.path.basename(srel)[:-4], "services", "service", source=srel)
            for c in ctrls:
                edges.append({"from": "c-" + short(c), "to": sid})
        ranked = sorted(tables.items(), key=lambda kv: ("file" in kv[1]["level"] and len(kv[1]["level"]) == 1, -len(kv[1]["ctrls"])))
        top_t, more_t = cap(ranked, 22)
        for (t, conn), info in top_t:
            tid = "t-" + t
            add(tid, f"{t}\n[{conn.split(' ')[0]}]" + (" (W)" if info["write"] else ""), "tables", "table")
            for c in sorted(info["ctrls"])[:2]:
                edges.append({"from": "c-" + short(c), "to": tid, "style": "data"})
        if more_t:
            add("t-more", f"+{more_t} more tables\n(see modules/{module_id}.md 2.2)", "tables", "note")
        for x in mod.get("external_systems", []):
            add("x-" + re.sub(r"\W+", "-", x), x, "external", "external")
        if mod.get("external_systems"):
            add("x-note", f"Call sites: modules/{module_id}.md section 2.3", "external", "note")
        repos = ["backend", "web", "app"]
    else:
        client = "web" if rname == "Nadi-Tarangini-Frontend" else "app"
        lanes = [{"id": "screens", "label": "Screens"}, {"id": "logic", "label": "Client logic"},
                 {"id": "apis", "label": "Backend APIs"}, {"id": "backend", "label": "Backend modules"}]
        mlinks = [l for l in links if l["client"] == client and l["client_module"] == module_id]
        logic = collections.Counter(l["client_entry"]["file"] for l in mlinks)
        for f, c in logic.most_common(14):
            lid = "l-" + re.sub(r"\W+", "-", f)[-60:]
            add(lid, f"{os.path.basename(f)}\n{c} API calls", "logic", "controller" if client == "web" else "service", source=f)
        scr = collections.Counter((s, l["client_entry"]["file"]) for l in mlinks for s in l["screens"][:3])
        for (s, f), c in scr.most_common(16):
            sid = "s-" + re.sub(r"\W+", "-", s)[-60:]
            add(sid, os.path.basename(s).replace(".blade.php", "").replace(".dart", ""), "screens", "screen", source=s)
            lid = "l-" + re.sub(r"\W+", "-", f)[-60:]
            if any(n["id"] == lid for n in nodes):
                edges.append({"from": sid, "to": lid})
        apis = collections.Counter((l["backend"]["controller"], l["backend"]["module"]) for l in mlinks)
        for (ctrl, bmod), c in apis.most_common(16):
            aid = "a-" + short(ctrl)
            add(aid, f"{short(ctrl)}\n{c} calls", "apis", "api")
            bid = "b-" + (bmod or "unmapped")
            add(bid, bmod or "(no backend module)", "backend", "area")
            edges.append({"from": aid, "to": bid, "style": "data"})
            for f in {l["client_entry"]["file"] for l in mlinks if l["backend"]["controller"] == ctrl}:
                lid = "l-" + re.sub(r"\W+", "-", f)[-60:]
                if any(n["id"] == lid for n in nodes):
                    edges.append({"from": lid, "to": aid})
        repos = [repo if repo in REPO_KEYS else {v: k for k, v in REPO_KEYS.items()}[rname], "backend"]
    edges = [dict(t) for t in {tuple(sorted(e.items())) for e in edges}]
    return {"title": f"{mod['name']} ({rname})", "repos": repos,
            "pages": [{"name": "Overview", "rows": "stack", "lanes": lanes, "nodes": nodes, "edges": edges}]}


def spec_system():
    from link_apis import Backend
    links_doc = load_json(os.path.join(docs_dir(), "api-links", "api-links.json"), "api-links.json (run link-apis)")
    bmap = load_json(os.path.join(docs_dir(), "Ashoka-World-Backend", "module-map.json"), "backend module map (run map backend)")
    area_of = {m["id"]: m["product_area"] for m in bmap["modules"]}
    status_of = collections.defaultdict(set)
    for m in bmap["modules"]:
        status_of[m["product_area"]].add(m["status"])
    lanes = [{"id": "clients", "label": "Clients"}, {"id": "areas", "label": "Backend (Ashoka-World-Backend) product areas"},
             {"id": "data", "label": "Databases"}, {"id": "external", "label": "External systems"}]
    nodes = [{"id": "web", "label": "Web app\nNadi-Tarangini-Frontend\n(Laravel 8 + Blade)", "lane": "clients", "kind": "client"},
             {"id": "app", "label": "Mobile app\nNadi-Tarangini-App\n(Flutter + BLoC)", "lane": "clients", "kind": "client"},
             {"id": "device", "label": "Nadi device\n(BLE / Web Serial)", "lane": "clients", "kind": "device"}]
    edges = [{"from": "device", "to": "app", "label": "BLE", "style": "async"}, {"from": "device", "to": "web", "label": "Web Serial/BLE", "style": "async"}]
    hints = collections.Counter(o["hint"] for o in links_doc["orphan_routes"] if o["hint"])
    other_clients = {"Ashoka dashboard": "ashoka", "Turyaa app": "turyaa", "public/partner": "partner", "external partner": "partner"}
    for hint, nid in other_clients.items():
        if hints.get(hint) and not any(n["id"] == nid for n in nodes):
            label = {"ashoka": "Ashoka dashboard", "turyaa": "Turyaa app", "partner": "Partner / public API users"}[nid]
            nodes.append({"id": nid, "label": f"{label}\n(inferred from route prefixes)", "lane": "clients", "kind": "client"})
    area_routes = collections.Counter()
    be = Backend()
    from module_map import owner
    conn_by_area = collections.defaultdict(collections.Counter)
    for r in be.routes:
        mid = owner(bmap["modules"], r["controller_file"])[0] if r["controller_file"] else None
        area = area_of.get(mid, "Unmapped")
        area_routes[area] += 1
        for t in be.route_tables(r):
            if t["level"] != "file":
                conn_by_area[area][t["connection"].split(" ")[0]] += 1
    for area, c in sorted(area_routes.items(), key=lambda kv: -kv[1]):
        status = "not-in-use" if status_of.get(area) == {"not-in-use"} else None
        nodes.append({"id": "area-" + area, "label": f"{area}\n{c} routes", "lane": "areas", "kind": "area",
                      **({"status": status} if status else {})})
    for client in ("web", "app"):
        per = collections.Counter(area_of.get(l["backend"]["module"], "Unmapped") for l in links_doc["links"] if l["client"] == client)
        for area, c in per.most_common():
            edges.append({"from": client, "to": "area-" + area, "label": f"{c} calls"})
    for o in links_doc["orphan_routes"]:
        nid = {"Ashoka dashboard": "ashoka", "Turyaa app": "turyaa", "public/partner": "partner", "external partner": "partner"}.get(o["hint"])
        if nid:
            hints[(nid, area_of.get(o["module"], "Unmapped"))] += 1
    for key, c in list(hints.items()):
        if isinstance(key, tuple):
            edges.append({"from": key[0], "to": "area-" + key[1], "label": f"{c} routes (inferred)", "style": "data"})
    for conn in ("mysql", "turyaa_db", "samvit_chakra_db"):
        nodes.append({"id": "db-" + conn, "label": conn, "lane": "data", "kind": "db"})
    for area, conns in conn_by_area.items():
        for conn, c in conns.items():
            if "db-" + conn in {n["id"] for n in nodes}:
                edges.append({"from": "area-" + area, "to": "db-" + conn, "label": f"{c}", "style": "data"})
    ext = collections.defaultdict(set)
    for m in bmap["modules"]:
        for x in m.get("external_systems", []):
            ext[x].add(m["product_area"])
    ref = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "references", "external-systems.md")
    with open(ref) as f:
        headings = [h.strip() for h in re.findall(r"^## (.+)$", f.read(), re.M) if not h.lower().startswith(("others", "second"))]
    for h in headings:
        nodes.append({"id": "x-" + re.sub(r"\W+", "-", h).strip("-").lower(), "label": h, "lane": "external", "kind": "external"})
    xids = {n["label"]: n["id"] for n in nodes if n["kind"] == "external"}
    for x, areas in ext.items():
        xid = next((v for k, v in xids.items() if x.lower() in k.lower() or k.lower().startswith(x.lower())), None)
        if not xid:
            xid = "x-" + re.sub(r"\W+", "-", x).lower()
            nodes.append({"id": xid, "label": x, "lane": "external", "kind": "external"})
            xids[x] = xid
        for a in areas:
            edges.append({"from": "area-" + a, "to": xid, "style": "async"})
    node_ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["from"] in node_ids and e["to"] in node_ids]
    return {"title": "Nadi Tarangini system", "repos": ["backend", "web", "app"],
            "pages": [{"name": "System overview", "rows": "stack", "lanes": lanes, "nodes": nodes, "edges": edges}]}


# ------------------------------------------------------------------ inspect

def inspect(path):
    with open(path) as f:
        xml = f.read()
    for dm in re.finditer(r'<diagram id="([^"]+)" name="([^"]*)">(.*?)</diagram>', xml, re.S):
        body = dm.group(3)
        print(f"# page: {dm.group(2)}")
        st = re.search(r'nt_kind="stamp"[^>]*nt_sources="([^"]*)"', body) or re.search(r'nt_sources="([^"]*)"[^>]*nt_kind="stamp"', body)
        if st:
            print("stamp:", st.group(1).replace("&quot;", '"'))
        ids = {}
        for m in re.finditer(r"<UserObject ([^>]*)>", body):
            attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
            if attrs.get("nt_id"):
                ids[attrs["id"]] = attrs
                lbl = re.sub(r"&lt;br&gt;|<br>", " / ", attrs.get("label", "")).replace("&amp;", "&")
                print(f"node {attrs['nt_id']:<28} {attrs.get('nt_kind', ''):<10} {lbl:<60} src={attrs.get('nt_source', '-')}")
        for m in re.finditer(r'<mxCell id="[^"]+" value="([^"]*)"[^>]*edge="1"[^>]*source="([^"]+)" target="([^"]+)"', body):
            s, t = ids.get(m.group(2), {}).get("nt_id", m.group(2)), ids.get(m.group(3), {}).get("nt_id", m.group(3))
            print(f"edge {s} -> {t}  {m.group(1)}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    cmd, args = sys.argv[1], sys.argv[2:]
    out = None
    if "--out" in args:
        i = args.index("--out")
        out = args[i + 1]
        args = args[:i] + args[i + 2:]
    if cmd == "build":
        with open(args[0]) as f:
            spec = json.load(f)
        errs = validate(spec)
        if errs:
            print("\n".join("ERROR " + e for e in errs))
            sys.exit(1)
        os.makedirs(os.path.dirname(os.path.abspath(args[1])), exist_ok=True)
        with open(args[1], "w") as f:
            f.write(render(spec))
        print(f"wrote {args[1]} ({len(spec['pages'])} page(s), {sum(len(p['nodes']) for p in spec['pages'])} nodes)")
    elif cmd in ("spec-system", "spec-module"):
        spec = spec_system() if cmd == "spec-system" else spec_module(args[0], args[1])
        text = json.dumps(spec, indent=1)
        if out:
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            with open(out, "w") as f:
                f.write(text)
            print(f"wrote {out}")
        else:
            print(text)
    elif cmd == "inspect":
        inspect(args[0])
    else:
        sys.exit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
