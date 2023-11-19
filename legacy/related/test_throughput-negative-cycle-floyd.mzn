% Test the throughput analysis of HSDF graphs with negative cycle detection

include "globals.mzn";
include "throughput-negative-cycle-floyd.mzn";

% Define the infinity value
int: INF = 1000;

% Define the number of actors in the graph
int: n;

% Define the adjacency matrix of the HSDF graph with initial tokens
array[1..n, 1..n] of opt 0..: Arc;

% Define the execution time of each node
array[1..n] of 0..: T;

% Define the maximum cycle mean
var 0..sum(T)*precision: iteration_bound;

% Define Precision which is the fractional resolution for time-related vriables
0..: precision;

% Post the negative cycle detection predicate
constraint thr_neg_cycl_det(Arc, [T[i]*precision | i in 1..n], iteration_bound);

% Solve the problem
solve satisfy;

% Output the maximum cycle mean
output ["Iteration bound: " ++ show(iteration_bound/precision) ++ "\n"];


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
precision = 10;

% Example Fig.2 in the paper
% n=4;
% %        i,  j,  k,  l
% Arc= [| <>, <>, <>,  1,
%       |  0, <>, <>, <>,
%       |  0,  0, <>, <>,
%       | <>, <>,  1, <>|];
% T = [1, 2, 2, 1];
% precision = 1;

% Example 2.2 from Govindarajant and Gao '93
% n=4;
% %       a0, a1, c0, b0
% Arc= [| <>,  0, <>, <>,
%       |  1, <>, <>,  0,
%       |  2,  2,  1, <>,
%       | <>, <>,  0,  1|];
% T = [1, 1, 2, 1];
% precision = 2;