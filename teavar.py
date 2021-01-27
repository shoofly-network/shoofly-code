import numpy as np

def ones(n):
    return [1 for i in range(n)]

def zeros(n):
    return [0 for i in range(n)]

def prod(xs):
    r = 1.0
    for x in xs:
        r *= x
    return r

#
# Scenario enumeration
# ported from https://github.com/manyaghobadi/teavar/blob/eb6de9ff0d47febb493e466c34edcadd975fdeca/code/util.jl
#
def subscenarios_rec(distribution, cutoff, remaining, offset = 0, partial = [],
                     scenario_probs = []):
    assert all(0 <= p and p <= 1 for p in distribution)
    assert all(index < len(distribution) for index in partial)
    index_set = range(len(distribution))
    bitmap = [0 if index in partial else 1 for index in index_set]
    probs  = [distribution[index] if index in partial else 1 - distribution[index] 
              for index in index_set]
        
    prob   = prod(probs)
    offset = len(distribution) - remaining
    
    if len(partial) == 0 or prob >= cutoff:
        scenario_probs.append((bitmap, prob))        

    for i in range(remaining):
        n = offset + i
        prefix_prob = prod([distribution[j] if j in partial else 1 - distribution[j]
                            for j in range(n)])
        if prefix_prob < cutoff:
            return scenario_probs
        subscenarios_rec(distribution, cutoff, remaining - i - 1, offset,
                         partial + [n], scenario_probs)
    return scenario_probs

def subscenarios(distribution, cutoff, first=True, last=True):
    scenario_probs = subscenarios_rec(distribution, cutoff, len(distribution))
    if not first:
        scenario_probs = scenario_probs[1:]
    sum_prob = sum(sp[1] for sp in scenario_probs)
    if sum_prob < 1 and last:
        scenario_probs.append((zeros(len(distribution)), 1 - sum_prob))        
    elif sum_prob > 1 or sum_prob < 1:
        scenario_probs = [(sp[0], sp[1]/sum_prob) for sp in scenario_probs]
    return scenario_probs


def weibull_probs(num, shape=.8, scale=.0001):
#def weibull_probs(num, shape=.8, scale=.1):
    def xv(z):
        return scale * pow(z, 1 / shape)
    return [xv(np.random.exponential()) for _ in range(num)]


def teavar(model, network, beta, scenario_probs):
    import helper
    from gurobipy import GRB
    alpha = model.addVar(lb = 0, name = "alpha")

    # A tunnel is enabled if all edges on tunnel are enabled under scenario
    def enabled(scenario, t):
        return all(scenario[edge.e] for edge in t.path)

    #
    # Assemble the following triples into qs:
    # - scenario map - it makes each edge into True or False.    
    # - probability  - probability of scenario
    # - slack        - a slack variable representing scenario
    #
    sp = scenario_probs
    qs = [(sp[i][0], sp[i][1], model.addVar(name = f"slack{i}", lb = 0)) for i in range(len(sp))]
    model.update()
    # for (scenario, prob, slack) in qs:
    #     print(prob, slack)
        
    # F_beta constraints:
    f_beta = alpha + (1.0 / (1.0 - beta)) * sum(prob * slack for (scenario, prob, slack) in qs)

    # The objective is f_beta
    model.setObjective(f_beta, GRB.MINIMIZE)
        
    # Add inequalities for slack variables that are used to define f_beta:
    for (scenario, prob, slack) in qs:
        for edge in scenario:
            assert edge in network.edges
        for d in network.demands.values():
            if d.amount == 0: continue
            t_dq = 1.0 - (1.0 / d.amount)*sum(t.v_flow for t in d.tunnels if enabled(scenario, t))
            model.addConstr(slack >= t_dq - alpha)
            
    # Capacity constraints:
    helper.flow_conservation_constraints(network, model)    
    helper.edge_capacity_constraints(network, model)    
    helper.wavelength_integrality_constraints(network, model)
    return alpha

# Convert scenario vectors to a map from edges to whether they are enabled
def init_scenario_map(edges, scenario_probs):
    index = 0
    e2idx = {}
    assert all(len(sp[0]) == len(edges)/2 for sp in scenario_probs)
    
    for (a, b) in edges:
        if (a, b) in e2idx:
            continue
        e2idx[(a, b)] = index
        e2idx[(b, a)] = index
        index += 1
    return [({edge : sp[0][e2idx[edge]] == 1 for edge in edges}, sp[1])
            for sp in scenario_probs]

def init_scenarios(network, cutoff):
    #
    # 1. initialize a distribution
    # 2. extract a set of failure scenarios using cutoffs
    # 3. represent the scenarios as mapping edges to failure modes
    #
    edges = { edge.e for edge in network.edges.values() }
    edges |= { (a, b) for (b, a) in edges }
    num_edges      = int(len(edges) / 2)
    distribution   = weibull_probs(num_edges)
    scenario_probs = subscenarios(distribution, cutoff)
    scenario_probs = init_scenario_map(edges, scenario_probs)
    return scenario_probs


if __name__ == '__main__':
    print("Test")
    cutoff = 0.000001
    wb = weibull_probs(10, shape=0.8, scale=0.001)
    scenario_probs = subscenarios(wb, cutoff, first=True, last=False)
    print(scenario_probs)
