"""Guarded superposition of safety patterns at SDF level (architecture C.2/C.3).

The central architectural decision: **topology is a parameter, selection is a
variable**.  Everything that can be settled by static analysis of the pattern
library happens here; the CP model receives a fixed graph plus guards and
decides only which parts of it are real.

For each SDF actor `a` the expander instantiates every component of every
applicable pattern, sharing component slots between patterns that need the same
number, and tags each added node and edge with the SET of patterns that use it.
The model then has one variable `pat[a]` per actor and derives

    active[v]  <->  pat[owner(v)] in guardset(v)

Why at SDF level (Q5): a pattern component mirrors its owner's rates exactly
(the token-preservation obligation), so the repetition vector of the superposed
graph extends the original with no new balance equations.  Unfolding afterwards
is therefore static, and `pat[a]` stays one variable per DESIGN decision rather
than one per HSDF copy.

The cost is that placement relations must be read PAIRWISE across copies (Q16):
copy i of the checker must differ from copy i of the doer, not merely from the
doer set as a whole.  The expander emits the pairwise form.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from sdf3 import Actor, Channel, SDFGraph

RELATIONS = {"SAME": 1, "DIFFERENT": 2, "DIFFERENT_FCR": 3, "DIVERSE": 4}


class PatternError(Exception):
    """A malformed pattern record, or one the platform cannot satisfy.

    Raised at build time with an explanation, rather than being left to surface
    as an opaque UNSAT after a long solve.
    """


@dataclass
class Pattern:
    id: str
    components: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    input_fanout: list[str] = field(default_factory=list)
    output_from: str = "owner"
    placement: list[dict] = field(default_factory=list)
    achieves_sil: list[int] = field(default_factory=list)
    covers_faults: list[str] = field(default_factory=list)
    failure_mode: str = "none"
    voter: str = "folded"
    dev_cost_multiplier: dict = field(default_factory=dict)
    recurring_cost_units: int = 0
    tactics: list[str] = field(default_factory=list)
    # Preschern EuroPLoP'15 s4.3: the GSN subgoals are the pattern's general
    # scenarios, and the tactics achieving a scenario sit under it as
    # strategies.  Consumed by tools/gsn.py; carried here so a malformed
    # scenario is caught by check_pattern at build time rather than surfacing
    # only when someone asks for a safety argument.
    scenarios: list[dict] = field(default_factory=list)
    sdf_compatible: bool = True
    source: list = field(default_factory=list)
    description: str = ""


@dataclass
class Superposition:
    """The expanded SDF plus everything the model needs to guard it."""
    graph: SDFGraph
    patterns: list[Pattern]
    # per SDF actor of the ORIGINAL graph
    applicable: dict[str, list[int]] = field(default_factory=dict)   # pattern ids
    owner_of: dict[str, str] = field(default_factory=dict)           # node -> owner
    guard_of: dict[str, list[int]] = field(default_factory=dict)     # node -> pattern ids
    # channel name -> (owner actor, pattern ids that use it).  Pattern edges are
    # added to the SDF graph as real channels so the UNFOLDER computes their
    # copy-to-copy mapping and repetition-vector consistency by the same rule as
    # every other channel -- rather than the expander reimplementing that logic
    # and getting the pairwise correspondence (Q16) subtly wrong.
    chan_guards: dict[str, tuple[str, list[int]]] = field(default_factory=dict)
    placements: list[tuple] = field(default_factory=list)   # (u,v,rel,owner,guards)
    notes: list[str] = field(default_factory=list)


def load_patterns(path: str | Path) -> list[Pattern]:
    doc = yaml.safe_load(Path(path).read_text())
    out = []
    for rec in doc["patterns"]:
        rec = dict(rec)
        rec.pop("description", None) if False else None
        out.append(Pattern(**{k: v for k, v in rec.items()
                              if k in Pattern.__dataclass_fields__}))
    return out


# ---------------------------------------------------------------------------
# C.4 well-formedness obligations
# ---------------------------------------------------------------------------
def check_pattern(p: Pattern, n_cores_by_fcr: tuple[int, int, int] | None = None
                  ) -> list[str]:
    """Returns a list of violations; empty means the record is well formed."""
    bad: list[str] = []
    roles = {"owner"} | {c["role"] for c in p.components}

    for e in p.edges:
        for end in ("from", "to"):
            if e[end] not in roles:
                bad.append(f"{p.id}: edge references unknown role {e[end]!r}")
    for r in p.input_fanout:
        if r not in roles:
            bad.append(f"{p.id}: input_fanout references unknown role {r!r}")
    for pl in p.placement:
        if pl["relation"] not in RELATIONS:
            bad.append(f"{p.id}: unknown placement relation {pl['relation']!r}")
        for m in pl["members"]:
            if m not in roles:
                bad.append(f"{p.id}: placement references unknown role {m!r}")

    # (2) every introduced cycle must carry an initial token, or the expanded
    #     graph deadlocks -- and a graph that deadlocks is not one whose
    #     throughput can be certified
    adj: dict[str, list[tuple[str, int]]] = {}
    for e in p.edges:
        adj.setdefault(e["from"], []).append((e["to"], int(e.get("tokens", 0))))
    for cyc in _cycles(adj):
        if sum(t for _, t in cyc) == 0:
            names = " -> ".join(r for r, _ in cyc)
            bad.append(f"{p.id}: cycle {names} carries no initial token and "
                       f"will deadlock; add tokens to one of its edges")

    # (5) anti-pattern rejection
    if p.failure_mode == "silent" and any(
            pl["relation"] == "SAME" for pl in p.placement):
        bad.append(f"{p.id}: claims to fail silent but co-locates its channels "
                   f"on one processor -- this is Koopman's 'Attempted High SIL "
                   f"Doer/Checker' anti-pattern")
    if max(p.achieves_sil or [0]) >= 3 and not p.components:
        bad.append(f"{p.id}: claims SIL {max(p.achieves_sil)} with no redundant "
                   f"component")

    # (6) scenario well-formedness (Phase 8).  A scenario is a CLAIM that will
    #     be emitted into a safety argument, so a malformed one is worse than a
    #     malformed edge: it does not fail, it just asserts something nobody
    #     checked.  Two obligations:
    #       * every tactic a scenario invokes is declared by the pattern, so
    #         the argument cannot quietly use a mechanism the record does not
    #         claim to implement;
    #       * a pattern with redundant components states at least one scenario,
    #         so silence is never mistaken for "nothing to argue".
    sids = [s.get("id") for s in p.scenarios]
    if len(sids) != len(set(sids)):
        bad.append(f"{p.id}: duplicate scenario ids {sorted(sids)}")
    for s in p.scenarios:
        if not s.get("text", "").strip():
            bad.append(f"{p.id}: scenario {s.get('id')} has no text")
        for t in s.get("tactics", []):
            if t not in p.tactics:
                bad.append(f"{p.id}: scenario {s.get('id')} invokes tactic "
                           f"{t!r}, which the pattern does not declare")
    if p.components and not p.scenarios:
        bad.append(f"{p.id}: has redundant components but states no general "
                   f"scenario, so no safety argument can be generated for it")

    # Phase 4/5 restriction (Q10)
    if p.voter == "explicit":
        bad.append(f"{p.id}: explicit voters are Phase 6; only voter=folded "
                   f"patterns are admitted so far")
    if not p.sdf_compatible:
        bad.append(f"{p.id}: marked sdf_compatible=false; a pattern whose "
                   f"runtime behaviour is rate-inconsistent or data-dependent "
                   f"cannot be expressed in SDF (see A.4)")
    return bad


def _cycles(adj: dict[str, list[tuple[str, int]]]) -> list[list[tuple[str, int]]]:
    """All simple cycles, by DFS.  Pattern graphs are tiny."""
    out: list[list[tuple[str, int]]] = []
    seen_sets: set[frozenset] = set()

    def walk(start: str, node: str, path: list[tuple[str, int]]) -> None:
        for nxt, tok in adj.get(node, ()):
            if nxt == start:
                cyc = path + [(node, tok)]
                key = frozenset(r for r, _ in cyc)
                if key not in seen_sets:
                    seen_sets.add(key)
                    out.append(cyc)
            elif nxt not in {r for r, _ in path} and nxt != start:
                walk(start, nxt, path + [(node, tok)])

    for s in list(adj):
        walk(s, s, [])
    return out


# ---------------------------------------------------------------------------
def expand(g: SDFGraph, patterns: list[Pattern], sil_req: dict[str, int],
           fault_model: str, force_none: bool = False,
           platform_fcrs: int = 0, platform_cores: int = 0) -> Superposition:
    """Build the superposed SDF graph.

    Slot sharing: actor `a` receives max(|components(p)|) slots over its
    applicable patterns, and a pattern using fewer simply guards fewer of them.
    So the expansion is O(sum_a max_p |components(p)|), not O(sum_a sum_p ...).
    """
    by_id = {p.id: p for p in patterns}
    ids = [p.id for p in patterns]
    faults = {"random_hw", "systematic_sw"} if fault_model == "both" else {fault_model}

    sup = Superposition(graph=SDFGraph(name=g.name), patterns=patterns)

    # ---- applicability -----------------------------------------------------
    for a in g.actors:
        need = sil_req.get(a.name, 0)
        if force_none:
            sup.applicable[a.name] = [ids.index("none")]
            continue
        app = [ids.index(p.id) for p in patterns
               if need in p.achieves_sil and faults <= set(p.covers_faults)]
        if not app:
            reachable = sorted({s for p in patterns
                                if faults <= set(p.covers_faults)
                                for s in p.achieves_sil})
            raise PatternError(
                f"actor {a.name!r} requires SIL {need} under fault model "
                f"{fault_model!r}, but no pattern in the library achieves it. "
                f"Reachable SILs under this fault model: {reachable}. "
                f"Either add a pattern, relax the requirement, or select a "
                f"different fault model.")
        sup.applicable[a.name] = app

    # ---- allocate component slots -----------------------------------------
    sup.graph.actors = list(g.actors)
    sup.graph.channels = list(g.channels)
    for a in g.actors:
        app = sup.applicable[a.name]
        nslots = max(len(by_id[ids[pi]].components) for pi in app)
        for k in range(nslots):
            guards = [pi for pi in app if len(by_id[ids[pi]].components) > k]
            # every pattern using slot k must agree on what the slot is for,
            # otherwise the sharing is unsound
            roles = {by_id[ids[pi]].components[k]["role"] for pi in guards}
            comp = by_id[ids[guards[0]]].components[k]
            name = f"{a.name}~{k}"
            # Keep <owner> UNSUBSTITUTED. Which key the WCET table uses for the
            # owner is not knowable here -- Rosvall's table keys on actor names
            # (`get_pixel`), SafeDSE's on task types (`getPixel`) -- so the
            # front-end resolves the owner's key first and substitutes then.
            wt = str(comp.get("wcet_type", "<owner>"))
            sup.graph.actors.append(Actor(name=name, type=wt,
                                          exec_time=a.exec_time,
                                          state_size=a.state_size))
            sup.owner_of[name] = a.name
            sup.guard_of[name] = guards
            if len(roles) > 1:
                sup.notes.append(
                    f"slot {name} is shared by patterns with differing roles "
                    f"{sorted(roles)}; sharing is by position, so verify the "
                    f"placement relations still say what you mean")

    # ---- edges and placements ---------------------------------------------
    def resolve(a_name: str, pi: int, role: str) -> str:
        if role == "owner":
            return a_name
        p = by_id[ids[pi]]
        k = next(i for i, c in enumerate(p.components) if c["role"] == role)
        return f"{a_name}~{k}"

    for a in g.actors:
        for pi in sup.applicable[a.name]:
            p = by_id[ids[pi]]
            for ei, e in enumerate(p.edges):
                u = resolve(a.name, pi, e["from"])
                v = resolve(a.name, pi, e["to"])
                cn = f"PAT:{a.name}:{p.id}:e{ei}"
                sup.graph.channels.append(Channel(
                    name=cn, src=u, dst=v, prod=1, cons=1,
                    initial_tokens=int(e.get("tokens", 0))))
                sup.chan_guards[cn] = (a.name, [pi])
            # components listed in input_fanout also consume the owner's inputs,
            # so every incoming channel is duplicated to them at the same rates
            for role in p.input_fanout:
                tgt = resolve(a.name, pi, role)
                for ch in g.channels:
                    if ch.dst == a.name:
                        cn = f"PAT:{a.name}:{p.id}:in:{ch.name}:{role}"
                        sup.graph.channels.append(Channel(
                            name=cn, src=ch.src, dst=tgt,
                            prod=ch.prod, cons=ch.cons,
                            initial_tokens=ch.initial_tokens,
                            token_size=ch.token_size))
                        sup.chan_guards[cn] = (a.name, [pi])
            for pl in p.placement:
                if "for" in pl and pl["for"] not in faults:
                    continue          # relation motivated by a fault model we
                                      # are not defending against (Q2)
                ms = pl["members"]
                for x in range(len(ms)):
                    for y in range(x + 1, len(ms)):
                        sup.placements.append((
                            resolve(a.name, pi, ms[x]),
                            resolve(a.name, pi, ms[y]),
                            RELATIONS[pl["relation"]], a.name, [pi]))

    # ---- (4) placement satisfiability -------------------------------------
    # Catching this here gives a diagnosable error instead of an opaque UNSAT.
    if platform_cores:
        for u, v, rel, owner, _ in sup.placements:
            if rel in (RELATIONS["DIFFERENT"], RELATIONS["DIFFERENT_FCR"]) \
                    and platform_cores < 2:
                raise PatternError(
                    f"placement {u}/{v} requires two distinct cores but the "
                    f"platform declares {platform_cores}")
            if rel == RELATIONS["DIFFERENT_FCR"] and platform_fcrs < 2:
                raise PatternError(
                    f"placement {u}/{v} requires two distinct fault containment "
                    f"regions but the platform declares {platform_fcrs}. Either "
                    f"add cards to the catalogue or select a pattern that does "
                    f"not need FCR separation.")

    return sup
