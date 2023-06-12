% Minizinc model of TODAES'17 paper from ROSVALL and SANDER
% https://doi.org/10.1145/3133210
include "globals.mzn";
%% First level of the model
% Parameters
int: n;      % number of actors
int: C = count_eq(array1d(graph),1);  % numer of channels
int: P;      % number of processors in the platform
set of int: actors = 0..n-1;
set of int: procs = 0..P-1;
set of int: chans = 0..C-1;
array[actors,actors] of int: graph;
array[actors,actors] of int: d;
array[actors,actors] of 0..1: precedes;
array[chans] of actors: src = array1d(chans,[i|i,j in actors where graph[i,j]=1]);
array[chans] of actors: dst = array1d(chans,[j|i,j in actors where graph[i,j]=1]);
array[chans] of int: tok = array1d(chans,[d[i,j]|i,j in actors where graph[i,j]=1]);
% set of 0..n*n-1: chanset = {i*n+j|i,j in actors where graph[i,j]=1};

% Decision Variables
array[actors] of var procs: proc;
array[0..n+P-1] of var 0..n+P-1: next;
array[actors] of var 0..n-1: rank;
array[actors] of var set of actors: preds;
% array[actors] of 0..: wcet;
array[0..C+P-1] of var 0..C+P-1: sendNext;
array[0..C+P-1] of var 0..C+P-1: recNext;
% array[chans] of var 0..: buffer_r;  % TODO: constrain the domain
% array[chans] of var 0..: buffer_s;  % TODO: constrain the domain
% var int period;
% var int transPhase;

% Constraints

constraint circuit(next);              % 13

constraint forall(i,j in actors) (precedes[i,j]=1 -> next[j]!=i);  % 14

constraint forall (i,j in actors) (precedes[i,j]=1 /\ proc[i]=proc[j] -> next[i]<n);  % 15

constraint forall (i,j,k in actors) (precedes[i,j]=1 /\ next[k]=i -> next[j]!=k);  %16

constraint forall (i,j,k in actors) (precedes[i,j]=1 /\ next[j]=k -> next[k]!=i);  %17

constraint forall (i,j,k,l in actors) (precedes[i,j]=1 /\ next[k]=i /\ next[j]=l -> next[l]!=k);  %18

constraint forall (i,j in actors) (proc[i]!=proc[j] -> next[i]!=j);  %19

constraint forall (i,j in actors) (next[i]=j \/ next[j]=i -> proc[i]=proc[j]);  %20

constraint forall (i,j in actors where i!=j) (next[i]>=n /\ next[j]>=n -> proc[i]!=proc[j]);  %21

constraint forall (i in actors) (next[i] != i);  %22

% TODO %23

constraint forall (i in actors, p in procs) (proc[i]!=((p+1) mod P) -> next[n+p]!=i);  %24

constraint forall (p in procs) (sum (i in actors) (proc[i] = (p+1) mod P) = 0 -> next[n+p] = n+(p+1) mod P);  %25

constraint forall (i,j in actors, p in procs) (next[i]=j -> next[n+p]!=j);  %26

constraint forall (i,j in actors, p in procs) (precedes[i,j]=1 /\ proc[i]=proc[j] -> next[n+p]!=j);  %27

constraint forall (i in actors, p in procs) (proc[i]!=p -> next[i] != n+p);  %28

constraint forall (i,j in actors) (precedes[i,j]=1 -> rank[i]<rank[j]);  %29

constraint forall (i,j in actors) (next[i]=j -> rank[i]<rank[j]);  %30

constraint forall (i,j in actors where i!=j) (next[i]>=n /\ proc[i]=proc[j] -> rank[i]>rank[j]);  %31

constraint forall (i in actors, p in procs) (next[i]=n+p -> rank[i]>=sum(j in actors)(proc[j]=p)-1);  %32

% TODO %33

constraint forall (i,j,k in actors where j!=k) (precedes[i,j]=1 /\ proc[i]=proc[j] /\ next[i]=k -> rank[j]>rank[k]);  %34

constraint forall (i,j,k in actors where i!=k) (precedes[i,j]=1 /\ proc[i]=proc[j] /\ next[k]=j -> rank[i]<rank[k]);  %35

