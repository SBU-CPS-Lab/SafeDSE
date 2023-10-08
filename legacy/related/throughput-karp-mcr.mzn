% Calculate the iteration bound of an HSDF graph using the extended Karp algorithm
% The extended algorithm essentially runs the karp algorithm for different number of delays encountered on HSDF graph cycles
include "globals.mzn";

% Define the number of actors in the graph
int: n;

% Define the adjacency matrix of the HSDF graph with initial tokens
array[1..n, 1..n] of opt 0..: Arc;

% Define the total number of tokens in the graph
int: nT = sum(i,j in 1..n) (Arc[i,j]);

% Define the execution time of each node
array[1..n] of 0..: T;

% Define the maximum cycle mean
var 0..sum(T): iteration_bound;

% Define Precision which is the fractional resolution for time-related vriables
0..: precision;

% A minizinc predicate which relates the iteration bound to an input HSDF graph according to the extended Karp algorithm
predicate iteration_bound_karp(var int: iteration_bound, array[1..n, 1..n] of opt 0..: Arc, array[1..n] of 0..: T) =
  let {
    % Define the distance matrix where dist[_ ,i, j] represents the execution time of actors on an i-length path from source to node j
    % The first index is the number of delays encountered on the path from source to node j
    array[0..nT, 0..n, 1..n] of var int: dists;
  } in
  (
    % Popualte the distance matrix
    dists[0, 0, 1] = 0 /\
    forall (t in 1..nT) (dists[t, 0, 1] = -1000) /\
    forall(t in 0..nT, i in 2..n) (
      dists[t, 0, i] = -1000
    ) /\
    forall(t in 0..nT, k, v in 1..n) (
        dists[t, k, v] = if exists (tp in 0..t, u in 1..n) (occurs(Arc[u, v]) /\ tp+Arc[u,v]=t) then 
                          max (tp in 0..t, u in 1..n where occurs(Arc[u, v]) /\ tp+Arc[u,v]=t) (
                            dists[tp, k - 1, u] + T[u]
                          )
                          else
                            -1000
                          endif
    ) /\
    % Calculate the iteration bound
    iteration_bound = max (v in 1..n) (
        if exists (t1, t2 in 0..nT, k in 0..n-1) (t1<t2 /\ dists[t2, n, v] >= 0 /\ dists[t1, k, v] >= 0 /\ dists[t2, n, v] - dists[t1, k, v] >= 0) then 
          min (t1, t2 in 0..nT, k in 0..n-1 where t1<t2 /\ dists[t2, n, v] >= 0 /\ dists[t1, k, v] >= 0 /\ dists[t2, n, v] - dists[t1, k, v] >= 0) (
                (dists[t2, n, v] - dists[t1, k, v]) div (t2-t1)
          )
        else
          -1000
        endif
    )
  );

% Post the iteration bound constraint
constraint iteration_bound_karp(iteration_bound, Arc, [T[i]*precision | i in 1..n]);

% Define the search space
solve satisfy;

% Output the iteration bound
output ["The iteration bound is: \(iteration_bound/precision)\n"];

% n = 2;
% Arc = [| <>, 1
%        |  2, <> |];
% T = [10, 20];
% precision = 1;

% Example Fig.2 in the paper
n=4;
%        i,  j,  k,  l
Arc= [| <>, <>, <>,  1,
      |  0, <>, <>, <>,
      |  0,  0, <>, <>,
      | <>, <>,  1, <>|];
T = [1, 2, 2, 1];
precision = 1;

% Example 2.2 from Govindarajant and Gao '93
% n=4;
% %       a0, a1, c0, b0
% Arc= [| <>,  0, <>, <>,
%       |  1, <>, <>,  0,
%       |  2,  2,  1, <>,
%       | <>, <>,  0,  1|];
% T = [1, 1, 2, 1];
% precision = 2;

% % Example Fig.1 in the paper
% n=6;
% %        h,  i,  j,  k,  l,  m
% Arc= [| <>,  0,  1, <>, <>, <>,
%       | <>, <>, <>, <>,  2, <>,
%       |  0, <>, <>, <>,  0,  0,
%       |  1, <>, <>, <>, <>, <>,
%       | <>, <>, <>, <>, <>,  0,
%       | <>, <>, <>,  0, <>, <>|];
% T = [1, 4, 2, 2, 1, 1];
% precision = 10;