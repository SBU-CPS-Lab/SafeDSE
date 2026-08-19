% ---------------------------------------------------------------------------
% mcm.mzn -- throughput (maximum cycle mean) and deadlock-freedom for HSDF
%
% A period mu is feasible for a self-timed HSDF schedule iff there exist node
% potentials pot[] satisfying, for every edge (i,j):
%
%       pot[j] >= pot[i] + T[i] - tok[i,j] * mu
%
% This is the Bellman-Ford / LP-duality characterisation of the maximum cycle
% mean.  Consequences:
%   * `minimize mu` returns exactly the MCM (= minimum iteration period);
%   * infeasibility  <=>  a token-less cycle exists  <=>  deadlock.
% So this single predicate subsumes both the throughput propagator and the
% deadlock-avoidance machinery (Rosvall's `rank` family, Bonfietti's
% throughput>0 test).
%
% Cost: |A| potential variables and one linear inequality per candidate edge.
% Compare: the edge-residual formulation needs 2|A|^2 variables.
%
% LINEARITY NOTE -------------------------------------------------------------
% tok[i,j] * mu is linear only while tok is a PARAMETER.  Variable-size buffer
% back-edges make this a var*var product.  Handle by (a) sweeping buffer sizes
% from the driver, (b) `element` over a small candidate set of precomputed
% tok*mu terms, or (c) letting CP-SAT handle int_times directly -- measure.
% Schedule-induced (serialisation) edges always carry zero tokens, so they stay
% linear unconditionally; that is why they get their own predicate below.
% ---------------------------------------------------------------------------

% Fixed application edges: tok[i,j] < 0 means "no channel".
predicate mcm_fixed_edges(
    array[int,int] of int: tok,
    array[int]     of int: T,
    array[int] of var int: pot,
    var int:               mu
) =
    let { set of int: A = index_set(T) } in
    assert(index_set_1of2(tok) = A /\ index_set_2of2(tok) = A,
           "mcm: tok must be indexed by the actor set") /\
    assert(index_set(pot) = A,
           "mcm: pot must be indexed by the actor set") /\
    forall (i, j in A where tok[i,j] >= 0) (
        pot[j] >= pot[i] + T[i] - tok[i,j] * mu
    );

% Schedule-induced edges (token-less by construction), selected by a reified
% Boolean matrix.  Use this for serialisation arcs added by the static order.
predicate mcm_schedule_edges(
    array[int,int] of var bool: sedge,
    array[int]     of int:      T,
    array[int] of var int:      pot
) =
    let { set of int: A = index_set(T) } in
    forall (i, j in A where i != j) (
        sedge[i,j] -> pot[j] >= pot[i] + T[i]
    );

% Convenience: anchor the potentials to remove the free additive constant.
predicate mcm_anchor(array[int] of var int: pot) =
    pot[min(index_set(pot))] = 0;

% Periodic-phase latency estimate (see architecture doc B.2).  In the periodic
% regime the k-th firing of actor i starts at approximately pot[i] + k*mu, so
% latency(s,d) ~= pot[d] - pot[s] + rho*mu + T[d], where rho is the minimum
% token-delay path from s to d.  Exact in the periodic phase; ignores the
% transient.  Use for constrain-and-prune; verify returned solutions exactly.
function var int: mcm_periodic_latency(
    array[int] of var int: pot, array[int] of int: T,
    int: s, int: d, int: rho, var int: mu
) = pot[d] - pot[s] + rho * mu + T[d];
