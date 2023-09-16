% Throughput calculation of an HSDF graph using a direct min,+ approach
% The model defines non-negative decision variables on the edge inputs and outputs holding the remaining iteration time budget constraining the throughput.
% Each initial token charges up this value by one iteration time and each actor decrements it by the execution time.
% On actor inputs, the minimum of these values are propagated as a bound to the output.
% For the moment these values are called cycle residual times until better names are found.

% The number of actors in the graph
int: n_actors;

% Set of actors
set of int: ACTORS = 1..n_actors;

% The graph topology as an adjacency matrix
array[ACTORS, ACTORS] of 0..1: graph;

% The number of tokens on each edge
array[ACTORS, ACTORS] of 0..: toks;

% The execution time of each actor
array[ACTORS] of int: exec_time;

% The inverse of throughput: iteration time
var 0..sum(exec_time): inv_thr;

% The residual cycle time on each edge input
array[ACTORS, ACTORS] of var 0..sum(toks)*sum(exec_time): inp_res_time;

% The residual cycle time on each edge output
array[ACTORS, ACTORS] of var 0..sum(toks)*sum(exec_time): out_res_time;

% Relate the output cycle residual times to the input cycle residual times for each edge
% The number of initial tokens times the iteration time is added to the edge input resdual cycle time of each edge
constraint forall (i, j in ACTORS where graph[i, j] == 1) (
    out_res_time[i, j] = inp_res_time[i, j] + toks[i, j] * inv_thr
);

% Relate the input cycle residual times to the output cycle residual times in each actor
% The input cycle residual time of all outgoing edges must be equal to the minimum of the output cycle residual times of all incoming edges minus actor execution time
constraint forall (a in ACTORS) (
    forall (i in ACTORS where graph[a, i] == 1) (
        inp_res_time[a, i] <= min([out_res_time[j, a] | j in ACTORS where graph[j, a] == 1]) - exec_time[a]
    )
);

% Fill out irrelevant cycle residual times
constraint forall (i, j in ACTORS where graph[i, j] == 0) (
    inp_res_time[i, j] = 0 /\ out_res_time[i, j] = 0
);

% Maximizing the throughput is equivalent to minimizing the inverse of the throughput (iteration period)
solve minimize inv_thr;

% Output the inverse of the throughput
output ["Inv Throughput (Iteration Period): \(inv_thr)ms\n"];
output ["Throughput: \(1000 div inv_thr)"];

%%%%%%%%% Data %%%%%%%%%
% The number of actors
n_actors = 3;

% The graph topology
graph = [|0, 0, 1,
         |0, 0, 1,
         |1, 1, 0
         |];

% The number of initial tokens on each edge
toks = [|0, 0, 0,
        |0, 0, 0,
        |1, 1, 0
        |];
% toks = [|0, 0, 1,
%         |0, 0, 1,
%         |2, 2, 0
%         |];

% The execution time of each actor (ms)
exec_time = [10, 20, 30];

