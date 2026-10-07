# Usage

Commands are run from the repository root. File formats are in
[inputs.md](inputs.md).

## Requirements

- MiniZinc 2.10 or later with the OR-Tools CP-SAT solver (`cp-sat`). The
  MiniZinc bundle includes CP-SAT, Gecode and Chuffed.
- Python 3.9 or later with `pyyaml`.
- Optional: Graphviz (`dot`) to render arguments.

`bootstrap_minizinc.sh` downloads the MiniZinc bundle (default 2.10.0) into
`/opt/mzn210`, checks that the binary runs before moving it into place, and
prints the line to add to your shell:

```bash
./bootstrap_minizinc.sh                     # PREFIX and MZN_VERSION can be overridden
export PATH=/opt/mzn210/bin:$PATH           # do not export LD_LIBRARY_PATH
minizinc --solvers                          # cp-sat must be listed
pip install pyyaml
```

An existing MiniZinc installation works as well; `tools/solve.py` uses the
`minizinc` found first among `minizinc` on the `PATH`, `/opt/mzn210/bin` and
`/opt/mzn/bin`.

## Build instances

```bash
./tools/build_all.sh                        # rebuilds every instance in out/
```

Run it again after any change to the front end or to the input data. A single
instance:

```bash
python3 tools/build_dzn.py \
    --app data/apps/c_rasta.hsdf.xml \
    --platform data/platform/mixed.xml --wcets data/WCETs_mixed.xml \
    --constraints data/desConst.xml --cost-model data/cost_model.xml \
    --safety data/safety_rasta.xml --patterns data/patterns.yaml \
    -o out/p_rasta.dzn
```

| Option | Meaning |
|---|---|
| `--app FILE` | application graph; repeat for several applications |
| `--platform`, `--wcets` | platform catalogue and WCET table (required) |
| `--constraints` | period bounds per application |
| `--safety` | SIL requirements, fault model, cost profile, promotion switch |
| `--cost-model`, `--cost-profile` | cost profiles; override the profile named in the safety file |
| `--patterns` | pattern catalogue; without it no pattern is applied |
| `--force-no-patterns` | restrict every actor to `none` (must reproduce the pattern-free result) |
| `--latency` | latency constraints |
| `--comm ideal\|tdma` | communication model (default `ideal`) |
| `--comm-scope app\|all` | which channels are refined ([cross-check traffic](design.md#cross-check-traffic)) |
| `--comm-sil exempt\|inherit\|core` | [communication SIL](design.md#communication-sil) |
| `--period-mode global\|partitioned` | `partitioned` forbids applications to share a core |
| `--wcet-fallback-scale X` | fill missing WCETs from nominal times; for bring-up only, never for reported results |
| `-o FILE` | output instance |

Exit codes: 2 inconsistent unfolding, 3 an actor without any WCET entry, 4
malformed pattern catalogue, 5 no admissible pattern for an actor.

## Solve

```bash
python3 tools/solve.py --dzn out/f_both3.dzn --optimise TOTALCOST \
        --json-out /tmp/sol.json
```

| Option | Meaning |
|---|---|
| `--optimise METRIC` | `THROUGHPUT`, `LATENCY`, `HWCOST` (default), `DEVCOST`, `TOTALCOST`, `POWER`, `NPROCS`, `PROMOTION` |
| `--bound METRIC=value` | upper bound on a metric; repeatable |
| `--solver` | MiniZinc solver id (default `cp-sat`) |
| `-p N` | solver threads (CP-SAT workers are capped at N) |
| `--time-limit MS` | MiniZinc time limit; the best solution found so far is reported |
| `--timeout S` | wall-clock limit of the Python call (default 300) |
| `--no-parent-symmetry` | switch off [copy-order symmetry](design.md#copy-order-symmetry) |
| `--no-verify` | do not run the verifier |
| `--json-out FILE` | solution file (default `/tmp/safedse_sol.json`) |

The status is `OPTIMAL` (proven), `SAT` (time limit reached with a solution),
`UNSAT`, `UNKNOWN` or `TIMEOUT`. When the period is not the objective, the
reported `mu` is a feasible period of the design, not necessarily its least
one; minimise `THROUGHPUT` with the design fixed to obtain it.

Directly with MiniZinc:

```bash
minizinc --solver cp-sat model/dse.mzn out/f_both3.dzn \
  -D "opt_metric=TOTALCOST; ub=[1000000000,1000000000,1000000000,1000000000,1000000000,1000000000,1000000000,1000000000]; use_parent_symmetry=true;"
```

Two-step solving for coupled multi-application instances:

```bash
python3 tools/twostep.py --dzn out/r_all.dzn --partitioned out/r_all_part.dzn \
        --optimise HWCOST
```

## Verify

```bash
python3 tools/verify.py --dzn out/f_both3.dzn --solution /tmp/sol.json \
        --json-report /tmp/sol.verify.json
```

Prints the checks and `VERIFY OK` or the failures; the exit code is 0 only if
every check passed. `--json-report` writes the [check log](inputs.md#check-log).

## Generate a safety argument

```bash
python3 tools/gsn.py --dzn out/f_both3.dzn --solution /tmp/sol.json \
        --out out/f_both3
dot -Tsvg out/f_both3.gsn.dot -o out/f_both3.svg
```

| Option | Meaning |
|---|---|
| `--patterns`, `--tactics` | catalogue and tactic table (defaults in `data/`); pass the catalogue the instance was built with |
| `--report FILE` | reuse a check log instead of running the verifier |
| `--fault-model` | assert the fault model; an error if it contradicts the instance |
| `--allow-unverified` | generate despite a failed verification (for inspection only) |

Exit codes: 2 verification failed or contradictory fault model, 3 the audit
found an unsupported leaf, 4 the instance uses a pattern missing from the
catalogue ([refusals](design.md#safety-argument-generation)).

## Scaffold WCET tables

```bash
python3 tools/mkwcets.py --app data/apps/c_rasta.hsdf.xml \
        --platform data/platform/mixed_3type.xml \
        --patterns data/patterns.yaml -o data/WCETs_3type.xml
```

Writes nominal execution time × mode cycle factor per core type, and entries
for pattern components (checkers at `--checker-scale`, default 0.3). The
result is scaffolding for exercising a platform, not WCET data.

## Tests

```bash
python3 tests/run_tests.py                   # all groups
python3 tests/run_tests.py gsn patterns      # selected groups
```

Groups: `golden` (reference algorithms against hand-computed values),
`unfold` (SDF to HSDF properties, multi-rate cases), `provenance` (multi-rate
input versus pre-unfolded input), `model` (model against the oracles on the
instances in `out/`), `symmetry` (copy-order symmetry never moves the
optimum), `latency`, `rosvall` (Rosvall's benchmark against published
bounds), `safety` (isolation, promotion, cost profiles), `patterns` (guarded
superposition, catalogue checks, neutrality with every actor at `none`),
`catalogue`, `multiapp` (period coupling under core sharing), `comm` (TDMA),
`commsil`, `composition` (patterns and TDMA together), `gsn` (argument
generator: evidence, refusals, audit), `crosscheck` (CP-SAT against Gecode and
Chuffed on small instances).

All groups except `crosscheck` take about 10 to 15 minutes on a desktop
machine; `crosscheck` adds about 25 minutes. `tests/sweep_crosscheck.py` runs
the cross-solver comparison with a shorter per-solver timeout and reports the
instances where no comparison was possible:

```bash
python3 tests/sweep_crosscheck.py --timeout 45 --skip r_all,r_lat
```
