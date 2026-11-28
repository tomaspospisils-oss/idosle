#!/usr/bin/env python3
"""IDOSle builder: GTFS (PID) -> index.html s vloženými daty.
Použití:  python3 build.py cesta/k/GTFS [--types 0,1,2,3] [--zone-regions 1,2] [--night] [--contact kontakt] [--server] [--merge-dist 500] [--days 30] [--puzzles puzzles.json] [--updated 23.11.2026] [-o index.html]
          python3 build.py --demo          (malá ukázková síť)"""
import csv, json, sys, os, argparse, zipfile, io, zlib, random, datetime
from collections import deque
sys.setrecursionlimit(10000)
HERE = os.path.dirname(os.path.abspath(__file__))
TYPE_COLOR = {0: "#C0392B", 1: "#2E7D32", 2: "#6A1B9A", 3: "#1565C0", 4: "#00838F", 7: "#8D6E63", 11: "#EF6C00"}

def rd(src, name):
    if zipfile.is_zipfile(src) if os.path.isfile(src) else False:
        z = zipfile.ZipFile(src); n = [x for x in z.namelist() if x.endswith(name)][0]
        f = io.TextIOWrapper(z.open(n), encoding="utf-8-sig", newline="")
    else:
        f = open(os.path.join(src, name), encoding="utf-8-sig", newline="")
    return csv.DictReader(f)

def cluster_stops(names, ll, node, dist):
    """sid -> zobrazený název. Nástupiště se stejným názvem se slučují do jedné zastávky, jen když jsou blízko
    (do dist metrů, řetězově) nebo mají stejné asw_node_id. Stejnojmenné zastávky jinde jsou samostatné a dostanou
    k názvu dodatek se vzdáleností a směrem od centra Prahy, např. „Nádraží (31 km Z od Prahy)“."""
    import math
    cy, cx = 50.0755, 14.4378
    def meters(p, q): return math.hypot((p[1] - q[1]) * math.cos(math.radians(p[0])) * 111320, (p[0] - q[0]) * 110540)
    def where(p):
        dx = (p[1] - cx) * math.cos(math.radians(cy)) * 111320; dy = (p[0] - cy) * 110540
        dirs = ["V", "SV", "S", "SZ", "Z", "JZ", "J", "JV"]
        return f"{round(math.hypot(dx, dy) / 1000)} km {dirs[round(math.degrees(math.atan2(dy, dx)) / 45) % 8]} od Prahy"
    by = {}
    for sid, n in names.items(): by.setdefault(n, []).append(sid)
    disp, many, used = {}, 0, set()
    for n, sids in sorted(by.items()):
        pts = sorted((s for s in sids if s in ll), key=lambda s: ll[s]); par = {s: s for s in pts}
        def f(x):
            while par[x] != x: par[x] = par[par[x]]; x = par[x]
            return x
        for i, a in enumerate(pts):
            for c in pts[i + 1:]:
                if meters(ll[a], ll[c]) <= dist or (node.get(a) and node.get(a) == node.get(c)): par[f(a)] = f(c)
        groups = {}
        for s in pts: groups.setdefault(f(s), []).append(s)
        groups = sorted(groups.values(), key=lambda g: ll[g[0]])
        if len(groups) > 1: many += 1
        for g in groups:
            if len(groups) == 1: label = n
            else:
                la = sum(ll[s][0] for s in g) / len(g); lo = sum(ll[s][1] for s in g) / len(g)
                label = f"{n} ({where((la, lo))})"
            while label in used: label += "'"   # pojistka proti shodě
            used.add(label)
            for s in g: disp[s] = label
        for s in sids:                          # nástupiště bez souřadnic: k první skupině
            if s not in disp: disp[s] = disp[pts[0]] if pts else n
    if many: print(f"stejnojmenné zastávky rozlišeny: {many} názvů (sloučení do {dist:g} m)")
    return disp

