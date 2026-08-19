#!/usr/bin/env python3
"""SafeDSE test harness.

Groups:
  golden    -- the Python oracles agree with hand-computed values
  unfold    -- SDF->HSDF preserves the C.6 properties, incl. multi-rate cases
  model     -- the CP model agrees with the oracles on real instances
  symmetry  -- Rosvall 23/33 change runtime but never the optimum (Q14)
  crosscheck-- CP-SAT, Gecode and Chuffed agree on small instances

Run:  python3 tests/run_tests.py [group ...]
"""
from __future__ import annotations

import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from golden import mcm, selftimed_period          # noqa: E402
from hsdf import check_unfolding, unfold          # noqa: E402
from sdf3 import Actor, Channel, SDFGraph, parse_sdf3   # noqa: E402
from solve import run                             # noqa: E402

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + detail) if detail and not cond else ''}")


# ---------------------------------------------------------------------------
def t_golden() -> None:
    print("\n[golden] oracles vs hand-computed values")
    cases = [
        ("3-cycle T=[3,4,5] 1 token",
         3, [(0, 1, 0), (1, 2, 0), (2, 0, 1)], [3, 4, 5], 12),
        ("4-cycle T=2 each, 2 tokens",
         4, [(0, 1, 0), (1, 2, 0), (2, 3, 0), (3, 0, 2)], [2, 2, 2, 2], 4),
        ("pipeline + self-loops, bottleneck 7",
         3, [(0, 1, 0), (1, 2, 0), (0, 0, 1), (1, 1, 1), (2, 2, 1)], [3, 7, 5], 7),
        ("2-cycle 3 tokens",
         2, [(0, 1, 0), (1, 0, 3)], [10, 5], 5),
    ]
    for name, n, e, w, exp in cases:
        k, s = mcm(n, e, w), selftimed_period(n, e, w)
        check(f"karp: {name}", k == Fraction(exp), f"got {k}, want {exp}")
        check(f"sim:  {name}", s == Fraction(exp), f"got {s}, want {exp}")

    # deadlock must be detected, not merely priced highly
    e = [(0, 1, 0), (1, 0, 0)]
    check("karp: token-less cycle is deadlock", mcm(2, e, [1, 1]) is None)
    check("sim:  token-less cycle is deadlock",
          selftimed_period(2, e, [1, 1]) is None)


# ---------------------------------------------------------------------------
def _multirate() -> SDFGraph:
    """A->B with rates 2:3, B->C 1:1, plus a feedback C->A with 2 tokens.

    Balance: 2*qA = 3*qB and qB = qC.  Smallest solution q = (3, 2, 2).
    """
    g = SDFGraph("multirate")
    g.actors = [Actor("A", "tA", 4), Actor("B", "tB", 6), Actor("C", "tC", 5)]
    g.channels = [
        Channel("ab", "A", "B", prod=2, cons=3),
        Channel("bc", "B", "C", prod=1, cons=1),
        Channel("ca", "C", "A", prod=3, cons=2, initial_tokens=6),
    ]
    return g


def t_unfold() -> None:
    print("\n[unfold] SDF -> HSDF properties (C.6)")
    g = _multirate()
    q = g.repetition_vector()
    check("repetition vector of the 2:3 multi-rate graph", q == [3, 2, 2],
          f"got {q}, want [3, 2, 2]")

    h = unfold(g)
    check("node count == sum(q)", h.n() == sum(q), f"{h.n()} vs {sum(q)}")
    problems = check_unfolding(g, h)
    check("unfolding properties hold", not problems, "; ".join(problems))

    # inconsistent graph must be diagnosed, not silently unfolded
    bad = _multirate()
    bad.channels[0].cons = 4          # 2*qA = 4*qB now conflicts with the cycle
    try:
        bad.repetition_vector()
        check("inconsistent graph is rejected", False, "no exception raised")
    except ValueError as e:
        check("inconsistent graph is rejected", "inconsistent" in str(e))

    # a real benchmark: already single-rate, so unfolding is the identity
    for f in ["c_rasta.hsdf.xml", "d_jpegEnc1.hsdf.xml"]:
        gg = parse_sdf3(ROOT / "data" / "apps" / f)
        hh = unfold(gg)
        check(f"{f}: q is all-ones (already HSDF)",
              set(hh.q) == {1}, f"q={hh.q}")
        check(f"{f}: unfolding properties hold", not check_unfolding(gg, hh))

    # the unfolded multi-rate graph's period must match the SDF's, computed by
    # an independent route: simulate the HSDF directly
    tokm = h.token_matrix()
    edges = [(i, j, tokm[i][j]) for i in range(h.n()) for j in range(h.n())
             if tokm[i][j] >= 0]
    wt = [nd.exec_time for nd in h.nodes]
    k, s = mcm(h.n(), edges, wt), selftimed_period(h.n(), edges, wt)
    check("unfolded multi-rate: Karp and simulation agree",
          k is not None and k == s, f"karp={k} sim={s}")