constraint forall (i,j in actors where i!=j) (proc[i]=proc[j] -> rank[i]!=rank[j]);  %36

constraint forall (i,j in actors) (rank[i]<rank[j] -> next[j]!=i);  %37

constraint sum (i in actors) (rank[i]=0) >= 1;  %38

constraint forall(i in actors)(preds[i]={j | j in actors where graph[j,i]=1 /\ d[j,i]=0});
% 39

constraint forall(i in actors, p in procs) (card(preds[i])=0 /\ next[n+p]=i <-> rank[i]=0 /\ (proc[i]=(p+1) mod P));  % 40

constraint forall (i,j in actors) (next[j]=i -> rank[i] = max (k in (preds[i] union {j})) (rank[k]) + 1);  %41

constraint forall (i in actors, j in n..(n+P-1)  ) ( next[j]=i -> if card(preds[i])!=0 then    rank[i] = max (k in preds[i]) (rank[k]) + 1 else true endif);  %42 FIXME: j is up to n+P-1 in the paper

constraint circuit(sendNext);  % 43

constraint circuit(recNext);  % 44

constraint forall (i,j in chans where i!=j) (proc[src[i]]!=proc[src[j]] -> sendNext[i]!=j);  %45

constraint forall (i,j in chans where i!=j) (proc[dst[i]]!=proc[dst[j]] -> recNext[i]!=j);  %46

constraint forall (i,j in chans where i!=j) (proc[src[i]]=proc[src[j]] /\ rank[src[i]]<rank[src[j]] -> sendNext[j]!=i);  %47

constraint forall (i,j in chans where i!=j) (proc[dst[i]]=proc[dst[j]] /\ rank[dst[i]]<rank[dst[j]] -> recNext[j]!=i);  %48

constraint forall (i,j in chans where i!=j /\ src[i]=src[j]) (
  proc[dst[i]]=proc[dst[j]] /\ rank[dst[i]]<rank[dst[j]] -> sendNext[j]!=i
);  %49

constraint forall (i,j in chans where i!=j /\ src[i]=src[j]) (precedes[dst[i],dst[j]]=1 -> sendNext[j]!=i);  %50

constraint forall (i,j in chans where i!=j /\ dst[i]=dst[j]) (
  tok[i]=tok[j] /\ proc[src[i]]=proc[src[j]] /\ rank[src[i]]<rank[src[j]] -> recNext[j]!=i
);  %51

constraint forall (i,j in chans where i!=j /\ src[i]=src[j]) (
  proc[dst[i]]=proc[dst[j]] /\ proc[src[i]]=proc[dst[i]] -> sendNext[j]!=i
);  %52

constraint forall (i,j in chans where i!=j /\ dst[i]=dst[j]) (
  proc[src[i]]!=proc[src[j]] /\ proc[dst[i]]=proc[src[i]] -> recNext[j]!=i
);  %53

constraint forall (c in chans) (sendNext[c]!=c);  % 54

constraint forall (c in chans) (recNext[c]!=c);  % 55

constraint forall (i in chans, p in procs) (proc[src[i]] != (p+1) mod P -> sendNext[C+p]!=i);  % 56

constraint forall (i in chans, p in procs) (proc[dst[i]] != (p+1) mod P -> recNext[C+p]!=i);  % 57

constraint forall (p in procs) (sendNext[C+p]<C \/ sendNext[C+p]=(p+1) mod P);  % 58

constraint forall (p in procs) (recNext[C+p]<C \/ recNext[C+p]=(p+1) mod P);  % 59


%%%%%%Farnoushhh
set of int: r_actors = 0..7*n;

%DECISION VARIABLES 
array [r_actors , r_actors] of var  0..1 : graph_p;
array [actors] of  var 0..5: pattern_using;
array [actors] of  var 0..7*n-n: pattern_redundant;
array [actors] of 1..4: actor_sil; 


%PATTERN_USING[I]=0 -> NO PATTERN
%PATTERN_USING[I]=1 -> MIXED SIL FAIL SILENT
%PATTERN_USING[I]=2 -> HIGH SIL FAIL OPERATIONAL 
%PATTERN_USING[I]=3 -> LOW SIL DOER/CHECKER
%PATTERN_USING[I]=4 -> Low SIL,FAIL SILENT Hardware
%PATTERN_USING[I]=5 -> HIGH SIL FAIL SILENT 

