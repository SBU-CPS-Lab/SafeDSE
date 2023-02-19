include "alldifferent.mzn";

int: n;   % number of nodes
int: m;   % number of edges
array[1..n, 1..n] of int: adj;  % adjacency matrix

% decision variables
array[1..n] of var 1..n: x;

% constraints
constraint alldifferent(x);
constraint x[1] < x[n];   % cycle starts at node 1
constraint adj[x[n], x[1]] = 1;   % cycle ends at node n
constraint forall(i in 1..n-1) (adj[x[i], x[i+1]] = 1);   % path along cycle
constraint exists(i in 1..n-1) (adj[x[i], x[n]] = 1);   % path from last node to first node

solve satisfy;


output ["Cycle: ", show(x), "\n"];


% dzn

% number of nodes
n = 5;

% number of edges
m = 6;

% adjacency matrix
adj = array2d(1..n, 1..n, [0, 1, 0, 0, 0,
                           0, 0, 1, 0, 0,
                           0, 0, 0, 1, 0,
                           1, 0, 0, 0, 1,
                           0, 1, 0, 0, 0]);
