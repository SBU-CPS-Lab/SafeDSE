# SafeDSE — Phase 2

Adds latency, the DeSyDe platform dialect, application-aware verification, and
the Rosvall ToDAES benchmark set. Still no safety patterns (Phase 4) and ideal
communication (Phase 6).

**43 tests passing, 0 failing** across eight groups.

Read `README_PHASE1.md` first for setup and the Phase 1 findings.

## What's new

| | |
|---|---|
| `lib/latency.mzn` | end-to-end latency via the periodic-phase estimate (B.2) |
| `tools/verify.py` | now application-aware, and checks latency against a transient-aware simulation |
| `tools/golden.py` | `selftimed_trace` — the full firing schedule, transient included |
| `tools/platform.py` | parses the DeSyDe/Rosvall platform dialect as well as the SafeDSE catalogue |
| `tools/build_dzn.py` | `--latency`; WCET keying by actor name or type; missing entries become binding restrictions |
| `data/rosvall/` | the four ToDAES applications, platform, WCETs, design constraints |

## Rosvall's ToDAES benchmark

Each application alone on the 9-core platform, minimising hardware cost, with
her published period constraints. All four solve in about a second and every
solution is verified independently.

| application | actors | period | bound | cores | hw cost | power |
|---|---|---|---|---|---|---|
| a_sobel | 4 | **384** | 400 | 2 | 16 | 102 |
| b_susan | 5 | **1659** | 2050 | 1 | 12 | 173 |
| c_rasta | 7 | **523** | 550 | 2 | 18 | 151 |
| d_jpegEnc1 | 16 | 9272 | — | 1 | 8 | 51 |

All four together — 32 actors, 9 cores, partitioned mode:

```
mu = [384, 1659, 523, 9272]   6 cores   hw_cost=54   power=477   VERIFY OK
```

Latency, on sobel + rasta with two constrained paths:

| bound | latencies | cores | hw cost | power |
|---|---|---|---|---|
| ≤ 1500 | 718, 1038 | 4 | 34 | 253 |
| ≤ 900 | 718, 893 | 4 | 36 | 326 |
| ≤ 700 | UNSAT | | | |

Tightening latency raises cost without changing the core count — the optimiser
switches processor modes rather than buying hardware. That is the kind of
trade-off the switchable-objective structure exists to expose.

## Findings

### 1. A missing WCET entry is a binding restriction, not an error

Phase 1 followed Q8 literally: no WCET entry for a (task, core, mode) triple was
a hard error. Rosvall's platform breaks that immediately. It has a `CS_HWacc`
accelerator, and exactly one actor — `CS_0`, the 2524-cycle bottleneck of
d_jpegEnc1 — has a WCET entry for it (1388). Every other actor has none.

Under the Phase 1 rule the benchmark is rejected. The correct reading is that a
missing entry means *this actor cannot be bound to that core*, which is how a
heterogeneous accelerator is specified in the first place. The rule is now:

- missing (task, core, mode) → the binding is forbidden;
- **no** entry for any core type → hard error, naming the XML element to add.

The encoding costs nothing. Forbidden combinations get a sentinel above every
real WCET, and since `T`'s domain is `0..maxwcet` computed over real entries
only, the binding is ruled out by domain propagation with no extra constraint.
The front-end reports the restrictions it inferred, so an accidental omission is
visible rather than silent.

### 2. WCETs.xml keys on actor name, not actor type

In Rosvall's files the actor named `get_pixel` has `type="getPixel"`, and the
WCET table keys on `get_pixel`. SafeDSE pattern components (Phase 4) will key on
a task type. Resolution is now per actor: prefer whichever of (name, type) the
table actually contains. Both dialects work without a flag.

### 3. Singleton FCRs restore strong symmetry breaking

Phase 1 noted that `seq_precede_chain(proc)` is unsound on a heterogeneous
platform, because swapping two cores in different cards changes their fault
containment region. There is an exception worth taking: **a card holding exactly
one core makes a core swap identical to a whole-card swap**, which *is* a
symmetry. `Platform.interchangeable_groups()` detects this and emits
`value_precede_chain` over those slots.

The DeSyDe dialect has no FCR concept, so each processor becomes its own
singleton FCR and the whole platform qualifies. That is why the 9-core Rosvall
instances solve in under a second where the 22-slot card-based platform needs
ten. The pruning that Phase 1 thought it had lost is recoverable wherever the
input does not actually claim shared failure regions.

