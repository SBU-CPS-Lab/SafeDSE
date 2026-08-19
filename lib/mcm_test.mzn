% Self-test for mcm.mzn -- the validation cases from the architecture doc A.6.
% Run:  minizinc --solver gecode lib/mcm_test.mzn -D "tc=1;"   (expect mu=12)
%       minizinc --solver gecode lib/mcm_test.mzn -D "tc=2;"   (expect mu=4)
%       minizinc --solver gecode lib/mcm_test.mzn -D "tc=3;"   (expect mu=4)
%       minizinc --solver gecode lib/mcm_test.mzn -D "tc=4;"   (expect UNSAT)
include "mcm.mzn";
int: tc;
int: n = if tc = 1 then 3 else 4 endif;
set of int: A = 1..n;
array[A] of int: T = if tc = 1 then [3,4,5] else [2,2,2,2] endif;
array[A,A] of int: tok =
  if tc = 1 then array2d(A,A,[-1,0,-1, -1,-1,0, 1,-1,-1])
  else array2d(A,A,[-1,0,-1,-1, -1,-1,0,-1, -1,-1,-1,0, 2,-1,-1,-1]) endif;
array[A,A] of var bool: sedge;
% NOTE: comparison binds TIGHTER than \/ in MiniZinc, so the right-hand side
% MUST be fully parenthesised.  Without the outer parens this parses as
% (sedge[i,j] = A) \/ B, which leaves sedge unconstrained whenever B holds.
constraint forall(i,j in A)( sedge[i,j] = (
    (tc = 3 /\ i = 1 /\ j = 3) \/
    (tc = 4 /\ ((i = 2 /\ j = 4) \/ (i = 4 /\ j = 2)))
) );
int: maxmu = sum(T) * max([1] ++ [tok[i,j] | i,j in A where tok[i,j] > 0]);
var 0..maxmu: mu;
array[A] of var -n*maxmu..n*maxmu: pot;
constraint mcm_fixed_edges(tok, T, pot, mu);
constraint mcm_schedule_edges(sedge, T, pot);
constraint mcm_anchor(pot);
solve minimize mu;
output ["testcase \(tc): mu=\(mu)  pot=\(pot)\n  sedge=\(sedge)\n"];
