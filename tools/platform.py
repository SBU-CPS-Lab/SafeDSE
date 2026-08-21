"""Platform catalogue -> flat slot array, per section C.5.

The designer declares FCR *templates* -- things you physically buy, whose cores
share power, clock and substrate and therefore fail together -- with a bound on
how many of each may be instantiated.  The front-end expands that into a flat
array of candidate core slots; the CP model then decides which cards to buy
(`fcr_used`) and which cores to populate (`used`).

This is the same guarded-superposition move used for safety patterns and for
communication refinement: enumerate every candidate statically, decide
activation in the model.

    <platform name="...">
      <fcr_template name="R-card" max_instances="3" monetary="120">
        <processor model="cortexR" count="2" max_sil="4" mem="64000"
                   partitionable="true" partition_cost="15">
          <mode name="standard" cycle="1"   dynPower="180" area="14" monetary="40"/>
          <mode name="eco"      cycle="1.3" dynPower="95"  area="14" monetary="40"/>
        </processor>
      </fcr_template>
      ...
    </platform>
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Mode:
    name: str
    cycle: float = 1.0
    dyn_power: int = 0
    area: int = 0
    monetary: int = 0


@dataclass
class CoreType:
    model: str
    max_sil: int = 0
    mem: int = 0
    partitionable: bool = False
    partition_cost: int = 0
    modes: list[Mode] = field(default_factory=list)


@dataclass
class FCRTemplate:
    name: str
    max_instances: int
    monetary: int
    cores: list[tuple[CoreType, int]] = field(default_factory=list)  # (type, count)


@dataclass
class Slot:
    """One candidate core in the expanded platform."""
    index: int
    core_type: CoreType
    fcr_index: int
    fcr_name: str
    template: str
    instance: int          # which copy of the template
    within: int            # position inside that card


@dataclass
class Platform:
    name: str
    templates: list[FCRTemplate]
    slots: list[Slot]
    fcrs: list[tuple[int, str, str, int]]   # (index, name, template, monetary)
    core_types: list[CoreType]
    tdma_slots: int = 0
    flit_size: int = 32
    cycle_length: int = 1

    def type_index(self) -> dict[str, int]:
        return {t.model: i for i, t in enumerate(self.core_types)}

    def symmetry_classes(self) -> list[list[int]]:
        """Groups of slots that are genuinely interchangeable.

        Two slots are interchangeable iff they have the same core type AND sit
        in the same card.  Cards of the same template are handled separately
        (by forcing `fcr_used` to be a prefix within a template), because
        swapping whole cards is a different symmetry from swapping cores
        inside one.  Getting this wrong is the main modelling risk C.5 flags.
        """
        groups: dict[tuple[int, str], list[int]] = {}
        for s in self.slots:
            groups.setdefault((s.fcr_index, s.core_type.model), []).append(s.index)
        return [v for v in groups.values() if len(v) > 1]

    def interchangeable_groups(self) -> list[list[int]]:
        """Slots that are interchangeable outright, so value precedence is sound.

        Cores in different cards are normally NOT interchangeable, because
        swapping two of them changes their fault containment region.  The
        exception is a card that holds exactly one core: then a core swap IS a
        whole-card swap, which is a symmetry.  This is the common case for the
        DeSyDe dialect, where every processor is its own singleton FCR, and it
        recovers most of the pruning that `seq_precede_chain(proc)` gave on a
        homogeneous platform.
        """
        size: dict[int, int] = {}
        for s in self.slots:
            size[s.fcr_index] = size.get(s.fcr_index, 0) + 1
        groups: dict[str, list[int]] = {}
        for s in self.slots:
            if size[s.fcr_index] == 1:
                groups.setdefault(s.core_type.model, []).append(s.index)
        return [sorted(v) for v in groups.values() if len(v) > 1]

    def template_groups(self) -> list[list[int]]:
        """FCR indices grouped by template, for card-level symmetry breaking."""
        groups: dict[str, list[int]] = {}
        for fi, _name, tmpl, _m in self.fcrs:
            groups.setdefault(tmpl, []).append(fi)
        return [v for v in groups.values() if len(v) > 1]


def _core_type(p: ET.Element, types_by_model: dict[str, CoreType]) -> CoreType:
    model = p.get("model")
    ct = types_by_model.get(model)
    if ct is None:
        ct = CoreType(
            model=model,
            max_sil=int(p.get("max_sil", "0")),
            mem=int(p.get("mem", "0")),
            partitionable=p.get("partitionable", "false").lower() == "true",
            partition_cost=int(p.get("partition_cost", "0")),
            modes=[Mode(name=m.get("name"),
                        cycle=float(m.get("cycle", "1")),
                        dyn_power=int(m.get("dynPower", "0")),
                        area=int(m.get("area", "0")),
                        monetary=int(m.get("monetary", "0")))
                   for m in p.findall("mode")] or [Mode("default")])
        # DeSyDe puts mem on the <mode>; SafeDSE puts it on the <processor>.
        if ct.mem == 0:
            mems = [int(m.get("mem", "0")) for m in p.findall("mode")]
            ct.mem = max(mems) if mems else 0
        types_by_model[model] = ct
    return ct


def _bus(root: ET.Element) -> dict:
    """TDMA bus parameters. flitSize is the data one slot carries."""
    bus = root.find(".//TDMA_bus")
    if bus is None:
        return {"tdma_slots": 0}
    mode = bus.find("mode")
    return {
        "tdma_slots": int(bus.get("tdma_slots", "0")),
        "flit_size": int(bus.get("flitSize", "32")),
        "cycle_length": int(mode.get("cycleLength", "1")) if mode is not None else 1,
    }


def parse_platform(path: str | Path) -> Platform:
    """Accepts two dialects.

    SafeDSE form:  <fcr_template name=".." max_instances=".." monetary="..">
                     <processor model=".." count=".." max_sil=".."/>
                   </fcr_template>

    DeSyDe/Rosvall form:  <processor model=".." number="..">  <mode .../>  </processor>

    The DeSyDe dialect has no notion of a fault containment region, so each
    processor becomes its own singleton FCR.  That is the conservative reading
    -- it never asserts independence that the input did not claim -- and it
    keeps Phase-1 results directly comparable with published DeSyDe numbers.
    Cost lands entirely on the core (per-mode `monetary`), with zero card price.
    """
    root = ET.parse(str(path)).getroot()
    if root.find("fcr_template") is None and root.find("processor") is not None:
        return _parse_desyde(root)
    templates: list[FCRTemplate] = []
    types_by_model: dict[str, CoreType] = {}

    for t in root.findall("fcr_template"):
        tmpl = FCRTemplate(name=t.get("name"),
                           max_instances=int(t.get("max_instances", "1")),
                           monetary=int(t.get("monetary", "0")))
        for p in t.findall("processor"):
            tmpl.cores.append((_core_type(p, types_by_model),
                               int(p.get("count", "1"))))
        templates.append(tmpl)

    # expand
    slots: list[Slot] = []
    fcrs: list[tuple[int, str, str, int]] = []
    for tmpl in templates:
        for inst in range(tmpl.max_instances):
            fi = len(fcrs)
            fname = f"{tmpl.name}#{inst}"
            fcrs.append((fi, fname, tmpl.name, tmpl.monetary))
            within = 0
            for ct, count in tmpl.cores:
                for _ in range(count):
                    slots.append(Slot(index=len(slots), core_type=ct,
                                      fcr_index=fi, fcr_name=fname,
                                      template=tmpl.name, instance=inst,
                                      within=within))
                    within += 1

    return Platform(name=root.get("name", "platform"), templates=templates,
                    slots=slots, fcrs=fcrs,
                    core_types=list(types_by_model.values()), **_bus(root))


def _parse_desyde(root: ET.Element) -> Platform:
    """DeSyDe dialect: a flat list of <processor model number>, one FCR each."""
    types_by_model: dict[str, CoreType] = {}
    slots: list[Slot] = []
    fcrs: list[tuple[int, str, str, int]] = []
    templates: list[FCRTemplate] = []
    for pe in root.findall("processor"):
        ct = _core_type(pe, types_by_model)
        for _ in range(int(pe.get("number", "1"))):
            fi = len(fcrs)
            fname = f"{ct.model}#{fi}"
            fcrs.append((fi, fname, ct.model, 0))     # no card-level price
            slots.append(Slot(index=len(slots), core_type=ct, fcr_index=fi,
                              fcr_name=fname, template=ct.model,
                              instance=fi, within=0))
    for m, ct in types_by_model.items():
        templates.append(FCRTemplate(name=m, max_instances=
                                     sum(1 for s in slots if s.core_type is ct),
                                     monetary=0, cores=[(ct, 1)]))
    return Platform(name=root.get("name", "platform"), templates=templates,
                    slots=slots, fcrs=fcrs,
                    core_types=list(types_by_model.values()), **_bus(root))
