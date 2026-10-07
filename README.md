# SafeDSE

SafeDSE is a constraint-based design space exploration tool for
safety-critical dataflow applications on heterogeneous multiprocessors. For
synchronous dataflow (SDF) applications with a required Safety Integrity Level
(SIL) per actor, it decides in one constraint model

- which safety architecture pattern (doer/checker, 2-of-2, mixed-SIL,
  failover, ...) protects each actor,
- where every actor and every pattern component runs, subject to the
  placement relations that the selected fault model requires (same core,
  different cores, different fault containment regions, different core types),
- the static order on each core and the resulting throughput,
- which cards and cores of the platform are bought, the SIL each core is
  provisioned to, and the cost of developing software to a higher SIL than it
  needs (SIL promotion),
- optionally, TDMA bus slots and communication buffers,

and minimises a selectable metric (period, latency, hardware cost,
development cost, total cost, power, core count, promotion cost) under bounds
on the others. Results are optimal within the model when the solver proves
them so.

Every solution is re-checked by an independent verifier that shares no code
with the model, and a generator turns the solution and the verifier's check
log into a Goal Structuring Notation (GSN) safety argument: deployment claims
cite verifier records, and everything a mapping cannot establish stays an
undeveloped goal with a stated reason.

The model is written in [MiniZinc](https://www.minizinc.org) and solved with
OR-Tools CP-SAT; the front end, verifier and generator are Python.

## Quick start

```bash
./bootstrap_minizinc.sh                   # or use an installed MiniZinc >= 2.10 with CP-SAT
export PATH=/opt/mzn210/bin:$PATH
pip install pyyaml

./tools/build_all.sh                      # build the instances in out/

python3 tools/solve.py --dzn out/f_both3.dzn --optimise TOTALCOST \
        --json-out /tmp/sol.json          # solve and verify
python3 tools/gsn.py --dzn out/f_both3.dzn --solution /tmp/sol.json \
        --out /tmp/f_both3                # safety argument (.gsn.json/.dot/.md)

python3 tests/run_tests.py gsn patterns   # a fast subset of the regression suite
```

## Documentation

| Document | Content |
|---|---|
| [docs/architecture.md](docs/architecture.md) | pipeline, components, model layers, repository layout |
| [docs/design.md](docs/design.md) | design decisions and their reasons, known limitations, modelling pitfalls |
| [docs/inputs.md](docs/inputs.md) | input and output formats: applications, platforms, WCETs, safety specifications, pattern catalogue, check log, arguments |
| [docs/usage.md](docs/usage.md) | installation, command-line tools, tests |

## Repository layout

| Path | Content |
|---|---|
| `model/dse.mzn` | top-level model: metrics, objective selector, periods, implied constraints |
| `lib/*.mzn` | model layers: platform, static order, symmetry, throughput (node potentials), latency, safety, pattern activation, communication |
| `tools/build_dzn.py` | front end: XML/YAML inputs to a MiniZinc instance |
| `tools/patterns.py`, `hsdf.py`, `sdf3.py`, `platform.py` | pattern expansion, SDF to HSDF unfolding, parsers |
| `tools/solve.py`, `twostep.py` | solve drivers |
| `tools/verify.py`, `golden.py` | independent verifier and reference algorithms |
| `tools/gsn.py` | safety-argument generator |
| `data/` | benchmark applications, platforms, WCET tables, safety specifications, pattern catalogue, tactic table, cost profiles |
| `out/` | generated instances and sample arguments |
| `tests/` | regression suite and cross-solver sweep |

## Experiments

The scripts, inputs and raw results of the experiments in the SafeDSE paper
and its technical report are in
[SafeDSE-experiments](https://github.com/SBU-CPS-Lab/SafeDSE-experiments),
which pins the version of this repository it was run with.

## Citing

If you use SafeDSE, please cite

> F. Bahrami and S.-H. Attarzadeh-Niaki, "SafeDSE: Joint Exploration of Safety
> Architecture Patterns, Mapping, and Scheduling for Dataflow Applications With
> Safety Arguments," manuscript, 2026.

## License

BSD 3-Clause, see [LICENSE](LICENSE). The benchmark applications and platform
in `data/rosvall/` and `data/apps/` come from DeSyDe (BSD 2-Clause); see
[NOTICE](NOTICE).

## Acknowledgments

The mapping and scheduling formulation follows Rosvall and Sander's
constraint-based design space exploration (DeSyDe). The pattern catalogue
draws on Koopman's safety architecture patterns, Armoush's design patterns for
safety-critical embedded systems, and Preschern, Kajtazovic and Kreiner's
safety architecture pattern system, whose tactic table the argument generator
uses.