constraint 
                   forall (i in actors where actor_sil[i]=3 /\ i !=0 )  (pattern_using[i]=0 /\ pattern_redundant[i]=pattern_redundant[i-1])
                   \/ 
                   forall (i in actors where actor_sil[i]=3 /\ i!=0) (pattern_using[i]=1 /\ pattern_redundant[i]=pattern_redundant[i-1] + 2 ) 
                   \/
                   forall (i in actors where actor_sil[i]=3 /\ i!=0) ( pattern_using[i]=2 /\ pattern_redundant[i]=pattern_redundant[i-1] + 7)
                   \/
                   forall (i in actors where actor_sil[i]=3 /\ i!=0) ( pattern_using[i]=3 /\ pattern_redundant[i]=pattern_redundant[i-1] + 1)
                   \/
                   forall (i in actors where actor_sil[i]=3 /\ i!=0) ( pattern_using[i]=4 /\ pattern_redundant[i]=pattern_redundant[i-1] + 1)
                   \/
                   forall (i in actors where actor_sil[i]=3 /\ i!=0) ( pattern_using[i]=5 /\ pattern_redundant[i]=pattern_redundant[i-1] + 3)
              ;
              
 %FOR FIRST INDEX IN PATTERN_REDUNDANT :)
constraint
                   forall (i in actors where actor_sil[i]=3 /\ i=0) ( pattern_using[i]=0 /\ pattern_redundant[i]=0 )
                   \/
                   forall (i in actors where actor_sil[i]=3 /\ i=0) ( pattern_using[i]=1 /\ pattern_redundant[i]=2 )
                   \/
                   forall (i in actors where actor_sil[i]=3 /\ i=0) ( pattern_using[i]=2 /\ pattern_redundant[i]=7 )
                   \/
                   forall (i in actors where actor_sil[i]=3 /\ i=0) ( pattern_using[i]=3 /\ pattern_redundant[i]=1 )    
                   \/
                   forall (i in actors where actor_sil[i]=3 /\ i=0) ( pattern_using[i]=4 /\ pattern_redundant[i]=1 )      
                   \/
                   forall (i in actors where actor_sil[i]=3 /\ i=0) ( pattern_using[i]=5 /\ pattern_redundant[i]=3 )          
               ;
               
%%%%%%%%
%filling graph_p with our original graph First :)
constraint forall ( i,j in actors)(graph_p[i,j]=graph[i,j]);
%forcing extra places to be 0 
constraint forall(i,j in r_actors)(i > n+pattern_redundant[n-1]+n-1 \/ j > n+pattern_redundant[n-1]+n-1 -> graph_p[i,j]=0);

%MIXED SIL FAIL SILENT
%out edges to checkers --> -1 primary checker /\ -2 secondary checker
constraint forall(i in actors  where pattern_using[i]=1)(  graph_p[i,pattern_redundant[i]+n-1] + graph_p[i , pattern_redundant[i]+n-2]=2);
%cross check edges between checkers 
constraint forall(i in actors where pattern_using[i]=1)( graph_p[pattern_redundant[i]+n-1,pattern_redundant[i]+n-2] + graph_p[pattern_redundant[i]+n-2 , pattern_redundant[i]+n-1]=2 );
%edge from primary checker to doer
constraint forall(i in actors where pattern_using[i]=1)(graph_p[pattern_redundant[i]+n-2 , i]=1);
 % primary doer in edges  should be in edges for  both checkers
 constraint forall(i,j in actors where pattern_using[i]=1 /\ graph[j,i]=1)(graph_p[j,pattern_redundant[i]+n-2] + graph_p[j,pattern_redundant[i]+n-1] = 2);
               
