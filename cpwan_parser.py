from itertools import groupby
from graph_tool.all import *
import graph_tool as gt
import graph_tool.draw
import graph_tool.collection
from geopy.distance import distance
from NetworkTopology import *
from consts import *
import pdb
import csv

def get_site_info(markets, region_to_nodes):
    '''
    Get the latitude and longitude of all markets.
    '''
    site_info = {}
    with open(OPTICAL_SITE_INFO) as fi:
        reader = csv.reader(fi)
        for row in reader:
            if row[0] == 'SiteCode': continue
            sitecode = row[0]
            lat = float(row[2])
            lon = float(row[3])
            if sitecode in markets:
                site_info[sitecode] = (lat, lon)
            elif sitecode in region_to_nodes:
                site_info[region_to_nodes[sitecode]] = (lat, lon)
    return site_info

def add_demands_network(network, scale):
    with open(CPWAN_TM) as fi:
        reader = csv.reader(fi)
        for row in reader:
            if row[0] == "SrcRegion": continue
            srcregion = row[0]
            dstregion = row[1]
            mktA = row[2]
            mktB = row[3]
            if srcregion not in region_to_nodes:
                region_to_nodes[srcregion] = mktA
            else:
                assert region_to_nodes[srcregion] == mktA
            if dstregion not in region_to_nodes:
                region_to_nodes[dstregion] = mktB
            else:
                assert region_to_nodes[dstregion] == mktB
                flow = float(row[-1])/1024.0
                network.add_demand(mktA, mktB, flow, scale)
                
    return region_to_nodes

def init_network(name, scale=1.0):
    network = Network(name)
    region_to_nodes = add_demands_network(network, scale)
    
    with open(CPWAN_TOPOLOGY) as fi:
        reader = csv.reader(fi)
        for row in reader:
            if row[0] == 'StartRegion': continue
            regionA = row[0]
            deviceA = row[1]
            interfaceA = row[2]
            regionB = row[4]        
            deviceB = row[5]
            interfaceB = row[6]
            opstate = row[8]
            # if opstate != 'Up': continue
            if regionA == regionB: continue
            try:
                mktA = region_to_nodes[regionA]
            except KeyError:
                print(regionA)
                continue
            try:
                mktB = region_to_nodes[regionB]
            except KeyError:
                print(regionB)
                continue
            if mktA == mktB: continue
            capacity = float(row[10])/1000
            network.add_node(mktA, regionA, deviceA)
            network.add_node(mktB, regionB, deviceB)
            # If the edge exists, this will increment its capacity
            # assuming that the edge has the highest possible
            # modulation format and will downgrade based on
            # distance.
            network.add_edge(mktA, mktB, 200, capacity)
           
    markets = network.nodes.keys()
    site_info = get_site_info(markets, region_to_nodes)
    for market in site_info:
        node = network.add_node(market)
        node.update(latitude=site_info[market][0], longitude=site_info[market][1])

    for edge_pair in network.edges:
        edge = network.edges[edge_pair]
        nodeA = network.nodes[edge_pair[0]]
        nodeB = network.nodes[edge_pair[1]]
        edge_length = distance((nodeA.latitude, nodeA.longitude),
                               (nodeB.latitude, nodeB.longitude)).km
        edge.add_distance(edge_length)
        if edge_length <= 800:
            pass
        elif edge_length <= 2500:
            edge.unity = 150
        else:
            edge.unity = 100

    parse_tunnels(network, region_to_nodes)
    # Make sure every demand has at least one tunnel
    # no_tunnel_demands = [x for x in network.demands if len(network.demands[x].tunnels) == 0]
    return network

def parse_tunnels(network, region_to_nodes):
    with open(CPWAN_PATHS) as fi:
        reader = csv.reader(fi)
        for row in reader:
            if row[0] == "Source": continue
            source_device = row[0]
            destination_region = row[1]
            path = row[2]
            path_processed = [region_to_nodes[x] for x in path.split(':')]
            path_processed = [x[0] for x in groupby(path_processed)]
            if len(path_processed) > len(set(path_processed)):
                # Loopy tunnel, skipping
                continue
            try:
                tunnel = network.add_tunnel(path_processed)
            except AssertionError:
                print("Some edges don't exist", path_processed)
