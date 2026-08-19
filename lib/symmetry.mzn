% ===========================================================================
% symmetry.mzn -- symmetry breaking for the heterogeneous platform (C.5)
%
% Must be included AFTER order.mzn: these constraints reference `proc`.
%
% In the homogeneous prototype a single `seq_precede_chain(proc)` sufficed
% because every core was interchangeable. That is no longer true, and applying
% it globally here would be unsound -- it would exclude optimal solutions.
% ===========================================================================
include "globals.mzn";

% ---- symmetry breaking (C.5) ----------------------------------------------
% Cores are no longer globally interchangeable, so `seq_precede_chain(proc)`
% over all of PR is unsound.  Break symmetry within equivalence classes only:
%   (1) cores of the same type inside the same card;
%   (2) whole cards built from the same template.
% Getting this split wrong is the main modelling risk flagged in C.5.
% (1) Cores of the same type inside the SAME card are fully interchangeable, so
%     value precedence over them is sound: slot k+1 may only carry an actor if
%     slot k already carries an earlier one.  This is much stronger than a bare
%     `used` prefix, and it is where most of the pruning comes from.
constraint forall(c in 1..nSymClasses)(
    value_precede_chain([symClass[c,k] | k in 1..symClassSize[c]], proc)
);

% (2) Whole cards built from the same template are interchangeable, but cores
%     in DIFFERENT cards are not once FCR constraints exist (Phase 4): swapping
%     two cores across cards changes their fault containment region, so it is
%     not a symmetry on its own. Only whole-card swaps are. Hence two weaker
%     constraints rather than one global chain:
%       (2a) buy a prefix of the cards;
constraint forall(g in 1..nTmplGroups, k in 1..tmplGroupSize[g]-1)(
    fcr_used[tmplGroup[g, k+1]] -> fcr_used[tmplGroup[g, k]]
);
%       (2b) and order successive identical cards by their actor membership,
%            so the same partition is not re-found under a card relabelling.
constraint forall(g in 1..nTmplGroups, k in 1..tmplGroupSize[g]-1)(
    lex_lesseq(
        [ bool2int(fcr[proc[i]] = tmplGroup[g, k+1]) | i in A ],
        [ bool2int(fcr[proc[i]] = tmplGroup[g, k])   | i in A ]
    )
);

% Declared-then-constrained rather than defined with `=`, so that these appear
% in the solver's JSON output and can be checked by the external verifier.
