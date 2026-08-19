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

    def template_groups(self) -> list[list[int]]:
        """FCR indices grouped by template, for card-level symmetry breaking."""
        groups: dict[str, list[int]] = {}
        for fi, _name, tmpl, _m in self.fcrs:
            groups.setdefault(tmpl, []).append(fi)
        return [v for v in groups.values() if len(v) > 1]


def parse_platform(path: str | Path) -> Platform:
    root = ET.parse(str(path)).getroot()
    templates: list[FCRTemplate] = []
    types_by_model: dict[str, CoreType] = {}

    for t in root.findall("fcr_template"):
        tmpl = FCRTemplate(name=t.get("name"),
                           max_instances=int(t.get("max_instances", "1")),
                           monetary=int(t.get("monetary", "0")))
        for p in t.findall("processor"):
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
                types_by_model[model] = ct
            tmpl.cores.append((ct, int(p.get("count", "1"))))
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

    tdma = 0
    bus = root.find(".//TDMA_bus")
    if bus is not None:
        tdma = int(bus.get("tdma_slots", "0"))

    return Platform(name=root.get("name", "platform"), templates=templates,
                    slots=slots, fcrs=fcrs,
                    core_types=list(types_by_model.values()), tdma_slots=tdma)
