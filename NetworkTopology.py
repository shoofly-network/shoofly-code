from gurobipy import *

class Node:
    def __init__(self, mkt):
        self.mkt = mkt
        self.latitude = None
        self.longitude = None
        self.devices = []
        self.regions = []
        
    def update(self, device=None, region=None, latitude=None, longitude=None):
        if device and device not in self.devices:
            self.devices.append(device)
        if region and region not in self.regions:
            self.regions.append(region)
        if latitude:
            self.latitude = latitude
        if longitude:
            self.longitude = longitude
            
class Edge:
    #
    # An Edge contains a Graph edge object.
    # and additional attributes.
    # shortcuts - List of shortcuts that the edge is a part of
    # tunnels   - List of tunnels that he edge is part of
    # x_e_t     - Traffic allocation on e for tunnel t
    #
    def __init__(self, e, unity, capacity):
        self.e = e
        self.unity    = unity
        self.capacity = capacity
        self.distance = None
        self.shortcuts = []
        self.tunnels = []
        self.x_e_t = {}

    def add_shortcut(self, s):
        assert self.e in [edge.e for edge in s.path]
        if all(s.pathstr != x.pathstr for x in self.shortcuts):
            self.shortcuts.append(s)

    def add_tunnel(self, t):
        assert self.e in [edge.e for edge in t.path]
        if all(t.pathstr != x.pathstr for x in self.tunnels):
            self.tunnels.append(t)        
    
    def increment_capacity(self, capacity_increment):
        self.capacity += capacity_increment

    def add_distance(self, distance):
        self.distance = distance

    def init_x_e_vars(self, model):
        for idx in range(len(self.tunnels)):
            tunnel = self.tunnels[idx]
            var = model.addVar(lb = 0, name = f"x_e_{idx}")
            self.x_e_t[tunnel] = var
        return model            
    
class Demand:
    def __init__(self, src, dst, amount):
        self.src = src
        self.dst = dst
        self.amount = amount
        self.tunnels = []

    def add_tunnel(self, t):
        assert t.pathstr.split(':')[0] == self.src
        assert t.pathstr.split(':')[-1] == self.dst
        if t.pathstr not in [x.pathstr for x in self.tunnels]:
            self.tunnels.append(t)        
        
class Shortcut:
    def __init__(self, path, pathstr, unity, distance):
        self.path = path
        self.pathstr = pathstr
        assert unity > 0
        self.unity = unity
        self.distance = distance
        self.src = path[0].e[0]
        self.src = path[-1].e[1]
        self.w_s = 0
        self.y_s = {}
        # List of tunnels that the shortcut is in
        self.tunnels = []
        for e in path:
            e.add_shortcut(self)

    def name(self):
        return self.pathstr
    
    def add_tunnel(self, t):
        assert self.pathstr in t.pathstr
        if all(t.pathstr != x.pathstr for x in self.tunnels):
            self.tunnels.append(t)        

    def init_wavelength_vars(self, model, var=None):
        if not var:
            self.w_s = model.addVar(lb = 0, vtype=GRB.INTEGER, name = self.name())
        else:
            self.w_s = var
        return model
    
    def init_y_s_vars(self, model):
        for idx in range(len(self.tunnels)):
            tunnel = self.tunnels[idx]
            self.y_s[tunnel] = model.addVar(lb = 0, name = f"y_{idx}")                 
        return model

class Tunnel:
    def __init__(self, path, pathstr):
        # path here is a list of edges
        self.path = path
        self.pathstr = pathstr
        # shortcuts that are a part of the tunnel
        self.shortcuts = []
        self.v_flow = None    # Solver variable for flow
        # add this tunnel to all relevant edges
        for e in path:
            e.add_tunnel(self)
        
    def name(self):
        return self.pathstr
    
    def init_flow_var(self, model):
        self.v_flow = model.addVar(lb = 0, name = self.name())
        return model

    def add_shortcut(self, s):
        self.shortcuts.append(s)
    
class Network:
    def __init__(self, name):
        self.name = name
        self.nodes = {}
        self.edges = {}
        self.shortcuts = {}
        self.tunnels = {}
        self.demands = {}
        self.graph = None
        
    def add_node(self, mkt, region=None, device=None):
        assert isinstance(mkt, str)
        if mkt in self.nodes:
            node = self.nodes[mkt]
        else:
            node = Node(mkt)
            self.nodes[mkt] = node
        node.update(device=device, region=region)
        return node

    def add_edge(self, mktA, mktB, unity=None, capacity=None):
        assert isinstance(mktA, str)
        assert isinstance(mktB, str)
        self.add_node(mktA)
        self.add_node(mktB)
        if mktA == mktB: return None
        
        if (mktA, mktB) in self.edges:
            edge = self.edges[(mktA, mktB)]
            edge.increment_capacity(capacity)
        else:
            edge = Edge((mktA, mktB), unity, capacity)
            self.edges[(mktA, mktB)] = edge
            
        return edge

    def add_demand(self, src, dst, amount, scale=1):
        assert isinstance(src, str)
        assert isinstance(dst, str)
        self.add_node(src)
        self.add_node(dst)
        
        if (src, dst) not in self.demands:
            self.demands[(src, dst)] = Demand(src, dst, amount*scale)

        return self.demands[(src, dst)]

    def add_tunnel(self, tunnel):
        assert isinstance(tunnel, list)
        assert isinstance(tunnel[0], str)
        tunnel_str = ":".join(tunnel)
        if tunnel_str in self.tunnels: return
        
        tunnel_start = tunnel[0]
        tunnel_end = tunnel[-1]
        tunnel_edge_list = []
        for src, dst in zip(tunnel, tunnel[1:]):
            nodeA = self.add_node(src)
            nodeB = self.add_node(dst)
            assert (src, dst) in self.edges
            edge = self.edges[(src, dst)]
            tunnel_edge_list.append(edge)

        tunnel_obj = Tunnel(tunnel_edge_list, tunnel_str)
        self.tunnels[tunnel_str] = tunnel_obj        
        if (tunnel_start, tunnel_end) in self.demands:
            demand = self.demands[(tunnel_start, tunnel_end)]
            demand.add_tunnel(tunnel_obj)
        
    def add_shortcut(self, shortcut, unity, distance):
        assert isinstance(shortcut, list)
        assert isinstance(shortcut[0], str)
        if unity == 0: return
        shortcut_str = ":".join(shortcut)
        if shortcut_str in self.shortcuts:
            return
        
        shortcut_edge_list = []
        for src, dst in zip(shortcut, shortcut[1:]):
            nodeA = self.add_node(src)
            nodeB = self.add_node(dst)
            assert (src, dst) in self.edges
            edge = self.edges[(src, dst)]
            shortcut_edge_list.append(edge)

        shortcut_obj = Shortcut(shortcut_edge_list, shortcut_str, unity, distance)
        self.shortcuts[shortcut_str] = shortcut_obj
        
        for tunnel_str in self.tunnels:
            if shortcut_str in tunnel_str:
                tunnel_obj = self.tunnels[tunnel_str]
                tunnel_obj.add_shortcut(shortcut_obj)
                shortcut_obj.add_tunnel(tunnel_obj)
        assert shortcut_obj 
        return shortcut_obj