def from_gtfs(src, types, regions=None, night=False, merge_dist=500):
    # night: vyřadí linky, které mají v routes.txt is_night = 1
    names, reg, ll, node = {}, {}, {}, {}
    for r in rd(src, "stops.txt"):
        node[r["stop_id"]] = (r.get("asw_node_id") or "").strip(); names[r["stop_id"]] = r["stop_name"]; reg[r["stop_id"]] = (r.get("zone_region_type") or "").strip()
        try: ll[r["stop_id"]] = (float(r["stop_lat"]), float(r["stop_lon"]))
        except (KeyError, ValueError): pass
    from collections import Counter
    disp = cluster_stops(names, ll, node, merge_dist)
    print("zone_region_type ve stops.txt:", dict(Counter(reg.values())))
    # regions=None -> bez filtru; jinak jen zastávky s danou hodnotou (neznámé stop_id se vyřadí)
    keep = lambda sid: regions is None or reg.get(sid) in regions
    routes = {r["route_id"]: r for r in rd(src, "routes.txt")}
    seqs = {}
    for r in rd(src, "route_stops.txt"):
        seqs.setdefault((r["route_id"], r["direction_id"]), []).append((int(r["stop_sequence"]), r["stop_id"]))
    stops, sidx, lines, acc = [], {}, {}, {}
    if night and routes and "is_night" not in next(iter(routes.values())):
        sys.exit("--night: routes.txt nemá sloupec is_night")
    dropped = set()
    def si(sid):
        n = disp.get(sid, sid)  # nástupiště téže zastávky = jedna zastávka; stejnojmenné jinde = jiná
        if n not in sidx: sidx[n] = len(stops); stops.append(n)
        if sid in ll: acc.setdefault(n, []).append(ll[sid])
        return sidx[n]
    for (rid, _d), v in sorted(seqs.items()):
        ro = routes.get(rid)
        if not ro or int(ro["route_type"]) not in types: continue
        if night and (ro.get("is_night") or "").strip() == "1":
            dropped.add(ro["route_short_name"]); continue
        seq = [si(s) for _, s in sorted(v) if keep(s)]
        seq = [x for i, x in enumerate(seq) if i == 0 or x != seq[i-1]]
        if len(seq) < 2: continue
        key = (ro["route_short_name"], ro["route_type"])
        col = "#" + ro["route_color"] if ro.get("route_color") else TYPE_COLOR.get(int(ro["route_type"]), "#555")
        l = lines.setdefault(key, {"n": ro["route_short_name"], "c": col, "t": int(ro["route_type"]), "d": []})
        if seq not in l["d"]: l["d"].append(seq)
    if night: print(f"--night: vyřazeno nočních linek: {len(dropped)}")
    # souřadnice zastávky = průměr souřadnic všech jejích nástupišť (stejný název)
    xy = [[round(sum(p[0] for p in acc[n]) / len(acc[n]), 5), round(sum(p[1] for p in acc[n]) / len(acc[n]), 5)] if n in acc else None for n in stops]
    return {"stops": stops, "xy": xy, "lines": list(lines.values())}

