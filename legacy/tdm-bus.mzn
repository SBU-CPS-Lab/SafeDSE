% Model for mapping HSDF on a system with a TDM BUS

int: no_processors ;
int: no_actors;
array[1..no_actors] of int: actor_flow;
 int: processor_load_capacity; % homogenous platform
array[1..no_processors] of var 0 .. processor_load_capacity : processor_load;
array[1..no_actors] of 1..4: actor_sil;
var  0..10000: developement_cost;
array [1..no_actors, 1..no_actors] of var 0..150: cost_graph;
int: safety_levels;
array[1..safety_levels] of 1..no_actors: Redundancy_level;
array [1..no_actors] of var 1..no_processors: actor_mapping;
array[1..no_actors ,1.. no_actors] of 0..1: hsdf; 
int: bus_bandwidth;
%int: mode;
array[1..no_actors] of int : actor_bandwidth;
%var  no_actors .. no_actors*no_actors: scheduling_size;
array[no_actors..no_actors*no_actors] of var 1..no_actors : scheduling;
%array [1..no_processors] of var int: monetary_cost;
%array [1..mode] of int : monetary_processor;
%array[1..mode]of  int : mode_processor_load;

%dzn
%mode=3;
%monetary_processor=[500,1200,4000];
%mode_processor_load=[1500,2500,6000];

 actor_flow=[500,500,500,500,500];
processor_load_capacity=1500;
no_processors=5;
no_actors=5;
safety_levels= 6;
Redundancy_level= [1,2,1,3,2,3];
 actor_sil=[1,2,3,4,4];
bus_bandwidth=340;
actor_bandwidth=[140,140,140,100,90];
hsdf= [| 0,0,0,1,1
           | 0,0,0,1,1
           | 0,0,0,0,1
           | 0,0,0,0,0
           | 0,0,0,0,0 |];
            
                                  
%dzn
%processor_cost=1000;
%actor_safety_level=3;

%Safety   constraint 
constraint   forall( i in 1..safety_levels-1 where i/2 !=0   )
         (actor_mapping [Redundancy_level[i]] != actor_mapping[Redundancy_level[i+1]]);
      
            
%constraint  processors' load and compute processor load // i should change it to bin_packing_load constraint

 constraint 
   forall (i in 1..no_processors) (sum (j in 1..no_actors where actor_mapping[j]=i )(actor_flow[j])<=processor_load_capacity)
 
   /\
   forall (i in 1..no_processors) (processor_load[i] = sum (j in 1..no_actors where actor_mapping[j]=i )(actor_flow[j]))
 
 ;
 
 %constraint developement cost
 constraint forall (i in 1..no_actors) (
                           forall(j in i+1..no_actors where actor_mapping[i]=actor_mapping[j] /\ actor_sil[i]+1=  actor_sil[j] ) (cost_graph[i,j]= 55))
                   /\
                   forall (i in 1..no_actors) (
                           forall(j in i+1..no_actors where actor_mapping[i]=actor_mapping[j] /\ actor_sil[i]=  actor_sil[j] +1) (cost_graph[i,j]= 55))
                   /\
                  forall (i in 1..no_actors) (
                           forall(j in i+1..no_actors where actor_mapping[i]=actor_mapping[j] /\ actor_sil[i] =actor_sil[j]+2 )(cost_graph[i,j]= 100) )
                   /\
                  forall (i in 1..no_actors) (
                           forall(j in i+1..no_actors where actor_mapping[i]=actor_mapping[j] /\ actor_sil[i] +2=actor_sil[j] )(cost_graph[i,j]= 100) )
                   /\
                  forall (i in 1..no_actors) (
                           forall(j in i+1..no_actors where actor_mapping[i]=actor_mapping[j] /\ actor_sil[i]=actor_sil[j]+3) (cost_graph[i,j]= 150) )
                                       /\
                  forall (i in 1..no_actors) (
                           forall(j in i+1..no_actors where actor_mapping[i]=actor_mapping[j] /\ actor_sil[i]+3=actor_sil[j]) (cost_graph[i,j]= 150) )
                    /\
                    forall (i in 1..no_actors*no_actors)(developement_cost = sum(cost_graph))
;

%Bandwidth constraint
constraint   forall( i in 1..no_actors    )
         (actor_bandwidth [i] <= bus_bandwidth);
      

%Schedulling // keeping the precedence


%%%%%%
solve minimize developement_cost;

output [ 
    "actor_mapping = \(actor_mapping);\n",
    "developement_cost = \(developement_cost);\n",
     "processor_load = \(processor_load);\n",
     "no_processors= \(no_processors);\n",
     "no_actors = \(no_actors);\n",
      "actor_sil = \(actor_sil);\n"
      
];