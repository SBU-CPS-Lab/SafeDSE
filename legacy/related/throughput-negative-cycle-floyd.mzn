% Calculate all the iteration bound of an HSDF graph using the negative cycle detection mthod and the Floyd-Warshall algorithm
% Based on the Ito and Parhi'95
% We calculate two ses of distance matrixes for Tc and Tc-1 (Tc: iteration bound) in such a way that Tc-1 gives negative cycles but Tc won't
% Since iteration bound might be fractional the precision can be adjusted for fractional part

% Define the number of actors in the graph
int: n;

% Define the adjacency matrix of the HSDF graph with initial tokens
array[1..n, 1..n] of opt 0..: Arc;

% Define the execution time of each node
array[1..n] of 0..: T;

% Define the maximum cycle mean
var 0..sum(T)*precision: iteration_bound;

% Define Precision which is the fractional resolution for iteration bound
0..: precision;

% Define the distance matrix where dist[_ ,_ ,i, j] represents the distance from node i to node j
array[0..1, 0..n, 1..n, 1..n] of var int: dists;  % First index is for two conseceutive investigation of iteration bound and second index is the algorithm iteration

% Initialize the distance matrix with the graph's edge weights
% For nodes i and j where i = j, set the distance to 0 (distance from a node to itself is 0)
% For nodes i and j where there is no direct edge (i ≠ j), set the distance to a large value (infinity)
constraint forall (t in 0..1, i, j in 1..n) (
  dists[t,0,i,j] = if i=j then 0 else
                     if occurs(Arc[i,j]) then 
                       (Arc[i,j]) * (iteration_bound-(1-t)) - (T[i]*precision)
                     else
                       1000 
                     endif
                   endif
);

% Floyd-Warshall algorithm to compute all-pairs shortest paths
% Update the distance matrices iteratively to find the shortest paths
constraint
  forall (t in 0..1, k, i, j in 1..n) (
    dists[t, k, i, j] = min(dists[t, k-1, i, j], dists[t, k-1, i, k] + dists[t, k-1, k, j])
);

constraint exists (i in 1..n) (dists[0,n,i,i] < 0);
constraint forall (i in 1..n) (dists[1,n,i,i] >= 0);

% Output the maximum cycle mean
output ["Iteration bound: " ++ show(iteration_bound/precision) ++ "\n"];

output [ if i == 1 /\ j==1 then "dists[\(k)] = \n" else "" endif ++
         show_int(4, dists[0,k,i,j]) ++ 
         if j == n then "\n" else " " endif |
         k in 0..n, i in 1..n, j in 1..n
];

solve satisfy;
% constraint iteration_bound = 35;
% Example Fig.1
n=6;
%        h,  i,  j,  k,  l,  m
Arc= [| <>,  0,  1, <>, <>, <>,
      | <>, <>, <>, <>,  2, <>,
      |  0, <>, <>, <>,  0,  0,
      |  1, <>, <>, <>, <>, <>,
      | <>, <>, <>, <>, <>,  0,
      | <>, <>, <>,  0, <>, <>|];
T = [1, 4, 2, 2, 1, 1];
precision = 10;

% Example Fig.2
% n=4;
% %        i,  j,  k,  l
% Arc= [| <>, <>, <>,  1,
%       |  0, <>, <>, <>,
%       |  0,  0, <>, <>,
%       | <>, <>,  1, <>|];
% T = [1, 2, 2, 1];
% precision = 1;
