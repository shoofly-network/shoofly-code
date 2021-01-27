import random
import json
import os
from gurobipy import *
import pdb
from graph_tool.all import *
import graph_tool as gt
import graph_tool.draw
import graph_tool.collection
from NetworkTopology import *

root_dir = ""

def shortest_path_by_distance(G, v1, v2, nhops):
    sp_list = all_shortest_paths(G, v1, v2)
    shortest_path_to_distance = {}
    for sp in sp_list:
        if len(sp) > nhops: continue
        sp_str = ':'.join([G.vp.market[x] for x in sp])
        sp_distance = 0
        for node1, node2 in zip(sp, sp[1:]):
            sp_distance += G.ep.distance[G.edge(node1, node2)]
        shortest_path_to_distance[sp_str] = sp_distance

    if not shortest_path_to_distance: return None, None
    sorted_sps = sorted(shortest_path_to_distance.items(), key=lambda x:x[1])
    return sorted_sps[0][0], sorted_sps[0][1]

def unity_from_distance(shortcut_distance):
    if shortcut_distance <= 800:
        unity = 200
    elif shortcut_distance <= 2500:
        unity = 150
    elif shortcut_distance <= 5000:
        unity = 100
    else:
        unity = 0
    return unity
    
def init_shortcuts(network, nhops=3):
    G = network.graph
    shortcut_node_pairs = {}
    for vertex_1 in G.vertices():
        for vertex_2 in G.vertices():
            if vertex_1 == vertex_2: continue
            if G.edge(vertex_1, vertex_2) or G.edge(vertex_2, vertex_1): continue
            if (G.vp.market[vertex_2], G.vp.market[vertex_1]) in shortcut_node_pairs:
                symmetrical_shortcut = shortcut_node_pairs[(G.vp.market[vertex_2],
                                                            G.vp.market[vertex_1])]
                shortcut_hop_list = symmetrical_shortcut.pathstr.split(':')
                shortcut_hop_list.reverse()
                shortcut_str = ':'.join(shortcut_hop_list)
                shortcut_distance = symmetrical_shortcut.distance
            else:
                shortcut_str, shortcut_distance = shortest_path_by_distance(G, vertex_1,
                                                                            vertex_2, nhops)
                if not shortcut_str: continue
            unity = unity_from_distance(shortcut_distance)
            shortcut_obj = network.add_shortcut(shortcut_str.split(':'), unity, shortcut_distance)
            if shortcut_obj:
                shortcut_node_pairs[(G.vp.market[vertex_1], G.vp.market[vertex_2])] = shortcut_obj

    for x in shortcut_node_pairs:
        assert (x[1], x[0]) in shortcut_node_pairs

    return shortcut_node_pairs


def init_graph(network):
    G = Graph(directed=True)
    G.vp.lat      = G.new_vertex_property("double")
    G.vp.lon      = G.new_vertex_property("double")
    G.vp.market   = G.new_vertex_property("string")
    G.ep.capacity = G.new_edge_property("double")
    G.ep.distance = G.new_edge_property("double")
    G.ep.unity    = G.new_edge_property("int")
    G.ep.shortcut = G.new_edge_property("boolean")
    
    for mkt in network.nodes:
        v = G.add_vertex()
        G.vp.market[v] = mkt
        try:
            G.vp.lat[v] = network.nodes[mkt].latitude
            G.vp.lon[v] = network.nodes[mkt].latitude
        except TypeError:
            pass

    for mktA, mktB in network.edges:
        v1 = find_vertex(G, G.vp.market, mktA)
        assert len(v1) == 1
        v1 = v1[0]
        v2 = find_vertex(G, G.vp.market, mktB)
        assert len(v2) == 1
        v2 = v2[0]
        if G.edge(v1, v2):
            e = G.edge(v1,v2)
        else:
            e = G.add_edge(v1,v2)
        try:
            G.ep.distance[e] = network.edges[(mktA, mktB)].distance
        except TypeError:
            pass
        G.ep.capacity[e] = network.edges[(mktA, mktB)].capacity
        G.ep.unity[e] = network.edges[(mktA, mktB)].unity
        G.ep.shortcut[e] = False
        
    network.graph = G
                
