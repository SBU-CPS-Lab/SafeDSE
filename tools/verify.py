#!/usr/bin/env python3
"""Independently verify a solution returned by the CP model.

Rebuilds the mapping-and-schedule-aware graph (MSAG) from the solver's
assignment, then computes its iteration period twice -- by Karp's algorithm and
by max-plus simulation -- and checks both against the mu the solver reported.

This exists because the failure mode of constraint modelling is silent: a wrong
encoding returns a plausible number, not an error.  The open-chain bug that
dropped the "core period >= sum of its WCETs" bound produced perfectly
well-formed output for weeks of prototyping.  Nothing in this file shares code
with the MiniZinc model.

    verify.py --dzn out/rasta.dzn --solution out/rasta.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from golden import mcm, selftimed_period, selftimed_trace  # noqa: E402


# --------------------------------------------------------------------------
def parse_dzn(path: str) -> dict:
    """Minimal .dzn reader for the arrays this framework emits."""
    txt = Path(path).read_text()
    txt = re.sub(r"^\s*%.*$", "", txt, flags=re.M)
    out: dict = {}
    for m in re.finditer(r"(\w+)\s*=\s*(.*?);", txt, re.S):
        name, body = m.group(1), m.group(2).strip()
        out[name] = _parse_value(body)
    return out


def _parse_value(body: str):
    body = body.strip()
    if body.startswith("array2d") or body.startswith("array3d"):
        inner = body[body.index("(") + 1: body.rindex(")")]
        # last bracketed group is the data
        depth, start = 0, None
        for i, ch in enumerate(inner):
            if ch in "[":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "]":
                depth -= 1
        data = inner[start:]
        return _parse_flat(data)
    if body.startswith("[|"):
        rows = [r for r in body[2:body.rindex("|]")].split("|") if r.strip()]
        return [[_atom(x) for x in r.split(",") if x.strip()] for r in rows]
    if body.startswith("["):
        return _parse_flat(body)
    return _atom(body)


def _parse_flat(body: str):
    if body.startswith("[|"):
        rows = [r for r in body[2:body.rindex("|]")].split("|") if r.strip()]
        return [x for r in rows for x in (_atom(y) for y in r.split(",") if y.strip())]
    return [_atom(x) for x in body.strip()[1:-1].split(",") if x.strip()]


def _atom(s: str):
    s = s.strip()
    if s.startswith('"'):
        return s.strip('"')
    if s in ("true", "false"):
        return s == "true"
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return s


# --------------------------------------------------------------------------
def build_msag(d: dict, sol: dict):
    """Reconstruct the MSAG: application edges + serialisation + wrap edges."""
    n = d["n"]
    tokflat = d["tok"]
    if tokflat and isinstance(tokflat[0], list):
        tok = tokflat
    else:
        tok = [tokflat[r * n:(r + 1) * n] for r in range(n)]

    proc = sol["proc"]
    succ = sol["succ"]
    T = sol["T"]

    edges: list[tuple[int, int, int]] = []
    for i in range(n):
        for j in range(n):
            if tok[i][j] >= 0:
                edges.append((i, j, tok[i][j]))

    # serialisation arcs, token-less
    for i in range(n):
        if succ[i] > 0:
            edges.append((i, succ[i] - 1, 0))

    # wrap arcs: last -> head on the same core, carrying one token
    heads = {}
    for j in range(n):
        if not any(succ[i] == j + 1 for i in range(n)):
            heads[proc[j]] = j
    for i in range(n):
        if succ[i] == 0 and proc[i] in heads:
            edges.append((i, heads[proc[i]], 1))

    return n, edges, T


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dzn", required=True)
    ap.add_argument("--solution", required=True)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    d = parse_dzn(a.dzn)
    sol = json.loads(Path(a.solution).read_text())
    n, edges, T = build_msag(d, sol)

    mus = sol["mu"] if isinstance(sol["mu"], list) else [sol["mu"]]
    app = d.get("app", [1] * n)
    nApps = d.get("nApps", 1)
    ok, msgs = True, []

    # In partitioned mode the applications occupy disjoint cores, so the MSAG
    # splits into independent components and each application's period must be
    # checked against its OWN component.  Checking a single global MCM here
    # would compare every application against the slowest one.
    partitioned = bool(d.get("period_mode_partitioned", False))
    if partitioned and nApps > 1:
        groups = [(z, [i for i in range(n) if app[i] == z]) for z in range(1, nApps + 1)]
    else:
        groups = [(1, list(range(n)))]

    for z, members in groups:
        if not members:
            continue
        idx = {g: k for k, g in enumerate(members)}
        sub = [(idx[u], idx[v], t) for u, v, t in edges
               if u in idx and v in idx]
        crossing = [(u, v) for u, v, _ in edges
                    if (u in idx) != (v in idx)]
        if partitioned and crossing:
            ok = False
            msgs.append(f"app {z}: {len(crossing)} MSAG edges cross application "
                        f"boundaries, but partitioned mode forbids core sharing")
        subT = [T[g] for g in members]
        reported = mus[z - 1] if z - 1 < len(mus) else mus[0]
        k = mcm(len(members), sub, subT)
        sim = selftimed_period(len(members), sub, subT)
        if k is None:
            ok = False
            msgs.append(f"app {z}: MSAG deadlocks but a period was returned")
        elif Fraction(reported) != k:
            ok = False
            msgs.append(f"app {z}: period mismatch -- solver {reported}, Karp {k}")
        if sim is not None and k is not None and sim != k:
            ok = False
            msgs.append(f"app {z}: oracle disagreement -- Karp {k}, simulation {sim}")
        if not a.quiet:
            print(f"  app {z}: reported {reported}, Karp {k}, simulation {sim}")

    # ---- exact latency, transient included -----------------------------
    # lib/latency.mzn uses the PERIODIC-PHASE estimate
    #     pot[d] - pot[s] + rho*mu + T[d]
    # which is exact once the schedule has settled but ignores the transient.
    # Simulate the real schedule and compare. A reported latency below the
    # simulated worst case is not a bug in the solver -- it is the documented
    # limitation of the estimate -- but it MUST be surfaced, because publishing
    # the estimate as a worst-case bound would be wrong.
    nlat = d.get("nLatCon", 0)
    if nlat and "latency" in sol:
        trace = selftimed_trace(n, edges, T, iters=40)
        src = d["lat_src"] if isinstance(d["lat_src"], list) else [d["lat_src"]]
        dst = d["lat_dst"] if isinstance(d["lat_dst"], list) else [d["lat_dst"]]
        rho = d["lat_rho"] if isinstance(d["lat_rho"], list) else [d["lat_rho"]]
        rep = sol["latency"] if isinstance(sol["latency"], list) else [sol["latency"]]
        if trace:
            for c in range(nlat):
                si, di, r = src[c] - 1, dst[c] - 1, rho[c]
                obs = max(trace[k + r][di] + T[di] - trace[k][si]
                          for k in range(len(trace) - r))
                if not a.quiet:
                    print(f"  latency[{c+1}]: model estimate {rep[c]}, "
                          f"simulated worst case {obs}")
                if obs > rep[c]:
                    msgs.append(
                        f"NOTE latency[{c+1}]: transient worst case {obs} exceeds "
                        f"the periodic-phase estimate {rep[c]} by {obs - rep[c]} "
                        f"-- expected (see lib/latency.mzn), but do not report "
                        f"the estimate as a worst-case bound")

    # the bound the open-chain bug used to lose
    load = {}
    for i in range(n):
        load[sol["proc"][i]] = load.get(sol["proc"][i], 0) + T[i]
    worst = max(load.values()) if load else 0
    if max(mus) < worst:
        ok = False
        msgs.append(f"worst period {max(mus)} is below the busiest core's load "
                    f"{worst} -- the processor-availability wrap edge is missing")
    if not a.quiet:
        print(f"  busiest core load = {worst}")
    for m in msgs:
        print(f"  FAIL: {m}")
    print("  VERIFY OK" if ok else "  VERIFY FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
