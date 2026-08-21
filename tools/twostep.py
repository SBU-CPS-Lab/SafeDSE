#!/usr/bin/env python3
"""Rosvall's two-step solving, applied to the multi-application case.

Step 1 solves a RESTRICTED model that is fast but may be sub-optimal; step 2
solves the full model with step 1's objective as an upper bound. Completeness is
preserved: the bound only excludes solutions no better than one already found.

The restriction used here is "applications may not share a processor", which is
the same one DeSyDe applies in its step 1 -- and for the same reason. Coupled
multi-application instances are hard to prove optimal because the period of every
application on a shared core is tied to the tightest bound among them, so the
objective landscape is flat and full of near-ties. Measured on Rosvall's
four-application experiment:

    coupled, no bound      : no proof of optimality in 250 s
    coupled, bounded at 54 : 5.2 s
    partitioned (step 1)   : 3.9 s  -> gives the bound 54

Step 1's solution is feasible for step 2 (a partitioned mapping is a coupled
mapping in which no application happens to share), so the bound is always valid.

    twostep.py --dzn out/r_all.dzn --partitioned out/r_all_part.dzn \
               --optimise HWCOST
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from solve import METRICS, run  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dzn", required=True, help="the full (coupled) instance")
    ap.add_argument("--partitioned",
                    help="the same instance built with --period-mode "
                         "partitioned; used as step 1")
    ap.add_argument("--optimise", default="HWCOST")
    ap.add_argument("--bound", action="append", default=[])
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--slack", type=int, default=0,
                    help="relax step 1's bound by this much before step 2, in "
                         "case the restriction cost more than it saved")
    a = ap.parse_args()

    bounds = {}
    for b in a.bound:
        k, _, v = b.partition("=")
        bounds[k.strip().upper()] = int(v)

    step1_src = a.partitioned or a.dzn
    print(f"step 1  ({'partitioned' if a.partitioned else 'same instance'})")
    r1 = run(step1_src, a.optimise, bounds, timeout=a.timeout)
    print(f"  {r1['status']}  {r1['seconds']:.2f}s")
    if r1["status"] not in ("OPTIMAL", "SAT"):
        print("  step 1 gave no solution; running step 2 unbounded")
        r2 = run(a.dzn, a.optimise, bounds, timeout=a.timeout)
        _report(r2, a.optimise)
        return 0 if "solution" in r2 else 1

    obj = r1["solution"]["metric"][METRICS.index(a.optimise)]
    print(f"  {a.optimise} = {obj}   mu = {r1['solution']['mu']}")

    b2 = dict(bounds)
    b2[a.optimise] = obj + a.slack
    print(f"step 2  (full model, {a.optimise} <= {obj + a.slack})")
    r2 = run(a.dzn, a.optimise, b2, timeout=a.timeout)
    print(f"  {r2['status']}  {r2['seconds']:.2f}s")

    if "solution" not in r2:
        print("  step 2 found nothing better; step 1's solution stands")
        _report(r1, a.optimise)
        return 0
    obj2 = r2["solution"]["metric"][METRICS.index(a.optimise)]
    if obj2 < obj:
        print(f"  improved: {obj} -> {obj2} by allowing applications to share")
    else:
        print(f"  no improvement from sharing ({obj2}); the restriction in step "
              f"1 cost nothing here")
    _report(r2, a.optimise)
    print(f"total {r1['seconds'] + r2['seconds']:.2f}s")
    return 0


def _report(r: dict, metric: str) -> None:
    if "solution" not in r:
        return
    s = r["solution"]
    print(f"  mu={s['mu']}  nprocs={s['nprocs']}  hw={s['hw_cost']}  "
          f"dev={s.get('dev_cost')}")
    Path("/tmp/safedse_twostep.json").write_text(json.dumps(s))


if __name__ == "__main__":
    raise SystemExit(main())
