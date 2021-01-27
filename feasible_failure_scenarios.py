import itertools
import json
from helper import *
from cpwan_parser import *
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("hops", help="maximum number of shortcut hops", type=int)
parser.add_argument("-s", "--scale", help="scale demands by this factor", type=float, default=1.0)
args = parser.parse_args()
print(args)

# This network is simply to enumerate all edges
network = init_network("cpwan", scale=args.scale)

possible_srlgs = {1:[], 2:[]}
for failed_edge_tuple in network.edges:
    print("Failure", failed_edge_tuple)
    model = Model("mip")
    if tuple(reversed(failed_edge_tuple)) in possible_srlgs[1]:
        # If this tuple has already been tested
        continue
    
    # Initialize a new network for the failure scenario
    f_network = init_network("cpwan", scale=args.scale)
    f_network = init_graph(f_network)
    f_network, shortcut_node_pairs = init_shortcuts(f_network, nhops=args.hops)
    f_network = remove_demands_without_tunnels(f_network)

    # Initialize all variables except wavelength variables on shortcuts
    model = initialize_optimization_variables(model, f_network)
    model.update()
    model = get_constraints(f_network, shortcut_node_pairs, model)
    model = failure_scenario_flow_constraint(f_network, [failed_edge_tuple], model)
    for shortcut in f_network.shortcuts.values():
        model.addConstr(shortcut.w_s <= 0)
        
    objective = get_wavelength_objective(f_network)
    model.setObjective(objective, GRB.MAXIMIZE)
    model.update()
    model.setParam("mipgap", 0.001)
    model.optimize()
    if model.status == 2: # Optimal solution found
        possible_srlgs[1].append("%s-%s" % (failed_edge_tuple[0], failed_edge_tuple[1]))

for failed_edge_tuple1, failed_edge_tuple2 in itertools.combinations(network.edges, r=2):
    model = Model("mip")
    print("Failure:", failed_edge_tuple1, failed_edge_tuple2)
    # Initialize a new network for the failure scenario
    f_network = init_network("cpwan", scale=args.scale)
    f_network = init_graph(f_network)
    f_network, shortcut_node_pairs = init_shortcuts(f_network, nhops=args.hops)
    f_network = remove_demands_without_tunnels(f_network)

    # Initialize all variables except wavelength variables on shortcuts
    model = initialize_optimization_variables(model, f_network)
    model.update()
    model = get_constraints(f_network, shortcut_node_pairs, model)
    model = failure_scenario_flow_constraint(f_network, [failed_edge_tuple1, failed_edge_tuple2],
                                             model)
    for shortcut in f_network.shortcuts.values():
        model.addConstr(shortcut.w_s <= 0)
        
    objective = get_wavelength_objective(f_network)
    model.setObjective(objective, GRB.MAXIMIZE)
    model.update()
    model.setParam("mipgap", 0.001)
    model.optimize()
    if model.status == 2: # Optimal solution found
        possible_srlgs[2].append("%s-%s|%s-%s" % (failed_edge_tuple1[0], failed_edge_tuple1[1],
                                                  failed_edge_tuple2[0], failed_edge_tuple2[1]))

DATADIR = ""
with open(DATADIR + "feasible_link_failures.json", "w") as fi:
    json.dump(possible_srlgs, fi)
    
