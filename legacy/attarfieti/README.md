# Todaes17+f.mzn file from line #148


## 📘 Overview

In safety-critical systems (e.g., aerospace, automotive, industrial control), different nodes require varying levels of fault tolerance depending on their SIL rating. This MiniZinc model:

- Assigns redundancy patterns to each node.
- Tracks cumulative redundant actors.
- Modifies the original system graph to include added redundants.
- Ensures structural and communication constraints are satisfied.

---

## 🧠 Redundancy Patterns

Each node is assigned one of the following redundancy patterns (represented by the `pattern_using[i]` variable):

| Code | Pattern Name                      | Description                                 |
|------|----------------------------------|---------------------------------------------|
| 0    | No Pattern                        | No redundancy applied                       |
| 1    | Mixed SIL – Fail Silent          | 2 checkers with cross-checking              |
| 2    | High SIL – Fail Operational      | Multiple doers/checkers + cross validation  |
| 3    | Low SIL – Doer/Checker           | 1 checker with mirrored input               |
| 4    | Low SIL – Fail Silent Hardware   | 1 checker with mirrored input               |
| 5    | High SIL – Fail Silent           | *(Reserved, currently disabled)*            |

The model chooses one valid pattern per node and calculates the number of additional redundant actors added (`pattern_redundant[i]`), using a cumulative sum approach.

---

## 🧩 Model Components

### Key Variables

- `actor_sil[i]`: SIL level of actor `i`
- `pattern_using[i]`: Redundancy pattern index used for actor `i`
- `pattern_redundant[i]`: Cumulative redundant actor index for actor `i`
- `graph`: Original adjacency matrix
- `graph_p`: Modified adjacency matrix including redundants
- `precedes`: Original precedence relations
- `precedes_p`: Modified precedence relations including redundants

### Redundancy Allocation

The redundancy per actor is calculated incrementally. For example, if `pattern_redundant[i] = 10`, then actors 0 through `i` have a total of 10 added redundant nodes. This is used to map and update the expanded graph structure (`graph_p`).

---

## ⚙️ Constraints Summary

### Pattern-Based Constraints

- **Pattern 1 – Mixed SIL Fail Silent**  
  Adds 2 checkers; includes out edges, cross-checks, and doer input duplication.
  
- **Pattern 2 – High SIL Fail Operational**  
  Adds 6+ redundant actors (doers, checkers, voters); enforces deep connectivity and mutual validation.

- **Patterns 3 & 4 – Doer/Checker & Fail Silent HW**  
  Adds 1 checker; mirrors inputs and enforces bidirectional communication.

- **Pattern 5 – High SIL Fail Silent**  
  *(Not yet implemented)*

### Precedence Graph (`precedes_p`) Updates

- Ensures every path to a base node is mirrored to its redundants.
- Applies pattern-specific mapping rules.
- Extra locations in `precedes_p` are reserved for further constraints.

---
