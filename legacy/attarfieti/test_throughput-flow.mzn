% Test the throughput calculation of an HSDF graph using a flow-based min,+ approach

include "globals.mzn";
include "throughput_flow.mzn";

% The number of actors in the graph
int: n_actors;

% Maximum number of tokens on an Arc
int: MAXTOKS;

% Set of actors
set of int: ACTORS = 1..n_actors;

% The graph topology as an adjacency matrix
array[ACTORS, ACTORS] of 0..1: graph;

% Define the adjacency matrix of the HSDF graph with initial tokens
array[1..n_actors, 1..n_actors] of var opt 0..MAXTOKS: Arc;

% The execution time of each actor
array[ACTORS] of int: exec_time;

% The inverse of throughput: iteration time
var 0..sum(exec_time): iteration_bound;

% Post the throughput predicate
constraint throughput_flow(Arc, exec_time, iteration_bound);

% Relate the graph topology to the Arc variable by forcing the absent Arcs
constraint forall (i, j in ACTORS) (
    absent(Arc[i, j]) <-> (graph[i, j] = 0)
);

% Maximizing the throughput is equivalent to minimizing the inverse of the throughput (iteration period)
% solve minimize sum(Arc)*iteration_bound;
% solve minimize sum(Arc);
solve minimize iteration_bound; constraint sum(array1d(Arc))=3;


% Output the inverse of the throughput, the throughput and the token matrix as a table
output ["Inv Throughput (Iteration Period): \(iteration_bound)ms\n"];
output ["Throughput: \(1000 div iteration_bound)\n"];
% output ["\nToken Matrix:\n"];
% output [show_int(3, deopt(Arc[i,j])) ++ if j == n_actors then "\n" else " " endif | i, j in ACTORS];

%%%%%%%%% Data %%%%%%%%%
MAXTOKS = 10;
% The number of actors
% n_actors = 3;
n_actors = 5;

% The graph topology
% graph = [|0, 0, 1,
%          |0, 0, 1,
%          |1, 1, 0
%          |];
% The execution time of each actor (ms)
% exec_time = [10, 20, 30];

graph = [|0, 0, 1, 0, 0
         |0, 0, 1, 0, 0
         |0, 0, 0, 1, 1
         |1, 0, 0, 0, 0
         |0, 1, 0, 0, 0
         |];
exec_time = [10, 20, 30, 15, 25];

