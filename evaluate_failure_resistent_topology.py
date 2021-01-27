from post_process_results import *

def parse_tunnels_bypass(bypass_gr, shortcuts, original_network, bypass_network):
    tunnels = {}
    for tunnel_str in original_network.tunnels:
        tunnel = original_network.tunnels[tunnel_str]
        assert tunnel_str == tunnel.pathstr
        # a graph object for every tunnel in the original network
        tunnels[tunnel_str] = nx.Graph()
        for node in tunnel.pathstr.split(':'):
            tunnels[tunnel.pathstr].add_node(node)
            
        for node1, node2 in zip(tunnel.pathstr.split(':'), tunnel.pathstr.split(':')[1:]):
            v1 = find_vertex(bypass_gr, bypass_gr.vp.market, node1)[0]
            v2 = find_vertex(bypass_gr, bypass_gr.vp.market, node2)[0]
            edge = bypass_gr.edge(v1, v2)
            if bypass_gr.ep.capacity[edge] > 0:
                tunnels[tunnel.pathstr].add_edge(node1, node2)
                
    for shortcut in shortcuts:
        shortcut_alloc = shortcuts[shortcut]
        if shortcut_alloc == 0: continue
        for tunnel in original_network.tunnels:
            if shortcut in original_network.tunnels[tunnel].pathstr:
                tunnel_gr = tunnels[original_network.tunnels[tunnel].pathstr]
                tunnel_gr.add_edge(shortcut.split(':')[0], shortcut.split(':')[-1])

    for tunnel in tunnels:
        tunnel_paths = \
        list(nx.all_simple_paths(tunnels[tunnel], tunnel.split(':')[0], tunnel.split(':')[-1]))
        for tunnel_p in tunnel_paths:
            bypass_network.add_tunnel(tunnel_p)

                
def init_network_from_graph(gr, shortcuts, original_network, scale):
    network = Network(network_name)
    network.graph = gr
    region_to_nodes = cpwan_parser.add_demands_network(network, scale)
    for edge in gr.edges():
        src = edge.source()
        dst = edge.target()
        network.add_edge(gr.vp.market[src], gr.vp.market[dst],
                         gr.ep.unity[edge], gr.ep.capacity[edge])
    parse_tunnels_bypass(gr, shortcuts, original_network, network)
    remove_demands_without_tunnels(network)
    return network

def solve_flow_allocations(network, failure_set):
    env = Env(empty=True)
    env.setParam('OutputFlag', 0)
    env.start()
    model = Model("mip", env=env)
    initialize_optimization_variables(model, network)
    model.update()
    demand_constraints_te(network, model)
    flow_conservation_constraints(network, model)
    edge_capacity_constraints(network, model)
    objective = get_max_flow_objective(network)
    failure_scenario_flow_constraint(network, failure_set, model)
    model.setObjective(objective, GRB.MAXIMIZE)
    model.update()
    model.setParam("mipgap", 0.001)
    model.optimize()
    assert model.status == 2
    return model.getObjective().getValue()

def solve_failure_model(network, num_edge_failures=1):
    allocations = []
    count = 0
    if num_edge_failures == 1:
        for failed_edge_tuple in network.edges:
            count += 1
            if count >= 10: break
            allocation = solve_flow_allocations(network, [failed_edge_tuple])
            allocations.append(allocation)
    else:
        for failed_edge_tuple1, failed_edge_tuple2 in itertools.combinations(network.edges, r=2):
            count += 1
            if count >= 10: break
            allocation = solve_flow_allocations(network, [failed_edge_tuple1, failed_edge_tuple2])
            allocations.append(allocation)
    return np.mean(allocations), np.median(allocations), np.std(allocations)
    
network_name = "cpwan"
failure_allocations = [["failure_num", "value", "type", "nhops", "scale", "name"]]
for nhops in [3,4,5]:
    original_network, total_capacity, total_lambdas, total_ports, total_regions = \
                                get_initial_network_state(network_name, nhops)
    for demand_scale in range(1, 9):
        _, _, _, _, _, _, _, bypass_enabled_graph, bypass_shortcuts = get_network_savings(
            original_network, network_name, total_capacity, total_lambdas,
            total_ports, total_regions, nhops, demand_scale, failure_num=0)
        bypass_network =\
                         init_network_from_graph(bypass_enabled_graph, bypass_shortcuts,
                                                 original_network, demand_scale)
        
        # flow_allocation = solve_flow_allocations(bypass_network, [])
        for failure_num in [1, 2]:
            print(network_name, nhops, demand_scale, failure_num)
            try:
                fraction_lambda_bypassed, fraction_bw_bypassed, fraction_ports_bypassed, \
                    fraction_regions_bypassed, wavelengths_by_mod, ports_by_mod, bypass_saving,\
                    failure_proof_graph, failure_allocated_shortcuts = get_network_savings(
                        original_network, network_name,
                        total_capacity, total_lambdas,
                        total_ports, total_regions, nhops, demand_scale,
                        failure_num=failure_num)
            except AssertionError:
                print("file not found")
                continue
            failure_bypass_network = init_network_from_graph(failure_proof_graph,
                                                             failure_allocated_shortcuts,
                                                             original_network, demand_scale)

            failure_allocation_mean, failure_allocation_median, failure_allocation_std = \
                                    solve_failure_model(failure_bypass_network,
                                                        num_edge_failures=failure_num)
            low = failure_allocation_mean - failure_allocation_std
            high = failure_allocation_mean + failure_allocation_std
            failure_allocations.append([failure_num, failure_allocation_mean,
                                        "mean", nhops, demand_scale,
                                        "shoofly-kwise-%d" % failure_num])
            
            failure_allocations.append([failure_num, failure_allocation_median,
                                        "median", nhops, demand_scale,
                                        "shoofly-kwise-%d" % failure_num])

            failure_allocations.append([failure_num, high,
                                        "high", nhops, demand_scale,
                                        "shoofly-kwise-%d" % failure_num])

            failure_allocations.append([failure_num, low,
                                        "low", nhops, demand_scale,
                                        "shoofly-kwise-%d" % failure_num])

            allocation_mean, allocation_median, allocation_std = \
                                            solve_failure_model(bypass_network,
                                                                num_edge_failures=failure_num)
            low = allocation_mean - allocation_std
            high = allocation_mean + allocation_std
            failure_allocations.append([failure_num, allocation_mean,
                                        "mean", nhops, demand_scale,
                                        "shoofly"])
            
            failure_allocations.append([failure_num, allocation_median,
                                        "median", nhops, demand_scale,
                                        "shoofly"])

            failure_allocations.append([failure_num, high,
                                        "high", nhops, demand_scale,
                                        "shoofly"])

            failure_allocations.append([failure_num, low,
                                        "low", nhops, demand_scale,
                                        "shoofly"])

DATADIR = ""
with open(DATADIR + "shoofly_allocations.csv", "w") as fi:
    writer  = csv.writer(fi)
    writer.writerows(failure_allocations)