def remove_demands_without_tunnels(network):
    removable_demands = [p for p, d in network.demands.items() if not d.tunnels]

    for demand_pair in removable_demands:
        del network.demands[demand_pair]
        

def initialize_optimization_variables(model, network, main_network=None):
    
    for tunnel in network.tunnels.values():
        tunnel.init_flow_var(model)

    for shortcut in network.shortcuts.values():
        shortcut.init_y_s_vars(model)

    for edge in network.edges.values():
        edge.init_x_e_vars(model)

    # If this is a failire scenario, do not re-define
    # wavelength variables
    if main_network is not None:
        for shortcut_str, shortcut in network.shortcuts.items():
            main_shortcut = main_network.shortcuts[shortcut_str]
            shortcut.init_wavelength_vars(model, var = main_shortcut.w_s)
    else:
        for shortcut_str, shortcut in network.shortcuts.items():
            shortcut.init_wavelength_vars(model)
        

def demand_constraints(network, model):
    for demand in network.demands.values():
        flow_on_tunnels = sum([tunnel.v_flow for tunnel in demand.tunnels])
        assert len(demand.tunnels) > 0
        model.addConstr(demand.amount <= flow_on_tunnels)

def demand_constraints_te(network, model):
    for demand in network.demands.values():
        flow_on_tunnels = sum([tunnel.v_flow for tunnel in demand.tunnels])
        assert len(demand.tunnels) > 0
        model.addConstr(demand.amount >= flow_on_tunnels)

def flow_conservation_constraints(network, model):
    for tunnel in network.tunnels.values():
        for edge in network.edges.values():
            if tunnel in edge.tunnels:
                x_e_t = edge.x_e_t[tunnel]
                y_s_t_sum = sum([shortcut.y_s[tunnel] for shortcut in edge.shortcuts
                                 if tunnel in shortcut.tunnels])
                model.addConstr(tunnel.v_flow <= x_e_t + y_s_t_sum)

def edge_capacity_constraints(network, model):
    for edge_pair in network.edges:
        edge = network.edges[edge_pair]
        x_e = sum(edge.x_e_t.values())
        w_s = sum([shortcut.w_s for shortcut in edge.shortcuts])
        model.addConstr(edge.capacity >= x_e + edge.unity*w_s)

def wavelength_integrality_constraints(network, model):
    for shortcut in network.shortcuts.values():
        y_s_all_tunnels = sum([shortcut.y_s[tunnel] for tunnel in shortcut.tunnels])
        model.addConstr(y_s_all_tunnels <= shortcut.w_s * shortcut.unity)

def complementary_shortcut_constraints(network, model, shortcut_node_pairs):
    for shortcut_pair in shortcut_node_pairs:
        shortcut_obj = shortcut_node_pairs[shortcut_pair]
        shortcut_obj_complementary = shortcut_node_pairs[(shortcut_pair[1], shortcut_pair[0])]
        model.addConstr(shortcut_obj.w_s == shortcut_obj_complementary.w_s)

def failure_scenario_flow_constraint(f_network, failed_edge_set, model):
    for tunnel in f_network.tunnels.values():
        for edge in tunnel.path:
            if edge.e in failed_edge_set or reversed(edge.e) in failed_edge_set:
                model.addConstr(tunnel.v_flow <= 0)

def get_constraints(network, shortcut_node_pairs, model):
    # Demand constraints
    demand_constraints(network, model)
    
    # Flow conservation constraints
    flow_conservation_constraints(network, model)
    
    # Edge capacity constraints
    edge_capacity_constraints(network, model)
    
    # Integral wavelength constraints
    wavelength_integrality_constraints(network, model)
    
    # Complementary shortcut equality constraints
    complementary_shortcut_constraints(network, model, shortcut_node_pairs)
    
