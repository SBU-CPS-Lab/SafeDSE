

% Use this editor as a MiniZinc scratch book
% Define the number of actors and the adjacency matrix
int: num_actors;
array[1..num_actors, 1..num_actors] of int: adjacency_matrix;

% Variables to represent start times of actor executions
array[1..num_actors] of var int: start_times;

% Constraints to ensure dependencies are respected
constraint forall(i in 1..num_actors, j in 1..num_actors where adjacency_matrix[i, j] == 1) (
    start_times[i] + 1 <= start_times[j]
);

% Find the maximum start time, which corresponds to the cycle time
var int: cycle_time = max(start_times);

% Objective: minimize the cycle time
solve minimize cycle_time;

% Output the cycle time (throughput)
output ["Cycle Time (Throughput): \(cycle_time)\n"];

num_actors = 3;
adjacency_matrix = [| 0, 1, 1
                     | 0, 0, 1
                     | 0, 0, 0 |];