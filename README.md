# SafeDSE — Phase 1

Core mapping model and front-end, per Part D of
SafeDSE Architecture and Plan. No safety patterns yet (Phase 4), ideal
communication (Phase 6).

Everything here was run and checked. The numbers are measurements.

## Setup

```bash
./bootstrap_minizinc.sh          # ~60 s, idempotent
export PATH=/opt/mzn/bin:$PATH
```

Do **not** export `LD_LIBRARY_PATH=/opt/mzn/lib` — the bundle ships its own
`libselinux.so.1`, which shadows the system copy and breaks coreutils.

## Layout

```
tools/
  sdf3.py        SDF3 XML parsing; multi-rate SDF model; exact repetition vector
  hsdf.py        SDF -> HSDF unfolding with parent[] provenance (C.6)
  platform.py    FCR-template catalogue -> flat core slots (C.5)
  build_dzn.py   the front-end driver: XML in, .dzn out
  mkwcets.py     scaffolding: bootstrap a WCET table for a new platform
  golden.py      independent oracles: Karp MCM + max-plus simulator
  verify.py      rebuild the MSAG from a solution and check it externally
  solve.py       run the model (CP-SAT) and verify the result
lib/
  mcm.mzn        throughput + deadlock via node potentials
  platform.mzn   core slots, FCRs, instantiation, cost
  order.mzn      binding, per-core static order, Rosvall 23/33
  symmetry.mzn   symmetry breaking (must be included after order.mzn)
model/
  dse.mzn        top level: metrics, switchable objective
tests/run_tests.py
```

## Run it

```bash
# XML -> dzn
python3 tools/build_dzn.py \
    --app data/apps/d_jpegEnc1.sdf.xml \
    --platform data/platform/mixed.xml \
    --wcets data/WCETs_mixed.xml \
    --constraints data/desConst.xml \
    -o out/jpeg_sdf.dzn

# solve and verify
python3 tools/solve.py --dzn out/jpeg_sdf.dzn \
    --optimise HWCOST --bound THROUGHPUT=4000

# tests
python3 tests/run_tests.py                  # all groups
python3 tests/run_tests.py golden unfold    # fast subset
```

Switching which metric is optimised needs no model edit — `--optimise` and
`--bound` are the whole interface. Metrics: `THROUGHPUT`, `HWCOST`, `DEVCOST`,
`TOTALCOST`, `POWER`, `NPROCS`.

## Results

`c_rasta`, minimise hardware cost under a throughput bound. Every solution
independently verified by `verify.py`.

| bound | period | cores | hw cost | power |
|---|---|---|---|---|
| μ ≤ 1620 | 1620 | 1 | 33 | 40 |
| μ ≤ 800 | 795 | 2 | 44 | 112 |
| μ ≤ 500 | 488 | 3 | 55 | 184 |
| μ ≤ 350 | 334 | 5 | 96 | 264 |
| μ ≤ 250 | 235 | 6 | 259 | 476 |

The jump at μ≤250 is the DSE being forced off cheap Cortex-M cards onto
expensive Cortex-R ones — heterogeneity doing real work.

`d_jpegEnc1` in multi-rate form:

| bound | period | cores | hw cost | power | time |
|---|---|---|---|---|---|
| μ ≤ 4000 | 3929 | 3 | 52 | 152 | 10.8 s |
| μ ≤ 5000 | 4853 | 2 | 47 | 144 | 8.9 s |
| μ ≤ 6000 | 5669 | 2 | 44 | 112 | 7.8 s |
| μ ≤ 8000 | 7561 | 2 | 41 | 80 | 7.4 s |

Test suite: **31 passing, 0 failing.**

## Findings

### 1. SDF-level provenance decides tractability, not just semantics

`d_jpegEnc1` gets its parallelism from six identical DCT/Huffman branches. The
DeSyDe benchmark ships it as `d_jpegEnc1.hsdf.xml` — already unfolded — so
those six branches are six *distinct* SDF actors. `parent[]` comes out
all-distinct, Rosvall's constraints 23/33 are inert, and the solver explores all
720 equivalent branch orderings.

Written as a multi-rate SDF (one DCT actor with rate 6), the unfolder produces
the identical 16-node HSDF but retains `parent = [1,2,3,3,3,3,3,3,4,4,4,4,4,4,5,6]`:

