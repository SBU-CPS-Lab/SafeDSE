#!/usr/bin/env python3
"""Generate a GSN safety argument from a solved SafeDSE instance.

    gsn.py --dzn out/f_random_hw.dzn --solution sol.json --out out/f_random_hw

Emits <prefix>.gsn.json, <prefix>.gsn.dot and <prefix>.gsn.md.

WHAT THIS IS
------------
Preschern, Kajtazovic & Kreiner (EuroPLoP'15) attach a GSN diagram to each
safety architecture pattern: a top goal of maintaining system safety, split
into subgoals that are the pattern's general scenarios, with the tactics that
achieve a scenario sitting under it as GSN strategies, and the tactics finally
replaced by the IEC 61508 methods actually used.  Everything left over is an
undeveloped goal for the architect.

Their diagrams are per pattern and generic.  This tool instantiates them
against a CONCRETE solved mapping, which is the only thing that makes them
checkable.  A pattern's GSN says "the replicated components are independent";
whether they are depends entirely on where the components were placed, and that
is what the DSE decided and what tools/verify.py independently re-checks.

THE RULE THIS FILE ENFORCES
---------------------------
Every leaf of the argument is either

  (a) a Solution backed by a check that actually ran in a specific verifier
      invocation, cited by index into that run's report, or
  (b) a Goal explicitly marked undeveloped.

There is no third kind.  A leaf that asserts something nobody checked is the
exact failure this project exists to prevent -- it is the safety-argument
analogue of a plausible period from a silently wrong constraint -- so
`audit()` refuses to emit an argument containing one.

WHAT IT CANNOT DISCHARGE, AND SAYS SO
-------------------------------------
Detection power, voting correctness, design independence and development
process are all value-domain or process claims.  A mapping says nothing about
them and the corresponding tactics carry `deployment_relations: []` in
data/gsn_tactics.yaml, so their goals come out as diamonds.  The generator's
headline number -- goals discharged versus goals left undeveloped -- is the
honest statement of how much of a safety case a DSE can actually produce.  It
is not most of one.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify import parse_dzn  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RELN = {1: "SAME", 2: "DIFFERENT", 3: "DIFFERENT_FCR", 4: "DIVERSE"}
FAULT_MODELS = {
    "random_hw": {"random_hw"},
    "systematic_sw": {"systematic_sw"},
    "both": {"random_hw", "systematic_sw"},
}


# ---------------------------------------------------------------------------
# GSN element model (GSN Community Standard v3 core elements)
# ---------------------------------------------------------------------------
@dataclass
class Element:
    id: str
    kind: str            # Goal | Strategy | Solution | Context | Assumption
                         # | Justification
    text: str
    undeveloped: bool = False
    supported_by: list[str] = field(default_factory=list)
    in_context_of: list[str] = field(default_factory=list)
    evidence: list[int] = field(default_factory=list)   # indices into report
    note: str = ""


class Argument:
    def __init__(self) -> None:
        self.el: dict[str, Element] = {}
        self.order: list[str] = []
        self._n: dict[str, int] = {}
        self.warnings: list[str] = []
        self.out_of_scope: list[str] = []

    def add(self, kind: str, text: str, **kw) -> str:
        prefix = {"Goal": "G", "Strategy": "S", "Solution": "Sn",
                  "Context": "C", "Assumption": "A", "Justification": "J"}[kind]
        self._n[prefix] = self._n.get(prefix, 0) + 1
        eid = f"{prefix}{self._n[prefix]}"
        self.el[eid] = Element(id=eid, kind=kind, text=" ".join(text.split()),
                               **kw)
        self.order.append(eid)
        return eid

    def support(self, parent: str, *children: str) -> None:
        for c in children:
            if c not in self.el[parent].supported_by:
                self.el[parent].supported_by.append(c)

    def context(self, parent: str, *children: str) -> None:
        for c in children:
            if c not in self.el[parent].in_context_of:
                self.el[parent].in_context_of.append(c)

    # -- the self-audit ----------------------------------------------------
    def audit(self) -> list[str]:
        """Every leaf is evidence or an admitted gap.  Nothing else."""
        bad: list[str] = []
        for e in self.el.values():
            if e.kind == "Goal" and not e.supported_by and not e.undeveloped:
                bad.append(f"{e.id} is a leaf Goal with neither supporting "
                           f"evidence nor an undeveloped marker: {e.text[:70]}")
            if e.kind == "Strategy" and not e.supported_by:
                bad.append(f"{e.id} is a Strategy that develops nothing")
            if e.kind == "Solution" and not e.evidence:
                bad.append(f"{e.id} is a Solution citing no verifier check: "
                           f"{e.text[:70]}")
            if e.undeveloped and e.supported_by:
                bad.append(f"{e.id} is marked undeveloped but has children")
        return bad

    def stats(self) -> dict:
        goals = [e for e in self.el.values() if e.kind == "Goal"]
        return {
            "elements": len(self.el),
            "goals": len(goals),
            "goals_undeveloped": sum(1 for g in goals if g.undeveloped),
            "solutions": sum(1 for e in self.el.values()
                             if e.kind == "Solution"),
            "assumptions": sum(1 for e in self.el.values()
                               if e.kind == "Assumption"),
        }


# ---------------------------------------------------------------------------
# instance reading
# ---------------------------------------------------------------------------
def _l(x):
    return x if isinstance(x, list) else [x]


def _grid(flat, ncol):
    flat = _l(flat)
    if flat and isinstance(flat[0], list):
        return flat
    return [flat[r * ncol:(r + 1) * ncol] for r in range(len(flat) // ncol)]


def infer_fault_model(d: dict, pats: list) -> tuple[str | None, str]:
    """Recover the fault model that produced this .dzn.

    The fault model is applied in the FRONT END -- it filters which patterns are
    admissible per actor (tools/patterns.py:195) and drops placement relations
    whose `for:` names a fault we are not defending against (line 269) -- and
    then it is gone.  Nothing in the .dzn records it.

    But it is recoverable: `pat_allowed` is a function of the fault model and
    the per-actor SIL requirement, both of which the .dzn does carry.  So try
    all three and keep the ones that reproduce `pat_allowed` exactly.

    Inferring beats a --fault-model flag because a wrong flag would not fail --
    it would produce a fluent argument claiming coverage of a fault class the
    design never defended against, which is the worst output this tool could
    have.  If the inference is ambiguous or empty, the caller must refuse.
    """
    npat = d.get("nPat", 0)
    if not npat or npat == 1:
        return None, "instance carries no pattern catalogue"
    names = _l(d["pat_name"])
    allowed = _grid(d["pat_allowed"], npat)
    sreq = _l(d["sil_req_parent"])
    pnames = _l(d["parent_name"])
    by_id = {p.id: p for p in pats}
    if set(names) - set(by_id):
        return None, f"catalogue mismatch: {sorted(set(names) - set(by_id))}"

    fits = []
    for fm, faults in FAULT_MODELS.items():
        ok = True
        for k, lbl in enumerate(pnames):
            appn, bare = lbl.split(".", 1)
            if appn == "__comm" or "~" in bare:
                continue                      # not a base SDF actor
            need = sreq[k]
            want = {names[j] for j in range(npat)
                    if need in by_id[names[j]].achieves_sil
                    and faults <= set(by_id[names[j]].covers_faults)}
            got = {names[j] for j in range(npat) if allowed[k][j]}
            if want != got:
                ok = False
                break
        if ok:
            fits.append(fm)
    if len(fits) == 1:
        return fits[0], "inferred from pat_allowed"
    if not fits:
        return None, "no fault model reproduces pat_allowed"
    return None, f"ambiguous between {fits} (this instance does not " \
                 f"distinguish them)"


# ---------------------------------------------------------------------------
def build(d: dict, sol: dict, report: dict, pats: list, tactics: dict,
          fault_model: str | None, label: str) -> Argument:
    a = Argument()
    by_id = {p.id: p for p in pats}
    n = d["nActors"] if "nActors" in d else len(_l(d["node_name"]))
    node_name = _l(d["node_name"])
    parent_name = _l(d["parent_name"])
    parent = _l(d["parent"])
    sreq = _l(d["sil_req_parent"])
    proc = _l(sol["proc"])
    act = _l(sol.get("active", [True] * n))
    csil = _l(sol.get("csil", []))
    sil_impl = _l(sol.get("sil_impl", []))
    core_model = _l(d.get("core_model", []))
    ctype = _l(d.get("ctype", []))
    fcr = _l(d.get("fcr", []))
    comm_flags = _l(d.get("comm_actor", [False] * n))
    npat = d.get("nPat", 0)
    pat = _l(sol.get("pat", [])) if npat else []
    pat_name = _l(d.get("pat_name", [])) if npat else []
    checks = report["checks"]

    # index the verifier's records so a Solution can cite them by position
    def find(kind, **match) -> list[int]:
        out = []
        for i, c in enumerate(checks):
            if c["kind"] != kind:
                continue
            if all(c.get(k) == v for k, v in match.items()):
                out.append(i)
        return out

    def who(i: int) -> str:
        """Node index -> a name a safety engineer can act on.

        The verifier records placement relations by node INDEX, which is the
        right thing for a machine and useless in an argument: "DIFFERENT_FCR
        between nodes 1 and 8" tells a reviewer nothing about which component
        of which pattern is being separated from what. Resolve to the HSDF node
        name, and where the node is a pattern component slot, name the role it
        fills in the selected pattern.
        """
        nm = node_name[i - 1] if 0 < i <= len(node_name) else f"node {i}"
        appn, bare = nm.split(".", 1) if "." in nm else ("", nm)
        if "~" in bare:
            owner, _, k = bare.partition("~")
            pk = next((j for j, lbl in enumerate(parent_name)
                       if lbl == f"{appn}.{owner}"), None)
            if pk is not None and npat and pk < len(pat):
                p = by_id.get(pat_name[pat[pk] - 1])
                try:
                    role = p.components[int(k)]["role"]
                    return f"{owner}/{role}"
                except (AttributeError, IndexError, ValueError):
                    pass
            return f"{owner}/slot {k}"
        return bare

    def evidence_text(c: dict) -> str:
        if c["kind"] != "placement":
            return c["detail"]
        return (f"{c['relation']} between {who(c['u'])} and {who(c['v'])}: "
                f"cores {c['cores'][0]}/{c['cores'][1]}, fault containment "
                f"regions {c['fcrs'][0]}/{c['fcrs'][1]}, core types "
                f"{core_model[c['ctypes'][0]-1]}/"
                f"{core_model[c['ctypes'][1]-1]}")

    # ---- context, assumptions, justification -----------------------------
    c_std = a.add("Context", "IEC 61508 is the governing functional safety "
                             "standard; integrity is allocated as a Safety "
                             "Integrity Level per actor (Q1, Q13).")
    ncores = len(csil) or len(ctype)
    nfcr = len(set(fcr)) if fcr else 0
    c_plat = a.add("Context",
                   f"Platform: {ncores} core slots across {nfcr} fault "
                   f"containment regions, core types "
                   f"{', '.join(sorted(set(core_model))) or 'unspecified'}. "
                   f"Cores actually instantiated in this solution: "
                   f"{sorted({proc[i] for i in range(n) if act[i]})}.")
    apps = sorted({lbl.split('.', 1)[0] for lbl in parent_name
                   if not lbl.startswith('__comm')})
    c_app = a.add("Context",
                  f"Applications: {', '.join(apps)}, modelled as synchronous "
                  f"dataflow graphs and unfolded to an equivalent homogeneous "
                  f"graph before mapping.")
    fm_txt = {"random_hw": "random hardware faults",
              "systematic_sw": "systematic software faults",
              "both": "random hardware faults and systematic software faults"}
    c_fm = a.add("Context",
                 f"Fault model under consideration: "
                 f"{fm_txt.get(fault_model, 'UNDETERMINED')} (Q2). "
                 f"Patterns not covering this fault class were excluded from "
                 f"the design space, and placement relations motivated only by "
                 f"an excluded fault class were not posted.")
    j_scope = a.add(
        "Justification",
        "This argument is generated from a design space exploration result. It "
        "argues only over properties of the ARCHITECTURE and its DEPLOYMENT: "
        "which pattern is applied to which actor, where components are placed "
        "relative to each other, how integrity levels are provisioned per core, "
        "and whether the resulting schedule meets its timing requirement. "
        "Claims about implementation correctness, detection coverage and "
        "development process are outside what a mapping can establish and are "
        "carried below as undeveloped goals.")
    a_wcet = a.add(
        "Assumption",
        "The worst-case execution times supplied to the exploration are sound "
        "upper bounds for every actor on every core type it may be bound to. "
        "The exploration consumes these figures; it does not establish them.")
    a_token = a.add(
        "Assumption",
        "Token preservation (Q4): every replica fires on every iteration and "
        "produces on all of its outputs, in the fault-free and in the degraded "
        "case alike. Detection marks a token invalid; it never withholds one. "
        "The timing argument therefore holds in the degraded mode, at the cost "
        "of being conservative when no fault is present.")

    top = a.add("Goal",
                f"The deployed architecture of {label} preserves the allocated "
                f"safety integrity of every safety-related actor.")
    a.context(top, c_std, c_app, c_plat, c_fm, j_scope, a_wcet, a_token)

    if any(comm_flags) and d.get("comm_sil_mode", 0) == 0:
        a_comm = a.add(
            "Assumption",
            "Inter-processor transfers are not safety functions and carry no "
            "integrity requirement of their own (Q21, --comm-sil exempt). If "
            "the interconnect can corrupt or lose a token, this assumption "
            "does not hold and the argument must be regenerated with "
            "--comm-sil inherit or core.")
        a.context(top, a_comm)

    strat = a.add("Strategy",
                  "Argument over each safety-related actor in turn, followed by "
                  "the platform-wide properties on which those per-actor "
                  "arguments depend.")
    a.support(top, strat)

    # ---- per-actor arguments ---------------------------------------------
    base = [(k, lbl) for k, lbl in enumerate(parent_name)
            if not lbl.startswith("__comm") and "~" not in lbl.split(".", 1)[1]]
    consumed: set[int] = set()          # placement record indices used
    out_of_scope: list[str] = []        # scenarios the fault model excludes

    n_actors = 0
    for k, lbl in base:
        need = sreq[k]
        if need < 1:
            continue                    # not safety-related
        n_actors += 1
        appn, aname = lbl.split(".", 1)
        copies = [i for i in range(n) if parent[i] == k + 1]
        cores = sorted({proc[i] for i in copies if act[i]})
        impl = sorted({sil_impl[i] for i in copies if act[i]}) if sil_impl else []
        pid = pat_name[pat[k] - 1] if npat and k < len(pat) else "none"
        p = by_id.get(pid)

        g_a = a.add("Goal",
                    f"Actor {aname} of application {appn}, allocated SIL "
                    f"{need}, attains SIL {need} in the deployed architecture.")
        a.support(strat, g_a)
        c_a = a.add("Context",
                    f"{aname} is unfolded into {len(copies)} concurrent "
                    f"{'copy' if len(copies) == 1 else 'copies'}, bound to core "
                    f"{cores if len(cores) != 1 else cores[0]}, implemented at "
                    f"SIL {impl[0] if len(impl) == 1 else impl}.")
        a.context(g_a, c_a)

        # the SIL provisioning of the owner's own copies
        ev = [j for i in copies if act[i] for j in find("sil_actor", node=i + 1)]
        if ev:
            sn = a.add("Solution",
                       f"Independent re-check of the solution: every active "
                       f"copy of {aname} is implemented at or above its "
                       f"allocated SIL and runs on a core provisioned to at "
                       f"least that level.",
                       evidence=ev)
            g_prov = a.add("Goal",
                           f"Every copy of {aname} is implemented at SIL "
                           f"{need} or above and is not hosted on a core "
                           f"provisioned below that level.")
            a.support(g_a, g_prov)
            a.support(g_prov, sn)

        if p is None or pid == "none":
            s_a = a.add("Strategy",
                        "Argument by development process alone: no structural "
                        "safety pattern is applied.")
            a.support(g_a, s_a)
            c_none = a.add(
                "Context",
                "IEC 61508 expects diagnostic coverage from SIL 2 upward, so "
                "process alone is admissible only to SIL 1 (Q20). The "
                "exploration enforced this ceiling when choosing the pattern.")
            a.context(s_a, c_none)
            g_proc = a.add("Goal",
                           f"{aname} is developed and verified to SIL {need} in "
                           f"accordance with IEC 61508-3.",
                           undeveloped=True,
                           note="process evidence; outside the DSE")
            a.support(s_a, g_proc)
            continue

        # Where the pattern's own components went. Without this the reader
        # meets "checker" for the first time inside a placement citation and
        # has no way to tell what it is or whether it was even instantiated.
        if p is not None and p.components:
            parts = []
            for ci, comp in enumerate(p.components):
                pk = next((j for j, lbl in enumerate(parent_name)
                           if lbl == f"{appn}.{aname}~{ci}"), None)
                if pk is None:
                    continue
                cn = [i for i in range(n)
                      if parent[i] == pk + 1 and act[i]]
                if not cn:
                    parts.append(f"{comp['role']} (not instantiated)")
                    continue
                cc = sorted({proc[i] for i in cn})
                cs = sorted({sil_impl[i] for i in cn}) if sil_impl else []
                parts.append(
                    f"{comp['role']} on core "
                    f"{cc[0] if len(cc) == 1 else cc}"
                    + (f" at SIL {cs[0] if len(cs) == 1 else cs}" if cs else ""))
            if parts:
                c_comp = a.add(
                    "Context",
                    f"Components introduced by {pid} for {aname}: "
                    + "; ".join(parts) + ".")
                a.context(g_a, c_comp)

        # ---- a structural pattern was applied ----------------------------
        s_a = a.add("Strategy",
                    f"Argument by application of the {pid} safety architecture "
                    f"pattern, over each of its general scenarios.")
        a.support(g_a, s_a)
        src = ", ".join(str(x) for x in (p.source or []))
        c_p = a.add("Context",
                    f"Pattern {pid} [{src}]: {' '.join(p.description.split())} "
                    f"Attainable SIL {p.achieves_sil}; covers "
                    f"{', '.join(p.covers_faults)}; fails {p.failure_mode}; "
                    f"voter {p.voter}.")
        a.context(s_a, c_p)

        # admissibility is a data check, not a mapping check, but it is a
        # check: it is what stops a pattern being credited with a fault class
        # it does not cover.
        faults = FAULT_MODELS.get(fault_model or "", set())
        adm = need in p.achieves_sil and faults <= set(p.covers_faults)
        if not adm:
            a.warnings.append(
                f"{aname}: pattern {pid} was selected but does not admit SIL "
                f"{need} under fault model {fault_model}; the argument below "
                f"overclaims")

        for sc in p.scenarios:
            # A scenario addressing a fault class outside the selected model is
            # not a defect and not a claim: the front end never posted the
            # relations that would enforce it, so this deployment does not
            # provide it even though the pattern could. Saying so explicitly
            # matters -- a reader who knows a 2-of-2 covers systematic faults
            # would otherwise assume this one does.
            cov = sc.get("covers")
            if cov and fault_model and cov not in FAULT_MODELS[fault_model]:
                g_out = a.add(
                    "Goal",
                    f"{sc['text']} [{pid}/{sc['id']}] -- OUT OF SCOPE: this "
                    f"scenario addresses {cov}, which the selected fault model "
                    f"({fault_model}) excludes. The pattern can support it, but "
                    f"the relations that would enforce it were not posted, so "
                    f"this deployment does not provide it.",
                    undeveloped=True,
                    note=f"out of scope under fault model {fault_model}")
                a.support(s_a, g_out)
                out_of_scope.append(f"{aname}/{pid}/{sc['id']} ({cov})")
                continue
            g_sc = a.add("Goal", f"{sc['text']} [{pid}/{sc['id']}]")
            a.support(s_a, g_sc)
            for tname in sc.get("tactics", []):
                t = tactics.get(tname)
                if t is None:
                    a.warnings.append(
                        f"{pid}/{sc['id']} invokes tactic {tname!r}, absent "
                        f"from data/gsn_tactics.yaml")
                    continue
                s_t = a.add("Strategy",
                            f"Achieved through the {tname} tactic "
                            f"({t.get('category','')}): "
                            f"{' '.join(str(t.get('aim','')).split())}")
                a.support(g_sc, s_t)
                c_t = a.add("Context",
                            f"{tname}: "
                            f"{' '.join(str(t.get('description','')).split())}")
                a.context(s_t, c_t)

                # (i) the deployment precondition, where the tactic has one
                rels = t.get("deployment_relations") or []
                if rels:
                    hits = [j for j in range(len(checks))
                            if checks[j]["kind"] == "placement"
                            and checks[j].get("owner") == k + 1
                            and checks[j].get("relation") in rels]
                    if hits:
                        consumed.update(hits)
                        g_dep = a.add(
                            "Goal",
                            f"In the deployed mapping, "
                            f"{' '.join(str(t['relation_claim']).split())}.")
                        a.support(s_t, g_dep)
                        for j in hits:
                            c = checks[j]
                            sn = a.add(
                                "Solution",
                                f"Independent re-check of the solution: "
                                f"{evidence_text(c)}.",
                                evidence=[j])
                            a.support(g_dep, sn)
                        if t.get("relation_caveat"):
                            a_cav = a.add(
                                "Assumption",
                                f"{' '.join(str(t['relation_caveat']).split())} "
                                f"The mapping evidence below establishes the "
                                f"deployment property only.")
                            a.context(g_dep, a_cav)
                    else:
                        # The tactic claims a deployment precondition and the
                        # instance posts none.  Usually this means the relation
                        # was dropped at build time because its `for:` names a
                        # fault class outside the selected model -- so the
                        # tactic is NOT realised here and the scenario must not
                        # be credited to it.
                        a.warnings.append(
                            f"{aname}/{pid}/{sc['id']}: tactic {tname} requires "
                            f"one of {rels} but no such relation is posted for "
                            f"this actor under fault model {fault_model}; the "
                            f"tactic is not realised in this deployment")
                        g_dep = a.add(
                            "Goal",
                            f"{' '.join(str(t['relation_claim']).split())} "
                            f"-- NOT ESTABLISHED: no such placement relation is "
                            f"posted for {aname} under fault model "
                            f"{fault_model}.",
                            undeveloped=True,
                            note="tactic unrealised in this deployment")
                        a.support(s_t, g_dep)

                # (ii) the part of the tactic that lives in the value domain
                meths = t.get("iec61508_methods") or []
                c_m = a.add("Context",
                            "Candidate methods from the standard: "
                            + "; ".join(meths) if meths else "No method listed.")
                g_m = a.add(
                    "Goal",
                    f"An IEC 61508 method realising {tname} is implemented in "
                    f"{aname}, and its effectiveness for the faults of concern "
                    f"is demonstrated.",
                    undeveloped=True,
                    note="value-domain / implementation evidence; the mapping "
                         "cannot establish this")
                a.context(g_m, c_m)
                a.support(s_t, g_m)

    # ---- placement relations no tactic claimed ---------------------------
    # A relation that no tactic consumed is still a constraint the design was
    # required to satisfy.  Dropping it silently would let the argument look
    # tidier than the design is, so it is surfaced with its own goal.
    left = [j for j in range(len(checks))
            if checks[j]["kind"] == "placement" and j not in consumed]
    if left:
        g_rest = a.add(
            "Goal",
            "The remaining placement constraints imposed by the selected "
            "patterns are satisfied by the deployment.")
        a.support(strat, g_rest)
        c_rest = a.add(
            "Context",
            "These relations constrain the mapping but are not the deployment "
            "precondition of any tactic. A SAME relation in particular confers "
            "no fault independence: it co-locates components, and the pattern "
            "that uses it claims coverage of systematic faults only.")
        a.context(g_rest, c_rest)
        for j in left:
            sn = a.add("Solution",
                       f"Independent re-check of the solution: "
                       f"{evidence_text(checks[j])}.",
                       evidence=[j])
            a.support(g_rest, sn)

    # ---- platform-wide: isolation ----------------------------------------
    iso = find("isolation")
    if iso:
        g_iso = a.add(
            "Goal",
            "No core hosts software of differing integrity without certified "
            "partitioning, and every core is provisioned to at least the "
            "highest integrity level it hosts.")
        a.support(strat, g_iso)
        c_iso = a.add(
            "Context",
            "Koopman's rule 2: absent certified partitioning, all software on "
            "a processor must be developed to the highest integrity level "
            "present on it. Whether a core type can provide such partitioning "
            "is declared per core type by the platform (Q18).")
        a.context(g_iso, c_iso)
        s_iso = a.add(
            "Strategy",
            "Achieved through the Barrier tactic (Isolation): protect a "
            "subsystem from influences of other subsystems.")
        a.support(g_iso, s_iso)
        sn_iso = a.add(
            "Solution",
            f"Independent re-check of the solution: all {len(iso)} core slots "
            f"re-examined against their type ceiling and against the set of "
            f"integrity levels actually hosted.",
            evidence=iso)
        a.support(s_iso, sn_iso)
        parted = [checks[j]["core"] for j in iso if checks[j].get("partitioned")]
        if parted:
            g_part = a.add(
                "Goal",
                f"The partitioning mechanism on core(s) {parted} is certified "
                f"to the integrity level of the highest-SIL software it "
                f"separates.",
                undeveloped=True,
                note="certification evidence for the separation mechanism")
            a.support(s_iso, g_part)

    # ---- platform-wide: timing -------------------------------------------
    per = find("period")
    lb = find("load_bound")
    if per or lb:
        g_t = a.add(
            "Goal",
            "The deployed mapping and static order meet the declared timing "
            "requirements, in the fault-free and in the degraded case alike.")
        a.support(strat, g_t)
        mus = _l(sol["mu"])
        c_t = a.add("Context",
                    f"Iteration period per application: {mus}. Timing is a "
                    f"safety property here because a replica that misses its "
                    f"deadline cannot perform the check the pattern credits it "
                    f"with.")
        a.context(g_t, c_t)
        a.context(g_t, a_wcet, a_token)
        if per:
            sn_p = a.add(
                "Solution",
                "Independent re-check of the solution: the mapping-and-"
                "schedule-aware graph was rebuilt from the returned assignment "
                "and its period computed twice by disjoint methods -- Karp's "
                "maximum cycle ratio and max-plus self-timed simulation -- both "
                "agreeing with the period the solver reported.",
                evidence=per)
            a.support(g_t, sn_p)
        if lb:
            sn_l = a.add(
                "Solution",
                "Independent re-check of the solution: the reported period is "
                "at least the total execution demand of the busiest core, the "
                "bound that a static order left open as a chain silently "
                "loses.",
                evidence=lb)
            a.support(g_t, sn_l)

    # ---- platform-wide: process ------------------------------------------
    g_dev = a.add(
        "Goal",
        "Every software component is developed, verified and validated to its "
        "allocated safety integrity level in accordance with IEC 61508-3.",
        undeveloped=True,
        note="process evidence; the DSE prices this effort but cannot supply it")
    a.support(strat, g_dev)
    if sil_impl:
        dist: dict[int, int] = {}
        for i in range(n):
            if act[i] and not (i < len(comm_flags) and comm_flags[i]):
                dist[sil_impl[i]] = dist.get(sil_impl[i], 0) + 1
        c_dev = a.add(
            "Context",
            "Integrity levels to be discharged by process, as active component "
            "counts: "
            + ", ".join(f"SIL {s}: {c}" for s, c in sorted(dist.items()))
            + ". Components implemented above their allocated level were "
              "promoted to satisfy Koopman's rule 2; the cost of that "
              "promotion is what the exploration minimised.")
        a.context(g_dev, c_dev)

    if n_actors == 0:
        a.warnings.append("no actor in this instance carries a SIL requirement "
                          "above 0; the argument has no per-actor branch")
    a.out_of_scope = out_of_scope
    return a


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def to_json(a: Argument, meta: dict) -> str:
    return json.dumps({
        "format": "GSN/1",
        "meta": meta,
        "stats": a.stats(),
        "warnings": a.warnings,
        "outOfScope": a.out_of_scope,
        "elements": [
            {"id": e.id, "kind": e.kind, "text": e.text,
             "undeveloped": e.undeveloped, "supportedBy": e.supported_by,
             "inContextOf": e.in_context_of, "evidence": e.evidence,
             "note": e.note}
            for e in (a.el[i] for i in a.order)],
    }, indent=1)


def _wrap(s: str, w: int = 42) -> str:
    words, line, out = s.split(), "", []
    for x in words:
        if len(line) + len(x) + 1 > w:
            out.append(line)
            line = x
        else:
            line = f"{line} {x}".strip()
    out.append(line)
    return "\\n".join(o.replace('"', "'") for o in out)


SHAPE = {
    "Goal": 'shape=box',
    "Strategy": 'shape=parallelogram',
    "Solution": 'shape=circle',
    "Context": 'shape=box style="rounded,filled" fillcolor="#f0f0f0"',
    "Assumption": 'shape=ellipse style=filled fillcolor="#fff6d5"',
    "Justification": 'shape=ellipse style=filled fillcolor="#fff6d5"',
}


def to_dot(a: Argument, title: str) -> str:
    L = [f'digraph GSN {{', '  rankdir=TB;',
         '  node [fontname="Helvetica" fontsize=9];',
         '  edge [fontname="Helvetica" fontsize=8];',
         f'  labelloc="t"; label="{title}"; fontname="Helvetica";']
    for eid in a.order:
        e = a.el[eid]
        sh = SHAPE[e.kind]
        tag = {"Assumption": " (A)", "Justification": " (J)"}.get(e.kind, "")
        mark = "  <>UNDEVELOPED" if e.undeveloped else ""
        if e.undeveloped:
            sh += ' style=dashed color="#b00020"'
        lbl = f"{e.id}{tag}\\n{_wrap(e.text)}{mark}"
        L.append(f'  {e.id} [{sh} label="{lbl}"];')
    for eid in a.order:
        e = a.el[eid]
        for c in e.supported_by:
            L.append(f'  {e.id} -> {c} [arrowhead=normal];')
        for c in e.in_context_of:
            L.append(f'  {e.id} -> {c} [arrowhead=onormal style=solid];')
    L.append("}")
    return "\n".join(L)


def to_md(a: Argument, meta: dict, report: dict) -> str:
    st = a.stats()
    out = [f"# Safety argument — {meta['label']}", "",
           "Generated by `tools/gsn.py` from a solved SafeDSE instance.",
           "Structure follows Preschern, Kajtazovic & Kreiner, *Building a "
           "Safety Architecture Pattern System*, EuroPLoP 2015 §4.3.", ""]
    out += ["| | |", "|---|---|",
            f"| instance | `{meta['dzn']}` |",
            f"| fault model | {meta['fault_model']} ({meta['fault_model_how']}) |",
            f"| verifier verdict | **{'PASS' if report['ok'] else 'FAIL'}** |",
            f"| verifier checks cited | {st['solutions']} solutions over "
            f"{len(report['checks'])} recorded checks |",
            f"| goals | {st['goals']} |",
            f"| of which undeveloped | **{st['goals_undeveloped']}** |", ""]
    out += ["## What this argument does and does not establish", "",
            f"{st['goals'] - st['goals_undeveloped']} of {st['goals']} goals "
            f"are discharged by evidence from an independent re-check of the "
            f"solution. The remaining {st['goals_undeveloped']} are marked "
            f"undeveloped and are the architect's to discharge: they concern "
            f"detection power, implementation correctness, certification of "
            f"separation mechanisms, and development process. A design space "
            f"exploration can decide where components go; it cannot decide "
            f"whether a checker checks.", ""]
    if a.out_of_scope:
        out += ["## Scenarios the fault model puts out of scope", "",
                f"The selected patterns state {len(a.out_of_scope)} scenarios "
                f"that this deployment does not provide, because they address "
                f"a fault class outside the fault model. The pattern is "
                f"capable of them; the design was not asked for them, so the "
                f"relations enforcing them were never posted. Widening the "
                f"fault model would re-post those relations and, in general, "
                f"change the optimal architecture.", ""]
        out += [f"- {s}" for s in a.out_of_scope] + [""]
    if a.warnings:
        out += ["## Warnings", ""]
        out += [f"- {w}" for w in a.warnings] + [""]

    seen: set[str] = set()

    def walk(eid: str, depth: int) -> None:
        if eid in seen:
            out.append(f"{'  ' * depth}- ({eid}, see above)")
            return
        seen.add(eid)
        e = a.el[eid]
        tag = {"Goal": "**Goal**", "Strategy": "*Strategy*",
               "Solution": "Solution", "Context": "Context",
               "Assumption": "Assumption",
               "Justification": "Justification"}[e.kind]
        mark = "  ◇ **UNDEVELOPED**" if e.undeveloped else ""
        cite = ""
        if e.evidence:
            cite = f"  `[checks {','.join(str(i) for i in e.evidence)}]`"
        out.append(f"{'  ' * depth}- **{e.id}** {tag}: {e.text}{cite}{mark}")
        for c in e.in_context_of:
            walk(c, depth + 1)
        for c in e.supported_by:
            walk(c, depth + 1)

    out += ["## Argument", ""]
    roots = [i for i in a.order
             if not any(i in a.el[j].supported_by or i in a.el[j].in_context_of
                        for j in a.order)]
    for r in roots:
        walk(r, 0)
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dzn", required=True)
    ap.add_argument("--solution", required=True)
    ap.add_argument("--out", required=True, help="output path prefix")
    ap.add_argument("--patterns", default=str(ROOT / "data" / "patterns.yaml"))
    ap.add_argument("--tactics", default=str(ROOT / "data" / "gsn_tactics.yaml"))
    ap.add_argument("--report", help="reuse an existing verify.py --json-report "
                                     "instead of running the verifier")
    ap.add_argument("--fault-model", choices=sorted(FAULT_MODELS),
                    help="override the inferred fault model (checked against "
                         "the inference; a mismatch is an error)")
    ap.add_argument("--allow-unverified", action="store_true",
                    help="emit even though the verifier rejected the solution")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    sys.path.insert(0, str(ROOT / "tools"))
    from patterns import load_patterns  # noqa: E402

    d = parse_dzn(a.dzn)
    sol = json.loads(Path(a.solution).read_text())
    pats = load_patterns(a.patterns)
    tdoc = yaml.safe_load(Path(a.tactics).read_text())
    tactics = {t["name"]: t for t in tdoc["tactics"]}

    # ---- evidence: run the verifier unless a report was supplied ---------
    if a.report:
        report = json.loads(Path(a.report).read_text())
    else:
        rp = f"{a.out}.verify.json"
        subprocess.run([sys.executable, str(ROOT / "tools" / "verify.py"),
                        "--dzn", a.dzn, "--solution", a.solution, "--quiet",
                        "--json-report", rp], check=False)
        report = json.loads(Path(rp).read_text())

    if not report["ok"] and not a.allow_unverified:
        print("REFUSING to generate: the independent verifier rejected this "
              "solution. An argument built on a solution that fails its own "
              "checks is worse than no argument. Re-run with "
              "--allow-unverified only to inspect the failure.", file=sys.stderr)
        for m in report["messages"]:
            print(f"  {m}", file=sys.stderr)
        return 2

    fm, how = infer_fault_model(d, pats)
    if a.fault_model:
        if fm and fm != a.fault_model:
            print(f"ERROR: --fault-model {a.fault_model} contradicts the "
                  f"instance, which {how} as {fm}", file=sys.stderr)
            return 2
        fm, how = a.fault_model, "supplied on the command line"

    label = Path(a.dzn).stem
    arg = build(d, sol, report, pats, tactics, fm, label)

    bad = arg.audit()
    if bad:
        print("REFUSING to generate: the argument contains leaves that are "
              "neither evidence nor admitted gaps.", file=sys.stderr)
        for b in bad:
            print(f"  {b}", file=sys.stderr)
        return 3

    meta = {"label": label, "dzn": a.dzn, "solution": a.solution,
            "fault_model": fm or "undetermined", "fault_model_how": how,
            "verifier_ok": report["ok"]}
    Path(f"{a.out}.gsn.json").write_text(to_json(arg, meta))
    Path(f"{a.out}.gsn.dot").write_text(to_dot(arg, f"SafeDSE safety argument "
                                                    f"— {label}"))
    Path(f"{a.out}.gsn.md").write_text(to_md(arg, meta, report))

    if not a.quiet:
        st = arg.stats()
        print(f"  fault model: {fm} ({how})")
        print(f"  {st['elements']} GSN elements, {st['goals']} goals, "
              f"{st['goals_undeveloped']} undeveloped, "
              f"{st['solutions']} solutions citing "
              f"{len(report['checks'])} verifier checks")
        if arg.out_of_scope:
            print(f"  {len(arg.out_of_scope)} scenario(s) out of scope under "
                  f"fault model {fm}: {', '.join(arg.out_of_scope)}")
        for w in arg.warnings:
            print(f"  WARNING: {w}")
        print(f"  wrote {a.out}.gsn.{{json,dot,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
