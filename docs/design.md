# Design decisions

This document records the design decisions behind SafeDSE and the reasons for
them. Source comments point here with links of the form
`docs/design.md#<section>`. The structure of the tool is described in
[architecture.md](architecture.md); file formats are in [inputs.md](inputs.md).

Contents

- [Modelling approach](#modelling-approach)
  - [Guarded superposition](#guarded-superposition)
  - [Neutralised inactive nodes](#neutralised-inactive-nodes)
  - [Everything static is decided in the front end](#everything-static-is-decided-in-the-front-end)
  - [Solver](#solver)
- [Timing](#timing)
  - [Throughput by node potentials](#throughput-by-node-potentials)
  - [Closed per-core static order](#closed-per-core-static-order)
  - [Periods of multiple applications](#periods-of-multiple-applications)
  - [Two-step solving](#two-step-solving)
  - [Implied constraints](#implied-constraints)
  - [Latency estimate](#latency-estimate)
- [Applications and platform](#applications-and-platform)
  - [Patterns at SDF level, mapping on the HSDF graph](#patterns-at-sdf-level)
  - [WCET table and forbidden bindings](#wcet-table-and-forbidden-bindings)
  - [Platform model](#platform-model)
  - [Symmetry breaking](#symmetry-breaking)
  - [Copy-order symmetry](#copy-order-symmetry)
- [Safety model](#safety-model)
  - [SIL per actor](#sil-per-actor)
  - [Fault model](#fault-model)
  - [SIL promotion](#sil-promotion)
  - [Partitioning](#partitioning)
  - [Cost profiles](#cost-profiles)
- [Pattern catalogue](#pattern-catalogue)
  - [Pattern records](#pattern-records)
  - [Well-formedness checks](#well-formedness-checks)
  - [Token preservation](#token-preservation)
  - [No nesting](#no-nesting)
  - [Voters](#voters)
  - [Pairwise placement](#pairwise-placement)
  - [The none ceiling](#the-none-ceiling)
  - [Component slots](#component-slots)
  - [Component SILs](#component-sils)
  - [DIVERSE](#diverse)
- [Communication](#communication)
  - [TDMA refinement](#tdma-refinement)
  - [Communication actors and the processor order](#communication-actors-and-the-processor-order)
  - [Remote channels replace the direct edge](#remote-channels-replace-the-direct-edge)
  - [Communication SIL](#communication-sil)
  - [Cross-check traffic](#cross-check-traffic)
  - [Channel separation](#channel-separation)
- [Objective selection](#objective-selection)
- [Independent verification](#independent-verification)
- [Safety-argument generation](#safety-argument-generation)
- [Known limitations](#known-limitations)
- [Modelling pitfalls](#modelling-pitfalls)

---

## Modelling approach

### Guarded superposition

Topology is a *parameter*; selection is a *variable*. The front end
instantiates every candidate replica, checker, voter and communication actor
into one fixed graph G⁺, and tags each added node, edge and placement relation
with the set of patterns that use it. The model has one decision `pat[a]` per
SDF actor and derives

    active[i]  <->  node_guard[i, pat[node_owner[i]]]

Because the graph shape is fixed when the model is flattened, all structural
constraints (static order, throughput cycles) are posted once, and no
constraint has a variable index into a variable topology. A formulation with a
variable adjacency matrix over all possible replicas needs O(n²) topology
variables and an `element` constraint on a variable index for every access; it
did not solve a five-actor instance in minutes.

The same mechanism is used three times:

- safety patterns (`tools/patterns.py`, `lib/activation.mzn`);
- communication refinement: block, send and receive actors per channel, active
  when the channel is remote (`lib/comm.mzn`);
- platform instantiation: fault containment region (FCR) templates that may or
  may not be bought (`tools/platform.py`, `lib/platform.mzn`).

### Neutralised inactive nodes

An inactive node is not deleted (the arrays are fixed); it is neutralised: its
execution time `T` is 0, it is pinned to the core of its owner's matching HSDF
copy (`owner_node`), and it is excluded from every cost, memory and SIL sum. A
zero-WCET node contributes nothing to any cycle ratio, so it is invisible to
throughput while it keeps its place in the static order. Pinning matters as
much as zeroing: an unpinned inactive node could move freely over the platform
and multiply every solution by the number of processors. Constraints that only
make sense between real nodes (for example implied constraint (3) in
`model/dse.mzn`, or the no-promotion rule) are guarded by `active`.

See [Known limitations](#known-limitations) for the one place where a
neutralised node still affects timing.

### Everything static is decided in the front end

SDF to HSDF unfolding, pattern expansion, communication refinement, platform
slot expansion, WCET lookup and the period upper bound are computed in Python
before solving. This keeps the model a fixed graph, keeps each transformation
testable on its own, and lets the front end reject an infeasible configuration
with an explanation (for example, an actor whose SIL no admissible pattern
reaches) instead of an opaque UNSAT.

### Solver

The model is plain MiniZinc. OR-Tools CP-SAT is the backend for all
experiments; it was much faster than Gecode on the benchmark set, and
lazy-clause generation handles the Boolean-heavy guarded structure well.
Gecode, Chuffed and HiGHS remain usable through `tools/solve.py --solver` as
correctness oracles on small instances. On instances that carry a pattern
catalogue, only CP-SAT reaches an answer in practice, so the independent
verifier is the main check there ([Independent verification](#independent-verification)).

---

## Timing

### Throughput by node potentials

A period μ is feasible for a self-timed HSDF schedule iff there are node
potentials `pot` such that, for every edge (i, j) of the mapping- and
scheduling-aware graph (MSAG),

    pot[j] >= pot[i] + T[i] - tok[i,j] * mu

This is the linear-programming (Bellman-Ford) characterisation of the maximum
cycle ratio (MCR), the potential form known from cyclic scheduling. Two
consequences:

- minimising μ yields the least integer period at or above the MCR;
- the system is infeasible iff a cycle without tokens and with positive WCET
  exists, so deadlock detection is included.

It needs n potential variables (against 2n² for an edge-residual
formulation) and replaces a dedicated throughput propagator, which MiniZinc
cannot host. Self-timed state-space exploration and SDF-level throughput
analysis were considered and rejected for the model: they have no declarative
form, and max-plus methods unfold the graph as well. Self-timed simulation is
used in the verifier instead, where it is a second oracle that shares no
reasoning with the MCR computation.

`tok[i,j] * mu` is linear as long as the token count is a parameter. The
communication buffers of `lib/comm.mzn` are variables, which makes their
back-edge terms products of two variables; CP-SAT handles them natively
(`int_times`).

### Closed per-core static order

Each core's static order is a `succ`/`ord` chain closed by a wrap edge from
the last to the first actor, carrying one initial token (the processor
availability token). This is what makes "core period ≥ sum of the WCETs on the
core" a consequence of the potential constraints. An open chain silently drops
that bound. The chain head is anchored by `ishead` (position 0); without the
anchor, positions float and the wrap edge cannot be identified.

The order uses successor plus rank instead of the `next` array over a
dummy-extended set closed by `circuit`, which MiniZinc decomposes anyway.
Deadlock is detected by the potentials, so `ord` only has to make each order
acyclic.

### Periods of multiple applications

Each application z has its own period `mu[z]`. Two applications that share a
core are coupled to one period: the static order links their actors, so they
lie in one connected component of the MSAG, whose MCR is the common period.
Applications on disjoint cores get independent periods. Within a connected
component every node has the same μ, so the potentials share a time base and
the formulation is sound.

The coupling is posted over application pairs through an (application, core)
occupancy matrix (`app_on`, `app_shares` in `model/dse.mzn`), which is
O(|APP|² + n·|APP|). The equivalent formulation over actor pairs is O(n²) and
timed out on a 32-actor instance.

The front end option `--period-mode partitioned` forbids applications to share
a core. It is used as the restricted first step of [two-step solving](#two-step-solving).

### Two-step solving

`tools/twostep.py` first solves a restricted model in which applications may
not share a core, then solves the full model with the first objective as an
upper bound. The bound only excludes solutions no better than one already
found, so optimality is preserved. With a single solver thread this turned a
coupled multi-application instance from "no proof" into a fast proof; with a
multi-threaded CP-SAT portfolio the one-step solve is competitive, so two-step
solving is optional.

### Implied constraints

`model/dse.mzn` states four constraints that follow from the potentials but
prune at the root instead of after search: (1) a core's load bounds its
applications' periods; (2) an active actor's WCET is at most its
application's period bound; (3) two active actors whose minimum WCETs exceed
the bound cannot share a core; (4) an application needs at least
⌈Σ min WCET / bound⌉ cores. Communication actors are excluded from (1) and (3)
because they run on the bus, and (3) is guarded by `active` because an
inactive slot is pinned to its owner's core.

### Latency estimate

In the periodic phase of a self-timed schedule the k-th firing of actor i
starts at about `pot[i] + k·μ`, so for a source s and sink d

    latency(s, d) ≈ pot[d] − pot[s] + rho(s, d)·μ + T[d]

where `rho(s, d)` is the least number of initial tokens on a path from s to d.
`rho` depends on the application graph only (serialisation edges carry no
tokens), so the front end computes it. The estimate costs no new variables. It
ignores the transient phase, so it is a filter, not a worst-case bound:
`tools/verify.py` simulates the schedule including the transient and prints a
NOTE when the transient exceeds the estimate.

---

## Applications and platform

### Patterns at SDF level

Patterns are applied to the SDF graph, and the superposed graph is then
unfolded to HSDF. A pattern is a design decision about a function, not about
one iteration of it, so `pat[a]` stays one variable per SDF actor. A component
mirrors its owner's rates, so the superposed graph has the same repetition
vector and needs no new balance equations. Pattern edges are added as ordinary
SDF channels, so the unfolder computes their copy-to-copy wiring by the same
rule as every other channel.

Mapping and scheduling happen on the unfolded HSDF graph, which exposes data
parallelism. The unfolder keeps provenance: `parent[i]` (the SDF actor of HSDF
copy i) and `copy_index[i]`. Provenance is needed for
[copy-order symmetry](#copy-order-symmetry) and [pairwise placement](#pairwise-placement).
For this reason a multi-rate `.sdf.xml` input is preferable to a
pre-unfolded `.hsdf.xml` one: in the pre-unfolded form identical branches are
distinct actors, the copy-order constraints are inert, and the solver explores
every equivalent ordering of the branches (`tests/run_tests.py provenance`
measures the gap).

### WCET table and forbidden bindings

A missing (task, core type, mode) entry in the WCET table means that the actor
cannot be bound to that core type; this is how an accelerator usable by one
actor only is specified. The front end encodes such entries with a sentinel
above every real WCET, so the domain of `T` rules the binding out without an
extra constraint, and it prints the restrictions it inferred. An actor with no
entry for any core type is an error that names the XML element to add.
`--wcet-fallback-scale` substitutes nominal times for missing entries when a
new platform is brought up; it warns on every use, and its results must not be
reported.

The table may key on the actor name (DeSyDe files) or on the task type
(SafeDSE files); the front end uses whichever the table contains. A pattern
component keys on a WCET type such as `<owner>` (a full replica) or
`checker_<owner>`, resolved against the owner's key.

### Platform model

The designer declares FCR templates: things that are bought as a unit (a
card), whose cores share power, clock and substrate and fail together. Each
template has a maximum instance count and contains cores of one or more core
types. A core type declares its certifiable maximum SIL (`max_sil`, default
4), memory, whether it offers certified partitioning, and operating modes with
price and power. The front end expands the catalogue into a flat array of
candidate core slots, each with a fixed core type and FCR; the model decides
which cards to buy (`fcr_used`), which cores to populate (`used`) and their
modes (`pmode`).

Because core type and FCR are parameters of a slot, the placement relations
`DIFFERENT_FCR` and `DIVERSE` are element lookups into parameter arrays.
A homogeneous platform cannot express `DIVERSE` at all, so heterogeneity is a
precondition for defending against systematic faults, not a refinement.

The DeSyDe platform dialect (a flat list of processors) has no FCRs; each
processor becomes its own single-core FCR, which never claims an independence
that the input did not state.

### Symmetry breaking

With heterogeneous cores and FCRs, cores are not globally interchangeable, and
a global `seq_precede_chain(proc)` would exclude optimal solutions.
`lib/symmetry.mzn` breaks symmetry only inside equivalence classes: (1) value
precedence over cores of one type in one card; (2) whole cards of one template
are bought as a prefix and ordered by their actor membership; (3) value
precedence over single-core cards of one type, where a core swap is a card
swap. On the DeSyDe dialect, (3) covers the whole platform. Multi-core cards
weaken symmetry breaking and cost solve time; the bounded `csil` domains of the
safety model partly compensate.

### Copy-order symmetry

Rosvall and Sander's constraints (23) and (33) in `lib/order.mzn` order the
HSDF copies of one SDF actor by processor index, and by position on a shared
core. They remove symmetric solutions and are switched by
`use_parent_symmetry` (`tools/solve.py --no-parent-symmetry`). The `symmetry`
test group checks that switching them changes run time but never the optimum.

---

## Safety model

### SIL per actor

A Safety Integrity Level (SIL, IEC 61508) is required per SDF actor, the unit
of mapping, matching the allocation of integrity to functions. IEC 61508 is
the governing standard of the tactic table and of the generated arguments.
The model distinguishes the required SIL (`sil_req_parent`, input), the SIL an
actor is developed to (`sil_impl`, decision), and the SIL a core is
provisioned to (`csil`, decision, at most the core type's `max_sil`). SIL 0
means no requirement. A pattern component carries its owner's requirement
([Component SILs](#component-sils)).

### Fault model

The safety specification selects a fault model: `random_hw` (random hardware
faults), `systematic_sw` (systematic software faults) or `both`. A pattern is
admissible for an actor only if its `achieves_sil` contains the actor's SIL and
its `covers_faults` contains the selected fault class(es). Placement relations
whose `for:` field names a fault class outside the model are not posted, and
scenarios marked with such a class are out of scope in the argument. An actor
with no admissible pattern is a build-time error that lists the reachable
SILs.

### SIL promotion

Koopman's rule 2: software that shares a processor without a certified
isolation argument is developed to the highest SIL present on that processor.
The model posts it as `sil_impl[i] = csil[proc[i]]` for every active actor on
an unpartitioned core, and pins `csil` to the highest `sil_impl` on the core,
so `csil` cannot be inflated for free. The gap between required and
implemented SIL is promotion, priced by the development-cost profile and
reported separately as `promotion_cost`, because it is the quantity the
consolidation trade-off is about: buy another core and keep low-SIL software
cheap, or co-locate and develop it to a SIL it does not need.

`allow_promotion="false"` in the safety specification forbids promotion of
active nodes; it is the baseline for "how much does allowing promotion save".

### Partitioning

Certified partitioning (a separation kernel or hypervisor with its own
certification evidence) is a capability of a core type (`partitionable`), not
of a mapping. On a partitioned core an actor may sit below the core's SIL, and
the core pays `partition_cost`. The cost is charged per partitioned core; a
one-off cost of the isolation argument would change the economics when several
cores are partitioned.

### Cost profiles

Development cost is `dev_base × dev_k[sil_impl] / 100` per active node. The
per-SIL multipliers come from `data/cost_model.xml`, which holds three
profiles derived from the estimates collected by Myklebust et al. (ISSC 2015);
SIL 0 and SIL 4 are extrapolated. The published estimates differ widely, so
the profile is an input and an experimental variable: the relevant question is
whether the optimal architecture changes with it. The safety specification
names a profile; `--cost-profile` overrides it.

---

## Pattern catalogue

### Pattern records

The catalogue (`data/patterns.yaml`) is data, not code, so that claims about
patterns and standards can be argued and edited without touching the model.
A record has three parts: structure (components, edges, input fan-out, output
source; after Koopman), placement (relations with the fault class that
motivates each; first class, because `low_sil_doer_checker` and
`same_cpu_doer_checker` have identical structure and differ only in placement),
and attributes (SIL range, covered faults, failure mode, costs, tactics and
scenarios; after Armoush and Preschern et al.). The schema is in
[inputs.md](inputs.md#pattern-catalogue).

### Well-formedness checks

`patterns.check_pattern` rejects a malformed record at build time with a
message, instead of letting it surface as UNSAT:

- edges, input fan-out and placement members refer to declared roles, and
  placement relations are known;
- every cycle a pattern introduces carries at least one initial token;
- a record that claims to fail silent may not co-locate its channels (Koopman's
  "attempted high-SIL doer/checker" anti-pattern), and a record that claims
  SIL 3 or higher must add a redundant component;
- scenarios have unique ids and text, invoke only tactics the record declares,
  and a record with redundant components states at least one scenario;
- an explicit voter is a declared component named in `output_from`, has at
  least two incoming edges, and none of them carries an initial token; a
  folded voter takes its output from the owner;
- the record is marked SDF-compatible ([Token preservation](#token-preservation)).

During expansion (`patterns.expand`) the front end also checks that a
pattern's placement relations can be satisfied on the platform: enough cores
and FCRs, and, for `DIVERSE` groups, enough core types certifiable at the
actor's SIL. A pattern that is not placeable is dropped as a candidate with a
NOTE; only an actor left with no candidate is an error.

### Token preservation

Every component fires once per iteration and produces on all outputs, also in
degraded mode. Failure behaviour lives in the value domain (a token is marked
invalid), never in the presence domain (a token is withheld). This keeps the
timing analysis valid under a fault and is the condition under which a
pattern component can mirror its owner's rates. It is conservative in the
fault-free case. A pattern whose run-time behaviour is rate-inconsistent or
data-dependent cannot be expressed in SDF; such a record is marked
`sdf_compatible: false` and rejected.

### No nesting

Patterns apply to base SDF actors only; a pattern is not applied to another
pattern's component. This keeps the superposition linear in the catalogue
size. A "checker for the checker" is represented flat, as a second component
with a cross-check edge.

### Voters

By default the comparison or vote is folded into existing components
(`voter: folded`) and needs no rerouting. A pattern with an explicit voter
(`output_from: voter`) reroutes every channel leaving the owner so that it
starts at the voter; the original channel survives only under folded-voter
patterns. Leaving the direct channel in place would let output bypass the
voter. A rerouted channel into a downstream actor that fans its input out to
its own components is selected by two actors' decisions; such an edge carries
a second, conjunctive guard (`pe_owner2`, `pe_guard2` in `lib/activation.mzn`).
An edge with one condition repeats its owner and has an all-true second guard
row, which avoids an out-of-range `pat[0]` lookup.

The explicit-voter N-version programming record (`nvp_three_version`) is kept
in a separate catalogue (`data/patterns_explicit_voter*.yaml`): it builds with
every instance, but adding it to the main catalogue would change the optimum of
existing regression instances.

### Pairwise placement

Placement relations are applied pairwise across HSDF copies: copy k of a
component must satisfy the relation with copy k of its partner. The set-wise
reading ("no checker copy shares a core with any doer copy") is strictly
stronger and forbids safe interleavings. The relations are

| Relation | Meaning | Motivating fault class |
|---|---|---|
| `SAME` | same core | (none: co-location provides no independence) |
| `DIFFERENT` | different cores, possibly one FCR | random hardware |
| `DIFFERENT_FCR` | different fault containment regions | random hardware |
| `DIVERSE` | different core types | systematic software |

### The none ceiling

The pattern `none` (no structural measure) is admissible up to SIL 1 only:
from SIL 2 upward IEC 61508 expects diagnostic coverage, so a SIL-2 actor must
take at least a checker pattern. This single value moves the whole design
space, which is why it is in the catalogue and not in the model.

### Component slots

Each SDF actor receives as many component slots as the largest admissible
pattern needs. Slots are shared between patterns, but only between components
of the same WCET type (`patterns.slot_layout`), so a checker is never priced as
a full replica or the other way round, and a voter gets a slot of its own.

### Component SILs

Every active component (checker, replica, voter) carries its owner actor's
required SIL. A record's `sil_offset` states how many levels below that SIL
the doer (the owner) could be developed (Koopman's low-SIL doer with a
high-SIL checker; Koopman and Wagner 2016). The model does not use it yet: the
owner stays at the actor's SIL, which is conservative for the doer. Likewise
`dev_cost_multiplier` and `dev_cost_multiplier_diverse` are recorded for each
component but not priced by the model; every node is priced at
`dev_base × dev_k[sil]`.

### DIVERSE

`DIVERSE` places components on different core types. Distinct instruction
sets imply distinct toolchains and object code (IEC 61508-7 B.1.4 and part of
C.4.4). It does not establish independent design, which is the substance of
diverse redundancy; the generated argument carries a standing assumption that
says so. N mutually diverse components at SIL n need N distinct core types,
each certifiable to SIL n; the placeability check counts only those types.

---

## Communication

### TDMA refinement

With `--comm tdma`, every application channel receives three MSAG actors,
block, send and receive, active when its endpoints are on different cores
(`ch_remote`). The worst-case communication times follow DeSyDe's TDMA model:
blocking is the worst-case wait for the sender's slot,
`(tdma_slots − (alloc − 1)) × cycle_length`; sending takes whole TDMA rounds,
`(rounds(alloc) × tdma_slots + tdma_slots) × cycle_length`; receiving takes no
time (the token lands in the receiver's local memory), but the receive actor
exists because the receive buffer closes a cycle. Slots are allocated to a
processor iff it sends something, never more than its largest message needs,
and at most `tdma_slots` in total. Send- and receive-side buffer sizes are
decision variables, with the send buffers bounded by the network-interface
capacity. Block and send run on the sending processor, receive on the
destination; their placement is derived. Bus parameters are read from the
platform file.

### Communication actors and the processor order

Communication actors are not in the processor static order and do not count
in a core's load. A transfer occupies the bus and the network interface, not
the core's execution unit; bus contention is already in the TDMA worst-case
times. Putting them in the processor order was both wrong (it charged the core
for bus time) and expensive (the order constraints are O(n²) and communication
triples the node count). A transfer therefore lengthens latency and lengthens
the period only when the bus is the bottleneck.

### Remote channels replace the direct edge

A remote channel's direct edge is replaced by the block/send/receive path, not
augmented: the front end removes the channel from `tok` and passes its initial
tokens as `ch_direct_tok`, and `lib/comm.mzn` posts the direct edge only while
the channel is local. A surviving direct edge would be a shortcut past the
whole communication delay. The path carries the channel's initial tokens on
its first edge.

### Communication SIL

`--comm-sil` states whether bus transfers count against their core's SIL; the
answer depends on the platform, not on the model:

| Mode | Meaning |
|---|---|
| `exempt` (default) | transfers carry no integrity requirement (DMA driven by dedicated hardware); communication actors are exempt from rule 2 |
| `inherit` | a transfer inherits the SIL of its sending actor |
| `core` | the bus driver is ordinary software on its core and follows rule 2 |

In `exempt` mode the generated argument states the assumption and names the
two modes to regenerate under if it is false.

### Cross-check traffic

`--comm-scope app` (default) refines application channels only and treats
replica cross-check traffic as a dedicated comparison link, which is what
Koopman's patterns assume. `--comm-scope all` routes pattern traffic over the
application bus as well; the graph grows several times and the period can
rise. A separately declared interconnect for cross-check traffic is not
modelled.

### Channel separation

`lib/comm.mzn` accepts pairs of channels that must not share a failure region
and requires their sources to be different processors, so their traffic uses
disjoint TDMA slots. A single bus remains a single point of failure that no
slot discipline removes; a replicated bus or a network-on-chip with disjoint
routes would be needed for full communication redundancy.

---

## Objective selection

Every metric (`THROUGHPUT`, `LATENCY`, `HWCOST`, `DEVCOST`, `TOTALCOST`,
`POWER`, `NPROCS`, `PROMOTION`) is always computed and can be bounded. The
objective is a parameter (`opt_metric`, set with `-D` or
`tools/solve.py --optimise`), so switching the optimised metric needs no model
edit. One optimum is returned per configuration; trade-off fronts are built by
sweeping bounds (`--bound METRIC=value`). `THROUGHPUT` is the worst period over
the applications. When the period is not the objective, the model only
guarantees MCR ≤ μ ≤ bound; a second solve with the design fixed and μ
minimised gives the least period of that design.

---

## Independent verification

`tools/verify.py` shares no code with the model. It rebuilds the MSAG of the
deployed design from the solution (inactive slots removed, static orders
spliced, refined channels restored) and computes the period twice by
different methods: Lawler's parametric MCR search and max-plus self-timed
simulation (`tools/golden.py`). It accepts the reported period if it equals
⌈MCR⌉ (μ is an integer in the model). It also re-derives every field the model
derives instead of taking it from the solution: WCETs from the table, one
static order per core over exactly its nodes, activation from the selected
pattern, pattern admissibility, partitioning capability, memory and costs. It
checks SIL provisioning and isolation (rule 2), the busiest-core load bound
and every active placement relation.

Every check appends a record to a structured check log (`--json-report`). The
log records what was checked, not what is true; a claim without a record is
treated like a failed one. This lets the argument generator distinguish
"nobody looked" from "looked and passed". Record kinds are listed in
[inputs.md](inputs.md#check-log).

---

## Safety-argument generation

`tools/gsn.py` instantiates the per-pattern GSN fragments of Preschern,
Kajtazovic and Kreiner (EuroPLoP 2015) for a solved, verified deployment: a
top goal, a strategy over actors, per actor a strategy "by application of
pattern P", one goal per general scenario of the pattern, one strategy per
tactic, and leaves. Tactics resolve to IEC 61508-7 methods through the
tactic table `data/gsn_tactics.yaml` (Preschern et al., Appendix B), held as
data for the same reason as the catalogue.

Some tactics have a precondition that is a property of the deployment:
replication redundancy is worthless if the replicas share a fault containment
region. The tactic table has a `deployment_relations` column for these; their
goals become GSN Solutions that cite specific records of a specific verifier
run. Value-domain tactics (sanity check, comparison, voting, repair, and
others) have no deployment relation and stay undeveloped. Each placement
relation has its own claim (`relation_claims`), so `DIFFERENT` is never cited
for FCR separation, and each separation claim has an undeveloped goal for the
common causes the relation leaves (`residual_common_cause`).

The generator enforces one invariant (`Argument.audit`): every leaf is either
a Solution citing a passed record of the check log, or a goal marked
undeveloped with a stated reason. It refuses to produce an argument (non-zero
exit) when

- the verifier rejected the solution (exit 2);
- a `--fault-model` flag contradicts the instance (exit 2);
- the audit finds a leaf that is neither (exit 3);
- the instance uses a pattern absent from the loaded catalogue (exit 4);
  otherwise such an actor would silently be argued as having no pattern.

The fault model is inferred from `pat_allowed`, which is a function of the
fault model and the per-actor SILs, both in the instance. A wrong flag would
not fail; it would produce a fluent argument claiming coverage the design
never had. On small catalogues the inference can be ambiguous; the generator
then names no fault model and does not mark scenarios out of scope.

Actor and top goals say that the deployment meets the architectural
preconditions that the catalogue states for SIL n, not that it attains SIL n:
a pattern's SIL range is necessary, not sufficient (no failure rates, hardware
fault tolerance, safe failure fraction or diagnostic coverage are computed).
Evidence is identified by SHA-256 hashes of the instance, the solution and the
check log.

---

## Known limitations

- **Least period above the MCR.** An inactive slot keeps its edges, with zero
  WCET. A path through an unselected pattern's channel into an inactive slot,
  followed by that slot's static-order edge, can raise the model's least
  period of a design above the MCR of the deployed graph, never below it.
  The model stays sound but can be pessimistic, so under a tight period bound
  "optimal within the model" can miss a design whose deployed period meets
  the bound. The verifier checks the deployed graph and reports the mismatch.
- **Guarded pattern edges.** The front end writes pattern channels into `tok`
  as well as into the guarded edge list, and `lib/mcm.mzn` posts every `tok`
  edge, so `mcm_pattern_edges` in `lib/activation.mzn` is redundant with the
  current front end. What neutralises an unselected edge is zero WCET. Making
  the guarded form the only one would need the verifier changed in step.
- **Cross-solver evidence.** On instances with a pattern catalogue, Gecode and
  Chuffed rarely answer, so solver agreement gives no evidence there.
- **Component SILs and diverse development** are conservative or unpriced
  ([Component SILs](#component-sils)).
- **Verdict timing.** Catalogue verdict edges carry one token: the fault
  reaction completes within one period.
- **Timing model.** WCETs are inputs; execution is self-timed with static
  orders. `tools/mkwcets.py` produces scaffolding WCETs (checker at a fixed
  fraction of the owner), not measurements.
- **Latency** is a periodic-phase estimate ([Latency estimate](#latency-estimate)).
- **Partitioning cost** is per core ([Partitioning](#partitioning)).
- **Arguments** are single GSN graphs; modules and away goals are not
  supported.

---

## Modelling pitfalls

Constraint models fail silently: a wrong encoding returns a plausible number,
not an error. These cost time during development and are worth knowing when
changing the model.

1. **MiniZinc precedence.** `=` binds tighter than `\/`, so `x = (A) \/ (B)`
   parses as `(x = A) \/ B` and leaves `x` unconstrained when B holds.
   Parenthesise every Boolean right-hand side.
2. **Disjunction outside the quantifier.** `forall(...) \/ forall(...)` lets
   either every actor take option A or every actor take option B. Per-actor
   decisions (`pat[a]`) avoid it.
3. **Open-chain static order** drops the core load bound
   ([Closed per-core static order](#closed-per-core-static-order)).
4. **Sentinels in bounds.** The period upper bound must exclude the forbidden
   WCET sentinel, or domains grow by orders of magnitude.
5. **Defaults.** `max_sil` defaults to 4 for platform dialects that do not
   declare it; a default of 0 makes every SIL requirement unsatisfiable.
6. **Communication actors** belong on the bus, not in the processor order or
   the core load.
7. **Measure before optimising.** Several plausible optimisations (stronger
   symmetry breaking, a flattened WCET lookup, tying communication actors'
   `active` to `ch_remote`) were measured to be no faster or slower. Building
   a deliberately unsound variant first bounds what an optimisation can gain.
8. **A broken install looks like an infeasible model.** `bootstrap_minizinc.sh`
   checks the binary before installing it.
9. **Stale instances.** `tools/build_all.sh` clears `out/*.dzn` before
   rebuilding, so a renamed instance cannot survive and be solved against a
   newer model.
10. **Zero-length arrays.** The front end always emits at least one padding row
    for sparse arrays (`nPE`, `nPL`, `nCh`, `nSep` control the index sets),
    because some MiniZinc versions crash on zero-length `array[int] of int`.
