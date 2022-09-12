
int: no_actors;
int: no_processors;
array[1..no_actors] of 1..4: actor_sil;
array[1..4*no_actors,1..4*no_actors] of var 0..1: Redundancy_level;
var int: pattern_cost;
var int: safety_levels;
var int: pattern_availability;
array [1..no_actors] of var 0..12: r;
array [1..no_actors] of var 0..200: pattern_cost_graph;
array [1..no_actors] of var 0..350: pattern_availability_graph;
array [1..no_actors] of var 0..4: redundancy_graph;
var int: n;
var int: redundant;
array [1..4*no_actors] of var 1..no_processors: actor_mapping;

%%%%
%constraint   forall( i in 1..no_actors+redundant   ) (
   %               forall (j in 1..no_actors+redundant where Redundancy_level[i,j]=1  )
      %   (actor_mapping [i] != actor_mapping[j]));
%%%%
constraint
 forall(i in 1..no_actors where actor_sil[i]=1)               ( Redundancy_level [i,sum(redundancy_graph)+no_actors+1] = 0 /\  pattern_cost_graph[i]=0 /\  redundancy_graph[i]=0 /\ r[i]=0 )
/\
forall(i in 1..4*no_actors)(Redundancy_level[i,i]=0)
/\
 forall(i in 1..no_actors where actor_sil[i]=1)               ( Redundancy_level [i,sum(redundancy_graph)+no_actors+1] = 0 /\  pattern_cost_graph[i]=0 /\  redundancy_graph[i]=0 /\ r[i]=0 )
;
 
 
 % constraint for sil2
constraint
 forall(i in 1..no_actors where actor_sil[i]=2)               ( Redundancy_level [i,sum(redundancy_graph)+no_actors+1] = 0 /\  pattern_cost_graph[i]=0 /\  redundancy_graph[i]=0 /\ r[i]=0 )
/\

 forall(i in 1..no_actors where actor_sil[i]=2)               ( Redundancy_level [i,sum(redundancy_graph)+no_actors+1] = 0 /\  pattern_cost_graph[i]=0 /\  redundancy_graph[i]=0 /\ r[i]=0 )
;
 %constraint patterns for sil 4
constraint forall (i in 1..no_actors where  actor_sil[i]=4) 
               ( Redundancy_level [i,sum(redundancy_graph)+no_actors+1] = 1 /\  pattern_cost_graph[i]=100 /\  redundancy_graph[i]=1 /\ r[i]=2 )
              \/
                forall (i in 1..no_actors where  actor_sil[i]=4) 
               ( Redundancy_level [i,sum(redundancy_graph)+no_actors+1] = 1/\ Redundancy_level [i,sum(redundancy_graph)      +no_actors+2] = 1 /\ Redundancy_level [i,sum(redundancy_graph)+no_actors+3] = 1 /\ Redundancy_level [ sum(redundancy_graph)+no_actors+1,sum(redundancy_graph)+no_actors+2] = 1 /\ Redundancy_level [ sum(redundancy_graph)+no_actors+1,sum(redundancy_graph)+no_actors+3] = 1 /\ Redundancy_level [ sum(redundancy_graph)+no_actors+2,sum(redundancy_graph)+no_actors+3] = 1 /\  Redundancy_level [i,no_actors] = 1 /\  pattern_cost_graph[i]=200 /\ redundancy_graph[i]=3 /\ r[i]=12 ) ;


 %constraint patterns for sil 3
constraint forall (i in 1..no_actors where  actor_sil[i]=3) 
               ( Redundancy_level [i,sum(redundancy_graph)+no_actors+1] = 1 /\  pattern_cost_graph[i]=100 /\  redundancy_graph[i]=1 /\ r[i]=2 )
              \/
                forall (i in 1..no_actors where  actor_sil[i]=3) 
               ( Redundancy_level [i,sum(redundancy_graph)+no_actors+1] = 1/\ Redundancy_level [i,sum(redundancy_graph)      +no_actors+2] = 1 /\ Redundancy_level [i,sum(redundancy_graph)+no_actors+3] = 1 /\ Redundancy_level [ sum(redundancy_graph)+no_actors+1,sum(redundancy_graph)+no_actors+2] = 1 /\ Redundancy_level [ sum(redundancy_graph)+no_actors+1,sum(redundancy_graph)+no_actors+3] = 1 /\ Redundancy_level [ sum(redundancy_graph)+no_actors+2,sum(redundancy_graph)+no_actors+3] = 1 /\  Redundancy_level [i,no_actors] = 1 /\  pattern_cost_graph[i]=200 /\ redundancy_graph[i]=3 /\ r[i]=12 ) ;
%safety level
constraint forall (i in 1.. no_actors)(safety_levels=sum(r));

   % computing pattern cost              
constraint  forall (i in 1..no_actors)(pattern_cost = sum(pattern_cost_graph))          
;   

% %%%



%%%%%
redundant=sum(redundancy_graph);
n= sum(Redundancy_level);                     
%computing array for mapping


 solve  minimize pattern_cost;
 
 output [ 
    "r= \(r);\n" ,
    "pattern_cost= \(pattern_cost);\n" ,
      "n = \(n);\n", 
       "redundant = \(redundant);\n" ,
       "actor_mapping = \(actor_mapping);\n"          
    ];  
 %%%MZN  
actor_sil=[1,3,3,4,4];   
no_processors=5;
no_actors=5;