%%%%%%%%%
%HIGH SIL FAIL OPERATIONAL   %% THIS PATTERN SHOULD BE CHECKED //INCONSISTENCY ERROR 
%cross check between primary doer and its checker
constraint forall(i in actors where pattern_using[i]=2 )(graph_p[i,pattern_redundant[i]+n -7] + graph_p[pattern_redundant[i]+n-7,i]=2);
%cross check between secondary checker and its checker
 constraint forall(i in actors where pattern_using[i]=2 )(graph_p[pattern_redundant[i]+n-6 , pattern_redundant[i]+n-5]=2);
 %primary doer and secondary doer should be in edges to each others checker
 constraint forall(i in actors where pattern_using[i]=2)(graph_p[i,pattern_redundant[i]+n -5 ] + graph_p[pattern_redundant[i]+n-6 , pattern_redundant[i]+n-7]=2);
 % primary doer inp edges  should be in edges for seconadry doer and both checkers
 constraint forall(i,j in actors where graph[j,i]=1 /\ pattern_using[i]=2  )(graph_p[j,pattern_redundant[i]+n-7]+graph_p[j,pattern_redundant[i]+n-6] + graph_p[j,pattern_redundant[i]+n-5]=3);
 % cross check between teritary doer and it's checker
 constraint forall(i in actors where pattern_using[i]=2 )(graph_p[pattern_redundant[i]+n-4 , pattern_redundant[i]+n-3] + graph_p[pattern_redundant[i]+n-3 , pattern_redundant[i]+n-4] =2);
  % cross check between quaternary doer and it's checker
 constraint forall(i in actors where pattern_using[i]=2 )(graph_p[pattern_redundant[i]+n-1 , pattern_redundant[i]+n-2] + graph_p[pattern_redundant[i]+n-2 , pattern_redundant[i]+n-1] =2);
  % primary doer inp edges  should be in edges for teritary and quemetary doers and both checkers
 constraint forall(i,j in actors where graph[j,i]=1 /\ pattern_using[i]=2  )(graph_p[j,pattern_redundant[i]+n-1]+graph_p[j,pattern_redundant[i]+n-2] + graph_p[j,pattern_redundant[i]+n-3] + graph_p[j,pattern_redundant[i]+n-4] =4);
 %  teritary doer and quematry doer should send data to each others checkers
 constraint forall(i in actors where pattern_using[i]=2)(graph_p[pattern_redundant[i]+n-4 , pattern_redundant[i]+n-1] + graph_p[pattern_redundant[i]+n-2, pattern_redundant[i]+n-3] =  2);
 %%%%%VOTER

 
% LOW SIL DOER/CHECKER
%cross check between doer and its checker
constraint forall(i in actors where pattern_using[i]=3)(graph_p[i,pattern_redundant[i]+n-1] + graph_p[pattern_redundant[i]+n-1 , i]=1);
%doer input edges should be input edges to checker
constraint forall(i,j in actors where graph[j,i] =1 /\ pattern_using[i]=3)(graph_p[j,pattern_redundant[i]+n-1]=1);

%Low SIL,FAIL SILENT Hardware
%cross check between doer and its checker
constraint forall(i in actors where pattern_using[i]=4)(graph_p[i,pattern_redundant[i]+n-1] + graph_p[pattern_redundant[i]+n-1 , i]=1);
%doer input edges should be input edges to checker
constraint forall(i,j in actors where graph[j,i] =1 /\ pattern_using[i]=4)(graph_p[j,pattern_redundant[i]+n-1]=1);

%HIGH SIL FAIL SILENT
%TODO

%NEW PRECEDES ARRAY CONSIDERING NEW ACTORS 
array [r_actors,r_actors] of var -1..1 : precedes_p;
constraint forall(i,j in actors)(precedes[i,j]=precedes_p[i,j]);
%extra places in our array shold be -1
%TODO

%MIXED SIL FAIL SILENT
constraint forall(i,j in actors, h in n-2 .. n-1 where pattern_using[i]=1)(precedes_p[j,pattern_redundant[i]+h]=precedes[j,i]);

%  HIGH SIL FAIL OPERATIONAL  // if there is path from j to i then there is a path to all redundant actors for this pattern :) 
%%CHECK 
constraint forall(i,j in actors, h in n-1..n-7 where pattern_using[i]=2)( precedes_p[j,pattern_redundant[i]+h]=precedes[j,i]);

% LOW SIL DOER/CHECKER // if there is a path for j to i then there is also a path from j to i's checker
constraint forall(i,j in actors where pattern_using[i]=3)(  precedes_p[j,pattern_redundant[i]+n-1]=precedes[j,i]); 

