from helper import *
from cpwan_parser import *
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("hops", help="maximum number of shortcut hops", type=int)
parser.add_argument("-s", "--scale", help="scale demands by this factor", type=float, default=1.0)
parser.add_argument("-f", "--failure", help="number of link failures", type=int, default=0)
parser.add_argument("-m", "--model", help="failure model: kwise or teavar", type=str,
                    default="kwise")
parser.add_argument("-n", "--name", help="network name", type=str, default="cpwan")
args = parser.parse_args()
print(args)


def mk_network(model, main_network):
    network = init_network(args.name, scale=args.scale)
    init_graph(network)
    shortcut_node_pairs = init_shortcuts(network, nhops=args.hops)
    remove_demands_without_tunnels(network)
    initialize_optimization_variables(model, network, main_network)
    model.update()
    get_constraints(network, shortcut_node_pairs, model)
    model.update()
    return network

def solve_wavelength(model, network):
    objective = get_wavelength_objective(network)
    model.setObjective(objective, GRB.MAXIMIZE)
    model.update()
    model.setParam("mipgap", 0.001)
    model.setParam("timelimit", 500)
    model.optimize()

def add_failures(model, network):
    if not args.failure:
        return
    elif args.failure == 1:
        viable_link_failures = get_viable_failures(network, k=1)
    else:
        viable_link_failures = get_viable_failures(network, k=2)
    
    # single link failure scenarios
    for failed_edge_list in viable_link_failures:
        print("Robust to failure on edge", failed_edge_list)

        # Initialize a new network for the failure scenario
        f_network = mk_network(model, network)

        failure_scenario_flow_constraint(f_network, [failed_edge_list], model)

def get_allocations(model, network, name):
    shortcut_allocations = get_shortcut_allocations(model, network)
    print("Number of shortcuts with non-zero capacity", len(shortcut_allocations))
    print("Bypassed capacity:", sum(shortcut_allocations.values()))
    write_shortcut_allocations(network, args.hops, args.scale, name, failure_links = args.failure)

# Solve for k-resiliency: 0, 1, 2 failure scenarios
def solve_k_resilient():
    model = Model("mip")
    network = mk_network(model, None)
    add_failures(model, network)
    solve_wavelength(model, network)
    get_allocations(model, network, args.name)

def add_wavelength_bound(model, network, bound):
    objective = get_wavelength_objective(network)
    model.addConstr(objective >= bound)

def solve_teavar_instance(beta, probs, bound, round):
    import teavar
    model = Model("mip")
    network = mk_network(model, None)    
    f_network = mk_network(model, network)    
    alpha = teavar.teavar(model, f_network, beta, probs)
    add_wavelength_bound(model, network, bound)
    model.update()
    model.setParam("mipgap", 0.001)
    model.setParam("timelimit", 600)
    model.optimize()
    name = f"{args.name}-beta{beta}-bound{bound}-round{round}"
    try:
        print("VAR:", alpha.x, model.getObjective().getValue())
        return alpha.x, model.getObjective().getValue()
    except AttributeError:
        print("Infeasible model")
        return None, None
    
def init_teavar():
    model = Model("mip")
    network = mk_network(model, None)
    solve_wavelength(model, network)
    max_bound = model.getObjective().getValue()
    return max_bound, network

def solve_teavar_scenarios(betas, rounds):
    import teavar
    max_bound, network = init_teavar()
    num_bounds = 5
    cutoff = 0.00001
    results = [["beta", "round", "alpha", "cvar", "ports_saved", "hops", "max_saving"]]
    for i in range(num_bounds + 1):
        bound = max_bound * (i / num_bounds)
        # if i < num_bounds:continue
        for beta in betas:
            for r in range(rounds):
                print("CASE:", bound, beta, r)
                scenario_probs = teavar.init_scenarios(network, cutoff)
                alpha, cvar = solve_teavar_instance(beta, scenario_probs, bound, r)
                results.append([beta, r, alpha, cvar, int(bound), args.hops, int(max_bound)])

        path = f"{root_dir}/cpwan/"
        fname = f"{path}/teavar_{args.hops}_{args.scale}.csv"
        with open(fname, "a") as fi:
            writer = csv.writer(fi)
            writer.writerows(results)

def solve_teavar():
    betas = [0.9, 0.99]
    rounds = 4
    solve_teavar_scenarios(betas, rounds)

if __name__ == '__main__':
    if args.model == "kwise":
        print("Solving the K-wise failure model")
        solve_k_resilient()
    else:
        print("Solving the TeaVaR failure model")
        solve_teavar()
