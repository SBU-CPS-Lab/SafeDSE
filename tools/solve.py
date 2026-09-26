#!/usr/bin/env python3
"""Run a SafeDSE model and verify the solution.

CP-SAT is the only backend used for experiments (measured 30x faster than
Gecode at n=10, and the only one that reaches n=30 in the Phase-0 study).
--solver is exposed anyway so the harness can cross-check small instances on
Gecode and Chuffed, where disagreement means a modelling error.

    solve.py --dzn out/rasta.dzn --optimise HWCOST --bound THROUGHPUT=900
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Prefer the newest install; bootstrap_minizinc.sh puts 2.10.0 in /opt/mzn.
MZN = next((p for p in ("minizinc", "/opt/mzn210/bin/minizinc", "/opt/mzn/bin/minizinc")
            if Path(p).exists()), "minizinc")
METRICS = ["THROUGHPUT", "LATENCY", "HWCOST", "DEVCOST", "TOTALCOST",
           "POWER", "NPROCS", "PROMOTION"]
BIG = 10 ** 9


def _last_json(out: str):
    """Extract the final JSON solution block by brace matching.

    MiniZinc interleaves solutions with `% time elapsed` lines, `----------`
    separators and a `%%%mzn-stat` block, so splitting on any one marker is
    fragile. Brace matching is not.
    """
    found = None
    depth, start = 0, None
    for i, ch in enumerate(out):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                try:
                    found = json.loads(out[start:i + 1])
                except json.JSONDecodeError:
                    pass
    return found


def run(dzn: str, optimise: str = "HWCOST", bounds: dict[str, int] | None = None,
        solver: str = "cp-sat", timeout: int = 300, model: str | None = None,
        parent_symmetry: bool = True, extra: str = "",
        threads: int | None = None, time_limit_ms: int | None = None) -> dict:
    """threads/time_limit_ms are passed to MiniZinc itself (-p, --time-limit)
    so a run that hits the limit still reports its best incumbent instead of
    being killed; the Python-level `timeout` is then only a safety margin and
    should be set comfortably above time_limit_ms (the harness does this).

    --intermediate-solutions is added whenever time_limit_ms is set: without
    it, CP-SAT via MiniZinc prints NOTHING until the search either proves
    optimality or exhausts itself -- a time-limited run that has not yet
    proved optimality reports zero solutions (measured: --time-limit 30000
    with no --intermediate-solutions on a 32-actor coupled instance gave
    nSolutions=0 after 30s of real search, not "best incumbent so far").
    """
    bounds = bounds or {}
    if optimise not in METRICS:
        raise SystemExit(f"unknown metric {optimise!r}; choose from {METRICS}")
    ub = [bounds.get(m, BIG) for m in METRICS]
    data = (f"opt_metric={optimise}; ub={ub}; "
            f"use_parent_symmetry={'true' if parent_symmetry else 'false'}; {extra}")
    cmd = [MZN, "--solver", solver, "--output-mode", "json", "--output-time",
           "--statistics", str(model or ROOT / "model" / "dse.mzn"), dzn, "-D", data]
    if threads is not None:
        cmd += ["-p", str(threads)]
    if time_limit_ms is not None:
        cmd += ["--time-limit", str(time_limit_ms), "--intermediate-solutions"]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "seconds": timeout}
    wall = time.time() - t0
    out = p.stdout

    if "UNSATISFIABLE" in out:
        return {"status": "UNSAT", "seconds": wall}
    if "=====UNKNOWN=====" in out or "=====ERROR=====" in out:
        return {"status": "UNKNOWN", "seconds": wall,
                "stderr": p.stderr[-800:], "stdout": out[-800:]}

    sol = _last_json(out)
    if sol is None:
        return {"status": "NOSOL", "seconds": wall,
                "stderr": p.stderr[-800:], "stdout": out[-1500:]}
    return {"status": "OPTIMAL" if "==========" in out else "SAT",
            "seconds": wall, "solution": sol,
            "objective": sol.get("metric", [None] * len(METRICS))[METRICS.index(optimise)]
            if isinstance(sol.get("metric"), list) else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dzn", required=True)
    ap.add_argument("--optimise", default="HWCOST")
    ap.add_argument("--bound", action="append", default=[],
                    help="METRIC=value, repeatable")
    ap.add_argument("--solver", default="cp-sat")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("-p", "--threads", type=int, default=None,
                    help="MiniZinc -p: fixed solver thread count")
    ap.add_argument("--time-limit", type=int, default=None,
                    help="MiniZinc --time-limit in ms; the best incumbent at "
                         "this point is kept instead of losing the run")
    ap.add_argument("--no-parent-symmetry", action="store_true")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--json-out")
    a = ap.parse_args()

    bounds = {}
    for b in a.bound:
        k, _, v = b.partition("=")
        bounds[k.strip().upper()] = int(v)

    r = run(a.dzn, a.optimise, bounds, a.solver, a.timeout,
            parent_symmetry=not a.no_parent_symmetry,
            threads=a.threads, time_limit_ms=a.time_limit)
    print(f"status={r['status']}  {r['seconds']:.2f}s  solver={a.solver}")
    if "solution" not in r:
        if r.get("stdout"):
            print(r["stdout"])
        if r.get("stderr"):
            print(r["stderr"], file=sys.stderr)
        return 1 if r["status"] not in ("UNSAT",) else 0

    s = r["solution"]
    print(f"  mu={s['mu']}  nprocs={s['nprocs']}  hw_cost={s['hw_cost']}  "
          f"dev_cost={s.get('dev_cost')}  promo={s.get('promotion_cost')}  "
          f"power={s['power']}")
    if "csil" in s:
        print(f"  csil={s['csil']}  sil_impl={s.get('sil_impl')}")
    print(f"  proc={s['proc']}")

    outp = a.json_out or "/tmp/safedse_sol.json"
    Path(outp).write_text(json.dumps(s))
    if not a.no_verify:
        rc = subprocess.run([sys.executable, str(ROOT / "tools" / "verify.py"),
                             "--dzn", a.dzn, "--solution", outp]).returncode
        return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
