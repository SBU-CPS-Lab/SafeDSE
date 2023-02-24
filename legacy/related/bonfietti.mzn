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
% constraint ???;

%% The second model
array[actors,actors] of var 0..1: ARC;

% Existing arcs in the input HSDFG result in some pre-filling of the ARC matrix
constraint forall (i,j in actors) (graph[i,j]==1 -> ARC[i,j]==1);

% Two arcs added, if two independent nodes are mapped to the same processor
constraint forall (i,j in actors where i<j /\ precedes[i,j]+precedes[j,i]==0) (P[i]==P[j] -> ARC[i,j]+ARC[j,i]==2);

% close the scheduling loop
constraint forall (i,j in actors) (
  P[i]==P[j] /\
  sum (k in actors where k!=i /\ precedes[k,i]==1) (P[k]==P[i]) == 0 /\
  sum (k in actors where j!=k /\ precedes[j,k]==1) (P[k]==P[j]) == 0
    -> ARC[j,i]==1
);

%% The throughput constraint


%%
int: num_edges;
array[0..num_edges-1,1..2] of actors: edges;


  constraint P[0]+P[1]+P[3]=0;
  constraint P[2]+P[4]+P[5]+P[6]+P[7]=5;
solve satisfy;

% output [show([true|i in 1..num_edges])];