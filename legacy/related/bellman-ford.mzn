% The Bellman-Ford algorithm used to find single-source shortest minimum-delay paths on an HSDF graph

% A MiniZinc predicate which finds single-source shortest minimum-delay paths on an HSDF graph from a given source actor using the Bellman-Ford algorithm
predicate bellman_ford(array[int,int] of opt int: Arc, int: s, array[int] of var int: dist) =
    let {
        set of int: S1 = index_set_1of2(Arc),
        set of int: S2 = index_set_2of2(Arc),
        set of int: S3 = index_set(dist),
        int: l = min(S1),
        int: u = max(S1),
        int: n = card(S1),
        % Define the distance matrix
        % The first index is the algorithm iteration
        % The second index is the destination actor
        array[0..n-1, l..u] of var 0..INF: dists;
    } in
        assert (S1 = S2 /\ S1 = S3, "The index sets of the adjacency matrix and the distance vector must be the same.") /\
        assert (lb_array(Arc) >= 0, "Arc must be non-negative.") /\
        assert (lb_array(dist) >= 0, "The distance vector must be non-negative.") /\
        % Initial distance from the source to itself is 0
        dists[0, s] = 0 /\
        % Initial distance from the source to all other actors is INF
        forall (i in S1 where i!=s) (dists[0, i] = INF) /\
        % Bellman-Ford algorithm to find the shortest (minimum-delay) path from the source to all other actors
        forall (k in 1..n-1) (
            forall (i in S1) (
                dists[k, i] = min(
                    dists[k-1, i],
                    min(j in S1 where occurs(Arc[j, i])) (dists[k-1, j] + Arc[j, i])
                )
            )
        ) /\
        % The distance from the source to each actor is the last element of the distance matrix
        forall (i in S1) (dist[i] = dists[n-1, i]);

% A MiniZinc predicate which finds single-source shortest minimum-delay paths on an HSDF graph from a given source actor to a destination actor using the Bellman-Ford algorithm
predicate bellman_ford(array[int,int] of opt int: Arc, int: s, int: d, var int: dist) =
    let {
        set of int: S1 = index_set_1of2(Arc),
        set of int: S2 = index_set_2of2(Arc),
        int: l = min(S1),
        int: u = max(S1),
        % Define the distance vector
        array[S1] of var 0..INF: dists;
    } in
        assert (S1 = S2, "The index sets of the adjacency matrix must be the same.") /\
        assert (lb_array(Arc) >= 0, "Arc must be non-negative.") /\
        % Use the more elaborate predicate
        bellman_ford(Arc, s, dists) /\
        % The distance from the source to the destination in the distance vector
        dist = dists[d];

% A MiniZinc predicate which finds single-source shortest minimum-delay paths on an HSDF graph from a given source actor using the Bellman-Ford algorithm, variable Arc
predicate bellman_ford(array[int,int] of var opt int: Arc, int: s, array[int] of var int: dist) =
    let {
        set of int: S1 = index_set_1of2(Arc),
        set of int: S2 = index_set_2of2(Arc),
        set of int: S3 = index_set(dist),
        int: l = min(S1),
        int: u = max(S1),
        int: n = card(S1),
        % Define the distance matrix
        % The first index is the algorithm iteration
        % The second index is the destination actor
        array[0..n-1, l..u] of var 0..INF: dists;
    } in
        assert (S1 = S2 /\ S1 = S3, "The index sets of the adjacency matrix and the distance vector must be the same.") /\
        assert (lb_array(Arc) >= 0, "Arc must be non-negative.") /\
        assert (lb_array(dist) >= 0, "The distance vector must be non-negative.") /\
        % Initial distance from the source to itself is 0
        dists[0, s] = 0 /\
        % Initial distance from the source to all other actors is INF
        forall (i in S1 where i!=s) (dists[0, i] = INF) /\
        % Bellman-Ford algorithm to find the shortest (minimum-delay) path from the source to all other actors
        forall (k in 1..n-1) (
            forall (i in S1) (
                dists[k, i] = min(
                    dists[k-1, i],
                    min(j in S1 where occurs(Arc[j, i])) (dists[k-1, j] + Arc[j, i])
                )
            )
        ) /\
        % The distance from the source to each actor is the last element of the distance matrix
        forall (i in S1) (dist[i] = dists[n-1, i]);

% A MiniZinc predicate which finds single-source shortest minimum-delay paths on an HSDF graph from a given source actor to a destination actor using the Bellman-Ford algorithm, variable Arc
predicate bellman_ford(array[int,int] of var opt int: Arc, int: s, int: d, var int: dist) =
    let {
        set of int: S1 = index_set_1of2(Arc),
        set of int: S2 = index_set_2of2(Arc),
        int: l = min(S1),
        int: u = max(S1),
        % Define the distance vector
        array[S1] of var 0..INF: dists;
    } in
        assert (S1 = S2, "The index sets of the adjacency matrix must be the same.") /\
        assert (lb_array(Arc) >= 0, "Arc must be non-negative.") /\
        % Use the more elaborate predicate
        bellman_ford(Arc, s, dists) /\
        % The distance from the source to the destination in the distance vector
        dist = dists[d];