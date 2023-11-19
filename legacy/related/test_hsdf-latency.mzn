% Test the HSDF latency calculation predicate

include "globals.mzn";
include "hsdf-latency.mzn";

% Define a large number used in the Bellman-Ford algorithm
int: INF = 1000;

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

% The latency
var 0..: latency;

% Call the predicate to calculate the latency
constraint hsdf_latency(Arc, T, s, d, latency);

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

