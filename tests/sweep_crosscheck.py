#!/usr/bin/env python3
"""Finish a crosscheck sweep over instances a previous run did not reach.

The full `crosscheck` group takes ~25 minutes because Gecode times out by
design on most instances, and a container that suspends between polls will not
let it finish. This runs the remainder with a shorter backend timeout.

That is a weakening of COVERAGE, not of correctness: a backend that would have
solved at 120s but times out at 45s produces "TIMEOUT", which the harness
already treats as a non-failure, so a shortened sweep can lose a comparison but
cannot manufacture a passing one. Any instance reported here as agreeing really
did have two backends reach the same answer.

    sweep_crosscheck.py --skip r_all,r_lat --timeout 45
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from solve import run  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", default="", help="comma-separated stems to skip")
    ap.add_argument("--timeout", type=int, default=45)
    ap.add_argument("--only", default="", help="comma-separated stems to run")
    a = ap.parse_args()

    skip = {s for s in a.skip.split(",") if s}
    only = {s for s in a.only.split(",") if s}
    dzns = sorted(ROOT.glob("out/*.dzn"))
    fails, agree, unproven, nocmp = [], 0, 0, 0

    for f in dzns:
        stem = f.stem
        if stem in skip or (only and stem not in only):
            continue
        ref = run(str(f), "HWCOST", solver="cp-sat", timeout=a.timeout)
        if ref["status"] not in ("OPTIMAL", "UNSAT"):
            print(f"  {stem}: cp-sat {ref['status']} -- no reference", flush=True)
            unproven += 1
            continue
        tag = "UNSAT" if ref["status"] == "UNSAT" else \
            f"hw_cost={ref['solution']['hw_cost']}"
        reached = 0
        for slv in ("gecode", "chuffed"):
            r = run(str(f), "HWCOST", solver=slv, timeout=a.timeout)
            if r["status"] not in ("OPTIMAL", "UNSAT"):
                print(f"  {stem}: {slv} {r['status']} -- no comparison",
                      flush=True)
                continue
            reached += 1
            if r["status"] != ref["status"]:
                fails.append(f"{stem}: {slv} says {r['status']}, cp-sat says "
                             f"{ref['status']}")
                print(f"  DISAGREE {fails[-1]}", flush=True)
                continue
            if ref["status"] == "UNSAT":
                print(f"  {stem}: {slv} agrees UNSAT", flush=True)
                agree += 1
                continue
            if r["solution"]["hw_cost"] != ref["solution"]["hw_cost"]:
                fails.append(f"{stem}: {slv} hw_cost {r['solution']['hw_cost']} "
                             f"vs cp-sat {ref['solution']['hw_cost']}")
                print(f"  DISAGREE {fails[-1]}", flush=True)
            else:
                print(f"  {stem}: {slv} agrees ({tag})", flush=True)
                agree += 1

        if reached == 0:
            print(f"  {stem}: NO backend comparison possible -- only CP-SAT "
                  f"reaches an answer here", flush=True)
            nocmp += 1

    print(f"\n{agree} agreements, {len(fails)} disagreements, "
          f"{unproven} without a reference, "
          f"{nocmp} where no other backend could reach an answer")
    if nocmp:
        print("  NOTE: on those instances crosscheck contributes no evidence. "
              "The safety net there is tools/verify.py, not backend agreement.")
    for x in fails:
        print(f"  DISAGREEMENT: {x}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
