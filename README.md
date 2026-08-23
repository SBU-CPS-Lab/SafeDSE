# SafeDSE

A declarative constraint-programming framework for **safety-aware design space
exploration**: mapping dataflow streaming applications onto time-predictable
multiprocessor platforms while applying safety architecture patterns to satisfy
per-actor SIL requirements, and trading off throughput, latency, hardware cost
and software development cost.

The output is a mapping **and a skeleton safety argument** in Goal Structuring
Notation, in which every deployment claim is discharged by evidence from an
independent re-check of the solution and everything else is explicitly marked
undeveloped.

Everything is MiniZinc plus a Python front-end. There are no dependencies beyond
`pyyaml`.

---

## Quick start

```bash
./bootstrap_minizinc.sh                 # MiniZinc 2.10.0 + CP-SAT, ~60 s
export PATH=/opt/mzn210/bin:$PATH       # do NOT export LD_LIBRARY_PATH
./tools/build_all.sh                    # build all 38 instances

# solve, then argue
python3 tools/solve.py --dzn out/f_both3.dzn --optimise TOTALCOST \
        --json-out /tmp/sol.json
python3 tools/gsn.py  --dzn out/f_both3.dzn --solution /tmp/sol.json \
        --out out/f_both3
dot -Tsvg out/f_both3.gsn.dot -o out/f_both3.svg

python3 tests/run_tests.py              # all groups (~25 min with crosscheck)
python3 tests/run_tests.py gsn patterns # a fast subset
```

`tools/build_all.sh` must be re-run after **any** front-end edit.

---

## What is where

| | |
|---|---|
| `model/dse.mzn` | top level, `Metric` enum, objective selector |
| `lib/mcm.mzn` | throughput and deadlock, by node potentials |
| `lib/order.mzn` | binding, per-core static order, Rosvall 23/33 |
| `lib/platform.mzn` | core types, FCRs, instantiation, cost |
| `lib/safety.mzn` | SIL assignment, Koopman rule 2, promotion cost |
| `lib/activation.mzn` | guarded superposition; pattern nodes, edges, placements |
| `lib/comm.mzn` | TDMA communication, slots, buffers, MSAG path |
| `lib/latency.mzn`, `lib/symmetry.mzn` | latency; class-wise symmetry breaking |
| `tools/build_dzn.py` | front-end: applications, platform, WCETs, safety → `.dzn` |
| `tools/patterns.py` | the pattern catalogue loader, validator and expander |
| `tools/gsn.py` | the GSN safety-argument generator |
| `tools/verify.py`, `tools/golden.py` | **independent** oracles; share no code with the model |
| `tools/solve.py`, `tools/twostep.py` | drivers |
| `data/patterns.yaml` | the 9-pattern catalogue — data, not code |
| `data/gsn_tactics.yaml` | Preschern's tactic → IEC 61508 method table |
| `data/cost_model.xml` | three SIL development-cost profiles |

Phase notes are in `README_PHASE1.md` … `README_PHASE8.md`; the last is the
longest and covers the safety-argument generator and explicit voters.

---

## The three ideas the design rests on

**Guarded superposition.** Topology is a *parameter*; selection is a *variable*.
The front-end statically instantiates every candidate replica and communication
actor into one fixed graph, each tagged with the pattern set that uses it. The
model chooses `pat[a]` per actor and derives `active[i]`. Inactive nodes are
*neutralised*, not deleted: `T = 0`, pinned to the owner's core, excluded from
every cost and memory sum. Safety patterns, communication refinement and
platform instantiation are three instances of this one mechanism.

**Throughput as node potentials.** Exact maximum cycle ratio by LP duality, in
`n` variables rather than the `2n²` an edge-residual formulation needs, and
UNSAT exactly when the graph deadlocks. It replaces DeSyDe's custom C++
propagator, which MiniZinc cannot host.

**The verifier is the safety net.** `tools/verify.py` shares no code with the
model. It rebuilds the mapping-and-schedule-aware graph from the returned
solution and checks the period *twice* by disjoint methods — Karp's maximum
cycle ratio and max-plus self-timed simulation — plus the busiest-core load
bound, the SIL and isolation invariants, and every active placement relation.
Constraint models fail silently. This is the only thing standing between a
plausible number and a wrong one.

