% Calculate all the shortest paths on a weighted directed acyclic graph
% Based on the "Algorithm book" (CLRS) 2nd ed. Section 25.2

% Define the number of nodes in the graph
int: n;

% Define the distance matrix where dist[i, j] represents the distance from node i to node j
array[1..n, 1..n] of int: dist;

array[0..n, 1..n, 1..n] of var int: dists;  % First index is the algorithm iteration
array[0..n, 1..n, 1..n] of var 0..n: preds; % First index is the algorithm iteration
array[1..n, 1..n, 1..n] of var 0..n: shortest;  % Last index is the index of the shortest path

% Initialize the distance matrix with the graph's edge weights
% For nodes i and j where i = j, set the distance to 0 (distance from a node to itself is 0)
% For nodes i and j where there is no direct edge (i ≠ j), set the distance to a large value (infinity)
% constraint forall (i, j in 1..n) (
%     if i == j then
%         dist[i, j] = 0
%     else
%         dist[i, j] = 10000 % Use a large value as infinity
%     endif
% );
constraint forall (i, j in 1..n) (
  dists[0,i,j] = dist[i,j] /\
  preds[0,i,j] = if i!=j /\ dist[i,j]<10000 then i else 0 endif
);

% Floyd-Warshall algorithm to compute all-pairs shortest paths
% Update the distance matrix iteratively to find the shortest paths
constraint
  forall (k, i, j in 1..n) (
    dists[k, i, j] = min(dists[k-1, i, j], dists[k-1, i, k] + dists[k-1, k, j]) /\
    preds[k, i, j] = if dists[k-1, i, j] <= dists[k-1, i, k] + dists[k-1, k, j] then preds[k-1, i, j] else preds[k-1, k, j] endif
);

constraint forall (i,j in 1..n) (
  shortest[i,j,n] = j /\
  forall (k in 1..n-1) (
    shortest[i,j,k] = if shortest[i,j,k+1]>0 then preds[k+1,i,shortest[i,j,k+1]] else 0 endif
  )
);

% Output the shortest distances between all pairs of nodes
% output ["Shortest distance from node " ++ show(i) ++ " to node " ++ show(j) ++ ": " ++ show(dists[n, i, j]) ++ "\n" | i, j in 1..n] ++
%   ["Precessor of node " ++ show(j) ++ " on shortest path from " ++ show(i) ++ ": " ++ show(preds[n, i, j]) ++ "\n" | i, j in 1..n];

output ["Shortest path from node " ++ show(i) ++ " to node " ++ show(j) ++ ": " ++ 
    show([shortest[i, j, k]|k in 1..n]) ++ " has length: " ++ show(dists[n, i, j]) ++ "\n"
  | i, j in 1..n];

solve satisfy;

n=5;
dist=[|    0,     3,     8, 10000,    -4,
      |10000,     0, 10000,     1,     7,
      |10000,     4,     0, 10000, 10000,
      |    2, 10000,    -5,     0, 10000,
      |10000, 10000, 10000,     6,     0|];
