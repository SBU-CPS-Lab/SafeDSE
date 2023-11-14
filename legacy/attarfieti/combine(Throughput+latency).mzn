% Latency calculation between a source and destination actor in an HSDF graph
% Latency is calculated by finding the end time of the ρ(src,dst)+1th invocation of the destination actor in a self-timed schedule of the graph
% ρ(src,dst) is the minimum-delay path from src to dst and is calculated using the included bellman_ford predicate

include "globals.mzn";
% include "bellman-ford.mzn";

% Define the number of actors in the graph
int: n;

% Define the adjacency matrix of the HSDF graph with initial tokens
array[1..n, 1..n] of var opt 0..: Arc;

% Define the execution time of each node
array[1..n] of 0..: T;

% Define the source actor
int: s;

% Define the destination actor
int: d;

% Define the number of initial tokens on the minimum-delay path which is equal to ρ(src,dst)
var 0..36: dist;

% Define the execution time vectors of the actors representing the self-timed schedule
% array[1..n, 1..dist] of var opt 0..: exec_times;
array[1..n, 1..n*n] of var opt 0..: exec_times;

% A MiniZinc predicate which finds single-source shortest minimum-delay paths on an HSDF graph from a given source actor using the Bellman-Ford algorithm
predicate bellman_ford(array[1..n, 1..n] of var opt 0..: Arc, int: s, array[0..n-1, 1..n] of var 0..: dists) =
    % Initial distance from the source to itself is 0
    dists[0, s] = 0 /\
    % Initial distance from the source to all other actors is 1000
    forall (i in 1..n where i!=s) (dists[0, i] = 1000) /\
    % Bellman-Ford algorithm to find the shortest (minimum-delay) path from the source to all other actors
    forall (k in 1..n-1) (
        forall (i in 1..n) (
            dists[k, i] = min(
                dists[k-1, i],
                min(j in 1..n where occurs(Arc[j, i])) (dists[k-1, j] + Arc[j, i])
            )
        )
    );

% A MiniZinc predicate which finds single-source shortest minimum-delay paths on an HSDF graph from a given source actor to a destination actor using the Bellman-Ford algorithm
predicate bellman_ford(array[1..n, 1..n] of var opt 0..: Arc, int: s, int: d, var 0..: dist) =
    let {
        % Define the distance matrix
        % The first index is the algorithm iteration
        % The second index is the destination actor
        array[0..n-1, 1..n] of var 0..: dists;
    } in (
        % Call the predicate
        bellman_ford(Arc, s, dists) /\
        % The distance from the source to the destination is the last element of the distance matrix
        dist = dists[n-1, d]
    );

% Calculate the minimum-delay path from the source to the destination
constraint bellman_ford(Arc, s, d, dist);

% Calculate the self-timed schedule of the graph (until the dist=ρ(src,dst)+1th invocation of the destination actor)
constraint forall (i in 1..n, j in 1..dist+1) (
    exec_times[i, j] = max (k in 1..n where occurs(Arc[k, i])) (
        if j-Arc[k, i] < 1 then 0 else exec_times[k, j-Arc[k, i]] + T[k] endif
    )
);

% Fix the unneeded execution times to absent
constraint forall (i in 1..n, j in 1..n where j>= dist+2) (
    absent(exec_times[i, j])
);

% The latency is the end time of the ρ(src,dst)+1th invocation of the destination actor
var 0..100: latency = deopt(exec_times[d, dist+1] + T[d] - exec_times[s, 1]);

% Solve for the latency
solve satisfy;

% Output the latency
% output ["Latency: \(latency)\n"];

% Output the self-timed schedule
% output ["Self-timed schedule: \(exec_times)\n"];

%%%%%%%%%%
% Throughput calculation of an HSDF graph using a flow-based min,+ approach
% The model defines non-negative decision variables on the edge inputs and outputs holding the remaining iteration time budget constraining the throughput.
% Each initial token charges up this value by one iteration time and each actor decrements it by the execution time.
% On actor inputs, the minimum of these values are propagated as a bound to the output.
% For the moment these values are called cycle residual times until better names are found.

% The number of actors in the graph


% Set of actors
set of int: ACTORS = 1..n;

% The graph topology as an adjacency matrix
array[ACTORS, ACTORS] of 0..1: graph;

% The number of tokens on each edge
array[ACTORS, ACTORS] of var 0..:   toks;

% The number of tokens on each edge


% The execution time of each actor


% The inverse of throughput: iteration time
var 0..sum(T): inv_thr;

% The residual cycle time on each edge input
array[ACTORS, ACTORS] of var 0..sum(graph)*sum(T): inp_res_time;

% The residual cycle time on each edge output
array[ACTORS, ACTORS] of var 0..sum(graph)*sum(T): out_res_time;

% Relate the output cycle residual times to the input cycle residual times for each edge
% The number of initial tokens times the iteration time is added to the edge input resdual cycle time of each edge
constraint forall (i, j in ACTORS where graph[i, j] == 1) (
    out_res_time[i, j] = inp_res_time[i, j] +   toks[i, j] * inv_thr
);

% Relate the input cycle residual times to the output cycle residual times in each actor
% The input cycle residual time of all outgoing edges must be equal to the minimum of the output cycle residual times of all incoming edges minus actor execution time
constraint forall (a in ACTORS) (
    forall (i in ACTORS where graph[a, i] == 1) (
        inp_res_time[a, i] <= min([out_res_time[j, a] | j in ACTORS where graph[j, a] == 1]) - T[a]
    )
);

% Fill out irrelevant cycle residual times
constraint forall (i, j in ACTORS where graph[i, j] == 0) (
    inp_res_time[i, j] = 0 /\ out_res_time[i, j] = 0 /\   toks[i, j] = 0
);

% Maximizing the throughput is equivalent to minimizing the inverse of the throughput (iteration period)
% solve minimize sum(  toks)*inv_thr;
% solve minimize sum(  toks);
 constraint sum(  toks)=3;

constraint forall(i,j in ACTORS)(graph[i,j]=0-> Arc[i,j]=<>);

constraint forall(i,j in ACTORS)(graph[i,j]=1 /\ toks[i,j] =0 ->Arc[i,j]=0 );

constraint forall(i,j in ACTORS)(graph[i,j]=1 /\ toks[i,j] !=0 ->Arc[i,j]=toks[i,j] );
% Output the inverse of the throughput, the throughput and the token matrix as a table
% output ["Inv Throughput (Iteration Period): \(inv_thr)ms\n"];
% output ["Throughput: \(1000 div inv_thr)\n"];
% output ["\nToken Matrix:\n"];
% output [show_int(3,   toks[i,j]) ++ if j == n then "\n" else " " endif | i, j in ACTORS];

%%%%%%%%% Data %%%%%%%%%
% The number of actors


%%%%%%%%% Data %%%%%%%%%

% Example Fig.1 in the paper
n=6;
%            h,  i,  j,  k,  l,  m
graph= [| 0,  1,  1, 0, 0, 0,
             | 0,  0,  0, 0,  1, 0,
             | 1,  0,  0, 0,  1,  1,
             | 1,  0,  0, 0,  0,   0,
             | 0,  0,  0, 0,  0,   1,
             | 0, 0, 0,  1, 0, 0|];
T = [1, 4, 2, 2, 1, 1];
s = 1; d = 6;