XYD = {}
for _r in """Nemocnice Motol|50.0746|14.3395;Petřiny|50.0833|14.3545;Nádraží Veleslavín|50.0888|14.3586;Bořislavka|50.0975|14.3735;Dejvická|50.1004|14.3944;Hradčanská|50.0971|14.4041;Malostranská|50.0911|14.4094;Staroměstská|50.0881|14.4172;Můstek|50.0838|14.4242;Muzeum|50.0790|14.4305;Náměstí Míru|50.0751|14.4375;Jiřího z Poděbrad|50.0777|14.4490;Flora|50.0777|14.4617;Želivského|50.0782|14.4741;Strašnická|50.0734|14.4902;Skalka|50.0693|14.5066;Depo Hostivař|50.0732|14.5203;Zličín|50.0536|14.2735;Stodůlky|50.0469|14.2987;Luka|50.0452|14.3186;Lužiny|50.0455|14.3317;Hůrka|50.0477|14.3441;Nové Butovice|50.0510|14.3523;Jinonice|50.0546|14.3711;Radlická|50.0587|14.3881;Smíchovské nádraží|50.0614|14.4100;Anděl|50.0707|14.4032;Karlovo náměstí|50.0759|14.4187;Národní třída|50.0803|14.4204;Náměstí Republiky|50.0902|14.4290;Florenc|50.0905|14.4396;Křižíkova|50.0921|14.4506;Invalidovna|50.0951|14.4617;Palmovka|50.1032|14.4741;Českomoravská|50.1060|14.4930;Vysočanská|50.1103|14.5026;Kolbenova|50.1105|14.5164;Hloubětín|50.1070|14.5384;Rajská zahrada|50.1066|14.5594;Černý Most|50.1086|14.5737;Letňany|50.1307|14.5138;Prosek|50.1254|14.5011;Střížkov|50.1260|14.4806;Ládví|50.1269|14.4691;Kobylisy|50.1255|14.4535;Nádraží Holešovice|50.1096|14.4403;Vltavská|50.1000|14.4390;Hlavní nádraží|50.0832|14.4349;I. P. Pavlova|50.0750|14.4300;Vyšehrad|50.0617|14.4300;Pražského povstání|50.0557|14.4351;Pankrác|50.0513|14.4390;Budějovická|50.0445|14.4490;Kačerov|50.0420|14.4519;Roztyly|50.0334|14.4770;Chodov|50.0316|14.4909;Opatov|50.0285|14.5069;Háje|50.0305|14.5278""".split(";"):
    _n, _a, _o = _r.split("|"); XYD[_n] = (float(_a), float(_o))  # přibližné souřadnice, jen pro demo

def demo():
    A = "Nemocnice Motol,Petřiny,Nádraží Veleslavín,Bořislavka,Dejvická,Hradčanská,Malostranská,Staroměstská,Můstek,Muzeum,Náměstí Míru,Jiřího z Poděbrad,Flora,Želivského,Strašnická,Skalka,Depo Hostivař"
    B = "Zličín,Stodůlky,Luka,Lužiny,Hůrka,Nové Butovice,Jinonice,Radlická,Smíchovské nádraží,Anděl,Karlovo náměstí,Národní třída,Můstek,Náměstí Republiky,Florenc,Křižíkova,Invalidovna,Palmovka,Českomoravská,Vysočanská,Kolbenova,Hloubětín,Rajská zahrada,Černý Most"
    C = "Letňany,Prosek,Střížkov,Ládví,Kobylisy,Nádraží Holešovice,Vltavská,Florenc,Hlavní nádraží,Muzeum,I. P. Pavlova,Vyšehrad,Pražského povstání,Pankrác,Budějovická,Kačerov,Roztyly,Chodov,Opatov,Háje"
    X = ["T1|Anděl,Karlovo náměstí,I. P. Pavlova,Náměstí Míru,Flora",
         "T2|Dejvická,Vltavská,Náměstí Republiky,Palmovka",
         "T3|Hradčanská,Nádraží Holešovice,Ládví",
         "T4|Smíchovské nádraží,Anděl,Malostranská,Staroměstská,Náměstí Republiky,Křižíkova",
         "T5|Pankrác,Budějovická,Karlovo náměstí,Národní třída,Můstek,Muzeum",
         "T6|Skalka,Strašnická,Chodov,Háje"]
    defs = [("A", "#00A562", 1, A), ("B", "#F8B322", 1, B), ("C", "#CF003D", 1, C)] + \
           [(x.split("|")[0], "#1565C0", 0, x.split("|")[1]) for x in X]
    stops, idx, lines = [], {}, []
    for n, c, t, s in defs:
        q = []
        for nm in s.split(","):
            if nm not in idx: idx[nm] = len(stops); stops.append(nm)
            q.append(idx[nm])
        lines.append({"n": n, "c": c, "t": t, "d": [q, q[::-1]]})
    return {"stops": stops, "xy": [list(XYD[n]) for n in stops], "lines": lines}

def graph(data):
    reach, at = [], [[] for _ in data["stops"]]
    for li, l in enumerate(data["lines"]):
        m = {}
        for q in l["d"]:
            for i in range(len(q) - 1):
                m.setdefault(q[i], set()).update(x for x in q[i+1:] if x != q[i])
        reach.append({k: sorted(v) for k, v in m.items()})
        for k in m: at[k].append(li)
    return reach, at

