% The Bellman-Ford algorithm used to find single-source shortest minimum-delay paths on an HSDF graph
include "globals.mzn";

% Define the number of actors in the graph
int: n;

% Define the adjacency matrix of the HSDF graph with initial tokens
array[1..n, 1..n] of opt 0..: Arc;

% Define the source actor
int: s;

% Define the shortest path
var 0..: dist;

% A MiniZinc predicate which finds single-source shortest minimum-delay paths on an HSDF graph from a given source actor using the Bellman-Ford algorithm
predicate bellman_ford(array[1..n, 1..n] of opt 0..: Arc, int: s, array[0..n-1, 1..n] of var 0..: dists) =
    % Initial distance from the source to itself is 0
    dists[0, s] = 0 /\
    % Initial distance from the source to all other actors is 1000
    forall (i in 1..n where i!=s) (dists[0, i] = 1000) /\
    % Bellman-Ford algorithm to find the shortest (minimum-delay) path from the source to all other actors
    forall (k in 1..n-1) (
        forall (i in 1..n) (
            dists[k, i] = min(
                dists[k-1, i],
                min(j in 1..n where occurs(Arc[j, i])) (dists[k-1, j] + Arc[j, i])
            )
        )
    );

% A MiniZinc predicate which finds single-source shortest minimum-delay paths on an HSDF graph from a given source actor to a destination actor using the Bellman-Ford algorithm
predicate bellman_ford(array[1..n, 1..n] of opt 0..: Arc, int: s, int: d, var 0..: dist) =
    let {
        % Define the distance matrix
        % The first index is the algorithm iteration
        % The second index is the destination actor
        array[0..n-1, 1..n] of var 0..: dists;
    } in (
        % Call the predicate
        bellman_ford(Arc, s, dists) /\
        % The distance from the source to the destination is the last element of the distance matrix
        dist = dists[n-1, d]
    );

% Call the predicate
% constraint bellman_ford(Arc, s, dists);
constraint bellman_ford(Arc, s, 5, dist);

% Solve the problem
solve satisfy;

% Example Fig.1 in the paper
n=6;
%        h,  i,  j,  k,  l,  m
Arc= [| <>,  0,  1, <>, <>, <>,
      | <>, <>, <>, <>,  2, <>,
      |  0, <>, <>, <>,  0,  0,
      |  1, <>, <>, <>, <>, <>,
      | <>, <>, <>, <>, <>,  0,
      | <>, <>, <>,  0, <>, <>|];
s = 1;

% Example Fig.2 in the paper
% n=4;
% %        i,  j,  k,  l
% Arc= [| <>, <>, <>,  1,
%       |  0, <>, <>, <>,
%       |  0,  0, <>, <>,
%       | <>, <>,  1, <>|];
% s = 1;