| input form | 23/33 | minimise hw cost, μ≤4000 |
|---|---|---|
| pre-unfolded `.hsdf.xml` | inert | **>70 s timeout** |
| multi-rate `.sdf.xml` | off | **>70 s timeout** |
| multi-rate `.sdf.xml` | on | **10.5 s, optimal** |

Minimising throughput instead: timeout vs 30.8 s.

This is empirical support for two decisions taken on semantic grounds. Q5
(apply patterns at SDF level, unfold afterwards) is also what keeps the model
tractable, because unfolding is where the symmetry information lives. Q14
(constraints 23/33 need `parent[]`) is load-bearing rather than a nice-to-have.

**Practical consequence:** the DeSyDe `.hsdf.xml` suite is the wrong input
format for this framework. Multi-rate `.sdf.xml` versions of Sobel and SUSAN
will be worth having before Phase 5 benchmarking. `t_provenance` in the test
suite records the gap and will report if it ever narrows.

### 2. The symmetry-breaking hypothesis was wrong

The obvious suspect for the timeout was the weakened symmetry breaking: with
heterogeneous cores, `seq_precede_chain(proc)` is no longer sound and the
replacement (within-card value precedence + card-level lex ordering) is weaker.
Four variants at μ≤4000 — sound, sound-minus-lex, a deliberately **unsound**
global chain, and none at all — **all four timed out identically**. The unsound
variant bounds what any scheme could buy, so symmetry breaking was not the
bottleneck. Running with `-a` then showed the solver never found a first
feasible solution, which pointed at branch symmetry instead.

Worth keeping the diagnostic habit: build the unsound variant to bound the
prize before optimising a sound one.

### 3. The speed-class WCET encoding was not worth it

`wcet[i, ctype[proc[i]], pmode[proc[i]]]` is a 3-D element with two nested
variable indices and looks like it should flatten badly. Replacing it with a
flattened speed-class encoding (one reified implication per (actor, slot)
feeding a 1-D parameter lookup) gave identical optima but was never faster and
up to 4× slower — `c_rasta` at μ≤500 went 0.85 s → 3.46 s. Reverted. The
comment in `dse.mzn` records this so it is not "fixed" again.

### 4. Two bugs the multi-application instance exposed

Both found by running, not reading:

- The `mcm_*` predicates took a scalar `mu` and the top level passed `mu[1]` for
  every application, so partitioned mode silently applied application 1's period
  to all of them. They now take a per-node `mu_of` array, which is also the
  interface Phase 6 needs for mode (c) (C.7).
- `period_ub` was derived from nominal `exec_time`, which is wrong on a
  heterogeneous platform where a slow core exceeds it. It produced a spurious
  UNSAT. Now derived from the slowest achievable WCET per node.

## Design notes worth carrying forward

**The verifier is the point.** `verify.py` shares no code with the model. It
rebuilds the MSAG from the solver's assignment — application edges,
serialisation arcs, and the processor-availability wrap edges — and computes the
period twice, by Karp and by max-plus simulation. It also checks the specific
bound that the open-chain bug used to lose: the period can never be below the
busiest core's total load. Constraint models fail silently; this is the only
thing standing between a plausible number and a wrong one.

**Missing WCET entries are a hard error** (Q8), naming the exact XML element to
add. `--wcet-fallback-scale` exists for bringing up a new platform but warns per
use and prints "Results are NOT publishable".

**Cost profiles are an experimental variable** (C.8). Three profiles derived from
Myklebust et al.: `myklebust2015`, `klosterman`, `do178b`. They disagree by a
factor of 3.7 at SIL3, which is a fact about the literature. The question to ask
is not "what is the right multiplier" but "does the optimal architecture change
when the profile does".

## Open for Phase 2

- Multi-rate `.sdf.xml` forms for the remaining benchmarks.
- Latency: periodic-phase estimate plus an exact unfolding verifier (B.2).
- Buffers and per-core memory beyond the current state-size bin-packing.
- `tools/twostep.py` — Rosvall's two-step solving.
- Per-application periods currently support modes (a) global and (b) partitioned;
  mode (c), per-app periods with core sharing, is Phase 6 and needs the per-app
  MSAG. The unsound naive version is documented in `lib/mcm.mzn` so it does not
  get written by accident.