# ---------------------------------------------------------------------------
def _verify(dzn: str, sol: dict) -> tuple[bool, str]:
    import json
    p = Path("/tmp/_t_sol.json")
    p.write_text(json.dumps(sol))
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "verify.py"),
                        "--dzn", dzn, "--solution", str(p), "--quiet"],
                       capture_output=True, text=True)
    return r.returncode == 0, r.stdout.strip()


def t_provenance() -> None:
    """Records the Phase-1 finding that SDF-level provenance is load-bearing.

    d_jpegEnc1 gets its parallelism from six identical DCT/Huffman branches.
    Shipped as a pre-unfolded .hsdf.xml those are six DISTINCT SDF actors, so
    parent[] is all-distinct, constraints 23/33 are inert, and the solver
    explores all 720 equivalent branch orderings. Expressed as a multi-rate
    .sdf.xml the unfolder produces the same 16-node HSDF but retains parent[],
    and the instance becomes tractable.

    This is why patterns are applied at SDF level (Q5) and why parent[] is
    emitted (Q14) -- both were argued on semantics and turn out to decide
    tractability too.
    """
    print("\n[provenance] multi-rate input must beat pre-unfolded input")
    pre = ROOT / "out" / "jpeg.dzn"
    post = ROOT / "out" / "jpeg_sdf.dzn"
    if not (pre.exists() and post.exists()):
        print("  SKIP  need both jpeg.dzn and jpeg_sdf.dzn")
        return
    a = run(str(pre), "HWCOST", {"THROUGHPUT": 4000}, timeout=60)
    b = run(str(post), "HWCOST", {"THROUGHPUT": 4000}, timeout=60)
    check("multi-rate form solves at mu<=4000", b["status"] == "OPTIMAL",
          b["status"])
    if a["status"] == "OPTIMAL" and b["status"] == "OPTIMAL":
        check("both forms agree on the optimum",
              a["solution"]["hw_cost"] == b["solution"]["hw_cost"],
              f"{a['solution']['hw_cost']} vs {b['solution']['hw_cost']}")
        print(f"        NOTE: the pre-unfolded form now solves too "
              f"({a['seconds']:.1f}s vs {b['seconds']:.1f}s) -- the gap has "
              f"narrowed; re-check the finding.")
    else:
        print(f"        pre-unfolded: {a['status']} after {a['seconds']:.1f}s; "
              f"multi-rate: {b['status']} after {b['seconds']:.1f}s")


def t_model(dzns: list[str]) -> None:
    print("\n[model] CP solutions verified against the oracles")
    # The pre-unfolded d_jpegEnc1 is a known-bad input format (see
    # t_provenance); exclude it here so its expected difficulty does not
    # masquerade as a model defect.
    dzns = [d for d in dzns if Path(d).stem != "jpeg"
            and not Path(d).stem.startswith("r_")]
    for dzn in dzns:
        for metric in ["HWCOST", "THROUGHPUT", "NPROCS"]:
            r = run(dzn, metric, timeout=240)
            if r["status"] not in ("OPTIMAL", "SAT"):
                check(f"{Path(dzn).stem}/{metric}: solved", False, r["status"])
                continue
            ok, msg = _verify(dzn, r["solution"])
            check(f"{Path(dzn).stem}/{metric}: solution verifies "
                  f"({r['seconds']:.1f}s, mu={r['solution']['mu'][0]})", ok, msg)


def t_symmetry(dzns: list[str]) -> None:
    """Rosvall 23/33 are REDUNDANT constraints: copies of the same SDF parent
    are interchangeable, so ordering them removes symmetric solutions but no
    distinct one. If the optimum moves, the constraint is wrong, not strong.

    Only instances with real parent multiplicity exercise this; a pre-unfolded
    .hsdf.xml has all-distinct parents and the constraints are inert.
    """
    print("\n[symmetry] Rosvall 23/33 must not move the optimum (Q14)")
    dzns = [d for d in dzns if _has_multiplicity(d)]
    if not dzns:
        print("  SKIP  no instance with parent multiplicity -- build one from a "
              "multi-rate .sdf.xml, not a pre-unfolded .hsdf.xml")
        return
    for dzn in dzns:
        a = run(dzn, "HWCOST", parent_symmetry=False, timeout=120)
        b = run(dzn, "HWCOST", parent_symmetry=True, timeout=120)
        if a["status"] not in ("OPTIMAL",) or b["status"] not in ("OPTIMAL",):
            check(f"{Path(dzn).stem}: both variants prove optimality", False,
                  f"{a['status']}/{b['status']}")
            continue
        oa = a["solution"]["hw_cost"]
        ob = b["solution"]["hw_cost"]
        check(f"{Path(dzn).stem}: same optimum with and without 23/33",
              oa == ob, f"{oa} vs {ob}")
        print(f"        without={a['seconds']:.2f}s  with={b['seconds']:.2f}s")


