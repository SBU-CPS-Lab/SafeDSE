% Latency calculation between a source and destination actor in an HSDF graph
% Latency is calculated by finding the end time of the ρ(src,dst)+1th invocation of the destination actor in a self-timed schedule of the graph
% ρ(src,dst) is the minimum-delay path from src to dst and is calculated using the included bellman_ford predicate

include "bellman-ford.mzn";

% Predicate to calculate the latency of an HSDF graph from a given source to a given destination
predicate hsdf_latency(array[int,int] of opt int: Arc, array[int] of int: T, int: s, int: d, var int: latency) =
    let {
        set of int: S1 = index_set_1of2(Arc),
        set of int: S2 = index_set_2of2(Arc),
        set of int: S3 = index_set(T),
        int: l = min(S1),
        int: u = max(S1),
        int: n = card(S1),
        var 0..: dist,
        array[S1, 1..sum(array1d(Arc))] of var opt 0..: invk_times,
    } in
    (
        assert (S1 = S2 /\ S2 = S3, "The index sets of Arc and T must be the same") /\
        assert (lb_array(Arc) >= 0, "Arc must be non-negative") /\
        assert (lb_array(T) >= 0, "T must be non-negative") /\
        % Calculate the minimum-delay path from the source to the destination
        bellman_ford(Arc, s, d, dist) /\
        % Calculate the self-timed schedule of the graph (until the dist=ρ(src,dst)+1th invocation of the destination actor)
        forall (i in S1, j in 1..dist+1) (
            invk_times[i, j] = max (k in S1 where occurs(Arc[k, i])) (
                if j-Arc[k, i] < 1 then 0 else invk_times[k, j-Arc[k, i]] + T[k] endif
            )
        ) /\
        % Fix the unneeded execution times to absent
        forall (i in S1, j in dist+2..sum(array1d(Arc))) (
            absent(invk_times[i, j])
        ) /\
        % The latency is the end time of the ρ(src,dst)+1th invocation of the destination actor
        latency = deopt(invk_times[d, dist+1] + T[d] - invk_times[s, 1])
    );
