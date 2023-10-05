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
% 0..: precision;

% Define the distance matrix
% The first index is the number of delays encountered on the cycle
array[0..nT, 0..n, 1..n] of var int: D;

% Popualte the distance and predecessor matrices
constraint forall (t in 0..nT) (D[t, 0, 1] = 0);
constraint
    forall(t in 0..nT, i in 2..n) (
        D[t, 0, i] = -1000
    );
constraint
    forall(t in 0..nT, k, v in 1..n) (
        D[t, k, v] = if exists (tp in 0..t, u in 1..n) (occurs(Arc[u, v]) /\ tp+Arc[u,v]=t) then 
                      max (tp in 0..t, u in 1..n where occurs(Arc[u, v]) /\ tp+Arc[u,v]=t) (
                        D[tp, k - 1, u] + T[u]
                      )
                      else
                        -1000
                      endif
    );
 
% Calculate the iteration bound
constraint
    iteration_bound = max (v in 1..n) (
        min (t1, t2 in 1..nT, k in 0..n-1 where t1<t2 /\ D[t2, n, v] - D[t1, k, v] >= 0) (
            (D[t2, n, v] - D[t1, k, v]) div (t2-t1+1)
        )
    );
%constraint
%    iteration_bound = max (v in 1..n) (
%        min (t1, t2 in 0..nT, k in 0..n-1 where t1<t2 /\ D[t2, n, v] - D[t1, k, v] >= 0) (
%            (D[t2, n, v] - D[t1, k, v]) div (t2-t1)
%        )
%    );

% Define the search space
solve satisfy;

% Output the iteration bound
output ["The iteration bound is: \(iteration_bound)\n"] ++
       ["The distance matrix is:\n"] ++
       [if i==0 /\ j==1 then "t=\(t)\n" else"" endif ++
        show_int(6,D[t, i, j]) ++ 
        if j==n then "\n" else "" endif 
        | t in 0..nT, i in 0..n, j in 1..n];

n = 2;
Arc = [| <>, 2
       |  1, <> |];
T = [10, 20];

% n=4;
% %        i,  j,  k,  l
% Arc= [| <>, <>, <>,  1,
%       |  0, <>, <>, <>,
%       |  0,  0, <>, <>,
%       | <>, <>,  1, <>|];
% T = [10, 20, 20, 10];

% Example 2.2 from Govindarajant and Gao '93
% n=4;
% %       a0, a1, c0, b0
% Arc= [| <>,  0, <>, <>,
%       |  1, <>, <>,  0,
%       |  2,  2,  1, <>,
%       | <>, <>,  0,  1|];
% T = [10, 10, 20, 10];
