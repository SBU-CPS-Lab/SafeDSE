% ---------------------------------------------------------------------------
% core.mzn -- SafeDSE Phase-1 + Phase-3 skeleton.
%
% Mapping + per-core static order + throughput (MCM) + processor-SIL isolation
% + hardware/development cost, with a switchable throughput bound.
%
% This is deliberately the *honest minimum*: no structural safety patterns yet
% (Phase 4), ideal communication (Phase 6), single application.  It already
% exhibits the central safety trade-off: buy another core, or promote a
% low-SIL actor's development to the SIL of the core it shares.
%
% Measured on the synthetic pipelined HSDFs in data/, proving optimality with
% the throughput bound set to 55% of sum(WCET):
%       n=10/P=4    Gecode >60s    Chuffed  0.34s   CP-SAT 0.33s
%       n=20/P=6    Gecode >60s    Chuffed  3.53s   CP-SAT 1.52s
%       n=30/P=8    Gecode >60s    Chuffed >60s     CP-SAT 4.08s
% Backend choice dominates: target CP-SAT, keep Gecode only for cross-checking.
% ---------------------------------------------------------------------------
include "globals.mzn";
include "lib/mcm.mzn";

% ---- Application (HSDF) ---------------------------------------------------
int: n;  set of int: A = 1..n;
array[A,A] of int: tok;        % -1 = no channel, >=0 = initial tokens
array[A]   of int: T;          % WCET (mapping-independent for now; Phase 1
                               % replaces this with element(proc,mode) lookup)

% ---- Platform -------------------------------------------------------------
int: P;  set of int: PR = 1..P;
array[PR] of int: pcost;       % monetary/area cost of instantiating a core

% ---- Safety requirements --------------------------------------------------
array[A] of 0..4: sil_req;     % 0 = non-safety-related
array[0..4] of int: dev_k;     % development-cost multiplier per SIL (x10, int)
array[A]    of int: dev_base;  % baseline development cost per actor

% ---- Decisions ------------------------------------------------------------
array[A]  of var PR:     proc;      % actor -> processor
array[PR] of var 0..4:   csil;      % SIL to which the core is provisioned
array[PR] of var bool:   used;
array[A]  of var 0..4:   sil_impl;  % SIL at which the actor is developed

% Koopman rule: no silent mixing.  Everything on a core is developed to the
% core's SIL.  (Phase 3 adds `partitioned[p]` to relax this to <= at a cost.)
constraint forall(i in A)( sil_impl[i] = csil[proc[i]] );
constraint forall(i in A)( sil_impl[i] >= sil_req[i] );
constraint forall(p in PR)( used[p] <-> exists(i in A)(proc[i] = p) );
constraint forall(p in PR)( not used[p] -> csil[p] = 0 );

% Symmetry breaking on identical cores -- not optional, see doc A.6.
constraint seq_precede_chain(proc);
constraint forall(p in 1..P-1)( used[p+1] -> used[p] );

% ---- Static order per processor -------------------------------------------
array[A] of var 0..n:   succ;   % 0 = last actor on its processor
array[A] of var 0..n-1: ord;    % position, for acyclicity
constraint alldifferent_except_0(succ);
constraint forall(i in A)( succ[i] != i );
constraint forall(i in A)( succ[i] > 0 -> proc[succ[i]] = proc[i] );
constraint forall(p in PR)( used[p] -> sum(i in A)(proc[i] = p /\ succ[i] = 0) = 1 );
constraint forall(i in A)( succ[i] > 0 -> ord[succ[i]] = ord[i] + 1 );
constraint forall(i,j in A where i != j)( proc[i] = proc[j] -> ord[i] != ord[j] );
% Anchor each chain: the head of a core's order sits at position 0.  Without
% this, `ord` floats and the wrap-edge condition below can never be detected.
array[A] of var bool: ishead;
constraint forall(j in A)( ishead[j] <-> not exists(i in A)(succ[i] = j) );
constraint forall(j in A)( ishead[j] -> ord[j] = 0 );

% ---- Throughput -----------------------------------------------------------
int: maxmu = sum(T) * max([1] ++ [tok[i,j] | i,j in A where tok[i,j] > 0]);
var 1..maxmu: mu;
array[A] of var -n*maxmu..n*maxmu: pot;
array[A,A] of var bool: sedge;
constraint forall(i,j in A)( sedge[i,j] <-> (i != j /\ succ[i] = j) );

% The per-core static order must close into a CYCLE carrying one initial token
% -- the "processor availability" token.  Each actor fires once per iteration,
% so the period of a core is at least the sum of the WCETs mapped onto it.
% Modelling the order as an open chain silently drops that bound, which is
% exactly why Rosvall/Bonfietti use `circuit` over a dummy-extended array.
% The wrap edge carries tok=1, so tok*mu stays linear.
array[A,A] of var bool: wrap;
constraint forall(i,j in A)(
    wrap[i,j] <-> ( succ[i] = 0 /\ ishead[j] /\ proc[i] = proc[j] )
);
constraint forall(i,j in A)( wrap[i,j] -> pot[j] >= pot[i] + T[i] - mu );

constraint mcm_fixed_edges(tok, T, pot, mu);
constraint mcm_schedule_edges(sedge, T, pot);
constraint mcm_anchor(pot);

% ---- Metrics --------------------------------------------------------------
var int: hwcost  = sum(p in PR)( bool2int(used[p]) * pcost[p] );
var int: devcost = sum(i in A)( (dev_base[i] * dev_k[sil_impl[i]]) div 10 );
var int: total   = hwcost + devcost;

% ---- Switchable objective (Phase 2 generalises this to the Metric enum) ---
int: mu_max;
constraint mu <= mu_max;
solve minimize total;

output [
  "mu=\(mu)  total=\(total)  hw=\(hwcost)  dev=\(devcost)\n",
  "proc=\(proc)\n", "csil=\(csil)\n", "sil_impl=\(sil_impl)\n"
];
