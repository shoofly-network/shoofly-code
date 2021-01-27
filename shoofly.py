import os
from other_networks_parser import *
import argparse

# TeaVaR data at: https://github.com/manyaghobadi/teavar/tree/master/code/data

parser = argparse.ArgumentParser()
parser.add_argument("hops", help="maximum number of shortcut hops", type=int)
parser.add_argument("-n", "--network", help="network name", type=str)
parser.add_argument("-s", "--scale", help="scale demands by this factor", type=float, default=1.0)
args = parser.parse_args()

if not os.path.isfile("teavar-data/%s/topology.txt" % args.network):
    print("Network %s does not exist" % args.network)

network, nxnetwork = parse_topology(args.network)
init_graph(network)
network = parse_demands(args.network, network, scale=args.scale)
network = parse_tunnels(network, nxnetwork)
shortcut_node_pairs = init_shortcuts(network, nhops=args.hops)
remove_demands_without_tunnels(network)

model = Model("mip")
initialize_optimization_variables(model, network)
model.update()
get_constraints(network, shortcut_node_pairs, model)
model.update()
objective = get_wavelength_objective(network)
model.setObjective(objective, GRB.MAXIMIZE)
model.update()
model.setParam("mipgap", 0.001)
model.optimize()
shortcut_allocations = get_shortcut_allocations(model, network)
print("Number of shortcuts with non-zero capacity", len(shortcut_allocations))
print("Bypassed capacity:", sum(shortcut_allocations.values()))
write_shortcut_allocations(network, args.hops, args.scale, args.network)
