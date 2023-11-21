% Test the throughput calculation of an HSDF graph using a flow-based min,+ approach under latency constraints

include "globals.mzn";
include "throughput_flow.mzn";
include "../related/hsdf-latency.mzn";

% Maximum number of tokens on an Arc
int: MAXTOKS = 1;

% Define a large number used in the Bellman-Ford algorithm
int: INF = 100;

% Define the number of actors in the graph
int: n_actors;

% Set of actors
set of int: ACTORS = 1..n_actors;

% The graph topology as an adjacency matrix
array[ACTORS, ACTORS] of 0..1: graph;

% Define the adjacency matrix of the HSDF graph with initial tokens
array[1..n_actors, 1..n_actors] of var opt 0..MAXTOKS: Arc;

% The execution time of each actor
array[ACTORS] of int: exec_time;

% Define the source actor
int: s;

% Define the destination actor
int: d;

% The inverse of throughput: iteration time
var 0..sum(exec_time): iteration_bound;

% The latency
var 0..: latency;

% Post the throughput predicate
constraint throughput_flow(Arc, exec_time, iteration_bound);

% Call the predicate to calculate the latency
constraint hsdf_latency(Arc, exec_time, s, d, latency);

% Relate the graph topology to the Arc variable by forcing the absent Arcs
constraint forall (i, j in ACTORS) (
    absent(Arc[i, j]) <-> (graph[i, j] = 0)
);

constraint latency <= 10;

% Maximizing the throughput is equivalent to minimizing the inverse of the throughput (iteration period)
solve minimize iteration_bound;


% Output the inverse of the throughput, the throughput and the token matrix as a table
output ["Inv Throughput (Iteration Period): \(iteration_bound)ms\n"];
output ["Throughput: \(1000 div iteration_bound)\n"];
% output ["\nToken Matrix:\n"];
% output [show_int(3, deopt(Arc[i,j])) ++ if j == n_actors then "\n" else " " endif | i, j in ACTORS];

%%%%%%%%% Data %%%%%%%%%
% The number of actors
% n_actors = 3;
% n_actors = 5;

% The graph topology
% graph = [|0, 0, 1,
%          |0, 0, 1,
%          |1, 1, 0
%          |];
% The execution time of each actor (ms)
% exec_time = [10, 20, 30];

% graph = [|0, 0, 1, 0, 0
%          |0, 0, 1, 0, 0
%          |0, 0, 0, 1, 1
%          |1, 0, 0, 0, 0
%          |0, 1, 0, 0, 0
%          |];
% exec_time = [10, 20, 30, 15, 25];

% Example Fig.1 in the paper
n_actors=6;
%        h,  i,  j,  k,  l,  m
graph= [| 0, 1, 1, 0, 0, 0,
        | 0, 0, 0, 0, 1, 0,
        | 1, 0, 0, 0, 1, 1,
        | 1, 0, 0, 0, 0, 0,
        | 0, 0, 0, 0, 0, 1,
        | 0, 0, 0, 1, 0, 0|];
exec_time = [1, 4, 2, 2, 1, 1];
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