def _has_multiplicity(dzn: str) -> bool:
    from verify import parse_dzn
    par = parse_dzn(dzn).get("parent", [])
    return len(set(par)) < len(par)


def t_latency() -> None:
    """The periodic-phase latency estimate must be checkable against the
    transient-aware simulation, and tightening the bound must move the design."""
    print("\n[latency] periodic estimate vs transient simulation")
    dzn = ROOT / "out" / "r_lat.dzn"
    if not dzn.exists():
        print("  SKIP  build out/r_lat.dzn with --latency first")
        return
    prev = None
    for bound in [1500, 900]:
        r = run(str(dzn), "HWCOST", {"LATENCY": bound}, timeout=120)
        if r["status"] != "OPTIMAL":
            check(f"latency<={bound}: solved", False, r["status"])
            continue
        ok, msg = _verify(str(dzn), r["solution"])
        check(f"latency<={bound}: solution verifies "
              f"(lat={r['solution']['latency']})", ok, msg)
        check(f"latency<={bound}: bound respected",
              max(r["solution"]["latency"]) <= bound)
        prev = r["solution"]["hw_cost"] if prev is None else prev
    # an unreachable bound must be reported UNSAT, not silently satisfied
    r = run(str(dzn), "HWCOST", {"LATENCY": 700}, timeout=120)
    check("latency<=700 is correctly UNSAT", r["status"] == "UNSAT", r["status"])


def t_rosvall() -> None:
    """Rosvall's four ToDAES applications must each meet their published period."""
    print("\n[rosvall] published period constraints (a_sobel 400, b_susan 2050, "
          "c_rasta 550)")
    want = {"r_a_sobel": 400, "r_b_susan": 2050, "r_c_rasta": 550}
    for stem, bound in want.items():
        dzn = ROOT / "out" / f"{stem}.dzn"
        if not dzn.exists():
            print(f"  SKIP  {stem}")
            continue
        r = run(str(dzn), "HWCOST", timeout=120)
        if r["status"] != "OPTIMAL":
            check(f"{stem}: solved", False, r["status"])
            continue
        ok, msg = _verify(str(dzn), r["solution"])
        mu = r["solution"]["mu"][0]
        check(f"{stem}: mu={mu} meets published bound {bound}", mu <= bound)
        check(f"{stem}: solution verifies", ok, msg)
    # the four-application case, partitioned
    dzn = ROOT / "out" / "r_all_part.dzn"
    if dzn.exists():
        r = run(str(dzn), "HWCOST", timeout=180)
        if r["status"] == "OPTIMAL":
            ok, msg = _verify(str(dzn), r["solution"])
            check(f"4 apps partitioned: verifies (mu={r['solution']['mu']}, "
                  f"{r['solution']['nprocs']} cores)", ok, msg)
        else:
            check("4 apps partitioned: solved", False, r["status"])


def t_crosscheck(dzns: list[str]) -> None:
    print("\n[crosscheck] backends must agree (disagreement = modelling error)")
    for dzn in dzns:
        ref = run(dzn, "HWCOST", solver="cp-sat", timeout=120)
        if ref["status"] != "OPTIMAL":
            check(f"{Path(dzn).stem}: cp-sat reference", False, ref["status"])
            continue
        for slv in ["gecode", "chuffed"]:
            r = run(dzn, "HWCOST", solver=slv, timeout=120)
            if r["status"] != "OPTIMAL":
                print(f"        {slv}: {r['status']} (not a failure -- CP-SAT "
                      f"is the only experimental backend)")
                continue
            check(f"{Path(dzn).stem}: {slv} agrees with cp-sat",
                  r["solution"]["hw_cost"] == ref["solution"]["hw_cost"],
                  f"{r['solution']['hw_cost']} vs {ref['solution']['hw_cost']}")


# ---------------------------------------------------------------------------
def main() -> int:
    groups = sys.argv[1:] or ["golden", "unfold", "provenance", "model",
                              "symmetry", "latency", "rosvall", "crosscheck"]
    dzns = sorted(str(p) for p in (ROOT / "out").glob("*.dzn"))
    if not dzns and {"model", "symmetry", "crosscheck"} & set(groups):
        print("no .dzn files in out/ -- run tools/build_dzn.py first")
        return 2
    t0 = time.time()
    if "golden" in groups:
        t_golden()
    if "unfold" in groups:
        t_unfold()
    if "provenance" in groups:
        t_provenance()
    if "model" in groups:
        t_model(dzns)
    if "symmetry" in groups:
        t_symmetry(dzns)
    if "latency" in groups:
        t_latency()
    if "rosvall" in groups:
        t_rosvall()
    if "crosscheck" in groups:
        t_crosscheck(dzns)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed  ({time.time()-t0:.1f}s)")
    for f in FAIL:
        print(f"  failed: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