---

## Selected results

* Rosvall's four-application ToDAES benchmark (32 actors, 9 cores, shared):
  **proven optimal in 10.6 s** via two-step solving, against 250 s without
  proof. Each application meets its published bound.
* **The cost profile changes the optimal architecture.** Same instance:
  `myklebust2015` → 3 cores, `klosterman` → 1 core, `do178b` → 3 cores.
* **Placement, not topology, distinguishes patterns.** `low_sil_doer_checker`
  and `same_cpu_doer_checker` are structurally identical and differ only in
  `DIFFERENT` versus `SAME`; the fault model picks between them.
* **The fault model prunes the argument, not just the design space.** Under
  `random_hw` the `DIVERSE` relation is never posted, so a 2-of-2's
  systematic-fault scenario is stated by the pattern but *not provided* by the
  deployment — and the generated argument says so rather than inheriting the
  claim.
* **Safety plus communication costs a_sobel a third of its throughput**: the
  minimum period with a SIL-3 pattern and TDMA is 512, against a published bound
  of 400 that was measured for neither.
* **N-version programming at SIL *n* needs *N* distinct core types each
  certifiable to SIL *n*.** Buying more of the same card does not help.

---

## Things that are true and easy to forget

* **Backend crosschecking contributes nothing on the pattern instances.** All
  37 non-voter instances agree across CP-SAT, Gecode and Chuffed with zero
  disagreements — but on every instance carrying a pattern catalogue, Gecode
  times out and Chuffed returns UNKNOWN. The guarded-superposition design space
  is solved by one backend, and `verify.py` is the only check on it.
* **`mcm_pattern_edges` is measured redundant.** The front-end writes pattern
  channels into `tok` as well as `pe_*`, and `lib/mcm.mzn` posts every `tok`
  pair unconditionally. Setting `nPE = 0` returns the identical optimum. What
  neutralises an unselected pattern's edges is `T = 0`, not the guard.
* **A satisfiability pre-check that does not fire is not evidence of
  satisfiability.** Two versions of the `DIVERSE` pre-check passed while the
  instance stayed UNSAT, for two different reasons.
* **An unplaceable pattern is not an instance error.** Patterns are
  alternatives; one that will not fit is dropped as a candidate, and only an
  actor left with nothing is a failure.

---

## Traps that have cost real time

1. **MiniZinc precedence**: `=` binds *tighter* than `\/`, so `x = (A) \/ (B)`
   parses as `(x = A) \/ B` and leaves `x` unconstrained. Bit this codebase
   twice.
2. **`forall(...) \/ forall(...)`** puts the disjunction outside the quantifier.
   It collapsed the original safety design space from 3ⁿ points to 3.
3. **An open-chain static order** silently drops the core-load bound. The
   per-core order must close into a cycle carrying one initial token.
4. **`period_ub` must exclude the FORBIDDEN sentinel**, or the bound inflates by
   three orders of magnitude and the search becomes hopeless.
5. **`max_sil` must default to 4, not 0**, for platform dialects that do not
   declare it. Latent for four phases.
6. **Communication actors belong on the bus**, not in the processor static order
   or `proc_load`. Phase 6's published TDMA periods were wrong because of this.
7. **Measure before optimising.** Three optimisation intuitions here were
   contradicted by measurement, and a fourth — that the guarded-edge constraint
   was doing work — turned out to be doing nothing at all.
8. **A corrupt tool install presents as "your model has no solutions."** The
   bootstrap now stages extraction and verifies the binary runs before moving it
   into place.

---

## Open questions

* **Q19** — is `partition_cost` a one-off or per-core? Currently per-core. A
  certified isolation argument is largely a one-off effort, which changes the
  economics once several cores would be partitioned.
* **Q22** — should pattern cross-check traffic get a separately declared
  interconnect, rather than being ignored (`--comm-scope app`, the default) or
  routed over the application bus (`--comm-scope all`, which comes back UNSAT)?
