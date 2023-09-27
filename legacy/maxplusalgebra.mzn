% The number of actors in the graph
int: n_actors;

% Set of actors
set of int: ACTORS = 1..n_actors;

% n-th firing
 int:n=10;

%set of firings
set of int: N = 1..n;

% The graph topology as an adjacency matrix
array[ACTORS, ACTORS] of 0..1: graph;

% The number of initial tokens on each edge
array[ACTORS, ACTORS] of 0..100 : toks;

% The execution time of each actor
array[ACTORS] of int: exec_time;

%start time of n-th firing of actors
array[N,ACTORS] of var 0..:S;

%Number of channels
int:n_channels = sum(graph) ;

% Set of channels
set of int: CHANNELS = 1..n_channels;

%time when k-th token is produced on a channel
array[N,CHANNELS] of var 0..:F;

%%%
array[ACTORS, ACTORS] of var 0..n_channels: graph_channel;

array[ACTORS,ACTORS] of int:num_ch;

int:n_ini_tok = sum(toks) ;

array[1..n_ini_tok] of int : initial_tokens;
% constraint forall(i,j in ACTORS)(graph[i,j]=0 ->graph_channel[i,j]=0);

%  
% constraint forall(i,j in ACTORS)(graph[i,j] != 0 ->graph_channel[i,j]=sum(m,h in ACTORS where  m < i  )(graph[m,h] ));
% constraint forall(i,j in ACTORS)(graph[i,j] != 0 ->graph_channel[i,j]=sum(m,h in ACTORS where   m==i /\ h<= j )(graph[m,h] ));

%initial tokens are already there from the start
constraint forall(i,j in ACTORS , m in 1..n_ini_tok  )(toks[i,j] =1 -> F[1, m]=0);

%all input token should be available so that actor can excutes 
constraint forall(i,j in ACTORS, h in N where graph[i,j]=1   )( S[h,j]= max([F[ h, num_ch[m,j] ] | m in ACTORS where graph[m,j]==1 ]));

%after excecution of actor the tokens will be ready on out channels --UNSATISFIABLE - initial token should be taken from this constraint
constraint forall(i,j in ACTORS, h in N where graph[i,j]=1 )(F[h,num_ch[i,j]]=S[h,i]+exec_time[i]);

%DATA
% The number of actors
% n_actors = 3;
n_actors = 3;


% The graph topology
% graph = [|0, 0, 1,
%          |0, 0, 1,
%          |1, 1, 0
%          |];
graph = [|0, 0, 1,
         |0, 0, 1,
         |1, 1, 0
         |];

% The number of initial tokens on each edge
toks = [|0, 0, 0,
        |0, 0, 0,
        |1, 1, 0
        |];
num_ch = [|0, 0, 1,
         |0, 0, 2,
         |3, 4, 0
         |];

initial_tokens=[3,4];
% The execution time of each actor (ms)
% exec_time = [10, 20, 30];
exec_time = [10, 20, 30];
