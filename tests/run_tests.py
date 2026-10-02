#!/usr/bin/env python3
"""SafeDSE test harness.

Groups:
  golden    -- the Python oracles agree with hand-computed values
  unfold    -- SDF->HSDF preserves the C.6 properties, incl. multi-rate cases
  model     -- the CP model agrees with the oracles on real instances
  symmetry  -- Rosvall 23/33 change runtime but never the optimum (Q14)
  gsn       -- the generated safety argument cites evidence that really ran
  crosscheck-- CP-SAT, Gecode and Chuffed agree on small instances

Run:  python3 tests/run_tests.py [group ...]
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

import yaml

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
            and not Path(d).stem.startswith(("r_", "s_", "x_", "m_",
                                             "p_", "d_", "f_", "c_", "pc"))]
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


def t_safety() -> None:
    """Phase 3: SIL isolation, promotion pricing, and cost-profile sensitivity."""
    print("\n[safety] isolation, promotion, and cost-profile sensitivity")
    noiso = ROOT / "out" / "s_myklebust2015.dzn"
    if not noiso.exists():
        print("  SKIP  build the Phase-3 instances first")
        return

    # Koopman rule 2 must hold in the returned solution, checked externally.
    for k in [3, 2, 1]:
        r = run(str(noiso), "TOTALCOST", {"NPROCS": k}, timeout=120)
        if r["status"] != "OPTIMAL":
            check(f"noiso nprocs<={k}: solved", False, r["status"])
            continue
        ok, msg = _verify(str(noiso), r["solution"])
        check(f"noiso nprocs<={k}: isolation invariants hold "
              f"(promo={r['solution']['promotion_cost']})", ok, msg)

    # Consolidation must cost promotion, monotonically.
    promos = []
    for k in [3, 2, 1]:
        r = run(str(noiso), "TOTALCOST", {"NPROCS": k}, timeout=120)
        promos.append(r["solution"]["promotion_cost"] if "solution" in r else None)
    check("fewer cores costs more promotion",
          promos == sorted(promos) and promos[0] == 0,
          f"promotion by core count 3/2/1 = {promos}")

    # Turning promotion off must make the tight case infeasible rather than
    # silently returning a mixed-SIL core.
    nop = ROOT / "out" / "s_nopromo.dzn"
    if nop.exists():
        a = run(str(nop), "TOTALCOST", {"NPROCS": 3}, timeout=90)
        b = run(str(nop), "TOTALCOST", {"NPROCS": 2}, timeout=90)
        check("allow_promotion=false: 3 cores feasible", a["status"] == "OPTIMAL",
              a["status"])
        check("allow_promotion=false: 2 cores correctly UNSAT",
              b["status"] == "UNSAT", b["status"])

    # C.8: the cost profile is an experimental variable. On expensive hardware
    # it once changed the optimal ARCHITECTURE (klosterman: 1 core), but only
    # while klosterman's SIL 3 took the ASIL C row of Klosterman's table; with
    # the ASIL D row (cost_model.xml) all three profiles buy 3 cores. What
    # stays true, and is checked, is that the profile prices consolidation:
    # the promotion cost of a one-core design differs between profiles.
    got = {}
    for prof in ["myklebust2015", "klosterman", "do178b"]:
        f = ROOT / "out" / f"x_{prof}.dzn"
        if not f.exists():
            continue
        r = run(str(f), "TOTALCOST", {"NPROCS": 1}, timeout=120)
        if r["status"] == "OPTIMAL":
            got[prof] = r["solution"]["promotion_cost"]
    if len(got) == 3:
        check(f"cost profile changes the price of consolidation {got}",
              len(set(got.values())) == 3,
              "two profiles price one-core promotion alike")


def t_patterns() -> None:
    """Phase 4: the guarded-superposition mechanism.

    Three claims, each checked rather than asserted:
      1. the library is well formed under the C.4 obligations;
      2. with every pattern forced to `none` the model reproduces the Phase-3
         numbers EXACTLY -- the machinery must be neutral when disabled;
      3. two structurally identical patterns differing only in placement yield
         different mappings, which is what proves a pattern is a rewrite PLUS a
         placement relation rather than topology alone.
    """
    print("\n[patterns] guarded superposition")
    sys.path.insert(0, str(ROOT / "tools"))
    from patterns import check_pattern, load_patterns

    for lib in ["patterns.yaml", "patterns_strict.yaml"]:
        f = ROOT / "data" / lib
        if not f.exists():
            continue
        pats = load_patterns(f)
        bad = [m for p in pats for m in check_pattern(p)]
        check(f"{lib}: {len(pats)} records well formed (C.4)", not bad,
              "; ".join(bad))

    # (2) neutrality regression
    base = ROOT / "out" / "s_myklebust2015.dzn"
    forced = ROOT / "out" / "p_none.dzn"
    if base.exists() and forced.exists():
        for k in [3, 2, 1]:
            a = run(str(base), "TOTALCOST", {"NPROCS": k}, timeout=120)
            b = run(str(forced), "TOTALCOST", {"NPROCS": k}, timeout=120)
            if "solution" not in a or "solution" not in b:
                check(f"forced-none regression at {k} cores: solved", False,
                      f"{a['status']}/{b['status']}")
                continue
            ma, mb = a["solution"]["metric"], b["solution"]["metric"]
            check(f"forced-none reproduces Phase 3 at {k} cores", ma == mb,
                  f"{ma} vs {mb}")

    # anti-patterns and malformed records must be REJECTED, not merely absent
    from patterns import Pattern
    rejects = [
        ("Koopman's Attempted High SIL Doer/Checker", Pattern(
            id="attempted", components=[{"role": "c", "wcet_type": "x"}],
            edges=[{"from": "owner", "to": "c", "tokens": 0},
                   {"from": "c", "to": "owner", "tokens": 1}],
            placement=[{"relation": "SAME", "members": ["owner", "c"]}],
            achieves_sil=[3], covers_faults=["random_hw"],
            failure_mode="silent")),
        ("a pattern whose cycle has no initial token", Pattern(
            id="deadlocks", components=[{"role": "r", "wcet_type": "x"}],
            edges=[{"from": "owner", "to": "r", "tokens": 0},
                   {"from": "r", "to": "owner", "tokens": 0}],
            achieves_sil=[3], covers_faults=["random_hw"])),
        ("SIL 3 claimed with no redundancy", Pattern(
            id="bare", achieves_sil=[3], covers_faults=["random_hw"])),
        ("an explicit voter before Phase 6", Pattern(
            id="nvp", components=[{"role": "v", "wcet_type": "x"}],
            edges=[{"from": "owner", "to": "v", "tokens": 0}],
            voter="explicit", achieves_sil=[3], covers_faults=["random_hw"])),
    ]
    for label, p in rejects:
        check(f"C.4 rejects {label}", bool(check_pattern(p)))

    # (3) placement, not topology, distinguishes the two Doer/Checker patterns
    got = {}
    for fm in ["random_hw", "systematic_sw"]:
        f = ROOT / "out" / f"d_{fm}.dzn"
        if not f.exists():
            continue
        r = run(str(f), "TOTALCOST", timeout=150)
        if r["status"] != "OPTIMAL":
            check(f"{fm}: solved", False, r["status"])
            continue
        sol = r["solution"]
        got[fm] = sol["nprocs"]
        # checkers are the second half of the node list (one slot per actor)
        half = len(sol["proc"]) // 2
        pairs = [(sol["proc"][i], sol["proc"][half + i])
                 for i in range(half) if sol["active"][half + i]]
        same = all(u == v for u, v in pairs)
        diff = all(u != v for u, v in pairs)
        if fm == "random_hw":
            check("random_hw picks the SEPARATED checker "
                  f"({len(pairs)} pairs, all on distinct cores)", diff and pairs,
                  f"pairs={pairs}")
        else:
            check("systematic_sw picks the CO-LOCATED checker "
                  f"({len(pairs)} pairs, all sharing a core)", same and pairs,
                  f"pairs={pairs}")
    if len(got) == 2:
        check(f"fault model changes the core count {got}",
              len(set(got.values())) > 1, "both fault models agree")

    # (4) a full-replica component (`<owner>` WCET type) of a multi-rate
    # owner: the owner exists only as HSDF copies `name#k`, and the WCET table
    # keys on task types that differ from the actor names
    import xml.etree.ElementTree as ET
    src = (ROOT / "data" / "apps" / "jpeg_r3.sdf.xml").read_text()
    app = Path("/tmp/mr_owner.sdf.xml")
    app.write_text(re.sub(r'(<actor name="[^"]*" type=")([^"]*)"', r'\1\2_t"',
                          src))
    saf = Path("/tmp/mr_owner_safety.xml")
    saf.write_text('<safety fault_model="random_hw" allow_promotion="true">'
                   '<default sil="1"/><actor name="CC" sil="3"/></safety>')
    wc = Path("/tmp/mr_owner_wcets.xml")
    subprocess.run([sys.executable, str(ROOT / "tools" / "mkwcets.py"),
                    "--app", str(app), "--platform",
                    str(ROOT / "data" / "platform" / "mixed_3type.xml"),
                    "--patterns", str(ROOT / "data" / "patterns.yaml"),
                    "-o", str(wc)], capture_output=True, check=True)
    tree = ET.parse(wc)
    for m in list(tree.getroot()):
        if m.tag == "mapping" and not m.get("task_type").endswith("_t"):
            tree.getroot().remove(m)
    tree.write(wc)
    p = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_dzn.py"), "--app", str(app),
         "--platform", str(ROOT / "data" / "platform" / "mixed_3type.xml"),
         "--wcets", str(wc), "--constraints", str(ROOT / "data" / "desConst.xml"),
         "--cost-model", str(ROOT / "data" / "cost_model.xml"),
         "--safety", str(saf), "--patterns", str(ROOT / "data" / "patterns.yaml"),
         "-o", "/tmp/mr_owner.dzn"], capture_output=True, text=True)
    check("multi-rate owner: full-replica component resolves the owner's "
          "WCET type", p.returncode == 0, p.stderr[-300:])


def t_catalogue() -> None:
    """Phase 5: the full Koopman catalogue, and what DIVERSE actually forbids."""
    print("\n[catalogue] full Koopman set")
    sys.path.insert(0, str(ROOT / "tools"))
    from patterns import load_patterns

    pats = load_patterns(ROOT / "data" / "patterns.yaml")
    check(f"catalogue has {len(pats)} patterns", len(pats) >= 9,
          f"only {len(pats)}")
    # `none` must stop at SIL 1: from SIL 2 up, IEC 61508 expects diagnostics
    nn = next(p for p in pats if p.id == "none")
    check("`none` is capped at SIL 1 per IEC 61508",
          max(nn.achieves_sil) == 1, f"achieves_sil={nn.achieves_sil}")

    for stem in ["f_random_hw", "f_sw3", "f_both3"]:
        f = ROOT / "out" / f"{stem}.dzn"
        if not f.exists():
            continue
        r = run(str(f), "TOTALCOST", timeout=240)
        if r["status"] != "OPTIMAL":
            check(f"{stem}: solved", False, r["status"])
            continue
        ok, msg = _verify(str(f), r["solution"])
        check(f"{stem}: solves and every placement relation verifies "
              f"({r['solution']['nprocs']} cores)", ok, msg)


def t_multiapp() -> None:
    """Q15: per-application periods couple exactly when applications share a core.

    Rosvall computes period[z] as the MCR of the MSAG's connected component
    containing z, so sharing a processing element forces a common period -- and
    therefore forces every application on that core down to the TIGHTEST bound
    among them. Verified by squeezing the core count until sharing is unavoidable.
    """
    print("\n[multiapp] period coupling under core sharing (Q15)")
    dzn = ROOT / "out" / "r_2app.dzn"
    if not dzn.exists():
        print("  SKIP  build out/r_2app.dzn first")
        return
    a = run(str(dzn), "HWCOST", timeout=150)
    if a["status"] != "OPTIMAL":
        check("2 apps with cores to spare: solved", False, a["status"])
        return
    mu = a["solution"]["mu"]
    check(f"disjoint cores give independent periods mu={mu}",
          len(set(mu)) > 1, "periods coincided; coupling may be over-applied")
    ok, msg = _verify(str(dzn), a["solution"])
    check("2 apps: solution verifies", ok, msg)
    # squeeze until sharing is forced: a common period must then meet the
    # tightest bound, which these two applications cannot do
    b = run(str(dzn), "HWCOST", {"NPROCS": 3}, timeout=150)
    check("forced sharing with incompatible bounds is UNSAT",
          b["status"] == "UNSAT", b["status"])
    for stem in ["r_3app"]:
        f = ROOT / "out" / f"{stem}.dzn"
        if f.exists():
            r = run(str(f), "HWCOST", timeout=200)
            if r["status"] == "OPTIMAL":
                ok, msg = _verify(str(f), r["solution"])
                check(f"{stem}: mu={r['solution']['mu']} verifies", ok, msg)
            else:
                check(f"{stem}: solved", False, r["status"])


def t_comm() -> None:
    """Phase 6: TDMA communication as guarded superposition."""
    print("\n[comm] TDMA block/send/rec superposition")
    for a in ["a_sobel", "b_susan", "c_rasta"]:
        ideal = ROOT / "out" / f"r_{a}.dzn"
        tdma = ROOT / "out" / f"c_{a}.dzn"
        if not (ideal.exists() and tdma.exists()):
            continue
        # relax the period bound: communication delay can push a mapping past a
        # constraint that was feasible with ideal communication, which is the
        # point of modelling it
        loose = Path(f"/tmp/_c_{a}.dzn")
        loose.write_text(re.sub(r"^period_ub = .*$", "period_ub = [100000];",
                                tdma.read_text(), flags=re.M))
        li = Path(f"/tmp/_i_{a}.dzn")
        li.write_text(re.sub(r"^period_ub = .*$", "period_ub = [100000];",
                             ideal.read_text(), flags=re.M))
        ri = run(str(li), "HWCOST", timeout=150)
        rt = run(str(loose), "HWCOST", timeout=200)
        if ri["status"] != "OPTIMAL" or rt["status"] != "OPTIMAL":
            check(f"{a}: both ideal and TDMA solve", False,
                  f"{ri['status']}/{rt['status']}")
            continue
        mi, mt = ri["solution"]["mu"][0], rt["solution"]["mu"][0]
        check(f"{a}: TDMA period {mt} >= ideal {mi} "
              f"(communication cannot make a schedule faster)", mt >= mi)
        nrem = rt["solution"].get("n_remote", 0)
        slots = sum(rt["solution"].get("tdma_alloc", []))
        check(f"{a}: {nrem} remote channels, {slots} TDMA slots allocated",
              (nrem > 0) == (slots > 0),
              f"remote={nrem} slots={slots} -- slots must be allocated iff "
              f"something is sent")


def t_commsil() -> None:
    """Q21: whether bus transfers count against their core's SIL is a designer
    setting, and the three modes must all be expressible and self-consistent."""
    print("\n[commsil] Q21 communication-SIL modes")
    import subprocess as sp
    outs = {}
    for mode in ["exempt", "inherit", "core"]:
        out = Path(f"/tmp/_csil_{mode}.dzn")
        r = sp.run([sys.executable, str(ROOT / "tools" / "build_dzn.py"),
                    "--app", str(ROOT / "data/rosvall/c_rasta.hsdf.xml"),
                    "--platform", str(ROOT / "data/rosvall/platform.xml"),
                    "--wcets", str(ROOT / "data/rosvall/WCETs.xml"),
                    "--constraints", str(ROOT / "data/rosvall/desConst.xml"),
                    "--cost-model", str(ROOT / "data/cost_model.xml"),
                    "--comm", "tdma", "--comm-sil", mode, "-o", str(out)],
                   capture_output=True, text=True)
        check(f"comm-sil={mode}: instance builds", r.returncode == 0,
              r.stderr[-200:])
        if r.returncode:
            continue
        loose = Path(f"/tmp/_csill_{mode}.dzn")
        loose.write_text(re.sub(r"^period_ub = .*$", "period_ub = [100000];",
                                out.read_text(), flags=re.M))
        res = run(str(loose), "TOTALCOST", timeout=150)
        if res["status"] != "OPTIMAL":
            check(f"comm-sil={mode}: solves", False, res["status"])
            continue
        outs[mode] = res["solution"]["metric"]
        ok, msg = _verify(str(loose), res["solution"])
        check(f"comm-sil={mode}: solution verifies", ok, msg)
    # exempt can never cost more than core: exempting transfers from Koopman
    # rule 2 only ever removes constraints
    if "exempt" in outs and "core" in outs:
        check("exempt is no more expensive than core",
              outs["exempt"][4] <= outs["core"][4],
              f"exempt total {outs['exempt'][4]} > core {outs['core'][4]}")


def t_composition() -> None:
    """Safety patterns and TDMA communication active at once.

    Both are guarded superposition (architecture doc A.5) and each works alone,
    but composing them was the one thing that did not work: the model grew to
    265 nodes and found no solution in 100 s. The cause was that communication
    actors were being folded into the PROCESSOR static order, whose machinery is
    O(n^2), when they belong on the bus. Excluding them took a_sobel with TDMA
    alone from 3.1 s to 0.66 s and made the composition solvable at all.
    """
    print("\n[composition] safety patterns + TDMA together")
    f = ROOT / "out" / "pc_sobel.dzn"
    if not f.exists():
        print("  SKIP  build out/pc_sobel.dzn first")
        return
    loose = Path("/tmp/_pc.dzn")
    loose.write_text(re.sub(r"^period_ub = .*$", "period_ub = [100000];",
                            f.read_text(), flags=re.M))
    r = run(str(loose), "TOTALCOST", timeout=200)
    if r["status"] != "OPTIMAL":
        check("patterns + TDMA solves", False, r["status"])
        return
    ok, msg = _verify(str(loose), r["solution"])
    check(f"patterns + TDMA solves and verifies "
          f"({r['seconds']:.1f}s, mu={r['solution']['mu'][0]})", ok, msg)
    sel = {r["solution"]["pat"][i] for i in range(len(r["solution"]["pat"]))}
    check("a safety pattern is actually applied", len(sel) > 1,
          "only one pattern selected; the composition may be trivial")

    # What the loosening above is hiding, stated as a number.
    # out/pc_sobel.dzn carries Rosvall's published period bound of 400 for
    # a_sobel, but it ALSO applies a SIL-3 pattern and TDMA communication. The
    # bound was measured for neither. So the raw instance is infeasible, and
    # the interesting quantity is by how much: safety plus communication costs
    # this application a third of its throughput. Pinned here so that if a
    # future change makes 400 reachable, someone has to explain why rather than
    # quietly enjoy it.
    # Explained change: until slots were shared only by equal WCET type, the
    # checker of high_sil_isolated_checker sat in a slot typed as a full
    # replica of get_pixel and was priced at get_pixel's WCET (256-384
    # instead of 77-115). The minimum period was 512; priced as a checker it
    # is 333, below the published 400. Four workers: at -p 1 the
    # FIXED_SEARCH strategy no longer proves this within minutes.
    r2 = run(str(loose), "THROUGHPUT", timeout=200, threads=4)
    if r2["status"] != "OPTIMAL":
        check("pc_sobel: minimum period is attainable", False, r2["status"])
        return
    ok2, msg2 = _verify(str(loose), r2["solution"])
    mn = r2["solution"]["mu"][0]
    check(f"pc_sobel: minimum period with patterns+TDMA is {mn}, below the "
          f"published bound of 400", ok2 and mn == 333,
          msg2 or f"got {mn}, expected 333")


def t_gsn() -> None:
    """Phase 8: the GSN safety-argument generator.

    The thing that makes a generated safety argument dangerous is that it reads
    exactly as well when it is wrong, so the tests here are mostly about the
    generator REFUSING things:

      1. every leaf is evidence or an admitted gap -- the self-audit, checked
         by breaking an argument on purpose and confirming the audit sees it;
      2. the fault model is recovered from the .dzn rather than trusted to a
         flag, and a contradicting flag is rejected;
      3. a solution the verifier rejects yields no argument at all;
      4. every Solution cites a check that really ran in that verifier
         invocation, by index, and the cited record really passed;
      5. widening the fault model moves scenarios from "out of scope" to
         "supported by evidence" -- the property that makes the argument a
         function of the design rather than of the catalogue.
    """
    print("\n[gsn] safety-argument generation")
    sys.path.insert(0, str(ROOT / "tools"))
    import json as _json

    import gsn as G
    from patterns import load_patterns

    pats = load_patterns(str(ROOT / "data" / "patterns.yaml"))
    tdoc = yaml.safe_load((ROOT / "data" / "gsn_tactics.yaml").read_text())
    tactics = {t["name"]: t for t in tdoc["tactics"]}

    # every tactic a pattern names must exist in the tactic table, or the
    # argument silently loses a strategy
    missing = sorted({t for p in pats for t in p.tactics if t not in tactics})
    check("every pattern tactic is in the tactic table", not missing,
          f"unknown: {missing}")
    # and every deployment_relations entry must be a relation the model knows
    known = set(G.RELN.values())
    badrel = sorted({r for t in tactics.values()
                     for r in (t.get("deployment_relations") or [])
                     if r not in known})
    check("tactic deployment_relations are real placement relations",
          not badrel, f"unknown: {badrel}")
    # a deployment goal states what its records establish, one claim per
    # relation; DIFFERENT allows one card, so it must not claim FCR separation
    noclaim = sorted({(t["name"], r) for t in tactics.values()
                      for r in (t.get("deployment_relations") or [])
                      if r not in (t.get("relation_claims") or {})})
    check("every deployment relation has its own claim", not noclaim,
          f"missing: {noclaim}")
    rr = tactics.get("Replication Redundancy", {})
    check("a DIFFERENT record is never claimed as FCR separation",
          "different fault containment regions" not in
          " ".join(str(rr.get("relation_claims", {}).get("DIFFERENT", ""))
                   .split()))

    def gen(name, dzn, metric="TOTALCOST", bounds=None):
        r = run(str(dzn), metric, bounds or {}, timeout=200)
        if "solution" not in r:
            return None, None, r["status"]
        sp = Path(f"/tmp/gsn_{name}.json")
        sp.write_text(_json.dumps(r["solution"]))
        rp = Path(f"/tmp/gsn_{name}.report.json")
        subprocess.run([sys.executable, str(ROOT / "tools" / "verify.py"),
                        "--dzn", str(dzn), "--solution", str(sp), "--quiet",
                        "--json-report", str(rp)], capture_output=True)
        rep = _json.loads(rp.read_text())
        d = G.parse_dzn(str(dzn))
        fm, _how = G.infer_fault_model(d, pats)
        arg = G.build(d, r["solution"], rep, pats, tactics, fm, name)
        return arg, rep, fm

    # ---- 2. fault model inference ---------------------------------------
    want = {"f_random_hw": "random_hw", "f_sw3": "systematic_sw",
            "f_both3": "both"}
    for stem, expect in want.items():
        f = ROOT / "out" / f"{stem}.dzn"
        if not f.exists():
            print(f"  SKIP  {stem}.dzn not built")
            continue
        got, how = G.infer_fault_model(G.parse_dzn(str(f)), pats)
        check(f"{stem}: fault model recovered from the .dzn as {expect}",
              got == expect, f"got {got} ({how})")

    # ---- 1/4. structure and evidence on a real argument ------------------
    f = ROOT / "out" / "f_random_hw.dzn"
    if not f.exists():
        print("  SKIP  out/f_random_hw.dzn not built")
    else:
        arg, rep, fm = gen("frh", f)
        if arg is None:
            check("f_random_hw: solved", False, str(fm))
        else:
            check("f_random_hw: argument passes its own audit",
                  not arg.audit(), "; ".join(arg.audit()))
            sols = [e for e in arg.el.values() if e.kind == "Solution"]
            check("every Solution cites at least one verifier check",
                  all(e.evidence for e in sols))
            check("every cited check exists and passed",
                  all(0 <= j < len(rep["checks"]) and rep["checks"][j]["ok"]
                      for e in sols for j in e.evidence))
            # the honest headline: a DSE cannot discharge most of a safety case
            und = [g for g in arg.el.values()
                   if g.kind == "Goal" and g.undeveloped]
            check("undeveloped goals are present and carry a reason",
                  bool(und) and all(g.note for g in und))
            # a value-domain tactic must never acquire mapping evidence
            for e in arg.el.values():
                if e.kind == "Strategy" and "Sanity Check tactic" in e.text:
                    kids = [arg.el[c] for c in e.supported_by]
                    check("Sanity Check yields only undeveloped goals",
                          all(k.undeveloped for k in kids
                              if k.kind == "Goal"))
                    break

            # ---- claims match their evidence (review rev1, D1, D3, D7, D9)
            goals = [e for e in arg.el.values() if e.kind == "Goal"]
            check("no goal claims that a SIL is attained",
                  not any("attains SIL" in g.text for g in goals))
            rel_of = {f"In the deployed mapping, {' '.join(str(c).split())}.": r
                      for t in tactics.values()
                      for r, c in (t.get("relation_claims") or {}).items()}
            deps = [g for g in goals if g.text in rel_of]
            wrong = [g.id for g in deps
                     for c in g.supported_by
                     for j in arg.el[c].evidence
                     if rep["checks"][j].get("relation") != rel_of[g.text]]
            check("every deployment goal cites only records of the relation "
                  "it claims", bool(deps) and not wrong, f"{wrong}")
            resid = {r for t in tactics.values()
                     for r in (t.get("residual_common_cause") or {})}
            lone = [g.id for g in deps if rel_of[g.text] in resid
                    and not any(arg.el[s].kind == "Goal"
                                and arg.el[s].undeveloped
                                and arg.el[s].text.startswith("Common-cause")
                                for p_ in arg.el.values()
                                if g.id in p_.supported_by
                                for s in p_.supported_by)]
            check("a separation claim comes with an undeveloped "
                  "common-cause goal", not lone, f"{lone}")
            d = G.parse_dzn(str(f))
            act = _json.loads(Path("/tmp/gsn_frh.json").read_text())["active"]
            comp = [i + 1 for i, nm in enumerate(G._l(d["node_name"]))
                    if "~" in nm and not nm.startswith("__comm") and act[i]]
            cited = {rep["checks"][j].get("node") for e in sols
                     for j in e.evidence
                     if rep["checks"][j]["kind"] == "sil_actor"}
            check("every active pattern component has cited SIL "
                  "provisioning", bool(comp) and set(comp) <= cited,
                  f"uncited nodes {sorted(set(comp) - cited)}")
            fr = [g for g in goals if g.undeveloped
                  and "process safety time" in g.text]
            check("the argument carries one undeveloped fault-reaction goal",
                  len(fr) == 1, f"{len(fr)}")

            # ---- 1. the audit must actually catch a broken argument -------
            probe = arg.add("Goal", "an unsupported claim nobody checked")
            check("audit catches a leaf goal with no evidence and no marker",
                  any("unsupported claim" in b for b in arg.audit()))
            del arg.el[probe]
            arg.order.remove(probe)
            probe = arg.add("Goal", "a gap admitted without saying why",
                            undeveloped=True)
            check("audit catches an undeveloped goal without a reason",
                  any("without a reason" in b for b in arg.audit()))
            del arg.el[probe]
            arg.order.remove(probe)
            keep = list(sols[0].evidence)
            sols[0].evidence = [len(rep["checks"]) + 7]
            check("audit with the check log catches a citation past its end",
                  any("not a passed record" in b
                      for b in arg.audit(rep["checks"])))
            sols[0].evidence = keep

            # ---- the verifier re-derives what the model derives -----------
            s0 = _json.loads(Path("/tmp/gsn_frh.json").read_text())
            comm = [bool(x) for x in G._l(d.get("comm_actor", []))]
            comm += [False] * (d["n"] - len(comm))

            def rejects_by(kind, mutate):
                s = _json.loads(_json.dumps(s0))
                mutate(s)
                sp = Path("/tmp/gsn_frh_mut.json")
                sp.write_text(_json.dumps(s))
                rp = Path("/tmp/gsn_frh_mut.report.json")
                rp.unlink(missing_ok=True)
                subprocess.run([sys.executable,
                                str(ROOT / "tools" / "verify.py"),
                                "--dzn", str(f), "--solution", str(sp),
                                "--quiet", "--json-report", str(rp)],
                               capture_output=True)
                if not rp.exists():
                    return False
                r = _json.loads(rp.read_text())
                return not r["ok"] and any(c["kind"] == kind and not c["ok"]
                                           for c in r["checks"])

            def lower_wcet(s):
                i = next(i for i in range(d["n"])
                         if act[i] and not comm[i] and s["T"][i] > 0)
                s["T"][i] -= 1

            def deactivate(s):
                s["active"][comp[0] - 1] = False
                s["T"][comp[0] - 1] = 0
            check("verifier rejects a lowered WCET by its wcet record",
                  rejects_by("wcet", lower_wcet))
            check("verifier rejects a deactivated pattern component by its "
                  "activation record", rejects_by("activation", deactivate))
            check("verifier rejects a solution without the pat field",
                  rejects_by("input", lambda s: s.pop("pat")))

    # ---- 5. widening the fault model widens the argument -----------------
    fb = ROOT / "out" / "f_both3.dzn"
    if not (f.exists() and fb.exists()):
        print("  SKIP  need f_random_hw.dzn and f_both3.dzn")
    else:
        # Whether the random_hw optimum selects a pattern with a systematic-
        # fault scenario is a tie-break (high_sil_isolated_checker and
        # low_sil_doer_checker have none, at the same total cost), so the
        # out-of-scope check runs on the same inputs with a catalogue in which
        # every pattern for SIL >= 2 has such a scenario.
        import yaml as _y
        keep = [x for x in _y.safe_load(open(ROOT / "data" / "patterns.yaml"))
                ["patterns"] if x["id"] not in ("high_sil_isolated_checker",
                                                "low_sil_doer_checker",
                                                "dual_two_of_two")]
        cat = Path("/tmp/gsn_sys_catalogue.yaml")
        cat.write_text(_y.safe_dump({"patterns": keep}, sort_keys=False))
        fsys = Path("/tmp/gsn_frh_sys.dzn")
        subprocess.run(
            [sys.executable, str(ROOT / "tools" / "build_dzn.py"),
             "--app", str(ROOT / "data" / "apps" / "c_rasta.hsdf.xml"),
             "--platform", str(ROOT / "data" / "platform" / "mixed_noiso.xml"),
             "--wcets", str(ROOT / "data" / "WCETs_mixed.xml"),
             "--constraints", str(ROOT / "data" / "desConst.xml"),
             "--cost-model", str(ROOT / "data" / "cost_model.xml"),
             "--safety", str(ROOT / "data" / "safety_fm_random_hw.xml"),
             "--patterns", str(cat), "-o", str(fsys)],
            capture_output=True)
        a0 = gen("frh_sys", fsys)[0] if fsys.exists() else None
        a1, r1, _ = gen("frh2", f)
        a2, r2, _ = gen("fb", fb)
        if a0 and a1 and a2:
            check("random_hw leaves systematic-fault scenarios out of scope",
                  len(a0.out_of_scope) > 0,
                  f"out_of_scope={a0.out_of_scope}")
            check("both leaves none out of scope",
                  len(a2.out_of_scope) == 0,
                  f"out_of_scope={a2.out_of_scope}")
            d1 = sum(1 for c in r1["checks"]
                     if c["kind"] == "placement" and c["relation"] == "DIVERSE")
            d2 = sum(1 for c in r2["checks"]
                     if c["kind"] == "placement" and c["relation"] == "DIVERSE")
            check("DIVERSE evidence appears only once diversity is required",
                  d1 == 0 and d2 > 0, f"random_hw={d1}, both={d2}")

    # ---- 3. refuse to argue over a rejected solution ---------------------
    if f.exists():
        r = run(str(f), "TOTALCOST", {}, timeout=200)
        if "solution" in r:
            sp = Path("/tmp/gsn_bad.json")
            bad = dict(r["solution"])
            # a period below the busiest core's load is exactly the open-chain
            # bug's signature, and the verifier must reject it
            bad["mu"] = [1]
            sp.write_text(_json.dumps(bad))
            p = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "gsn.py"),
                 "--dzn", str(f), "--solution", str(sp),
                 "--out", "/tmp/gsn_bad_out"],
                capture_output=True, text=True)
            check("refuses to generate from a solution the verifier rejects",
                  p.returncode == 2 and not
                  Path("/tmp/gsn_bad_out.gsn.md").exists(),
                  f"rc={p.returncode}")

    # ---- a voter must never share a slot (and its WCET) with a replica ---
    from patterns import expand
    from sdf3 import SDFGraph, Actor, Channel
    demo = ROOT / "data" / "patterns_explicit_voter_demo.yaml"
    clash = ROOT / "data" / "patterns_explicit_voter.yaml"
    if clash.exists():
        import yaml as _y
        def _recs(f):
            d = _y.safe_load(open(f))
            return d["patterns"] if isinstance(d, dict) else d
        recs = [x for x in _recs(ROOT / "data" / "patterns.yaml")
                if x["id"] in ("none", "dual_two_of_two")]
        recs += [x for x in _recs(clash) if x["id"] == "nvp_three_version"]
        cf = Path("/tmp/gsn_clash.yaml")
        cf.write_text(_y.safe_dump({"patterns": recs}, sort_keys=False))
        g = SDFGraph(name="t")
        g.actors = [Actor(name="a", type="ta", exec_time=10),
                    Actor(name="b", type="tb", exec_time=10)]
        g.channels = [Channel(name="ab", src="a", dst="b", prod=1, cons=1,
                              initial_tokens=0)]
        sup = expand(g, load_patterns(str(cf)), {"a": 3, "b": 0},
                     "random_hw", platform_fcrs=9, platform_cores=9,
                     platform_ctypes=4, platform_ctype_sils=[4, 4, 4, 4])
        slots = {x.name: x.type for x in sup.graph.actors if "~" in x.name}
        voters = [nm for nm, t in slots.items() if t.startswith("voter_")]
        ids = [p.id for p in sup.patterns]
        ok = (len(voters) == 1 and len(slots) == 4 and
              [ids[pi] for pi in sup.guard_of[voters[0]]]
              == ["nvp_three_version"])
        check("a voter gets its own slot, never a replica's (slots by "
              "wcet_type)", ok, f"slots {slots}")

    # ---- rendering ------------------------------------------------------
    if Path("/tmp/gsn_frh.json").exists() and f.exists():
        p = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "gsn.py"), "--dzn", str(f),
             "--solution", "/tmp/gsn_frh.json", "--out", "/tmp/gsn_render",
             "--quiet"], capture_output=True, text=True)
        ok = all(Path(f"/tmp/gsn_render.gsn.{e}").exists()
                 for e in ("json", "dot", "md"))
        check("emits json, dot and md", ok and p.returncode == 0, p.stderr[-200:])
        if ok:
            doc = _json.loads(Path("/tmp/gsn_render.gsn.json").read_text())
            ids = {e["id"] for e in doc["elements"]}
            dangling = [c for e in doc["elements"]
                        for c in e["supportedBy"] + e["inContextOf"]
                        if c not in ids]
            check("no dangling references in the emitted graph", not dangling,
                  str(dangling[:3]))
            dot = Path("/tmp/gsn_render.gsn.dot").read_text()
            check("undeveloped goals are marked in the diagram",
                  dot.count("UNDEVELOPED") ==
                  sum(1 for e in doc["elements"] if e["undeveloped"]))


    # ---- catalogue mismatch must be refused, not degraded ---------------
    # The nastiest failure this tool has had. build() looks patterns up by
    # name; an absent one becomes None and falls through to the "no structural
    # pattern applied" branch, producing a fluent, audit-passing argument that
    # says an actor is argued by development process alone when it in fact
    # carries three-version programming and a voter.
    vn = ROOT / "out" / "v_nvp.dzn"
    if not vn.exists():
        print("  SKIP  out/v_nvp.dzn not built")
    else:
        r = run(str(vn), "TOTALCOST", {}, timeout=200)
        if "solution" not in r:
            check("v_nvp: solved", False, r["status"])
        else:
            sp = Path("/tmp/gsn_vnvp.json")
            sp.write_text(_json.dumps(r["solution"]))
            p = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "gsn.py"), "--dzn",
                 str(vn), "--solution", str(sp), "--out", "/tmp/gsn_mm"],
                capture_output=True, text=True)
            check("refuses to generate against the wrong pattern catalogue",
                  p.returncode == 4
                  and not Path("/tmp/gsn_mm.gsn.md").exists(),
                  f"rc={p.returncode}")
            demo = ROOT / "data" / "patterns_explicit_voter_demo.yaml"
            if demo.exists():
                p2 = subprocess.run(
                    [sys.executable, str(ROOT / "tools" / "gsn.py"), "--dzn",
                     str(vn), "--solution", str(sp), "--out", "/tmp/gsn_ok",
                     "--patterns", str(demo), "--quiet"],
                    capture_output=True, text=True)
                ok = Path("/tmp/gsn_ok.gsn.md").exists()
                check("generates against the catalogue the instance was built "
                      "with", p2.returncode == 0 and ok, p2.stderr[-200:])
                if ok:
                    md = Path("/tmp/gsn_ok.gsn.md").read_text()
                    # the explicit voter must appear as a real component, and
                    # the actor must NOT be argued as pattern-free
                    check("the explicit voter appears in the argument",
                          "voter on core" in md)
                    check("an actor with a pattern is not argued as "
                          "pattern-free",
                          "nvp_three_version" in md)


def t_crosscheck(dzns: list[str]) -> None:
    """Backends must agree. UNSAT is an answer, not a harness failure.

    This group used to demand OPTIMAL from the cp-sat reference and record a
    failure otherwise, which conflated two different things: a backend falling
    over, and an instance that is genuinely infeasible under its own declared
    bounds. out/pc_sobel.dzn is the second -- it carries Rosvall's published
    period bound of 400 for a_sobel while ALSO applying a SIL-3 pattern and
    TDMA communication, and the minimum attainable period once both are present
    is 512 (measured, verified). t_composition already knew this and loosens
    period_ub before solving; crosscheck globbed the raw file and reported the
    infeasibility as a defect.

    Agreement on UNSAT is worth as much as agreement on an optimum -- more, in
    a way, since a backend that finds a solution where another proves there is
    none is an unambiguous modelling error. So compare the STATUS first and the
    objective only when both solved.
    """
    print("\n[crosscheck] backends must agree (disagreement = modelling error)")
    for dzn in dzns:
        stem = Path(dzn).stem
        ref = run(dzn, "HWCOST", solver="cp-sat", timeout=120)
        if ref["status"] not in ("OPTIMAL", "UNSAT"):
            check(f"{stem}: cp-sat reference", False, ref["status"])
            continue
        if ref["status"] == "UNSAT":
            print(f"        {stem}: cp-sat proves UNSAT under the instance's "
                  f"own bounds")
        for slv in ["gecode", "chuffed"]:
            r = run(dzn, "HWCOST", solver=slv, timeout=120)
            if r["status"] not in ("OPTIMAL", "UNSAT"):
                print(f"        {slv}: {r['status']} (not a failure -- CP-SAT "
                      f"is the only experimental backend)")
                continue
            if r["status"] != ref["status"]:
                check(f"{stem}: {slv} agrees with cp-sat", False,
                      f"{slv} says {r['status']}, cp-sat says {ref['status']} "
                      f"-- one of them is wrong")
                continue
            if ref["status"] == "UNSAT":
                check(f"{stem}: {slv} agrees with cp-sat that it is UNSAT",
                      True)
                continue
            check(f"{stem}: {slv} agrees with cp-sat",
                  r["solution"]["hw_cost"] == ref["solution"]["hw_cost"],
                  f"{r['solution']['hw_cost']} vs {ref['solution']['hw_cost']}")


# ---------------------------------------------------------------------------
def main() -> int:
    groups = sys.argv[1:] or ["golden", "unfold", "provenance", "model",
                              "symmetry", "latency", "rosvall", "safety",
                              "patterns", "catalogue", "multiapp", "comm",
                              "commsil", "composition", "gsn", "crosscheck"]
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
    if "safety" in groups:
        t_safety()
    if "patterns" in groups:
        t_patterns()
    if "catalogue" in groups:
        t_catalogue()
    if "multiapp" in groups:
        t_multiapp()
    if "comm" in groups:
        t_comm()
    if "commsil" in groups:
        t_commsil()
    if "composition" in groups:
        t_composition()
    if "gsn" in groups:
        t_gsn()
    if "crosscheck" in groups:
        t_crosscheck(dzns)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed  ({time.time()-t0:.1f}s)")
    for f in FAIL:
        print(f"  failed: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
