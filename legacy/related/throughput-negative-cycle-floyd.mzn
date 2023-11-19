% Calculate the iteration bound of an HSDF graph using the negative cycle detection method and the Floyd-Warshall algorithm
% Based on Ito and Parhi'95
% We calculate two sets of distance matrixes for Tc and Tc-1 (Tc: iteration bound)
% in such a way that Tc-1 gives negative cycles but Tc won't
% Since iteration bound might be fractional the precision can be adjusted for fractional part of the time domain

% A minizinc predicate which relates the iteration bound to an input graph according to the negative cycle detection method
predicate thr_neg_cycl_det(array[int,int] of opt int: Arc, array[int] of int: T, var int: iteration_bound) =
  let {
    set of int: S1 = index_set_1of2(Arc);
    set of int: S2 = index_set_2of2(Arc);
    set of int: S3 = index_set(T);
    int: l = min(S1);
    int: u = max(S1);
    int: n = card(S1);
    % Define the distance matrix where dist[_ ,_ ,i, j] represents the distance from node i to node j
    % First index is for two conseceutive investigation of iteration bound
    % Second index is the algorithm iteration
    array[0..1, 0..n, S1, S1] of var int: dists;
  } in
  (
    assert (S1 = S2 /\ S1 = S3, "The index sets of the adjacency matrix and the execution times must be the same.") /\
    assert (lb_array(Arc) >= 0, "The adjacency matrix must have non-negative values.") /\
    assert (lb_array(T) >= 0, "The execution times must be non-negative.") /\
    % Initialize the distance matrix with the graph's edge weights
    % For nodes i and j where i = j, set the distance to 0 (distance from a node to itself is 0)
    % For nodes i and j where there is no direct edge (i ≠ j), set the distance to a large value (infinity)
    forall (t in 0..1, i, j in S1) (
      dists[t,0,i,j] = if i=j then 0 else
                         if occurs(Arc[i,j]) then 
                           (Arc[i,j]) * (iteration_bound-(1-t)) - T[i]
                         else
                           INF
                         endif
                       endif
    )
    /\
    % Floyd-Warshall algorithm to compute all-pairs shortest paths
    % Update the distance matrices iteratively to find the shortest paths
    forall (t in 0..1, k in 1..n, i, j in S1) (
      dists[t, k, i, j] = min(dists[t, k-1, i, j], dists[t, k-1, i, k] + dists[t, k-1, k, j])
    )
    /\
    % For Tc-1 there should be at least one negative cycle (negative number on diagonal of the result matrix)
    exists (i in S1) (dists[0,n,i,i] < 0)
    /\
    % For Tc there should not be any negative cycle
    forall (i in S1) (dists[1,n,i,i] >= 0)
  );
