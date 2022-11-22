include "globals.mzn";
%% First level of the model

int: n;      % number of actors
int: p;      % number of processors in the platform
set of int: actors = 0..n-1;
set of int: procs = 0..p-1;

array[actors,actors] of int: graph;
array[actors,actors] of 0..1: precedes;

array[actors] of var 0..p-1: P;      % Pi: the processor allocated to actors
array[actors] of var -1..n-1: N;     % Ni: the actor following actor i if allocated on the same processor

% dependencies in the input SDFG cannot be violated
constraint forall(i,j in actors) ((precedes[i,j]==1)->(N[j]!=i));

% two nodes on the same resource cannot have the same successor
constraint forall(i,j in actors where i<j) (
  (P[i]==P[j] -> N[i]!=N[j]) /\
  (P[i]!=P[j] -> (N[i]!=j) /\ (N[j]!=i))
);
  
% The −1 value is given to the last node of each (non empty) processor
constraint forall(proc in procs) (
  sum(i in actors)(P[i]) > 0 -> sum(i in actors)(P[i]==proc /\ N[i]==-1) == 1
);

% the transitive closure on the actors running on a single processor is kept by posting a nocycle constraint


%% The second model
% array[actors,actors] of var bool: ARC;

int: num_edges;
array[0..num_edges-1,1..2] of actors: edges;


  constraint P[0]+P[1]+P[2]=0;
  constraint P[3]+P[4]+P[5]+P[6]+P[7]=5;
solve satisfy;

% output [show([true|i in 1..num_edges])];