def get_wavelength_objective(network):
    objective = 0
    for shortcut in network.shortcuts.values():
        objective += (len(shortcut.path) -1 )* shortcut.w_s
    return objective

def get_max_flow_objective(network):
    objective = 0
    for tunnel in network.tunnels.values():
        objective += tunnel.v_flow
    return objective

def get_shortcut_allocations(model, network):
    shortcuts = {}
    for shortcut_str in network.shortcuts:
        shortcut = network.shortcuts[shortcut_str]
        wavelengths = int(shortcut.w_s.x)
        if wavelengths == 0 or shortcut.unity == 0: continue
        shortcut_len = len(shortcut_str.split(':'))
        assert shortcut_len <= 5
        shortcuts[shortcut.pathstr] = wavelengths * shortcut.unity

    return shortcuts

def write_shortcut_allocations(network, nhops, scale, network_name, failure_links = 0):
    path = f"{root_dir}/{network_name}/"
    if not os.path.exists(path):
        os.makedirs(path)

    file = f"{path}/shortcut_distance_distributions_hops_{nhops}_scale_{scale}_failure_{failure_links}.csv"
    fd = open(file, "w")
    fd.write("shortcut,hops,distance,capacity,wavelengths,unity,failure_links\n")
    for shortcut_str in network.shortcuts:
        shortcut = network.shortcuts[shortcut_str]
        shortcut_len = len(shortcut_str.split(':'))
        wavelengths = int(shortcut.w_s.x)
        assert shortcut_len <= nhops
        shortcut_capacity = wavelengths * shortcut.unity
        shortcut_distance = shortcut.distance
        fd.write(f"{shortcut_str},{shortcut_len},{shortcut_distance},{shortcut_capacity},{wavelengths},{shortcut.unity},{failure_links}\n")        
    fd.close()


def close_edges(gr, edge1_str, edge2_str):
    e1_src = find_vertex(gr, gr.vp.market, edge1_str.split('-')[0])[0]
    e1_dst = find_vertex(gr, gr.vp.market, edge1_str.split('-')[1])[0]
    e2_src = find_vertex(gr, gr.vp.market, edge2_str.split('-')[0])[0]
    e2_dst = find_vertex(gr, gr.vp.market, edge2_str.split('-')[1])[0]
    # vertex hops in the shortest path between edge1 and edge2
    # are <=3.
    if len(shortest_path(gr, e1_src, e2_src)[0]) <= 2 or \
       len(shortest_path(gr, e1_src, e2_dst)[0]) <= 2 or \
       len(shortest_path(gr, e1_dst, e2_dst)[0]) <= 2 or \
       len(shortest_path(gr, e1_dst, e2_dst)[0]) <= 2:
        return True
    else:
        return False

    
def get_viable_failures(network, k=1):
    with open(f"{root_dir}/feasible_link_failures.json") as fi:
        feasible_failures = json.load(fi)
    edge_tuples = []
    if k == 1:
        for edge_str in feasible_failures['1']:
            failed_edge_tuple = tuple(edge_str.split('-'))
            if tuple(reversed(failed_edge_tuple)) in edge_tuples: continue
            edge_tuples.append([failed_edge_tuple])
    else:
        for edge_pair_str in feasible_failures['2']:
            failed_edge_str1, failed_edge_str2 = edge_pair_str.split('|')
            failed_edge_tuple1 = tuple(failed_edge_str1.split('-'))
            failed_edge_tuple2 = tuple(failed_edge_str2.split('-'))
            if tuple(reversed(failed_edge_tuple1)) == failed_edge_tuple2: continue
            if close_edges(network.graph, failed_edge_str1, failed_edge_str2):
                edge_tuples.append([failed_edge_str1, failed_edge_str2])
        edge_tuples = random.sample(edge_tuples, 500)

    print("Failure scenarios", len(edge_tuples))
    return edge_tuples
