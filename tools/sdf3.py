"""SDF3 XML parsing for SafeDSE.

Reads the DeSyDe/SDF3 input ecosystem:
  * application graphs   (sdf3 ... type="sdf")
  * WCETs.xml            (task_type x processor x mode -> wcet)
  * platform.xml         (SafeDSE catalogue form, see platform.py)
  * desConst.xml         (per-application period constraints)

The SDF data model here is deliberately multi-rate. The benchmark files that
ship with DeSyDe are already single-rate (*.hsdf.xml, all rates 1), but the
whole point is that patterns are applied at SDF level and unfolding happens
afterwards (docs/design.md#patterns-at-sdf-level), so the front-end must handle
general SDF.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------
@dataclass
class Actor:
    name: str
    type: str                 # keys into WCETs.xml <mapping task_type="...">
    exec_time: int = 0        # default/nominal WCET (fallback if no WCET table)
    state_size: int = 0
    auto_concurrency: int = 1  # max simultaneous firings; 1 => self-loop


@dataclass
class Channel:
    name: str
    src: str                  # actor name
    dst: str                  # actor name
    prod: int = 1             # tokens produced per firing of src
    cons: int = 1             # tokens consumed per firing of dst
    initial_tokens: int = 0
    token_size: int = 0


@dataclass
class SDFGraph:
    name: str
    actors: list[Actor] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=list)

    def index(self) -> dict[str, int]:
        return {a.name: i for i, a in enumerate(self.actors)}

    def actor(self, name: str) -> Actor:
        for a in self.actors:
            if a.name == name:
                return a
        raise KeyError(f"no actor named {name!r} in graph {self.name!r}")

    # ---- consistency -----------------------------------------------------
    def repetition_vector(self) -> list[int]:
        """Smallest positive integer solution q of the balance equations.

        For every channel u->v:  q[u] * prod = q[v] * cons.

        Solved by propagation over the (weakly) connected graph using exact
        rationals, then scaled by the LCM of denominators.  Floats would lose
        exactness here on realistic rate ratios; Fraction is not optional.

        Raises ValueError with the offending channel if the graph is
        inconsistent, and if the graph is disconnected (each component would
        otherwise get an independent, arbitrary scale factor).
        """
        n = len(self.actors)
        if n == 0:
            return []
        idx = self.index()
        adj: list[list[tuple[int, Fraction, str]]] = [[] for _ in range(n)]
        for c in self.channels:
            u, v = idx[c.src], idx[c.dst]
            if c.prod <= 0 or c.cons <= 0:
                raise ValueError(f"channel {c.name!r}: rates must be positive")
            # q[v] = q[u] * prod / cons
            adj[u].append((v, Fraction(c.prod, c.cons), c.name))
            adj[v].append((u, Fraction(c.cons, c.prod), c.name))

        q: list[Fraction | None] = [None] * n
        q[0] = Fraction(1)
        stack = [0]
        while stack:
            u = stack.pop()
            for v, ratio, cname in adj[u]:
                want = q[u] * ratio
                if q[v] is None:
                    q[v] = want
                    stack.append(v)
                elif q[v] != want:
                    raise ValueError(
                        f"graph {self.name!r} is inconsistent at channel "
                        f"{cname!r}: {self.actors[u].name} implies "
                        f"q[{self.actors[v].name}]={want}, but a different "
                        f"path implies {q[v]}"
                    )
        if any(x is None for x in q):
            unreached = [self.actors[i].name for i, x in enumerate(q) if x is None]
            raise ValueError(
                f"graph {self.name!r} is disconnected; unreachable from "
                f"{self.actors[0].name!r}: {unreached}. The repetition vector "
                f"is only defined up to an independent scale factor per "
                f"component, so this must be resolved in the input."
            )
        lcm = 1
        for x in q:
            d = x.denominator                     # type: ignore[union-attr]
            lcm = lcm * d // _gcd(lcm, d)
        out = [int(x * lcm) for x in q]           # type: ignore[operator]
        g = 0
        for v in out:
            g = _gcd(g, v)
        return [v // g for v in out]


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a or 1


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------
def parse_sdf3(path: str | Path) -> SDFGraph:
    root = ET.parse(str(path)).getroot()
    sdf = root.find(".//sdf")
    if sdf is None:
        raise ValueError(f"{path}: no <sdf> element found")
    name = sdf.get("name") or Path(path).stem

    # port rates, keyed (actor, port)
    rates: dict[tuple[str, str], int] = {}
    actors: list[Actor] = []
    for a in sdf.findall("actor"):
        an = a.get("name")
        actors.append(Actor(name=an, type=a.get("type") or an))
        for p in a.findall("port"):
            rates[(an, p.get("name"))] = int(p.get("rate", "1"))

    channels: list[Channel] = []
    for c in sdf.findall("channel"):
        src, dst = c.get("srcActor"), c.get("dstActor")
        channels.append(Channel(
            name=c.get("name"),
            src=src, dst=dst,
            prod=rates.get((src, c.get("srcPort")), 1),
            cons=rates.get((dst, c.get("dstPort")), 1),
            initial_tokens=int(c.get("initialTokens", "0")),
        ))

    g = SDFGraph(name=name, actors=actors, channels=channels)

    # properties block
    props = root.find(".//sdfProperties")
    if props is not None:
        for ap in props.findall("actorProperties"):
            a = g.actor(ap.get("actor"))
            et = ap.find(".//executionTime")
            if et is not None:
                a.exec_time = int(round(float(et.get("time", "0"))))
            ss = ap.find(".//stateSize")
            if ss is not None:
                a.state_size = int(ss.get("max", "0"))
        by_name = {c.name: c for c in channels}
        for cp in props.findall("channelProperties"):
            c = by_name.get(cp.get("channel"))
            ts = cp.find("tokenSize")
            if c is not None and ts is not None:
                c.token_size = int(ts.get("sz", "0"))
    return g


# --------------------------------------------------------------------------
# WCET table
# --------------------------------------------------------------------------
class WCETTable:
    """(task_type, processor_model, mode) -> wcet.

    This is the single authoritative source of timing, including for
    pattern-introduced components (their `wcet_type` keys in here too).
    A missing (task, core type, mode) entry forbids that binding; an actor
    with no entry for any core type is a hard error naming the exact XML
    element to add -- silently substituting a scaled value is how
    unpublishable numbers happen (docs/design.md#wcet-table-and-forbidden-bindings).
    """

    def __init__(self, path: str | Path):
        self.path = str(path)
        self.table: dict[tuple[str, str, str], int] = {}
        root = ET.parse(str(path)).getroot()
        for m in root.findall("mapping"):
            tt = m.get("task_type")
            for w in m.findall("wcet"):
                key = (tt, w.get("processor", "default"), w.get("mode", "default"))
                self.table[key] = int(round(float(w.get("wcet"))))

    def types(self) -> set[str]:
        return {k[0] for k in self.table}

    def get(self, task_type: str, proc_model: str, mode: str) -> int | None:
        return self.table.get((task_type, proc_model, mode))

    def require(self, task_type: str, proc_model: str, mode: str) -> int:
        v = self.get(task_type, proc_model, mode)
        if v is None:
            raise KeyError(
                f"{self.path}: no WCET for task_type={task_type!r} on "
                f"processor={proc_model!r} mode={mode!r}. Add:\n"
                f'  <mapping task_type="{task_type}">\n'
                f'    <wcet processor="{proc_model}" mode="{mode}" wcet="..."/>\n'
                f"  </mapping>"
            )
        return v


def parse_design_constraints(path: str | Path) -> dict[str, int]:
    """app_name -> required period (-1 means unconstrained)."""
    root = ET.parse(str(path)).getroot()
    return {c.get("app_name"): int(c.get("period", "-1"))
            for c in root.findall("constraint")}
