from helper import *
from itertools import islice
import networkx as nx
import pdb
import csv
from NetworkTopology import *

# teavar-data directory can be downloaded from: https://github.com/manyaghobadi/teavar/tree/master/code/data

def parse_topology(network_name):
    network = Network(network_name)
    nxnetwork = nx.Graph()
    with open("teavar-data/%s/topology.txt" % network_name) as fi:
        reader = csv.reader(fi, delimiter=" ")
        for row_ in reader:
            if row_[0] == 'to_node': continue
            row = [x for x in row_ if x]
            to_node = row[0]
            from_node = row[1]
            capacity = float(row[2])/1000.0
            network.add_node(to_node, None, None)
            network.add_node(from_node, None, None)
            network.add_edge(from_node, to_node, 100, capacity)
            nxnetwork.add_node(to_node)
            nxnetwork.add_node(from_node)
            nxnetwork.add_edge(from_node, to_node)

    return network, nxnetwork

def k_shortest_paths(G, source, target, k):
    return list(islice(nx.shortest_simple_paths(G, source, target), k))

def parse_demands(network_name, network, scale=1):
    num_nodes = len(network.nodes)
    demand_matrix = {}
    with open("teavar-data/%s/demand.txt" % network_name) as fi:
        reader = csv.reader(fi, delimiter=" ")
        for row_ in reader:
            if row_[0] == 'to_node': continue
            row = [float(x) for x in row_ if x]
            assert len(row) == num_nodes ** 2
            for idx, dem in enumerate(row):
                from_node = int(idx/num_nodes) + 1
                to_node = idx % num_nodes + 1
                assert str(from_node) in network.nodes
                assert str(to_node) in network.nodes
                if from_node not in demand_matrix:
                    demand_matrix[from_node] = {}
                if to_node not in demand_matrix[from_node]:
                    demand_matrix[from_node][to_node] = []
                demand_matrix[from_node][to_node].append(dem/1000.0)
        for from_node in demand_matrix:
            for to_node in demand_matrix[from_node]:
                max_demand = max(demand_matrix[from_node][to_node])
                network.add_demand(str(from_node), str(to_node), max_demand, scale)

    return network

def parse_tunnels(network, nxnetwork):
    # Parse tunnels
    for node1 in network.nodes:
        for node2 in network.nodes:
            if node1 == node2: continue
            paths = k_shortest_paths(nxnetwork, node1, node2, 5)
            for path in paths:
                tunnel = network.add_tunnel(path)
    return network