### 4. Rosvall's benchmark needs period mode (c), which is Phase 6

The four-application experiment is the clearest possible demonstration of the
Q15 limitation. Mode (a) forces one global period, so `mu ≤ min(400, 2050, 550)
= 400`, while `CS_0` alone costs 1388 even on the accelerator. Correctly UNSAT
in 1.3 s. Mode (b) partitioned solves and verifies, but it forbids core sharing
— and core sharing is exactly what Rosvall's experiment is about.

**A semantics question to settle before Phase 6.** In an order-based static
schedule where each core executes its order once per iteration, every
application on a shared core completes one iteration per system period — so
where do different per-application periods come from? Two readings:

- `period[z]` is the maximum cycle mean over MSAG cycles *containing* application
  z's actors, so applications differ because their critical cycles differ; or
- each application has its own processor-cycle structure, implying system-level
  unfolding when the rates differ.

These are not the same model and they need different constraints. Node
potentials express "MCM of the whole graph" directly but not "MCM over cycles
touching a subset", so the first reading needs work beyond the current layer.
**Which one does the ToDAES formulation use?** Her constraints are in the paper's
image-only PDF; if you can read off the definition of `period[z]`, that settles
Phase 6's design.

### 5. The latency estimate matched the transient exactly here

`lib/latency.mzn` uses the periodic-phase estimate `pot[d] − pot[s] + rho·mu +
T[d]`, which is exact once the schedule settles and ignores the transient. The
verifier now simulates the real schedule over 40 iterations and compares. On
every instance tested the two agreed exactly (718 vs 718, 893 vs 893).

That is reassuring but **not** a proof that the estimate is always safe. When it
disagrees the verifier prints a NOTE rather than failing, because the gap is a
documented property of the estimate and not a solver bug. Do not report the
model's latency as a worst-case bound without the verification step.

`rho(s,d)` is computed once in the front-end by shortest-path over token counts.
It is a property of the application graph alone: serialisation edges carry no
tokens, so no mapping can shorten a token-path. The CP model never sees it.

## Usage

```bash
# Rosvall's benchmark
python3 tools/build_dzn.py --app data/rosvall/c_rasta.hsdf.xml \
    --platform data/rosvall/platform.xml --wcets data/rosvall/WCETs.xml \
    --constraints data/rosvall/desConst.xml -o out/r_c_rasta.dzn

# all four, partitioned
python3 tools/build_dzn.py \
    --app data/rosvall/a_sobel.hsdf.xml --app data/rosvall/b_susan.hsdf.xml \
    --app data/rosvall/c_rasta.hsdf.xml --app data/rosvall/d_jpegEnc1.hsdf.xml \
    --platform data/rosvall/platform.xml --wcets data/rosvall/WCETs.xml \
    --constraints data/rosvall/desConst.xml --period-mode partitioned \
    -o out/r_all_part.dzn

# with latency constraints
python3 tools/build_dzn.py ... --latency data/rosvall/latency.xml -o out/r_lat.dzn
python3 tools/solve.py --dzn out/r_lat.dzn --optimise HWCOST --bound LATENCY=900
```

Metrics: `THROUGHPUT`, `LATENCY`, `HWCOST`, `DEVCOST`, `TOTALCOST`, `POWER`,
`NPROCS`. Any one optimised, any subset bounded, no model edit.

## Not done in Phase 2

- **`tools/twostep.py`** — Rosvall's two-step solving. Deferred: nothing in the
  benchmark set is currently slow enough to need it. Revisit when Phase 4
  superposition grows the instances.
- **Channel buffer memory.** Per-core memory is bin-packed on actor state size;
  channel buffers are not yet counted. Belongs with Phase 6, where the
  communication model gives buffers a size.
- **Multi-rate `.sdf.xml` forms of sobel and susan.** Both are small and
  single-rate with no repeated actors, so the Phase 1 provenance finding does not
  bite. `d_jpegEnc1` is the one that mattered and it is done.

## Before Phase 3

The C.5 measurement is now available and worth taking seriously:
`jpeg_sdf` (16 nodes, 22 card-based slots) needs 11 s where the 9-core
singleton-FCR platform needs 1 s. Phase 4 superposition grows node counts by
roughly 1.5–3×. That gap should be measured against a card-based platform *with*
FCR constraints active, since that is the configuration Phase 4 actually needs,
before committing to the superposition sizing.