def rev_graph(reach, ns):
    """radj[t] = zastávky, ze kterých se do t dá dojet jedním spojem."""
    radj = [set() for _ in range(ns)]
    for m in reach:
        for x, ts in m.items():
            for t in ts: radj[t].add(x)
    return radj

def dist_to(radj, b):
    """h[x] = nejmenší počet spojů z x do b při zanedbání omezení (dolní mez, přípustná), -1 = nedojede."""
    h = [-1] * len(radj); h[b] = 0; q = deque([b])
    while q:
        t = q.popleft()
        for x in radj[t]:
            if h[x] < 0: h[x] = h[t] + 1; q.append(x)
    return h

def shortest(reach, at, h, a, b, cap=40):
    """PŘESNÁ nejkratší trasa (počet spojů) podle pravidel hry: každá linka max 1x, přestupní zastávka (ani start) se neopakuje.
    Postupné prohlubování limitu od h[a]; prohledávání do hloubky se ořezává odhadem h (zbývá-li víc spojů, než limit dovolí).
    Odhad je dolní mez, takže první limit, při kterém se trasa najde, je optimum. Vrací [(linka, zastávka), ...] nebo None."""
    if a == b or h[a] < 1: return None
    for limit in range(h[a], cap + 1):
        used, vis, path = set(), {a}, []
        def dfs(c, d):
            r = limit - d
            if r < 1: return False
            for l in at[c]:
                if l in used: continue
                used.add(l)
                for t in reach[l][c]:
                    if t == b: path.append((l, t)); return True
                    if t in vis or h[t] < 0 or h[t] > r - 1: continue
                    vis.add(t); path.append((l, t))
                    if dfs(t, d + 1): return True
                    path.pop(); vis.discard(t)
                used.discard(l)
            return False
        if dfs(a, 0): return path
    return None

def reachable(reach, at, a, b):
    """Přesná kontrola, že se z a dá do b dojet (bez limitu uzlů, na datech nezávislá náhoda)."""
    seen = {a}; st = [a]
    while st:
        x = st.pop()
        for l in at[x]:
            for t in reach[l][x]:
                if t == b: return True
                if t not in seen: seen.add(t); st.append(t)
    return False

