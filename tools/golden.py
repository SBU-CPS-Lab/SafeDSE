"""Independent reference implementations, used to check the CP model.

The whole risk profile of this project is that a constraint model returns a
plausible number rather than an error.  These functions are deliberately written
in a *different style* from the MiniZinc encoding -- Lawler's parametric
maximum-cycle-ratio search and a direct max-plus simulation, rather than node potentials -- so that agreement
between them is real evidence and not a shared bug.

Nothing here is imported by the model; it exists to be disagreed with.
"""
from __future__ import annotations

from fractions import Fraction

NEG = float("-inf")


def mcm_karp(n: int, edges: list[tuple[int, int, int]], wt: list[int]) -> Fraction | None:
    """Maximum cycle ratio per SCC, by Lawler's parametric search (_karp_scc).

    The names mcm_karp/_karp_scc are historical: the method is not Karp's
    minimum-mean-cycle algorithm but Lawler's (see _karp_scc).

    edges: (u, v, tokens).  Cycle mean of a cycle C is
        sum of wt[u] over edges (u,v) in C   /   sum of tokens over C.
    Returns the maximum over all cycles, or None if the graph is acyclic.

    The search runs per strongly connected component, so we decompose first.  Cycles with
    zero total tokens are the deadlock case and are reported as +infinity by
    returning None from the caller's perspective -- see mcm() below, which is
    the function tests should use.
    """
    best: Fraction | None = None
    for comp in _sccs(n, edges):
        if len(comp) == 1 and not any(u == v for u, v, _ in edges if u in comp):
            continue
        sub = [(u, v, t) for u, v, t in edges if u in comp and v in comp]
        if not sub:
            continue
        m = _karp_scc(sorted(comp), sub, wt)
        if m is not None and (best is None or m > best):
            best = m
    return best


def _karp_scc(nodes: list[int], edges: list[tuple[int, int, int]],
              wt: list[int]) -> Fraction | None:
    """Lawler's method on a strongly connected subgraph.

    Uses the ratio form: the maximum cycle ratio of (weight, tokens) is found by
    parametric search -- find the smallest mu such that no cycle has positive
    weight under w(u,v) = wt[u] - tokens*mu.  Binary search on rationals is
    fragile, so we instead enumerate candidate ratios via Bellman-Ford
    feasibility (Lawler's method) over a bounded search on the finite set of
    achievable ratios.
    """
    idx = {u: i for i, u in enumerate(nodes)}
    k = len(nodes)
    e = [(idx[u], idx[v], wt[u], t) for u, v, t in edges]

    # Candidate ratios are p/q with p <= sum of all weights, q <= total tokens.
    lo, hi = Fraction(0), Fraction(sum(abs(wt[u]) for u in nodes) or 1)
    if not _feasible(k, e, hi):
        # even a very large period is infeasible -> a token-less positive cycle
        return None
    # widen until feasible bound is comfortable, then bisect on rationals via
    # Stern-Brocot style refinement bounded by the max denominator
    maxden = sum(t for _, _, _, t in e) or 1
    for _ in range(200):
        if hi - lo < Fraction(1, maxden * maxden * 4):
            break
        mid = (lo + hi) / 2
        if _feasible(k, e, mid):
            hi = mid
        else:
            lo = mid
    return _best_rational(lo, hi, maxden)


def _feasible(k: int, e: list[tuple[int, int, int, int]], mu: Fraction) -> bool:
    """Bellman-Ford: is there no positive cycle under w = wt - tokens*mu?"""
    d = [Fraction(0)] * k
    for it in range(k + 1):
        changed = False
        for u, v, w, t in e:
            cand = d[u] + w - t * mu
            if cand > d[v]:
                d[v] = cand
                changed = True
        if not changed:
            return True
        if it == k:
            return False
    return True


def _best_rational(lo: Fraction, hi: Fraction, maxden: int) -> Fraction:
    """Smallest-denominator rational in (lo, hi]; the true MCM is one of these."""
    for q in range(1, maxden + 1):
        p = int(lo * q)
        while Fraction(p, q) <= lo:
            p += 1
        if Fraction(p, q) <= hi:
            return Fraction(p, q)
    return hi


def mcm(n: int, edges: list[tuple[int, int, int]], wt: list[int]) -> Fraction | None:
    """Minimum feasible iteration period.  None means deadlock.

    Deadlock detection is explicit rather than inferred: a cycle with zero
    initial tokens can never fire.
    """
    if _has_tokenless_cycle(n, edges):
        return None
    r = mcm_karp(n, edges, wt)
    return r if r is not None else Fraction(max(wt) if wt else 0)


