"""SDF -> HSDF unfolding (docs/design.md#patterns-at-sdf-level).

Runs *after* pattern superposition (patterns apply at SDF level), so it must
carry provenance forward:

  parent[i]     which SDF actor HSDF copy i came from  -- needed for Rosvall's
                constraints 23 and 33 (docs/design.md#copy-order-symmetry)
  copy_index[i] which copy, 0..q[parent]-1             -- needed for the
                *pairwise* reading of placement relations

The rewiring rule is the standard one.  For a channel u->v with production rate
p, consumption rate c and d initial tokens, let Ttot = q[u]*p = q[v]*c be the
number of tokens exchanged per graph iteration.  Token k (0 <= k < Ttot) is
produced by copy (k div p) of u and consumed by copy (((k+d) mod Ttot) div c)
of v, and the resulting HSDF edge carries (k+d) div Ttot initial tokens.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sdf3 import SDFGraph


@dataclass
class HSDFNode:
    name: str
    type: str
    parent: int          # index into the SDF actor list
    copy_index: int
    exec_time: int
    state_size: int


@dataclass
class HSDFEdge:
    src: int
    dst: int
    initial_tokens: int
    token_size: int = 0
    origin: str = ""     # originating SDF channel name, or "auto-concurrency"


@dataclass
class HSDFGraph:
    name: str
    nodes: list[HSDFNode] = field(default_factory=list)
    edges: list[HSDFEdge] = field(default_factory=list)
    q: list[int] = field(default_factory=list)          # repetition vector
    parent_names: list[str] = field(default_factory=list)

    def n(self) -> int:
        return len(self.nodes)

    def token_matrix(self) -> list[list[int]]:
        """Dense form for the .dzn: -1 = no edge, >=0 = initial tokens.

        Parallel edges between the same node pair are collapsed to the
        *minimum* token count, which is the binding one for throughput: the
        tightest precedence dominates and the others are implied.
        """
        n = self.n()
        m = [[-1] * n for _ in range(n)]
        for e in self.edges:
            cur = m[e.src][e.dst]
            m[e.src][e.dst] = e.initial_tokens if cur < 0 else min(cur, e.initial_tokens)
        return m


def unfold(g: SDFGraph, add_auto_concurrency: bool = True) -> HSDFGraph:
    q = g.repetition_vector()
    idx = g.index()

    nodes: list[HSDFNode] = []
    first: list[int] = []            # first HSDF index of each SDF actor
    for ai, a in enumerate(g.actors):
        first.append(len(nodes))
        for k in range(q[ai]):
            nodes.append(HSDFNode(
                name=a.name if q[ai] == 1 else f"{a.name}#{k}",
                type=a.type, parent=ai, copy_index=k,
                exec_time=a.exec_time, state_size=a.state_size))

    edges: list[HSDFEdge] = []
    for c in g.channels:
        u, v = idx[c.src], idx[c.dst]
        ttot = q[u] * c.prod
        assert ttot == q[v] * c.cons, (
            f"channel {c.name!r}: balance broken after repetition vector "
            f"({q[u]}*{c.prod} != {q[v]}*{c.cons}) -- this is a bug in "
            f"repetition_vector(), not in the input")
        for k in range(ttot):
            sc = k // c.prod
            kk = (k + c.initial_tokens) % ttot
            dc = kk // c.cons
            delay = (k + c.initial_tokens) // ttot
            edges.append(HSDFEdge(
                src=first[u] + sc, dst=first[v] + dc,
                initial_tokens=delay, token_size=c.token_size,
                origin=c.name))

    if add_auto_concurrency:
        for i, node in enumerate(nodes):
            ac = g.actors[node.parent].auto_concurrency
            if ac >= 1:
                edges.append(HSDFEdge(src=i, dst=i, initial_tokens=ac,
                                      origin="auto-concurrency"))

    return HSDFGraph(name=g.name, nodes=nodes, edges=edges, q=q,
                     parent_names=[a.name for a in g.actors])


# --------------------------------------------------------------------------
# Validation -- three properties of a correct unfolding
# --------------------------------------------------------------------------
def check_unfolding(g: SDFGraph, h: HSDFGraph) -> list[str]:
    """Returns a list of failures; empty means all properties hold."""
    problems: list[str] = []

    # (1) node count
    if h.n() != sum(h.q):
        problems.append(f"node count {h.n()} != sum(q) {sum(h.q)}")

    # (2) token preservation, per originating channel
    per_channel: dict[str, int] = {}
    for e in h.edges:
        if e.origin and e.origin != "auto-concurrency":
            per_channel[e.origin] = per_channel.get(e.origin, 0) + e.initial_tokens
    for c in g.channels:
        got = per_channel.get(c.name, 0)
        if got != c.initial_tokens:
            problems.append(
                f"channel {c.name!r}: {c.initial_tokens} initial tokens in the "
                f"SDF but {got} distributed across its HSDF edges")

    # (3) firing count -- each SDF actor's copies must together consume and
    #     produce exactly one iteration's worth of tokens on each channel
    idx = g.index()
    for c in g.channels:
        ttot = h.q[idx[c.src]] * c.prod
        got = sum(1 for e in h.edges if e.origin == c.name)
        if got != ttot:
            problems.append(
                f"channel {c.name!r}: expected {ttot} HSDF edges, got {got}")

    return problems
