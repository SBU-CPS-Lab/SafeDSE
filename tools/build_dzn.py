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


# Development-cost multipliers x100 (C.8).  SIL0 and SIL4 are extrapolated;
# the source paper (Myklebust/Stalhane/Haugset, ISSC 2015) covers SIL1-SIL3.
COST_PROFILES = {
    # Paper's own recommendation: +100% SIL1->2, +130% SIL2->3
    "myklebust2015": [100, 113, 225, 518, 906],
    # Table 1 (Klosterman): effort increase 5-20 / 10-36 / 20-60 / 40-100%, midpoints
    "klosterman":    [100, 113, 123, 140, 170],
    # Allen / DO-178B ratios E=1, D=3, C=5, B=9 with the paper's D~SIL2, C~SIL3
    "do178b":        [100, 200, 300, 500, 900],
}


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", action="append", required=True)
    ap.add_argument("--platform", required=True)
    ap.add_argument("--wcets", required=True)
    ap.add_argument("--constraints")
    ap.add_argument("--safety")
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
    missing: list[str] = []
    # wcet[node, coretype, mode]
    wcet = []
    for i in range(n):
        per_type = []
        for ct in plat.core_types:
            per_mode = []
            for mi in range(max_modes):
                if mi < len(ct.modes):
                    v = wt.get(node_types[i], ct.model, ct.modes[mi].name)
                    if v is None:
                        # try the DeSyDe default processor label
                        v = wt.get(node_types[i], "default", ct.modes[mi].name)
                    if v is None and args.wcet_fallback_scale is not None:
                        v = max(1, int(round(nodes[i].exec_time
                                             * args.wcet_fallback_scale
                                             * ct.modes[mi].cycle)))
                        missing.append(f"{node_types[i]}/{ct.model}/{ct.modes[mi].name}")
                    if v is None:
                        print(
                            f"ERROR: no WCET for task_type={node_types[i]!r} on "
                            f"processor={ct.model!r} mode={ct.modes[mi].name!r}.\n"
                            f"  Add to {args.wcets}:\n"
                            f'    <mapping task_type="{node_types[i]}">\n'
                            f'      <wcet processor="{ct.model}" '
                            f'mode="{ct.modes[mi].name}" wcet="..."/>\n'
                            f"    </mapping>", file=sys.stderr)
                        return 3
                else:
                    v = 10 ** 6          # unusable mode index, priced out
                per_mode.append(v)
            per_type.append(per_mode)
        wcet.append(per_type)
    if missing:
        uniq = sorted(set(missing))
        print(f"  WARNING: --wcet-fallback-scale substituted {len(missing)} "
              f"values across {len(uniq)} (type, core, mode) combinations. "
              f"Results are NOT publishable.", file=sys.stderr)
        for u in uniq[:8]:
            print(f"      missing: {u}", file=sys.stderr)

    # ---- 5. safety / cost ----------------------------------------------
    sdf_actor_names = []
    for h, g in zip(hgraphs, graphs):
        sdf_actor_names += [a.name for a in g.actors]
    saf = load_safety(args.safety, sdf_actor_names)
    sil_req_parent = [saf["sil"][pn.split(".", 1)[1]] for pn in parent_names]
    dev_k = COST_PROFILES[saf["cost_profile"]]

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
    W(f"dev_k = array1d(0..4, {mzn_array(dev_k)});")
    W(f"allow_promotion = {'true' if saf['allow_promotion'] else 'false'};")
    W("")
    W("% ---- design constraints ----")
    W(f"period_ub = {mzn_array(period_ub)};")
    W(f"period_mode_partitioned = "
      f"{'true' if args.period_mode == 'partitioned' else 'false'};")

    Path(args.out).write_text("\n".join(L) + "\n")
    print(f"  wrote {args.out}  ({n} nodes, {P} core slots)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
