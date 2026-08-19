# SafeDSE — seed bundle (Phase 0 output)

Validated starting point for the framework described in
SafeDSE Architecture and Plan. Everything here was run and checked;
the numbers below are measurements, not estimates.

## Contents

```
bootstrap_minizinc.sh     install MiniZinc 2.8.7 + Gecode + Chuffed + CP-SAT
seed/
  lib/mcm.mzn             throughput (max cycle mean) + deadlock, node potentials
  lib/mcm_test.mzn        self-test for the above (4 cases, incl. a deadlock case)
  core.mzn                Phase-1 + Phase-3 skeleton: mapping + static order
                          + throughput + processor-SIL isolation + cost
  data/p{10,20,30}.dzn    synthetic pipelined HSDF instances
  tools/gen.py            instance generator
```

## Setup

```bash
./bootstrap_minizinc.sh          # ~60 s; idempotent
export PATH=/opt/mzn/bin:$PATH
```

Do **not** export `LD_LIBRARY_PATH=/opt/mzn/lib`. The bundle ships its own
`libselinux.so.1`, which shadows the system copy and breaks coreutils
(`mkdir`, `cp`, …) with "no version information available". MiniZinc runs
fine without it.

## Run the throughput self-test

```bash
cd seed
for t in 1 2 3 4; do minizinc --solver gecode lib/mcm_test.mzn -D "tc=$t;"; done
```

Expected:

| case | graph | expected | got |
|---|---|---|---|
| 1 | 3-cycle, T=[3,4,5], 1 token | μ = 12 | 12 ✓ |
| 2 | 4-cycle, T=[2,2,2,2], 2 tokens | μ = 4 | 4 ✓ |
| 3 | case 2 + schedule edge 1→3 (adds a ratio-3 cycle) | μ = 4 | 4 ✓ |
| 4 | case 2 + schedule edges 2→4 and 4→2 (token-less cycle) | UNSAT | UNSAT ✓ |

Case 4 is the important one: deadlock falls out of the same constraint that
computes throughput. No separate `rank` family, no "throughput > 0" test.

## Run the core model

```bash
cd seed
minizinc --solver cp-sat core.mzn data/p20.dzn -D "mu_max=53;"
```

```
mu=25  total=176  hw=40  dev=136
proc=[1, 2, 1, 1, 1, 3, 3, 4, 4, 3]
csil=[1, 3, 1, 3]
```

`csil` is the SIL each core is provisioned to; `0` means unused. Cores 1 and 3
are low-SIL, cores 2 and 4 high-SIL — the isolation constraint at work.

## Measured baselines

Proving optimality, throughput bound at 55% of ΣWCET, 60 s cap:

| instance | Gecode | Chuffed | CP-SAT |
|---|---|---|---|
| n=10, P=4 | >60 s | 0.34 s | **0.33 s** |
| n=20, P=6 | >60 s | 3.53 s | **1.52 s** |
| n=30, P=8 | >60 s | >60 s | **4.08 s** |

Use CP-SAT as the primary backend. Keep Gecode only for cross-validating
answers on small instances — the DeSyDe lineage is Gecode-based, but that
assumption does not carry over to a MiniZinc encoding without custom
propagators.

## The safety/cost trade-off, reproduced

`data/p20.dzn` with `dev_k = [1.0, 1.0, 1.4, 2.2, 3.5]` (×10, integer),
sweeping the per-core price:

| throughput bound | cheap cores (price 5) | expensive cores (price 40) |
|---|---|---|
| μ ≤ 60 | 4 cores, dev = 344 | 3 cores, dev = 356 |
| μ ≤ 40 | 5 cores, dev = 344 | 4 cores, dev = 368 |
| μ ≤ 25 | 6 cores, dev = 344 | 5 cores, dev = 380 |

As cores get expensive the optimiser buys fewer of them and pays to promote
low-SIL actors to the SIL of a core they share. That is the Phase-3 result,
and it needs no structural safety patterns.

To reproduce, strip the `pcost` and `dev_k` lines out of the `.dzn` (MiniZinc
rejects double assignment) and pass them with `-D`:

```bash
grep -vE '^(pcost|dev_k)=' data/p20.dzn > /tmp/p20b.dzn
minizinc --solver cp-sat core.mzn /tmp/p20b.dzn \
  -D "mu_max=40; pcost=array1d(1..6,[40,40,40,40,40,40]);
      dev_k=array1d(0..4,[10,10,14,22,35]);"
```

## Two modelling traps found while building this

**1. The per-core static order must close into a cycle.** Modelling it as an
open chain (`succ[i] = 0` for the last actor) silently drops the bound "a
core's period ≥ the sum of the WCETs mapped onto it", because no cycle is
created and the MCM stays at max(T). The fix is the `wrap` edge in `core.mzn`
carrying one initial token — the processor-availability token. This is
precisely why Rosvall and Bonfietti use `circuit` over a dummy-extended array;
the dummy node *is* the wrap. It also needs `ishead` to anchor `ord`, or the
positions float and the wrap condition can never be detected.

Symptom if you get this wrong: μ comes out equal to max(WCET) no matter how
many actors you pile onto one core, and the model happily reports a 20-actor
graph running on 2 cores at full pipeline rate.

**2. Comparison binds tighter than `\/` in MiniZinc.** Writing

```minizinc
constraint sedge[i,j] = (A) \/ (B);
```

parses as `(sedge[i,j] = A) \/ B`, which leaves `sedge` completely
unconstrained whenever `B` holds. Fully parenthesise the right-hand side.
This cost me a false pass on deadlock test case 4. It is the same family of
error as the `forall(...) \/ forall(...)` issue in `attarfieti/todaes17+f.mzn`
— MiniZinc's precedence around `=` is a recurring trap in this codebase, and
worth a lint rule.

## Instance generator

```bash
python3 tools/gen.py -n 40 -P 10 --seed 3 -o data/p40.dzn
```

Generates a chain with per-actor self-loops (auto-concurrency 1) plus random
forward dependencies. The self-loops matter: without them a single back-edge
makes the whole graph one cycle, so μ = ΣT regardless of the mapping and the
instance is trivially uninteresting.

## Next (Phase 1)

1. Replace the constant `T[]` with `element(proc, mode)` WCET lookup from
   `WCETs.xml`, restoring Rosvall's processor modes.
2. Extend `experiment/main.py` into a proper SDF3-XML → `.dzn` front-end.
3. Build the regression harness against `related/todaes17.mzn` — same optimal
   periods on the 5-actor example and on ≥3 real benchmarks.
4. Fill the two `% TODO` gaps (constraints 23 and 33) in the Rosvall
   transcription, or confirm they are redundant.
