% Throughput calculation of an HSDF graph using a flow-based min,+ approach
% The model defines non-negative decision variables on the edge inputs and outputs holding the remaining iteration time budget constraining the throughput.
% Each initial token charges up this value by one iteration time and each actor decrements it by the execution time.
% On actor inputs, the minimum of these values are propagated as a bound to the output.
% For the moment these values are called cycle residual times until better names are found.

predicate throughput_flow(array[int,int] of var opt int: Arc, array[int] of int: exec_time, var 0..sum(exec_time): iteration_bound) =
    let {
        set of int: S1 = index_set_1of2(Arc);
        set of int: S2 = index_set_2of2(Arc);
        set of int: S3 = index_set(exec_time);
        set of int: res_time = 0..n_actors*n_actors*ub_array(Arc)*sum(exec_time);
        % The residual cycle time on each edge input (FIXME: a good bound for vaiables domain?)
        array[S1, S1] of var res_time: inp_res_time;
        % The residual cycle time on each edge output (FIXME: a good bound for vaiables domain?)
        array[S1, S1] of var res_time: out_res_time;
    } in
        assert (S1 == S2 /\ S1 ==S3, "The sets of actors and execution times must be equal") /\
        assert (lb_array(Arc) >= 0, "Arc values must be non-negative") /\
        assert (has_ub_set(dom_bounds_array(Arc)), "Arc values must be bounded") /\
        % Relate the output cycle residual times to the input cycle residual times for each edge
        % The number of initial tokens times the iteration time is added to the edge input resdual cycle time of each edge
        forall (i, j in S1 where occurs(Arc[i, j])) (
            out_res_time[i, j] = inp_res_time[i, j] + Arc[i, j] * iteration_bound
        ) /\
        % Relate the input cycle residual times to the output cycle residual times in each actor
        % The input cycle residual time of all outgoing edges must be equal to the minimum of the output cycle residual times of all incoming edges minus actor execution time
        forall (a in S1) (
            forall (i in S1 where occurs(Arc[a, i])) (
                inp_res_time[a, i] <= min([out_res_time[j, a] | j in S1 where occurs(Arc[j, a])]) - exec_time[a]
            )
        ) /\
        % Fill out irrelevant cycle residual times
        forall (i, j in S1 where absent(Arc[i, j])) (
            inp_res_time[i, j] = 0 /\ out_res_time[i, j] = 0
        );
