#!/usr/bin/env python3
"""SafeDSE front-end: XML inputs -> MiniZinc data file.

Phase 1 pipeline (C.6), with steps 2 and 6 not yet present:

    parse  ->  [pattern superposition -- Phase 4]  ->  SDF->HSDF unfold
           ->  platform catalogue expansion  ->  [communication -- Phase 6]
           ->  emit .dzn

Usage:
    build_dzn.py --app a.sdf3.xml [--app b.sdf3.xml ...] \
                 --platform platform.xml --wcets WCETs.xml \
                 [--constraints desConst.xml] [--safety safety.xml] \
                 -o out.dzn
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hsdf import HSDFGraph, check_unfolding, unfold          # noqa: E402
from platform import Platform, parse_platform                # noqa: E402
from sdf3 import WCETTable, parse_design_constraints, parse_sdf3  # noqa: E402


# --------------------------------------------------------------------------
def mzn_array(vals) -> str:
    return "[" + ", ".join(str(v) for v in vals) + "]"


def mzn_matrix(rows, base1: int = 1, base2: int = 1) -> str:
    if not rows:
        return "array2d(1..0, 1..0, [])"
    body = "\n     | ".join(", ".join(str(v) for v in r) for r in rows)
    return "[| " + body + " |]"


def mzn_str_array(vals) -> str:
    return "[" + ", ".join('"%s"' % v for v in vals) + "]"


# --------------------------------------------------------------------------
def min_token_path(n: int, tok: list[list[int]], src: int) -> list[int]:
    """Shortest path from src measured in INITIAL TOKENS (Dijkstra, tiny graph).

    rho(s,d) is the pipeline depth between two actors: how many iterations of
    delay separate them. It is a property of the application graph alone --
    serialisation edges added by the schedule carry no tokens, so no mapping
    can shorten a token-path.  Computing it in the front-end keeps the CP model
    free of it entirely.
    """
    INF = float("inf")
    dist = [INF] * n
    dist[src] = 0
    seen = [False] * n
    for _ in range(n):
        u, best = -1, INF
        for k in range(n):
            if not seen[k] and dist[k] < best:
                u, best = k, dist[k]
        if u < 0:
            break
        seen[u] = True
        for v in range(n):
            if tok[u][v] >= 0 and dist[u] + tok[u][v] < dist[v]:
                dist[v] = dist[u] + tok[u][v]
    return dist


def load_latency(path: str | None, node_names: list[str],
                 tok: list[list[int]]) -> list[tuple[int, int, int, int]]:
    """latency.xml -> (src, dst, rho, bound), 1-based actor indices.

        <latency>
          <path src="a_sobel.get_pixel" dst="a_sobel.abs" max="1200"/>
        </latency>
    """
    if not path:
        return []
    idx = {nm: i for i, nm in enumerate(node_names)}
    out = []
    root = ET.parse(path).getroot()
    for pe in root.findall("path"):
        s_, d_ = pe.get("src"), pe.get("dst")
        for nm in (s_, d_):
            if nm not in idx:
                raise KeyError(f"latency.xml names actor {nm!r}, which is not "
                               f"in any application graph")
        si, di = idx[s_], idx[d_]
        rho = min_token_path(len(node_names), tok, si)[di]
        if rho == float("inf"):
            raise ValueError(f"latency.xml: no path from {s_!r} to {d_!r}")
        out.append((si + 1, di + 1, int(rho), int(pe.get("max"))))
    return out


def load_safety(path: str | None, actor_names: list[str]) -> dict:
    """safety.xml -> per-SDF-actor SIL requirement + global fault model.

        <safety fault_model="random_hw" cost_profile="myklebust2015">
          <actor name="brake_ctl" sil="3"/>
          <default sil="0"/>
        </safety>
    """
    out = {"sil": {n: 0 for n in actor_names},
           "fault_model": "random_hw",
           "cost_profile": "myklebust2015",
           "allow_promotion": True}
    if not path:
        return out
    root = ET.parse(path).getroot()
    out["fault_model"] = root.get("fault_model", "random_hw")
    out["cost_profile"] = root.get("cost_profile", "myklebust2015")
    out["allow_promotion"] = root.get("allow_promotion", "true").lower() == "true"
    d = root.find("default")
    if d is not None:
        for n in actor_names:
            out["sil"][n] = int(d.get("sil", "0"))
    for a in root.findall("actor"):
        n = a.get("name")
        if n not in out["sil"]:
            raise KeyError(f"safety.xml names actor {n!r}, which is not in any "
                           f"application graph. Known actors: {sorted(actor_names)}")
        out["sil"][n] = int(a.get("sil"))
    return out


# Fallback if no cost_model.xml is supplied. The authoritative source is
# data/cost_model.xml; these mirror it so the tool still runs standalone.
COST_PROFILES = {
    "myklebust2015": [100, 113, 225, 518, 906],
    "klosterman":    [100, 113, 123, 140, 170],
    "do178b":        [100, 200, 300, 500, 900],
}


def load_cost_model(path: str | None, profile: str):
    """cost_model.xml -> (per-SIL multipliers x100, per-task baseline, default).

    The profile is an experimental variable, not a constant (C.8): the three
    published profiles disagree by up to 3.7x at SIL3, so the interesting
    question is whether the optimal architecture is stable across them.
    """
    if not path:
        if profile not in COST_PROFILES:
            raise KeyError(f"unknown cost profile {profile!r}; supply a "
                           f"cost_model.xml or use one of "
                           f"{sorted(COST_PROFILES)}")
        return COST_PROFILES[profile], {}, 100
    root = ET.parse(path).getroot()
    profiles = {p.get("name"): p for p in root.findall("profile")}
    if profile not in profiles:
        raise KeyError(f"cost profile {profile!r} not in {path}; available: "
                       f"{sorted(profiles)}")
    pe = profiles[profile]
    mult = [0] * 5
    for se in pe.findall("sil"):
        mult[int(se.get("level"))] = int(se.get("multiplier"))
    base_el = root.find("baseline")
    default = int(base_el.get("default", "100")) if base_el is not None else 100
    per_task = {t.get("task_type"): int(t.get("cost"))
                for t in (base_el.findall("task") if base_el is not None else [])}
    return mult, per_task, default


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", action="append", required=True)
    ap.add_argument("--platform", required=True)
    ap.add_argument("--wcets", required=True)
    ap.add_argument("--constraints")
    ap.add_argument("--safety")
    ap.add_argument("--latency", help="latency.xml: constrained src/dst pairs")
    ap.add_argument("--cost-model", help="cost_model.xml (C.8)")
    ap.add_argument("--cost-profile",
                    help="override the profile named in safety.xml")
    ap.add_argument("--period-mode", choices=["global", "partitioned"],
                    default="global",
                    help="C.7: 'global' = one period for all apps (default); "
                         "'partitioned' = per-app periods, apps may not share "
                         "cores. Per-app periods WITH sharing is Phase 6.")
    ap.add_argument("--wcet-fallback-scale", type=float, default=None,
                    help="DANGER: substitute exec_time*scale for missing WCET "
                         "entries. Warns per use. Never publish results built "
                         "with this.")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    # ---- 1. parse applications, unfold ----------------------------------
    graphs, hgraphs = [], []
    for a in args.app:
        g = parse_sdf3(a)
        h = unfold(g)
        problems = check_unfolding(g, h)
        if problems:
            print(f"unfolding of {g.name!r} FAILED:", file=sys.stderr)
            for p in problems:
                print("   -", p, file=sys.stderr)
            return 2
        graphs.append(g)
        hgraphs.append(h)
        print(f"  {g.name}: {len(g.actors)} SDF actors, q={h.q}, "
              f"-> {h.n()} HSDF nodes, {len(h.edges)} edges", file=sys.stderr)

    # ---- 2. flatten applications into one node list ---------------------
    nodes, app_of, parent_of, copy_of, node_names, node_types = [], [], [], [], [], []
    parent_names, parent_app = [], []
    poff = 0
    for ai, h in enumerate(hgraphs):
        for pn in h.parent_names:
            parent_names.append(f"{h.name}.{pn}")
            parent_app.append(ai + 1)
        for nd in h.nodes:
            nodes.append(nd)
            app_of.append(ai + 1)
            parent_of.append(poff + nd.parent + 1)     # 1-based
            copy_of.append(nd.copy_index)
            node_names.append(f"{h.name}.{nd.name}")
            node_types.append(nd.type)
        poff += len(h.parent_names)

    n = len(nodes)

    # token matrix across all applications (block diagonal)
    tok = [[-1] * n for _ in range(n)]
    off = 0
    for h in hgraphs:
        sub = h.token_matrix()
        for i in range(h.n()):
            for j in range(h.n()):
                if sub[i][j] >= 0:
                    tok[off + i][off + j] = sub[i][j]
        off += h.n()

    # ---- 3. platform ----------------------------------------------------
    plat: Platform = parse_platform(args.platform)
    tidx = plat.type_index()
    P = len(plat.slots)
    nF = len(plat.fcrs)
    print(f"  platform {plat.name!r}: {nF} FCR slots, {P} core slots, "
          f"{len(plat.core_types)} core types", file=sys.stderr)

    # ---- 4. WCETs -------------------------------------------------------
    wt = WCETTable(args.wcets)
    modes_per_type = [len(ct.modes) for ct in plat.core_types]
    max_modes = max(modes_per_type)
    FORBIDDEN = 10 ** 6

    # Rosvall's WCETs.xml keys on the actor NAME (get_pixel, CS_0); SafeDSE
    # pattern components key on a task TYPE. Resolve per actor: prefer whichever
    # of (name, type) the table actually knows, and report the choice.
    known = wt.types()
    wkey: list[str] = []
    for i in range(n):
        bare = node_names[i].split(".", 1)[1].split("#", 1)[0]
        wkey.append(bare if bare in known else node_types[i])

    # A missing (task, core, mode) entry means the actor CANNOT be bound there.
    # This is a mapping restriction, not an error: Rosvall's platform has a
    # CS_HWacc accelerator with a WCET entry for exactly one actor, and every
    # other actor is thereby excluded from it. Encoding it as a sentinel above
    # every real WCET makes T's domain rule the binding out automatically, with
    # no extra constraint. It IS an error for an actor to have no entry at all.
    wcet = []
    fallback_used: list[str] = []
    for i in range(n):
        per_type = []
        for ct in plat.core_types:
            per_mode = []
            for mi in range(max_modes):
                v = None
                if mi < len(ct.modes):
                    v = wt.get(wkey[i], ct.model, ct.modes[mi].name)
                    if v is None:
                        v = wt.get(wkey[i], "default", ct.modes[mi].name)
                    if v is None and args.wcet_fallback_scale is not None:
                        v = max(1, int(round(nodes[i].exec_time
                                             * args.wcet_fallback_scale
                                             * ct.modes[mi].cycle)))
                        fallback_used.append(f"{wkey[i]}/{ct.model}/{ct.modes[mi].name}")
                per_mode.append(FORBIDDEN if v is None else v)
            per_type.append(per_mode)
        if all(v >= FORBIDDEN for t in per_type for v in t):
            print(
                f"ERROR: actor {node_names[i]!r} (WCET key {wkey[i]!r}) has no "
                f"WCET entry for ANY core type in this platform, so it cannot "
                f"be mapped anywhere.\n  Add to {args.wcets}:\n"
                f'    <mapping task_type="{wkey[i]}">\n'
                f'      <wcet processor="{plat.core_types[0].model}" '
                f'mode="{plat.core_types[0].modes[0].name}" wcet="..."/>\n'
                f"    </mapping>", file=sys.stderr)
            return 3
        wcet.append(per_type)

    restricted = [(node_names[i], [ct.model for ti, ct in enumerate(plat.core_types)
                                   if all(v >= FORBIDDEN for v in wcet[i][ti])])
                  for i in range(n)]
    restricted = [(nm, ms) for nm, ms in restricted if ms]
    if restricted:
        print(f"  binding restrictions from missing WCET entries: "
              f"{len(restricted)} actors", file=sys.stderr)
        for nm, ms in restricted[:4]:
            print(f"      {nm} cannot use {', '.join(ms)}", file=sys.stderr)
        if len(restricted) > 4:
            print(f"      ... and {len(restricted)-4} more", file=sys.stderr)
    if fallback_used:
        uniq = sorted(set(fallback_used))
        print(f"  WARNING: --wcet-fallback-scale substituted "
              f"{len(fallback_used)} values across {len(uniq)} combinations. "
              f"Results are NOT publishable.", file=sys.stderr)

    # ---- 5. safety / cost ----------------------------------------------
    sdf_actor_names = []
    for h, g in zip(hgraphs, graphs):
        sdf_actor_names += [a.name for a in g.actors]
    saf = load_safety(args.safety, sdf_actor_names)
    if args.cost_profile:
        saf["cost_profile"] = args.cost_profile
    sil_req_parent = [saf["sil"][pn.split(".", 1)[1]] for pn in parent_names]
    dev_k, dev_base, dev_base_default = load_cost_model(
        args.cost_model, saf["cost_profile"])

    # ---- 6. design constraints -----------------------------------------
    periods = {}
    if args.constraints:
        periods = parse_design_constraints(args.constraints)
    # An unconstrained application still needs a finite bound for the solver's
    # domains.  Use the sum of its slowest achievable WCETs -- the period when
    # every actor of that application shares one core, which is the worst any
    # feasible mapping can do.  Deriving it from nominal exec_time instead would
    # be wrong on a heterogeneous platform, where a slow core can exceed it.
    nT = len(plat.core_types)
    period_ub = []
    base = 0
    for ai, h in enumerate(hgraphs):
        p = periods.get(h.name, -1)
        if p > 0:
            period_ub.append(p)
        else:
            worst = sum(max(wcet[base + k][t][m]
                            for t in range(nT) for m in range(len(plat.core_types[t].modes)))
                        for k in range(h.n()))
            period_ub.append(worst or 10 ** 6)
        base += h.n()

    # ---- 7. emit --------------------------------------------------------
    L: list[str] = []
    W = L.append
    W("% Generated by SafeDSE build_dzn.py -- do not edit by hand.")
    W(f"% applications : {', '.join(h.name for h in hgraphs)}")
    W(f"% platform     : {plat.name}")
    W(f"% period mode  : {args.period_mode}   (C.7)")
    W(f"% fault model  : {saf['fault_model']}")
    W(f"% cost profile : {saf['cost_profile']}  {dev_k}")
    W("")
    W("% ---- applications ----")
    W(f"nApps = {len(hgraphs)};")
    W(f"n = {n};")
    W(f"app = {mzn_array(app_of)};")
    W(f"nParents = {len(parent_names)};")
    W(f"parent = {mzn_array(parent_of)};")
    W(f"copy_index = {mzn_array(copy_of)};")
    W(f"node_name = {mzn_str_array(node_names)};")
    W(f"parent_name = {mzn_str_array(parent_names)};")
    W(f"tok = array2d(1..{n}, 1..{n},")
    W("  " + mzn_matrix(tok).replace("\n", "\n  ") + ");")
    W("")
    W("% ---- platform (C.5) ----")
    W(f"P = {P};")
    W(f"nFCR = {nF};")
    W(f"nCoreTypes = {len(plat.core_types)};")
    W(f"nModes = {max_modes};")
    W(f"ctype = {mzn_array([tidx[s.core_type.model] + 1 for s in plat.slots])};")
    W(f"fcr = {mzn_array([s.fcr_index + 1 for s in plat.slots])};")
    W(f"core_model = {mzn_str_array([ct.model for ct in plat.core_types])};")
    W(f"max_sil = {mzn_array([ct.max_sil for ct in plat.core_types])};")
    W(f"core_mem = {mzn_array([ct.mem for ct in plat.core_types])};")
    W(f"partitionable = {mzn_array([('true' if ct.partitionable else 'false') for ct in plat.core_types])};")
    W(f"partition_cost = {mzn_array([ct.partition_cost for ct in plat.core_types])};")
    W(f"n_modes_of = {mzn_array(modes_per_type)};")
    W(f"fcr_price = {mzn_array([m for _, _, _, m in plat.fcrs])};")
    W(f"core_price = array2d(1..{len(plat.core_types)}, 1..{max_modes},")
    W("  " + mzn_matrix([[ct.modes[i].monetary if i < len(ct.modes) else 0
                          for i in range(max_modes)]
                         for ct in plat.core_types]) + ");")
    W(f"core_power = array2d(1..{len(plat.core_types)}, 1..{max_modes},")
    W("  " + mzn_matrix([[ct.modes[i].dyn_power if i < len(ct.modes) else 0
                          for i in range(max_modes)]
                         for ct in plat.core_types]) + ");")
    W("")
    W("% symmetry classes: slots that are genuinely interchangeable (C.5)")
    sym = plat.symmetry_classes()
    W(f"nSymClasses = {len(sym)};")
    W(f"symClassSize = {mzn_array([len(c) for c in sym])};")
    maxsym = max([len(c) for c in sym] + [1])
    W(f"maxSymClassSize = {maxsym};")
    W(f"symClass = array2d(1..{max(len(sym),1)}, 1..{maxsym},")
    W("  " + mzn_matrix([[c[i] + 1 if i < len(c) else 0 for i in range(maxsym)]
                         for c in sym] or [[0] * maxsym]) + ");")
    ig = plat.interchangeable_groups()
    W(f"nInterGroups = {len(ig)};")
    maxig = max([len(c) for c in ig] + [1])
    W(f"maxInterGroupSize = {maxig};")
    W(f"interGroupSize = {mzn_array([len(c) for c in ig])};")
    W(f"interGroup = array2d(1..{max(len(ig),1)}, 1..{maxig},")
    W("  " + mzn_matrix([[c[i] + 1 if i < len(c) else 0 for i in range(maxig)]
                         for c in ig] or [[0] * maxig]) + ");")

    tg = plat.template_groups()
    W(f"nTmplGroups = {len(tg)};")
    maxtg = max([len(c) for c in tg] + [1])
    W(f"maxTmplGroupSize = {maxtg};")
    W(f"tmplGroupSize = {mzn_array([len(c) for c in tg])};")
    W(f"tmplGroup = array2d(1..{max(len(tg),1)}, 1..{maxtg},")
    W("  " + mzn_matrix([[c[i] + 1 if i < len(c) else 0 for i in range(maxtg)]
                         for c in tg] or [[0] * maxtg]) + ");")
    W("")
    W("% ---- timing ----")
    flat = []
    for i in range(n):
        for t in range(len(plat.core_types)):
            for m in range(max_modes):
                flat.append(wcet[i][t][m])
    W(f"wcet = array3d(1..{n}, 1..{len(plat.core_types)}, 1..{max_modes}, "
      f"{mzn_array(flat)});")
    W(f"mem_req = {mzn_array([nd.state_size for nd in nodes])};")
    W("")
    W("% ---- safety (C.8) ----")
    W(f"sil_req_parent = {mzn_array(sil_req_parent)};")
    W(f"dev_base = {mzn_array([dev_base.get(node_types[i], dev_base_default) for i in range(n)])};")
    W(f"dev_k = array1d(0..4, {mzn_array(dev_k)});")
    W(f"allow_promotion = {'true' if saf['allow_promotion'] else 'false'};")
    W("")
    W("% ---- design constraints ----")
    W(f"period_ub = {mzn_array(period_ub)};")
    W(f"period_mode_partitioned = "
      f"{'true' if args.period_mode == 'partitioned' else 'false'};")
    W("")
    W("% ---- latency (B.2) ----")
    lat = load_latency(args.latency, node_names, tok)
    W(f"nLatCon = {len(lat)};")
    W(f"lat_src = {mzn_array([x[0] for x in lat])};")
    W(f"lat_dst = {mzn_array([x[1] for x in lat])};")
    W(f"lat_rho = {mzn_array([x[2] for x in lat])};")
    W(f"lat_ub  = {mzn_array([x[3] for x in lat])};")
    if lat:
        print(f"  {len(lat)} latency constraints", file=sys.stderr)

    Path(args.out).write_text("\n".join(L) + "\n")
    print(f"  wrote {args.out}  ({n} nodes, {P} core slots)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
