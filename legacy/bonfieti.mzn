% Use this editor as a MiniZinc                    scratch book
int : num_a;
%dzn
num_a=3;
%

int:num_p;
%dzn
num_p=6;

% pi represent the processor allocated to actor i 
array [0..num_a-1  ] of var 0..num_p-1  : p;

% ni represent the actor following actor i if allocated on the same processor 
array [0..num_a-1 ] of var -1..num_a-1 : n;

% 2 nodes on the same resource cannot have the same successor
%constraint forall (i in 0..num_a-1  )(
        %        forall(j in 0..num_a-1  where p[i]=p[j])(n[i] != n[j])
     %          );
               
% dependencies in the input sdfg cannot be violated
 array[1.. num_a, 1..num_a] of 0..1: path;
 %dzn
path = [|0,1,0
                       |1,1,1
                       |1,1,1|];
constraint
             forall ( i in 0..num_a-1  )(
             forall ( j in 0..num_a-1  where path[i,j]=1)(n[j] != i )
               );