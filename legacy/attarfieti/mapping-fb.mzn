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
 array[actors,actors] of var 0..1: ARC;

int: num_edges;
array[0..num_edges-1,1..2] of actors: edges;
%prefiling ARC with input HSDF
constraint forall(i,j in actors where graph[i,j]=1)(ARC[i,j]=1);
%to force two arc added to graph (i two independant actor are mapped on the same processor)
constraint forall(i,j in actors where P[i]=P[j] /\  (graph[i,j] !=1 \/ graph[j,i]!=1) ) (ARC[i,j]+ARC[j,i]=2);

% if there is a path from i to j 
 constraint forall(i,j,k in actors where P[i]=P[j] /\ (precedes[k,i]=1 -> P[k]=P[i] ) /\  (precedes[j,k]=1 -> P[k]=P[j] ) ) (ARC[j,i]=1);
 
 % to keep zeros stay 0 
 var int : pp = sum(ARC); 
 solve minimize pp;
 
 % stores weight of each path

  
  
   
  constraint P[0]+P[1]+P[2]=0;
  constraint P[3]+P[4]+P[5]+P[6]+P[7]=5;
%solve satisfy;

% output [show([true|i in 1..num_edges])];
n=8;
p=2;
graph =
[|   0: 1: 2: 3: 4: 5: 6: 7:
 |0: 0, 1, 1, 0, 0, 0, 0, 0
 |1: 0, 0, 0, 1, 0, 0, 0, 0
 |2: 0, 0, 0, 0, 1, 0, 0, 0
 |3: 0, 0, 0, 0, 0, 1, 1, 0
 |4: 0, 0, 0, 0, 0, 0, 1, 1
 |5: 0, 0, 0, 1, 1, 0, 0, 0
 |6: 0, 0, 0, 1, 0, 0, 0, 0
 |7: 0, 0, 0, 0, 1, 0, 0, 0
 |];
precedes =
[|   0: 1: 2: 3: 4: 5: 6: 7:
 |0: 1, 1, 1, 1, 1, 1, 1, 1
 |1: 0, 1, 0, 1, 1, 1, 1, 1
 |2: 0, 0, 1, 0, 1, 0, 1, 1
 |3: 0, 0, 0, 1, 1, 1, 1, 1
 |4: 0, 0, 0, 0, 1, 0, 1, 1
 |5: 0, 0, 0, 0, 1, 1, 1, 1
 |6: 0, 0, 0, 0, 0, 0, 1, 0
 |7: 0, 0, 0, 0, 0, 0, 0, 1
 |];
num_edges = 12;
edges = array2d(0..11,1..2,
[0, 1,
 0, 2,
 1, 3,
 2, 4,
 3, 5,
 3, 6,
 4, 6,
 4, 7,
 5, 3,
 5, 4,
 6, 3,
 7, 4
]);
