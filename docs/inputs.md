# Inputs and outputs

All inputs are XML or YAML files under `data/` (any path works on the command
line). The XML formats follow the SDF3 and DeSyDe conventions where those
exist. The reasons behind the semantics are in [design.md](design.md).

## Application graphs (SDF3 XML)

Standard SDF3 `type="sdf"` files. The front end reads actors (name, type),
ports with rates, channels with initial tokens and token size, and, per actor,
`executionTime` (used only by `tools/mkwcets.py` and by
`--wcet-fallback-scale`) and `stateSize`.

```xml
<sdf3 type="sdf" version="1.0">
  <applicationGraph name="c_rasta">
    <sdf name="c_rasta" type="RASTA">
      <actor name="frontEnd" type="FrontEnd">
        <port name="out" type="out" rate="1"/>
      </actor>
      ...
      <channel name="ch0" srcActor="frontEnd" srcPort="out"
               dstActor="rasta" dstPort="in" initialTokens="0"/>
    </sdf>
    <sdfProperties> ... </sdfProperties>
  </applicationGraph>
</sdf3>
```

Multi-rate graphs (`*.sdf.xml`) are unfolded to HSDF by the front end. Prefer
them to pre-unfolded `*.hsdf.xml` files ([why](design.md#patterns-at-sdf-level)).
The application name (`applicationGraph name`) prefixes every node name in the
instance (`c_rasta.frontEnd`).

## Platform catalogue

Two dialects are accepted (`tools/platform.py`).

**SafeDSE dialect** with fault containment region (FCR) templates:

```xml
<platform name="mixed_criticality_demo">
  <fcr_template name="R-card" max_instances="3" monetary="120">
    <processor model="cortexR" count="2" max_sil="4" mem="64000"
               partitionable="true" partition_cost="15">
      <mode name="standard" cycle="1"   dynPower="180" area="14" monetary="40"/>
      <mode name="eco"      cycle="1.3" dynPower="95"  area="14" monetary="40"/>
    </processor>
  </fcr_template>
  ...
  <interconnect>
    <TDMA_bus name="TDMA-bus" x-dimension="8" flitSize="32" tdma_slots="16"
              maxSlotsPerProc="8">
      <mode name="default" cycleLength="1"/>
    </TDMA_bus>
  </interconnect>
</platform>
```

| Element / attribute | Meaning |
|---|---|
| `fcr_template` `max_instances`, `monetary` | how many cards of this kind may be bought; price per card |
| `processor` `model`, `count` | core type and number of cores per card |
| `max_sil` | highest SIL a core of this type can be certified to (default 4) |
| `mem` | memory per core |
| `partitionable`, `partition_cost` | certified partitioning available on this type, and its cost per core |
| `mode` `cycle`, `dynPower`, `monetary` | operating mode: cycle factor (used by `mkwcets.py`), power, price per core |
| `TDMA_bus` `tdma_slots`, `flitSize`, `cycleLength` | bus used by `--comm tdma`: slots per round, data per slot, slot length |

**DeSyDe dialect**: a flat list of `<processor model=".." number="..">` with
modes. Each processor becomes its own single-core FCR; the price is the
per-mode `monetary` value.

## WCET table

```xml
<WCET_table>
  <mapping task_type="FrontEnd">
    <wcet processor="cortexR" mode="standard" wcet="108"/>
    <wcet processor="cortexM" mode="standard" wcet="173"/>
  </mapping>
</WCET_table>
```

`task_type` may be an actor name or an actor type; `processor` is a core type,
or `default`. A missing (task, core type, mode) entry forbids that binding
([details](design.md#wcet-table-and-forbidden-bindings)). Pattern components
need entries for their WCET types, for example `checker_FrontEnd` and the
owner's own key for a replica. `tools/mkwcets.py` writes a scaffold table from
the nominal execution times (mode cycle factor applied; checkers at
`--checker-scale` of the owner, default 0.3); the generated file says that it
is scaffolding, not measurement.

## Design constraints

```xml
<designConstraints>
  <constraint app_name="c_rasta" period="550"/>
</designConstraints>
```

`period` bounds the application's period; `-1` means unconstrained, in which
case the front end uses the period of all actors on one core with their
slowest feasible WCETs.

## Safety specification

```xml
<safety fault_model="random_hw" cost_profile="myklebust2015" allow_promotion="true">
  <default sil="1"/>
  <actor name="frontEnd" sil="3"/>
</safety>
```

| Attribute | Values |
|---|---|
| `fault_model` | `random_hw`, `systematic_sw`, `both` ([fault model](design.md#fault-model)) |
| `cost_profile` | a profile name in the cost model ([cost profiles](design.md#cost-profiles)) |
| `allow_promotion` | `true` (default) or `false` ([SIL promotion](design.md#sil-promotion)) |
| `default sil`, `actor sil` | required SIL per SDF actor, 0-4 |

Without a safety specification every actor has SIL 0.

## Latency constraints

```xml
<latency>
  <path src="a_sobel.get_pixel" dst="a_sobel.abs" max="1200"/>
</latency>
```

Node names are `<application>.<actor>`; see [latency estimate](design.md#latency-estimate).

## Cost model

```xml
<cost_model>
  <profile name="myklebust2015" default="true">
    <sil level="0" multiplier="100"/>
    ...
  </profile>
  <baseline default="100">
    <task task_type="FrontEnd" cost="120"/>
  </baseline>
</cost_model>
```

Multipliers are per SIL, times 100. The baseline gives the development cost of
a task at SIL 0. `data/cost_model.xml` documents the source of each profile.

## Pattern catalogue

`data/patterns.yaml` holds the main catalogue. `data/patterns_explicit_voter.yaml`
and `data/patterns_explicit_voter_demo.yaml` hold the explicit-voter N-version
programming record ([voters](design.md#voters)). A record:

```yaml
- id: two_of_two_high_sil
  source: [koopman, "Two Channel (2-of-2)"]
  description: >
    ...
  components:
    - {role: channel_b, sil_offset: 0, wcet_type: "<owner>"}
  edges:
    - {from: owner,     to: channel_b, tokens: 0}
    - {from: channel_b, to: owner,     tokens: 1}
  input_fanout: [channel_b]
  output_from: owner
  placement:
    - {relation: DIFFERENT_FCR, members: [owner, channel_b], for: random_hw}
    - {relation: DIVERSE,       members: [owner, channel_b], for: systematic_sw}
  achieves_sil: [3, 4]
  covers_faults: [random_hw, systematic_sw]
  failure_mode: silent
  voter: folded
  dev_cost_multiplier: {channel_b: 1.0}
  dev_cost_multiplier_diverse: {channel_b: 2.0}
  recurring_cost_units: 2
  scenarios:
    - id: SC2
      text: >
        A random hardware fault in one channel does not affect the other channel.
      covers: random_hw
      tactics: [Replication Redundancy]
  tactics: [Replication Redundancy, Comparison, Voting, Diverse Redundancy]
  sdf_compatible: true
```

| Field | Meaning |
|---|---|
| `components` | added roles; `wcet_type` is a WCET-table key, `<owner>` is replaced by the owner's key; `sil_offset` see [component SILs](design.md#component-sils) |
| `edges` | channels between `owner` and component roles, with initial tokens |
| `input_fanout` | roles that also receive the owner's inputs |
| `output_from` | `owner`, or the explicit voter role |
| `placement` | relations `SAME`, `DIFFERENT`, `DIFFERENT_FCR`, `DIVERSE` over roles; `for` names the fault class that motivates the relation (posted only under a fault model that includes it) |
| `achieves_sil` | SILs the pattern is admissible for |
| `covers_faults` | fault classes the pattern defends against |
| `failure_mode` | `none`, `active`, `silent`, `operational` |
| `voter` | `folded` or `explicit` |
| `dev_cost_multiplier`, `dev_cost_multiplier_diverse` | recorded per role; not priced by the model |
| `recurring_cost_units` | recurring cost per actor that applies the pattern (`pattern_cost`) |
| `scenarios` | general scenarios for the safety argument; `covers` marks a fault-specific scenario |
| `tactics` | tactics of the tactic table that the pattern uses |
| `sdf_compatible` | the record can be expressed in SDF ([token preservation](design.md#token-preservation)) |

The checks applied to each record are listed in
[design.md](design.md#well-formedness-checks).

## Tactic table

`data/gsn_tactics.yaml` lists tactics after Preschern et al. (EuroPLoP 2015,
Appendix B): `name`, `category`, `aim`, `description`, `iec61508_methods`
(IEC 61508-7 method identifiers), `deployment_relations` (placement relations
whose verifier records can discharge the tactic's deployment precondition),
and for those `relation_claims` and `residual_common_cause` per relation.

## Generated instance (`.dzn`)

`tools/build_dzn.py -o out/x.dzn` writes a MiniZinc data file. Its header
comments name the applications, platform, period mode, fault model and cost
profile. Do not edit it by hand; rebuild instead. `tools/build_all.sh`
rebuilds every instance in `out/` (instance names: `r_*` Rosvall benchmark,
`m_*`, `rasta`, `jpeg*` card-based platform, `s_*`, `x_*` safety without
patterns on a cheap and a costly platform, `p_*`, `d_*`, `f_*` with
patterns, `c_*` with TDMA communication, `pc_sobel` patterns and TDMA,
`v_nvp` explicit voter).

## Solution (JSON)

`tools/solve.py --json-out sol.json` writes the MiniZinc JSON solution: every
output variable of the model (`proc`, `succ`, `pat`, `active`, `T`, `mu`,
`sil_impl`, `csil`, `partition`, `used`, `fcr_used`, `pmode`, `tdma_alloc`,
buffers, costs, `metric`, ...). This file is the input of the verifier and the
generator.

## Check log

`tools/verify.py --json-report report.json` writes

```json
{"ok": true, "dzn": "...", "solution": "...", "messages": [...],
 "checks": [{"kind": "period", "ok": true, "detail": "...", ...}, ...]}
```

Record kinds: `input` (required fields present), `wcet`, `order`,
`activation`, `memory`, `cost`, `period`, `load_bound`, `sil_actor`,
`isolation`, `placement`. Records carry extra fields that name the nodes,
cores, FCRs and core types involved. The generator cites records by their
index in `checks`.

## Safety argument

`tools/gsn.py --out prefix` writes

- `prefix.gsn.json`: format tag, metadata (instance, solution, fault model
  and how it was determined, verifier verdict), statistics, warnings,
  out-of-scope scenarios, and the elements (id, kind, text, `undeveloped`,
  `supportedBy`, `inContextOf`, cited check indices in `evidence`, and the
  reason in `note`);
- `prefix.gsn.dot`: Graphviz with GSN shapes (render with
  `dot -Tsvg prefix.gsn.dot -o prefix.svg`);
- `prefix.gsn.md`: an indented, readable form;
- `prefix.verify.json`: the check log, when the generator ran the verifier.