%Low SIL,FAIL SILENT Hardware // if there is a path for j to i then there is also a path from j to i's checker
constraint forall(i,j in actors where pattern_using[i]=4)(  precedes_p[j,pattern_redundant[i]+n-1]=precedes[j,i]); 

%HIGH SIL FAIL SILENT
%TODO

constraint forall(i in actors)(pattern_using[i] !=0);
constraint forall(i in actors)(pattern_using[i] !=5);

%SHOULD BE EDITED
% %%%%%COST           -- r_actors_sil is defined for capturing everyones SIL :)
% array[r_actors] of var int: cost_array;

% %% computing Cost
% %if we have extra placs for redundant actors
% constraint forall(i in r_actors)(r_actors_sil[i]=0 -> cost_array[i]=0);
% % if there is an actor with higher sil beside a actor with lower sil   //FOR DOER
% constraint forall(i,j in r_actors)(proc[i]=proc[j] /\ r_actors_sil[i] < r_actors_sil[j] /\ checker_array[i]=0-> cost_array[j] = 0 );

% constraint forall(i in r_actors )(n <= i  /\ i <= pattern_redundant[n-1]+n-1   -> doer_array[i]=0 \/ checker_array[i] =0 );

% % checker array  -- it's necessary for computing cost ---- checkers have different costs :)
% array[r_actors] of var 0..3*n+n+1 : checker_array;
% array[r_actors] of var 0..3*n+n+1 : doer_array;
% %no primary actor can be its checker 
% constraint forall(i in actors)(checker_array[i]=0);
% % when we have extra places
% constraint forall(i in r_actors)(r_actors_sil[i]=0 -> checker_array[i]=0);
% constraint forall(i in r_actors)(r_actors_sil[i]=0 -> doer_array[i]=0); 
 
% %%%%
% array[r_actors]of var 0..4: r_actors_sil;
% %when we have extra places in our array 
% constraint forall(i in r_actors)(i>pattern_redundant[n-1]+n-1 -> r_actors_sil[i]=0);
% %NO PATTERN == PATTERN_USING[I]=0 /\ r_actors_sil[i]=0 == ther no actor :)
% constraint forall(i in actors )(pattern_using[i]=0->r_actors_sil[i]=actor_sil[i]);
% %every primary doer it's it's own doer  //+1 -> mumber of acctors starts with zero but in this array 0 means this number is extra place
% constraint forall(i in actors)(doer_array[i]=i+1);

% %MIXED SIL FAIL SILENT
% % primary Doer with Low SIL=2
% constraint forall(i in actors )(pattern_using[i]=1->r_actors_sil[i]=2);
% % primary Checker with high SIL=4
% constraint forall(i in actors)(pattern_using[i]=1-> r_actors_sil[pattern_redundant[i]+n-1] =4);
% % specifying checker in the array
% constraint forall(i in actors)(pattern_using[i]=1->checker_array [pattern_redundant[i]+n-1] =i+1);
% % secondary Checker(for checking the primary checker) with high SIL=4
% constraint forall(i in actors)(pattern_using[i]=1-> r_actors_sil[pattern_redundant[i]+n-2] =4);
% % specifying checker in the array
% constraint forall(i in actors)(pattern_using[i]=1->checker_array [pattern_redundant[i]+n-2] =i+1);


