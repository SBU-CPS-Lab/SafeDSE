# Architecture

SafeDSE is a MiniZinc constraint model with a Python front end, an independent
verifier and a safety-argument generator. This document describes the
components and how data flows between them. The reasons behind the main
choices are in [design.md](design.md); file formats are in
[inputs.md](inputs.md); commands are in [usage.md](usage.md).

## Pipeline

```
 inputs (XML, YAML)                front end                 model
 ------------------                ---------                 -----
 SDF3 application graphs  ─┐
 platform catalogue        │      tools/build_dzn.py          model/dse.mzn
 WCET table                ├──►   parse, superpose      ──►   (lib/*.mzn)
 design constraints        │      patterns, unfold to         MiniZinc + CP-SAT
 safety specification      │      HSDF, refine channels,          │
 pattern catalogue         │      expand platform slots           │ solution (JSON)
 cost profiles            ─┘      ──► instance (.dzn)              ▼
                                                     tools/verify.py ──► check log (JSON)
                                                     (independent)          │
                                                                            ▼
                                  tools/gsn.py  ◄── solution + check log + catalogue
                                  ──► GSN argument (.gsn.json, .gsn.dot, .gsn.md)
```

1. **Front end** (`tools/build_dzn.py`) resolves everything that does not need
   the solver and writes one MiniZinc data file (`.dzn`) per instance.
2. **Model** (`model/dse.mzn` and `lib/*.mzn`) decides pattern choice, binding,
   static order, platform instantiation, SILs and communication slots, and
   minimises one selectable metric under bounds on the others.
3. **Drivers** (`tools/solve.py`, `tools/twostep.py`) run MiniZinc, parse the
   JSON solution and call the verifier.
4. **Verifier** (`tools/verify.py`, with `tools/golden.py`) re-checks the
   solution without sharing code with the model and writes a structured check
   log.
5. **Generator** (`tools/gsn.py`) builds a Goal Structuring Notation (GSN)
   argument whose deployment claims cite records of the check log.

## Front end

`tools/build_dzn.py` runs these steps:

1. **Parse** the SDF3 application graphs (`tools/sdf3.py`), the safety
   specification, the cost profile and the platform catalogue
   (`tools/platform.py`).
2. **Superpose patterns** (`tools/patterns.py`): load and check the catalogue,
   compute per actor the admissible patterns (required SIL, fault model,
   placeability), allocate component slots, add the component actors and
   pattern edges to the SDF graph, and tag every added node, edge and
   placement relation with its pattern set. Explicit voters reroute the
   owner's output channels.
3. **Unfold** the superposed SDF graph to HSDF (`tools/hsdf.py`), keeping
   `parent` and `copy_index` for every node, and check the unfolding (one
   node per firing, initial tokens preserved per channel, one HSDF edge per
   token exchanged in an iteration).
4. **Flatten applications** into one node list with a block-diagonal token
   matrix `tok`.
5. **Refine communication** (`--comm tdma`): three actors (block, send,
   receive) per application channel, and removal of those channels from `tok`.
6. **Expand the platform** into core slots with fixed core type and FCR, and
   compute the symmetry classes.
7. **Look up WCETs** per node, core type and mode; missing entries become a
   forbidden-binding sentinel.
8. **Compute bounds**: per-application period bounds (from the design
   constraints, or the all-on-one-core sum of the slowest feasible WCETs),
   minimum core counts, latency token distances `rho`.
9. **Emit** the `.dzn`: application arrays, platform tables, safety and cost
   tables, guarded pattern nodes, edges and placement relations, communication
   arrays.

The front end fails early with an explanation when an actor has no admissible
pattern, a pattern record is malformed, an actor has no WCET entry for any core
type, or the unfolding is inconsistent.

## Model

`model/dse.mzn` includes the library files in this order: platform, order,
symmetry, mcm, latency, safety, activation, comm.

| File | Content |
|---|---|
| `model/dse.mzn` | WCET follows the binding; communication actor placement; per-application periods with coupling under core sharing; MSAG constraints; implied constraints; memory; total cost; metric vector and objective selector; search annotation |
| `lib/platform.mzn` | core slots, FCRs, `used`, `fcr_used`, `pmode`; hardware cost and power |
| `lib/order.mzn` | binding `proc`, static order `succ`/`ord`/`ishead`, serialisation edges `sedge`, wrap edges `wrap`; copy-order symmetry; partitioned period mode |
| `lib/symmetry.mzn` | class-wise symmetry breaking over core slots and cards |
| `lib/mcm.mzn` | node-potential constraints for application, serialisation and wrap edges; potential anchor |
| `lib/latency.mzn` | periodic-phase latency of constrained source/sink pairs |
| `lib/safety.mzn` | `sil_impl`, `csil`, `partition`; requirement, core capability, Koopman's rule 2, promotion switch; development, partitioning and promotion cost |
| `lib/activation.mzn` | `pat`, `active`; neutralisation of inactive nodes; guarded pattern edges with a second guard; placement relations; recurring pattern cost |
| `lib/comm.mzn` | TDMA slot allocation, remote channels, worst-case communication times, buffers, communication path in the MSAG, channel separation, communication-SIL modes |

