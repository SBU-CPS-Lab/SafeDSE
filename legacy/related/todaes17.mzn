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

constraint forall (i in actors) (
  let {
    array[actors] of bool: ispred = array1d(actors,[graph[j,i]=1/\(d[j,i]=0) | j in actors]);
  } in 
    link_set_to_booleans(preds[i], ispred)
);  % 39

constraint forall(i in actors, p in procs) (card(preds[i])=0 /\ next[n+p]=i <-> rank[i]=0 /\ (proc[i]=(p+1) mod P));  % 40

constraint forall (i,j in actors) (next[j]=i -> rank[i] = max (k in (preds[i] union {j})) (rank[k]) + 1);  %41

constraint forall (i in actors, j in n..(n+P-2)) (next[j]=i -> rank[i] = max (k in preds[i]) (rank[k]) + 1);  %42 FIXME: j is up to n+P-1 in the paper

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


  constraint proc[0]+proc[1]+proc[4]=0;
  constraint proc[2]+proc[3]=2;
solve satisfy;

output [show(chans) ++ "\n" ++ show(src) ++ "\n" ++ show(dst) ++ "\n" ++ show(tok)];