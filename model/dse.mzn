% ===========================================================================
% dse.mzn -- SafeDSE Phase 1 top level
%
% Mapping + per-core static order + per-application throughput + heterogeneous
% platform with FCRs + switchable objective.  Safety patterns are Phase 4;
% communication is ideal here and refined in Phase 6.
%
% Backend: CP-SAT.  Gecode and Chuffed remain wired up in the test harness as
% small-instance correctness oracles only -- disagreement between them signals
% a modelling error, not a performance question.
% ===========================================================================
include "globals.mzn";
include "../lib/platform.mzn";
include "../lib/order.mzn";
include "../lib/symmetry.mzn";
include "../lib/mcm.mzn";
include "../lib/latency.mzn";
include "../lib/safety.mzn";

% ---- application data -----------------------------------------------------
array[A,A] of int: tok;                       % -1 = no channel
array[A, CT, MD] of int: wcet;
array[A] of int: mem_req;
array[APP] of int: period_ub;

% ---- derived: WCET follows the binding ------------------------------------
% This is a 3-D element with two nested variable indices (pmode[proc[i]] is
% itself an element on a var array), which looks like it ought to flatten
% badly. It was replaced during Phase 1 with a flattened "speed class" encoding
% -- one reified implication per (actor, slot) feeding a 1-D lookup into a
% parameter row -- on the theory that the nesting was the scalability
% bottleneck. Measured head to head, the class encoding produced identical
% optima but was never faster and up to 4x slower (c_rasta at mu<=500: 3.46s
% vs 0.85s), so the simpler form is kept. The actual bottleneck was elsewhere;
% see the branch-symmetry finding in README_PHASE1.md.
int: maxwcet = max([wcet[i,t,m] | i in A, t in CT, m in MD
                    where wcet[i,t,m] < 1000000]);
array[A] of var 0..maxwcet: T;
constraint forall(i in A)( T[i] = wcet[i, ctype[proc[i]], pmode[proc[i]]] );

% ---- throughput (C.7: per-application periods) ----------------------------
int: maxmu = sum(i in A)(maxwcet) * max([1] ++ [tok[i,j] | i,j in A where tok[i,j] > 0]);
array[APP] of var 1..maxmu: mu;
array[A] of var -maxmu..maxmu: pot;

% Mode (a), the default: one period shared by all applications.  Mode (b) is
% selected by period_mode_partitioned in order.mzn, which forbids core sharing
% and thereby lets the potential graph decompose.  Mode (c) -- per-app periods
% WITH sharing -- needs a per-application MSAG and is Phase 6.  See C.7 for why
% the naive version of (c) is unsound rather than merely imprecise.
constraint not period_mode_partitioned ->
    forall(z in APP where z > 1)( mu[z] = mu[1] );

array[A] of var 1..maxmu: mu_of;
constraint forall(i in A)( mu_of[i] = mu[app[i]] );

constraint mcm_fixed_edges(tok, T, pot, mu_of);
constraint mcm_schedule_edges(sedge, T, pot);
constraint mcm_wrap_edges(wrap, T, pot, mu_of);
constraint mcm_anchor(pot);
constraint latency_periodic(pot, T, mu_of);

constraint forall(z in APP)( mu[z] <= period_ub[z] );

% ---- memory ---------------------------------------------------------------
constraint forall(p in PR)(
    sum(i in A)( bool2int(proc[i] = p) * mem_req[i] ) <= core_mem[ctype[p]]
);

% ---- costs ----------------------------------------------------------------
% dev_cost, partition_total and promotion_cost come from lib/safety.mzn.
var int: total_cost;
constraint total_cost = hw_cost + dev_cost + partition_total;

% ---- switchable objective (B.6) -------------------------------------------
% Every metric is always computed and always bounded; the objective is a
% parameter, so switching what is optimised needs a -D flag and no model edit.
enum Metric = { THROUGHPUT, LATENCY, HWCOST, DEVCOST, TOTALCOST, POWER,
                NPROCS, PROMOTION };
Metric: opt_metric;
array[Metric] of int: ub;

var 0..P: nprocs;
constraint nprocs = sum(p in PR)( bool2int(used[p]) );

% THROUGHPUT is reported as the worst application period, so a single bound
% constrains every application even in partitioned mode.
var 1..maxmu: mu_worst;
constraint mu_worst = max(mu);

array[Metric] of var int: metric;
constraint metric = [ mu_worst, max_latency, hw_cost, dev_cost,
                      total_cost, power, nprocs, promotion_cost ];
constraint forall(m in Metric)( metric[m] <= ub[m] );

solve :: seq_search([
    int_search(proc, first_fail, indomain_min),
    int_search(succ, first_fail, indomain_min),
    int_search([mu[z] | z in APP], input_order, indomain_min),
])  minimize metric[opt_metric];

output [
  "objective(\(opt_metric)) = \(metric[opt_metric])\n",
  "mu       = \(mu)\n",
  "nprocs   = \(nprocs)   hw_cost = \(hw_cost)   power = \(power)\n",
  "proc     = \(proc)\n",
  "pmode    = \(pmode)\n",
  "used     = \(used)\n",
  "fcr_used = \(fcr_used)\n",
  "T        = \(T)\n",
  "sil_impl = \(sil_impl)\n",
  "csil     = \(csil)\n",
  "promo    = \(promotion_cost)  partition = \(partition_total)\n",
  "latency  = \(latency)\n",
  "metric   = \(metric)\n",
];
