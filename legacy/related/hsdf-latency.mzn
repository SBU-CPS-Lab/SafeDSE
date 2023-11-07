% Latency calculation between a source and destination actor in an HSDF graph
% Latency is calculated by finding the end time of the ρ(src,dst)+1th invocation of the destination actor in a self-timed schedule of the graph
% ρ(src,dst) is the minimum-delay path from src to dst and is calculated using the included bellman_ford predicate

include "globals.mzn";
% include "bellman-ford.mzn";

% Define the number of actors in the graph
int: n;

% Define the adjacency matrix of the HSDF graph with initial tokens
array[1..n, 1..n] of opt 0..: Arc;

% Define the execution time of each node
array[1..n] of 0..: T;

% Define the source actor
int: s;

% Define the destination actor
int: d;

% Define the number of initial tokens on the minimum-delay path which is equal to ρ(src,dst)
var 0..: dist;

% Define the execution time vectors of the actors representing the self-timed schedule
% array[1..n, 1..dist] of var opt 0..: exec_times;
array[1..n, 1..sum(array1d(Arc))] of var opt 0..: exec_times;

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

% Calculate the minimum-delay path from the source to the destination
constraint bellman_ford(Arc, s, d, dist);

% Calculate the self-timed schedule of the graph (until the dist=ρ(src,dst)+1th invocation of the destination actor)
constraint forall (i in 1..n, j in 1..dist+1) (
    exec_times[i, j] = max (k in 1..n where occurs(Arc[k, i])) (
        if j-Arc[k, i] < 1 then 0 else exec_times[k, j-Arc[k, i]] + T[k] endif
    )
);

% Fix the unneeded execution times to absent
constraint forall (i in 1..n, j in dist+2..sum(array1d(Arc))) (
    absent(exec_times[i, j])
);

% The latency is the end time of the ρ(src,dst)+1th invocation of the destination actor
var 0..: latency = deopt(exec_times[d, dist+1] + T[d] - exec_times[s, 1]);

% Solve for the latency
solve satisfy;

% Output the latency
output ["Latency: \(latency)\n"];

% Output the self-timed schedule
% output ["Self-timed schedule: \(exec_times)\n"];


% Example Fig.1 in the paper
n=6;
%        h,  i,  j,  k,  l,  m
Arc= [| <>,  0,  1, <>, <>, <>,
      | <>, <>, <>, <>,  2, <>,
      |  0, <>, <>, <>,  0,  0,
      |  1, <>, <>, <>, <>, <>,
      | <>, <>, <>, <>, <>,  0,
      | <>, <>, <>,  0, <>, <>|];
T = [1, 4, 2, 2, 1, 1];
s = 1; d = 6;

% Example Fig.2 in the paper
% n=4;
% %        i,  j,  k,  l
% Arc= [| <>, <>, <>,  1,
%       |  0, <>, <>, <>,
%       |  0,  0, <>, <>,
%       | <>, <>,  1, <>|];
% T = [1, 2, 2, 1];

% Example 2.2 from Govindarajant and Gao '93
% n=4;
% %       a0, a1, c0, b0
% Arc= [| <>,  0, <>, <>,
%       |  1, <>, <>,  0,
%       |  2,  2,  1, <>,
%       | <>, <>,  0,  1|];
% T = [1, 1, 2, 1];