def _has_tokenless_cycle(n: int, edges: list[tuple[int, int, int]]) -> bool:
    zero = [(u, v) for u, v, t in edges if t == 0]
    adj: dict[int, list[int]] = {}
    for u, v in zero:
        adj.setdefault(u, []).append(v)
    WHITE, GREY, BLACK = 0, 1, 2
    color = [WHITE] * n

    def dfs(s: int) -> bool:
        stack = [(s, iter(adj.get(s, ())))]
        color[s] = GREY
        while stack:
            u, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                color[u] = BLACK
                stack.pop()
                continue
            if color[nxt] == GREY:
                return True
            if color[nxt] == WHITE:
                color[nxt] = GREY
                stack.append((nxt, iter(adj.get(nxt, ()))))
        return False

    return any(color[s] == WHITE and dfs(s) for s in range(n))


def _sccs(n: int, edges: list[tuple[int, int, int]]) -> list[set[int]]:
    """Iterative Tarjan."""
    adj: dict[int, list[int]] = {}
    for u, v, _ in edges:
        adj.setdefault(u, []).append(v)
    index = [None] * n
    low = [0] * n
    on = [False] * n
    stack: list[int] = []
    out: list[set[int]] = []
    counter = 0
    for root in range(n):
        if index[root] is not None:
            continue
        work = [(root, iter(adj.get(root, ())))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on[root] = True
        while work:
            u, it = work[-1]
            nxt = next(it, None)
            if nxt is None:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[u])
                if low[u] == index[u]:
                    comp = set()
                    while True:
                        w = stack.pop()
                        on[w] = False
                        comp.add(w)
                        if w == u:
                            break
                    out.append(comp)
                continue
            if index[nxt] is None:
                index[nxt] = low[nxt] = counter
                counter += 1
                stack.append(nxt)
                on[nxt] = True
                work.append((nxt, iter(adj.get(nxt, ()))))
            elif on[nxt]:
                low[u] = min(low[u], index[nxt])
    return out


# --------------------------------------------------------------------------
# Self-timed simulator -- the strongest available oracle
# --------------------------------------------------------------------------
def selftimed_period(n: int, edges: list[tuple[int, int, int]], wt: list[int],
                     max_iters: int = 4000) -> Fraction | None:
    """Max-plus simulation until the schedule becomes periodic.

    Returns the steady-state iteration period, or None on deadlock.  This is an
    entirely different computation from the Lawler search -- it fires actors -- so agreement
    with mcm() is meaningful cross-validation.
    """
    if _has_tokenless_cycle(n, edges):
        return None
    # start times of each firing, iteration by iteration
    prev = [0] * n
    hist: list[list[int]] = []
    inc: dict[int, list[tuple[int, int]]] = {}
    for u, v, t in edges:
        inc.setdefault(v, []).append((u, t))

    starts = [[0] * n]
    order = _topo_zero(n, edges)
    if order is None:
        return None
    for it in range(1, max_iters):
        cur = [0] * n
        for v in order:
            s = 0
            for u, t in inc.get(v, ()):
                k = it - t
                if k < 0:
                    continue
                src = cur[u] if t == 0 else starts[k][u]
                s = max(s, src + wt[u])
            cur[v] = s
        starts.append(cur)
        # Steady state may repeat with a multi-iteration cycle (a cycle with d
        # initial tokens settles into a d-iteration pattern), so look for any
        # k with starts[it] - starts[it-k] constant over two consecutive
        # windows.  Actors in different SCCs can advance at different rates in
        # a graph without back-pressure edges; the graph period is the slowest.
        for k in range(1, 9):
            if it < 2 * k:
                break
            d1 = [starts[it][i] - starts[it - k][i] for i in range(n)]
            d2 = [starts[it - k][i] - starts[it - 2 * k][i] for i in range(n)]
            if d1 == d2 and max(d1) > 0:
                return Fraction(max(d1), k)
    return None


def selftimed_trace(n: int, edges: list[tuple[int, int, int]], wt: list[int],
                    iters: int = 60) -> list[list[int]] | None:
    """Start times of the first `iters` firings of every actor, transient included.

    Same recurrence as selftimed_period, but it returns the whole schedule
    rather than the steady-state slope, so end-to-end latency can be measured
    over the transient as well as the periodic phase.
    """
    if _has_tokenless_cycle(n, edges):
        return None
    order = _topo_zero(n, edges)
    if order is None:
        return None
    inc: dict[int, list[tuple[int, int]]] = {}
    for u, v, t in edges:
        inc.setdefault(v, []).append((u, t))
    starts = [[0] * n]
    for it in range(1, iters):
        cur = [0] * n
        for v in order:
            s = 0
            for u, t in inc.get(v, ()):
                k = it - t
                if k < 0:
                    continue
                s = max(s, (cur[u] if t == 0 else starts[k][u]) + wt[u])
            cur[v] = s
        starts.append(cur)
    return starts


def _topo_zero(n: int, edges: list[tuple[int, int, int]]) -> list[int] | None:
    indeg = [0] * n
    adj: dict[int, list[int]] = {}
    for u, v, t in edges:
        if t == 0:
            adj.setdefault(u, []).append(v)
            indeg[v] += 1
    q = [i for i in range(n) if indeg[i] == 0]
    out: list[int] = []
    while q:
        u = q.pop()
        out.append(u)
        for v in adj.get(u, ()):
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    return out if len(out) == n else None