% %  HIGH SIL FAIL OPERATIONAL 
% %primary  Doer with high SIL=4
% constraint forall(i in actors)(pattern_using[i]=2 -> r_actors_sil[i]=4);
% %First Checker for primary doer with high SIL=4
% constraint forall(i in actors)(pattern_using[i]=2 -> r_actors_sil[pattern_redundant[i]+n-7]=4);
% % specifying checker in the array
% constraint forall(i in actors)(pattern_using[i]=2 -> checker_array[pattern_redundant[i]+n-7]=i+1);
% %Secondary Doer with high SIL=4
% constraint forall(i in actors)(pattern_using[i]=2 -> r_actors_sil[pattern_redundant[i]+n-6]=4);
% %specifying Second Doer in the array
% constraint forall(i in actors)(pattern_using[i]=2 -> doer_array[pattern_redundant[i]+n-6]= i+1);
% %Second checker for Secondary Doer with High SIL=4
% constraint forall(i in actors)(pattern_using[i]=2 -> r_actors_sil[pattern_redundant[i]+n-5]=4);
% % specifying checker in the array
% constraint forall(i in actors)(pattern_using[i]=2 -> checker_array[pattern_redundant[i]+n-5]=i+1);
% %tertiary Doer with high SIL=4
% constraint forall(i in actors)(pattern_using[i]=2 -> r_actors_sil[pattern_redundant[i]+n-4]=4);
% %specifying third Doer in the array
% constraint forall(i in actors)(pattern_using[i]=2 -> doer_array[pattern_redundant[i]+n-4]= i+1);
% %third checker for teritary Doer with high SIL=4
% constraint forall(i in actors)(pattern_using[i]=2 -> r_actors_sil[pattern_redundant[i]+n-3]=4);
% % specifying checker in the array
% constraint forall(i in actors)(pattern_using[i]=2 -> checker_array[pattern_redundant[i]+n-3]=i+1);
% %quaternary Doer with high SIL=4
% constraint forall(i in actors)(pattern_using[i]=2 -> r_actors_sil[pattern_redundant[i]+n-2]=4);
% %specifying fourth Doer in the array
% constraint forall(i in actors)(pattern_using[i]=2 -> doer_array[pattern_redundant[i]+n-2]= i+1);
% %fourth checker for quaternary Doer with high SIL=4
% constraint forall(i in actors)(pattern_using[i]=2 -> r_actors_sil[pattern_redundant[i]+n-1]=4);
% % specifying checker in the array
% constraint forall(i in actors)(pattern_using[i]=2 -> checker_array[pattern_redundant[i]+n-1]=i+1);


% % LOW SIL DOER/CHECKER
% %primary Doer with low SIL=1
% constraint forall(i in actors)(pattern_using[i]=3 -> r_actors_sil[i]=1);
% %checker for primary Doer with low SIL=2
% constraint forall(i in actors)(pattern_using[i]=3 -> r_actors_sil[pattern_redundant[i]+n-1]=2);
% % specifying checker in the array
% constraint forall(i in actors)(pattern_using[i]=3 -> checker_array[pattern_redundant[i]+n-1]=i+1);


% %Low SIL,FAIL SILENT Hardware
% %primary doer with low SIL=1
% constraint forall(i in actors)(pattern_using[i]=4 -> r_actors_sil[i]=1);
% %checker for primary Doer with low SIL=2
% constraint forall(i in actors)(pattern_using[i]=4 -> r_actors_sil[pattern_redundant[i]+n-1]=2);
% % specifying checker in the array
% constraint forall(i in actors)(pattern_using[i]=4 -> checker_array[pattern_redundant[i]+n-1]=i+1);


% %HIGH SIL FAIL SILENT  
% %primary doer with high SIL=3
% constraint forall(i in actors)(pattern_using[i]=5 -> r_actors_sil[i]=3);
% %first checker for primary doer
% constraint forall(i in actors)(pattern_using[i]=5->r_actors_sil[pattern_redundant[i]+n-3]=3);
% % specifying checker in the array
% constraint forall(i in actors)(pattern_using[i]=5 -> checker_array[pattern_redundant[i]+n-3]=i+1);
% %secondary doer with high SIL=3
% constraint forall(i in actors)(pattern_using[i]=5->r_actors_sil[pattern_redundant[i]+n-2]=3);
% %specifying Second Doer in the array
% constraint forall(i in actors)(pattern_using[i]=5 -> doer_array[pattern_redundant[i]+n-2]= i+1);
% %second checker for secondary Doer with high SIL=3
% constraint forall(i in actors)(pattern_using[i]=5  -> r_actors_sil[pattern_redundant[i]+n-1]=3);
% % specifying checker in the array
% constraint forall(i in actors)(pattern_using[i]=5 -> checker_array[pattern_redundant[i]+n-1]=i+1);



%%%%%%%%%%%%%%%%%%%
  constraint proc[0]+proc[1]+proc[4]=0;
  constraint proc[2]+proc[3]=2;
solve satisfy;

%output [show(chans) ++ "\n" ++ show(src) ++ "\n" ++ show(dst) ++ "\n" ++ show(tok)];