def pin_puzzles(data, path, days, lo=3, hi=6):
    """Zadání dne se jednou vylosuje a uloží do puzzles.json jako [start, cíl, optimum]. Losuje se dvojice, jejíž nejkratší trasa má
    lo až hi spojů. Dvojice zůstává při dalších buildech (i s novými daty PID) beze změny, přelosuje se jen když zastávka zmizela
    nebo do cíle už nejde dojet. Optimum se při každém buildu přepočítá podle aktuálních dat, aby vždy platilo."""
    pinned = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    reach, at = graph(data); ns = len(data["stops"]); radj = rev_graph(reach, ns); idx = {n: i for i, n in enumerate(data["stops"])}
    ok = [i for i, x in enumerate(at) if x]; today = datetime.date.today(); new = upd = 0
    for k in range(days):
        d = (today + datetime.timedelta(days=k)).isoformat(); seed = zlib.crc32(d.encode())
        p = pinned.get(d)
        if p and p[0] in idx and p[1] in idx and p[0] != p[1]:
            a, b = idx[p[0]], idx[p[1]]; s = shortest(reach, at, dist_to(radj, b), a, b)
            if s:
                if len(p) < 3 or p[2] != len(s): upd += 1
                pinned[d] = [p[0], p[1], len(s)]; continue
        if p: print(f"  zadání {d} ({p[0]} -> {p[1]}) už v datech nejde hrát, losuji nové")
        rng = random.Random(seed); pair = None; far = None
        for _ in range(40):
            if not ok: break
            b = rng.choice(ok); h = dist_to(radj, b)
            cand = [a for a in ok if lo <= h[a] <= hi]
            if cand: pair = (rng.choice(cand), b); break
            m = max((h[a], a) for a in ok); far = far if far and far[2] >= m[0] else (m[1], b, m[0])
        pair = pair or (far[:2] if far and far[2] >= 1 else None)
        if pair:
            s = shortest(reach, at, dist_to(radj, pair[1]), pair[0], pair[1])
            if s: pinned[d] = [data["stops"][pair[0]], data["stops"][pair[1]], len(s)]; new += 1
    json.dump(pinned, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print(f"zadání: {len(pinned)} připnuto v {os.path.basename(path)} ({new} nových, {upd} s přepočítaným optimem)")
    return pinned

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("src", nargs="?"); p.add_argument("--demo", action="store_true")
    p.add_argument("--updated", default=None, help="datum aktualizace spojů (DD.MM.RRRR), výchozí = dnes")
    p.add_argument("--night", action="store_true", help="vyřadí noční linky (routes.txt: is_night = 1)")
    p.add_argument("--puzzles", default=None, help="soubor s připnutými zadáními (výchozí puzzles.json vedle build.py, s --server data/puzzles.json)")
    p.add_argument("--contact", default=None, help="kontakt (e-mail/odkaz) pro žádosti o smazání údajů; zobrazí se v okně o ochraně soukromí")
    p.add_argument("--server", action="store_true", help="ostrý provoz: zadání se do stránky NEvkládá, stránka si dnešní zadání bere ze serveru (api/puzzle.js, datum podle serveru)")
    p.add_argument("--days", type=int, default=30, help="na kolik dní dopředu zadání připnout (výchozí 30)")
    p.add_argument("--merge-dist", type=float, default=500, help="do jaké vzdálenosti (m) se stejnojmenná nástupiště slučují do jedné zastávky (výchozí 500)")
    p.add_argument("--types", default="0,1,2,3")
    p.add_argument("--zone-regions", default=None, help="hodnoty zone_region_type ke ponechání, např. 1 nebo 1,2"); p.add_argument("-o", default=None, help="výstup (výchozí index.html, s --server public/index.html)")
    a = p.parse_args()
    if a.server and a.demo: sys.exit("--server nejde s --demo (nejsou připnutá zadání)")
    a.o = a.o or os.path.join(HERE, "public", "index.html") if a.server else (a.o or "index.html")
    a.puzzles = a.puzzles or os.path.join(HERE, "data" if a.server else "", "puzzles.json")
    for f in (a.o, a.puzzles): os.makedirs(os.path.dirname(os.path.abspath(f)), exist_ok=True)
    data = demo() if a.demo else from_gtfs(a.src, {int(x) for x in a.types.split(",")}, {x.strip() for x in a.zone_regions.split(",")} if a.zone_regions else None, a.night, a.merge_dist)
    import hashlib   # verze dat: stránka ji posílá s výsledkem, server odmítne výsledek z jiné verze dat
    data["ver"] = hashlib.sha1(json.dumps([data["stops"], [[l["n"], l["t"], l["d"]] for l in data["lines"]]], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()[:10]
    if a.contact: data["contact"] = a.contact
    if a.demo: data["demo"] = True   # ukázka: žebříček je jen nasimulovaný v prohlížeči
    if not a.demo:
        keep = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()  # do stránky jen aktuální a budoucí dny
        pz = pin_puzzles(data, a.puzzles, a.days)
        if a.server:   # server si pro ověření výsledků do žebříčku nechá kopii grafu (data/graph.json), ve stránce není
            gp = os.path.join(os.path.dirname(os.path.abspath(a.puzzles)), "graph.json")
            json.dump({"ver": data["ver"], "stops": data["stops"], "lines": [{"n": l["n"], "t": l["t"], "d": l["d"]} for l in data["lines"]]}, open(gp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
            data["api"] = "/api/puzzle"   # zadání zůstane jen na serveru (data/puzzles.json), ve stránce není
        else: data["puzzles"] = {k: v for k, v in pz.items() if k >= keep}
    tpl = open(os.path.join(HERE, "idosle_template.html"), encoding="utf-8").read()
    import datetime
    upd = a.updated or datetime.date.today().strftime("%d.%m.%Y")
    open(a.o, "w", encoding="utf-8").write(tpl.replace("__UPDATED__", upd).replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":"))))
    print(f"{len(data['stops'])} zastávek, {len(data['lines'])} linek -> {a.o}")