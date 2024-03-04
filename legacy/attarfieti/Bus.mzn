array[aactors] of var opt 0..3*(C-1) : bus_redundant;
array[aactors] of var opt 0..C-1 : bus_nr;
set of int: r_b_actors = 0..21*n;
set of int: aactors = 0..(n-1)*(n-1);
set of int: procs = 0..P-1;
set of int: chans = 0..C-1;
array [r_b_actors, r_b_actors] of var opt  0 .. 1 : graph_bus;
int: n;      % number of actors
int: C = count_eq(array1d(graph),1);  % numer of channels
int: P;      % number of processors in the platform
set of int: actors = 0..n-1;
array[actors] of var procs: proc;
array[actors,actors] of int: graph;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%if there is no edge between nodes  
constraint forall(i,j in actors )(if graph[i,j] = 0 then bus_redundant[j+i*n]= <> else bus_redundant[j+i*n] != <> endif );
%constraint forall(i,j in aactors )(graph[i,j] != 0 -> bus_redundant[j+i*n] != <>);
%two constraint above are the summrize of this 4 constraints below
% constraint forall(i,j in aactors where i = 0 )(graph[i,] = 0 -> bus_redundant[j]= <>);
% constraint forall(i,j in aactors where i != 0 )(graph[i,] = 0 -> bus_redundant[j+i*n]= <>);
% constraint forall(i,j in aactors where i != 0 )(graph[i,] != 0 -> bus_redundant[j+i*n] != <>);
% constraint forall(i,j in aactors where i = 0 )(graph[i,] != 0 -> bus_redundant[j] != <>);
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

%if there is an edge between 2 nodes 
constraint forall(i,j in actors where graph[i,j]=1 )(if  proc[i] !=proc[j] then  bus_redundant[j+i*n] = 3 else bus_redundant[j+i*n] = 0 endif );
%the constraint above is the summrize of this 2 constraints below
% constraint forall(i,j in aactors)(graph[i,j]=1 /\ proc[i] !=proc[j] -> bus_redundant[j+i*n] = 3  ); %if they are on different processors
% constraint forall(i,j in aactors)(graph[i,j]=1 /\ proc[i] =proc[j] -> bus_redundant[j+i*n] = 0  ); %if they are on same processors

%for locating  3's in the array so we can calculate the extra nodes
% predicate count_threes(array[aactors] of var opt 0..3*(C-1): bus_redundant, var int: i ,var int: j) =
%     var int: ss = sum(x in 0..i, y in 0..j)(if bus_redundant[y+x*n] == 3 then 1 else 0 endif);



%filling the base graph in the modified graph based on bus considerations
% constraint forall(i,j in actors)(graph_bus[i,j] = graph[i,j]);

% to specify extra places in the array
var  0..: ub= sum(bus_redundant);
%to locate 3's in the array
array [aactors] of var opt 0.. : counting_threes;

constraint forall(i in aactors where i<=(ub/3)-1)( if i = 0 then counting_threes [i] = 3 else counting_threes [i] = counting_threes [i-1]+3 endif );

constraint forall(i in aactors where i>(ub/3)-1)(counting_threes [i] = <>); % to locate extra places


constraint forall(i ,j in r_b_actors)( i >= ub+n \/ j>=ub+n -> graph_bus[i,j] = <>); % to locate extra places in the modified graph

% to specify new relations and nodes in the graph
constraint forall(i in aactors where counting_threes[i] != <> )(
forall (x,y in aactors, m in 1..3 where bus_redundant[y+x*n]=3 )(graph_bus[n+(i+1)*3,(n+(i+1)*3)-1] + graph_bus[n+((i+1)*3)-1,n+(i+1)*3] =2)
);
constraint forall(i in aactors where counting_threes[i] != <> )(
forall (x,y in aactors, m in 1..3 where bus_redundant[y+x*n]=3 )(graph_bus[n+((i+1)*3)-2,(n+(i+1)*3)-1] + graph_bus[n+((i+1)*3)-1,n+((i+1)*3)-2] =2)
);

%to add edges from src(a) to block(a) 
constraint forall(i in aactors where counting_threes[i] != <> )(
forall (x,y in aactors, m in 1..3 where bus_redundant[y+x*n]=3 )(graph_bus[n+(i*3),x] + graph_bus[x,n+(i*3)] =2)
);



%to add edges from rec(a) to dest(a) 
constraint forall(i in aactors where counting_threes[i] != <> )(
forall (x,y in aactors, m in 1..3 where bus_redundant[y+x*n]=3 )(graph_bus[n+(i+1)*3,y] + graph_bus[y,n+(i+1)*3] =2)
);

array[0..C+P-1] of var 0..C+P-1: sendNext;
array[0..C+P-1] of var 0..C+P-1: recNext;
array[0..n+P-1] of var 0..n+P-1: next;
next = [1, 4, 3, 7, 5, 6, 2, 0];
sendNext = [1, 2, 4, 5, 3, 0];
recNext = [3, 5, 1, 4, 2, 0];

%for relations caused by next and sendNext Array's
constraint forall(i,j in actors)( next[i]=j -> bus_graph[i,j]=1); %next (happens when 2 actor are on the same processor)

constraint forall(i,j in  aactors)();