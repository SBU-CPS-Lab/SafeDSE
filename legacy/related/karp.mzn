% Calculate the maximum cycle mean of an event graph according to the Karp's algorithm
% The example and the algorithm formulation based on Dasdan and Gupta'98
include "globals.mzn";
% Define the number of nodes in the graph
int: n;

% Define the adjacency matrix of the weighted event graph
array[1..n, 1..n] of opt int: A;

% Define the maximum cycle mean
var int: max_cycle_mean;

% Define the distance matrix
array[0..n, 1..n] of var int: D;

% Define the predecessor matrix
% array[0..n, 1..n] of var opt int: P;

% Popualte the distance and predecessor matrices
constraint D[0, 1] = 0;% /\ absent(P[0, 1]);
constraint
    forall(i in 2..n) (
        D[0, i] = -1000
    );
constraint
    forall(k, v in 1..n) (
        D[k, v] = max (u in 1..n where occurs(A[u, v])) (
            D[k - 1, u] + A[u, v]
        )
    );

% Calculate the maximum cycle mean
constraint
    max_cycle_mean = max (v in 1..n) (
        min (k in 0..n-1) (
            (D[n, v] - D[k, v]) div (n - k)
        )
    );

% Define the search space
solve satisfy;

% Output the maximum cycle mean
output ["The maximum cycle mean is: \(max_cycle_mean)\n The distance matrix is: \(D)"];

% Sample input
n = 4;
A = [| <>,  3,  2, <>
     | <>, <>,  4, <>
     | <>, <>, <>,  7
     |  2, <>, <>, <> |];
        