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
from golden import mcm, selftimed_period  # noqa: E402


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

    reported = sol["mu"][0] if isinstance(sol["mu"], list) else sol["mu"]
    by_karp = mcm(n, edges, T)
    by_sim = selftimed_period(n, edges, T)

    ok = True
    msgs = []
    if by_karp is None:
        ok = False
        msgs.append("MSAG deadlocks (token-less cycle) but the solver returned a period")
    elif Fraction(reported) != by_karp:
        ok = False
        msgs.append(f"period mismatch: solver {reported}, Karp {by_karp}")
    if by_sim is not None and by_karp is not None and by_sim != by_karp:
        ok = False
        msgs.append(f"oracle disagreement: Karp {by_karp}, simulation {by_sim}")

    # the bound the open-chain bug used to lose
    load = {}
    for i in range(n):
        load[sol["proc"][i]] = load.get(sol["proc"][i], 0) + T[i]
    worst = max(load.values()) if load else 0
    if reported < worst:
        ok = False
        msgs.append(f"period {reported} is below the busiest core's load {worst} "
                    f"-- the processor-availability wrap edge is missing")

    if not a.quiet:
        print(f"  reported mu = {reported}")
        print(f"  Karp MCM    = {by_karp}")
        print(f"  simulation  = {by_sim}")
        print(f"  busiest core load = {worst}")
    for m in msgs:
        print(f"  FAIL: {m}")
    print("  VERIFY OK" if ok else "  VERIFY FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