Main decision variables:

| Variable | Meaning |
|---|---|
| `pat[a]` | pattern applied to SDF actor `a` |
| `active[i]` | node `i` is part of the deployed design |
| `proc[i]` | core slot of node `i` |
| `succ[i]`, `ord[i]` | static-order successor and position on the core |
| `used[p]`, `fcr_used[f]`, `pmode[p]` | core populated, card bought, core mode |
| `mu[z]`, `pot[i]` | period of application `z`, node potentials |
| `sil_impl[i]`, `csil[p]`, `partition[p]` | implemented SIL, provisioned core SIL, partitioning used |
| `tdma_alloc[p]`, `sendbuf[c]`, `recbuf[c]` | TDMA slots, buffer sizes |

The objective is `metric[opt_metric]`, with
`metric = [mu_worst, max_latency, hw_cost, dev_cost, total_cost, power, nprocs, promotion_cost]`
and `metric[m] <= ub[m]` for every metric. `total_cost = hw_cost + dev_cost +
partition_total + pattern_cost`. The search annotation branches on binding,
then static order, then periods.

## Drivers

`tools/solve.py` calls MiniZinc with the instance, the objective, the bounds
and the copy-order symmetry switch (`-D`), parses the last JSON solution, and
runs the verifier unless `--no-verify` is given. It passes `-p` and
`--time-limit` to MiniZinc so that a time-limited run reports its best
incumbent, and caps the CP-SAT worker count at the requested threads. Its
`run()` function is the programmatic interface used by the tests and by
experiment harnesses. `tools/twostep.py` implements [two-step solving](design.md#two-step-solving).

## Verifier

`tools/verify.py` parses the `.dzn` and the solution JSON, rebuilds the
MSAG of the deployed design, computes its period with Lawler's parametric MCR
search and with max-plus simulation (`tools/golden.py`), and checks the
reported period, the core load bound, latency (with the transient), SIL
provisioning and isolation, placement relations, and every field that the
model derives (see [design.md](design.md#independent-verification)). It
prints a summary, exits non-zero on any failed check, and with
`--json-report` writes the check log used by the generator.

`tools/golden.py` holds the reference algorithms (MCR, self-timed simulation,
token-free cycle detection). It is written in a different style from the model
so that agreement is evidence and not a shared bug.

## Generator

`tools/gsn.py` reads the instance, the solution, the catalogue, the tactic
table and a check log (it runs the verifier itself if no log is given). It
infers the fault model, refuses on a failed verification or a catalogue
mismatch, builds the argument (top goal, actor goals, pattern strategies,
scenario goals, tactic strategies, Solutions and undeveloped goals, contexts
and assumptions), audits it, and writes JSON, Graphviz DOT and Markdown. See
[design.md](design.md#safety-argument-generation).

## Repository layout

```
model/      dse.mzn (top level); dse.ozn is a compiled output specification
            that the tools do not use
lib/        model layers (*.mzn)
tools/      front end, drivers, verifier, generator, helpers (*.py), build_all.sh
data/       inputs: applications, platforms, WCET tables, safety specifications,
            design constraints, pattern catalogues, tactic table, cost profiles
out/        generated instances (*.dzn) and sample arguments (*.gsn.*, *.svg)
tests/      regression suite and cross-solver sweep
docs/       this documentation
```

`out/*.dzn` is regenerated by `tools/build_all.sh`, which clears it first.
The sample arguments in `out/` (`*.gsn.json`, `*.gsn.dot`, `*.gsn.md`, `*.svg`)
were generated from the verified total-cost optima in `out/*.sol.json`, with
the check logs in `out/*.verify.json`:

```bash
python3 tools/gsn.py --dzn out/f_both3.dzn --solution out/f_both3.sol.json --out out/f_both3
python3 tools/gsn.py --dzn out/v_nvp.dzn --solution out/v_nvp.sol.json \
        --patterns data/patterns_explicit_voter_demo.yaml --out out/v_nvp
```
