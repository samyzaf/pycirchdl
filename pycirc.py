import sys
import os
import networkx as nx
from copy import deepcopy
from .util import *
from . import cfg
from .cfg import set_path, path_add, path_del
from .logops import *
from fnmatch import fnmatch
from urllib.request import urlopen, Request
#import inspect

class Cell(object):
    def __init__(self, name, **opt):
        self.name = name
        inp = opt.get("input")
        if isinstance(inp, str):
            inp = expand(inp)
        out = opt.get("output")
        if isinstance(out, str):
            out = expand(out)
        self.input = inp
        self.output = out
        self.operator = opt.get("operator")
        self.depth = opt.get("depth", 0)
        self.type = opt.get("type", "box")  # type = "circ", "box", or "const"
        self.i = Assign(self.input)
        self.o = Assign(self.output)
        if self.type == "const":
            #o = self.operator({**self.i , **self.o})
            o = self.operator(self.i + self.o)
            for y in self.output: self.o[y] = o[y]

    def set(self, a):
        for x in self.input:
            self.i[x] = a[x]

    def run(self):
        o = self.operator(self.i)
        for name in o.names:
            self.o[name] = o[name]

    def get(self):
        return self.o

    def __call__(self, a):
        self.set(a)
        self.run()
        return self.get()

    def __setitem__(self, x, v):
        self.i[x] = v

    def __getitem__(self, y):
        return self.o[y]

#-------------------------------------------------------------------------------

#class PyCirc(nx.DiGraph):
class PyCirc(nx.MultiDiGraph):
    __circmap = dict()
    def __class_getitem__(cls, key):
        return cls.__circmap[key]

    def __init__(self, name, gates, wires, **attr):
        super(PyCirc, self).__init__()
        self.name = name
        #print(f"PyCirc: name={name}\n gates={[g.name for g in gates]}\n wires={[(w.source,w.target) for w in wires]}")
        self.__name_map = dict()
        self.__edge_map = dict()
        self.read_wires(wires)
        self.wires = wires
        self.gates = sorted(self.nodes, key=lambda n: n.id)

        G1 = set([g.name for g in gates])
        G2 = set([g.name for g in self.gates])
        dif1 = tuple(G1 - G2)
        if dif1:
            raise Exception("Isolated gates: %s" % dif1)
        dif2 = tuple(G2 - G1)
        if dif2:
            raise Exception("Missing gates: %s" % [g.name for g in dif2])
        self.depth = 0
        self.validity_check()
        self.input = []
        self.output = []
        self.logic_gates = []
        for gate in self.gates:
            self.__name_map[gate.name] = gate
            if gate.type == "inp":
                self.input.append(gate)
            elif gate.type == "out":
                self.output.append(gate)
            else:
                self.logic_gates.append(gate)
        self.reset()
        self.__assign_depth()
        self.__class__.__circmap[name] = self

    def reset(self):
        self.curr_layer = 0
        for gate in self.gates:
            gate.reset()

    #todo: check that in lgate, from every pin has an outgoing edge?
    def validity_check(self):
        for gate in self.gates:
            if gate.type == "inp":
                in_edges = list(self.in_edges(gate))
                if len(in_edges):
                    raise Exception("INP gate cannot have an incoming edge!")
            elif gate.type == "out":
                out_edges = list(self.out_edges(gate))
                if len(out_edges):
                    raise Exception("OUT gate cannot have an outgoing edge!")
                in_edges = list(self.in_edges(gate, data=True))
                if len(in_edges) != 1:
                    raise Exception("OUT gate must have exactly one incoming edge!")
            else:
                in_edges = self.in_edges(gate, data=True)
                in_pins = set()
                for e in in_edges:
                    e0, e1, data = e
                    in_pins.add(data["target_pin"])
                inpset = set(gate.cell.input)
                #print("in_pins =", in_pins)
                #print("inpset =", inpset)
                dif = inpset - in_pins
                if dif:
                    raise Exception("Not all gate pins initialized! %s : %s" % (gate, dif))

                out_edges = self.out_edges(gate, data=True)
                out_pins = set()
                for e in out_edges:
                    e0, e1, data = e
                    out_pins.add(data["source_pin"])
                    #print("Edge[0] =",str(e0))
                outset = set(gate.cell.output)
                #print("out_edges=", str(gate), self.out_edges(gate))
                #print("output of gate", str(gate), "=", gate.cell.output)
                #print("out_pins", str(out_pins))
                #print("outset", outset)
                dif = outset - out_pins
                if dif:
                    print("ATTENTION: some outputs are dangling! %s (%s) : %s" % (gate.name, gate.cell.name, dif))
        try:
            C = nx.find_cycle(self, orientation="original")
            if C:
                print("No cycles allowed in a circuit!")
        except nx.NetworkXNoCycle:
            print("Cell = %s: Validity check: OK." % (self.name,))

    # Edges are created using the Wire class.
    # Besides the two gates g1, g2, need to specify source_pin (p1) and target_pin (p2).
    # By default, target_pin is "y" since most logic cells have exacly one output "y"
    # except when g1 is of type "inp" which has no logic pins
    def read_wires(self, wires):
        for wire in wires:
            g1 = wire.gate1
            g2 = wire.gate2
            p1 = wire.source_pin
            p2 = wire.target_pin
            self.add_edge(g1, g2, source_pin=p1, target_pin=p2, key=wire.id)
            self.__edge_map[wire.id] = wire
            self.__name_map[wire.source,wire.target] = wire

    def in_wires(self, gate):
        wires = list()
        for edge in self.in_edges(gate, data=True, keys=True):
            edge_key = edge[2]
            #print("edge_key=", edge_key)
            wires.append(self.__edge_map[edge_key])
        return wires

    def out_wires(self, gate):
        wires = list()
        for edge in self.out_edges(gate, data=True, keys=True):
            edge_key = edge[2]
            wires.append(self.__edge_map[edge_key])
        return wires

    def in_gates(self, gate):
        in_gates = set()
        for wire in self.in_wires(gate):
            in_gates.add(wire.gate1)
        return sorted(in_gates)

    def out_gates(self, gate):
        out_gates = set()
        for wire in self.out_wires(gate):
            out_gates.add(wire.gate2)
        return sorted(out_gates)

    def set(self, a):
        for x in self.input:
            x.value = a[x.name]
        self.curr_layer = 1

    def get(self):
        names = [y.name for y in self.output]
        bits = [y.value for y in self.output]
        o = Assign(names, bits)
        return o

    def step(self):
        l = self.curr_layer
        if l > self.depth:
            raise Exception("Cannot exceed graph depth")
        for gate in self.layer[l]: 
            if gate.type == "out":
                in_edges = list(self.in_edges(gate, data=True))
                pgate, _, data = in_edges[0]
                if pgate.type == "inp":
                    gate.value = pgate.value
                else:
                    gate.value = pgate.cell.o[data["source_pin"]]
            else:
                d = dict()
                for e in self.in_edges(gate, data=True):
                    g1,g2,data = e
                    if g1.type == "inp":
                        d[data["target_pin"]] = g1.value
                    else:
                        p1 = data["source_pin"]
                        p2 = data["target_pin"]
                        d[p2] = g1.cell.o[p1]
                if not set(d) == set(gate.cell.i):
                    raise Exception("Not all gate pins initialized exception")
                gate.cell.set(d)
                gate.cell.run()
                #print("aaa>>>", pnodes[0], n)

        self.curr_layer += 1

    def run(self):
        while self.curr_layer <= self.depth:
            self.step()

    def dangling_pins(self):
        dang_pins = []
        for gate in self.gates:
            if gate.type == "inp" or gate.type == "out":
                continue
            out_edges = self.out_edges(gate, data=True)
            out_pins = set()
            for e in out_edges:
                source, target, data = e
                out_pins.add(data["source_pin"])
            outset = set(gate.cell.output)
            #print("out_edges=", str(gate), self.out_edges(gate))
            #print("output of gate", str(gate), "=", gate.cell.output)
            #print("out_pins", str(out_pins))
            #print("outset", outset)
            for p in outset - out_pins:
                dang_pins.append(f"{gate.name}/{p}")
        return dang_pins

    def getframes(self, d):
        self.reset()
        f0 = self.getframe()
        self.set(d)
        f1 = self.getframe()
        frames = [f0,f1]
        while self.curr_layer <= self.depth:
            self.step()
            f = self.getframe()
            frames.append(f)
        return frames

    def getframe(self):
        f = dict()
        for gate in self.gates:
            val = gate.get()
            if gate.type == "inp" or gate.type == "out":
                f[gate.name] = val
            else:
                for pin in val:
                    f[gate.name + "." + pin] = val[pin]
        return f

    def __assign_depth(self):
        dp = dict()
        for g in self.gates:
            dp[g] = 0
        ctr = 0
        n = 2 * len(self.gates)
        while True:
            ctr += 1
            stable = True
            for gate in self.gates:
                ingates = self.in_gates(gate)
                if ingates:
                    old = dp[gate]
                    dp[gate] = max(dp[g] for g in ingates) + 1
                    if not old == dp[gate]:
                        stable = False
            if stable:
                break
            if ctr > n:
                print("Could not assign depth. Check graph. ctr=", ctr)

        for g in self.gates:
            g.depth = dp[g]
        if self.gates:
            self.depth = max(g.depth for g in self.gates)

        self.layer = dict()
        for l in range(self.depth+1):
            self.layer[l] = []
        for g in self.gates:
            self.layer[g.depth].append(g)

    def __call__(self, a):
        self.reset()
        self.set(a)
        self.run()
        return self.get()

    def __getitem__(self, name):
        return self.__name_map[name]

    def __str__(self):
        inp = "Input: " + " : ".join([str(n) for n in self.input])
        out = "Output: " + " : ".join([str(n) for n in self.output])
        gts = "Gates: " + " : ".join([str(n) for n in self.logic_gates])
        return inp + "\n" + out + "\n" + gts

    @classmethod
    def delete(cls, key):
        del cls.__circmap[key]

    @classmethod
    def names(cls):
        return cls.__circmap.keys()

    #def __del__(self):
    #    del self.__class__.__circmap[self.name]

#-------------------------------------------------------------------------------

class Gate(object):
    id = 0
    map = dict()
    def __class_getitem__(cls, key):
        return cls.map[key]

    def __init__(self, name, **opt):
        self.name = name
        self.type = opt.get("type")
        self.depth = None
        if self.type == "inp" or self.type == "out":
            self.value = None
        else:
            self.cell = pycircLib.get(self.type)
        self.reset()
        self.id = self.__class__.id
        self.__class__.id += 1
        self.__class__.map[self.name] = self
        if cfg.circd:
            cellname = [*cfg.circd.keys()][-1]
            cfg.circd[cellname][0].append(self)
        #print(f"Gate: {self.name}, cellname={cellname}")
        ##globals()[self.name] = self
        ##thiscell = sys.cells[__name__]
        ##curr_cell = sys.cells[__name__]
        ##curr_cell.__dict__[self.name] = self
        #stk = inspect.stack()[1]
        ##print("stk =", stk)
        #cell = inspect.getcell(stk[0])
        ##print("mod =", mod.name)
        #if cell.name == "logcirc":
        #    return
        #cell.__dict__[self.name] = self

    def reset(self):
        if self.type == "inp" or self.type == "out":
            self.value = None
        elif self.type == "zero" or self.type == "one":
            pass
        else:
            for x in self.cell.input:
                self.cell.i[x] = None
            for y in self.cell.output:
                self.cell.o[y] = None

    def set(self, d):
        if self.type == "inp" or self.type == "out":
            self.value = d
        else:
            for y in self.cell.output:
                self.cell.o[y] = None
            for x in self.cell.input:
                self.cell.i[x] = d[x]

    def run(self):
        if self.type == "inp" or self.type == "out":
            return
        self.cell.run()

    def get(self):
        if self.type == "inp" or self.type == "out":
            return self.value
        else:
            return self.cell.o

    def __lt__(self, other):
        return self.id <= other.id

    #def __call__(self, x):
    #    if self.type == "inp" or self.type == "out":
    #        raise Exception("__all__ invalid for inp/out gate!")
    #    return self, x

    #def __getitem__(self, x):
    #    if self.type == "inp" or self.type == "out":
    #        raise Exception("__getitem__ invalid for inp/out gate!")
    #    return self, x

    #def __truediv__(self, x):
    #    if self.type == "inp" or self.type == "out":
    #        raise Exception("__getitem__ invalid for inp/out gate!")
    #    return self, x

    def __str__(self):
        val = self.get()
        return "gate id=%d: name=%s, type=%s, value=(%s), depth=%s" % (self.id, self.name, self.type, val, self.depth)

#-------------------------------------------------------------------------------

def GATE(name, **opt):
    gates = list()
    for n in expand(name):
        g = Gate(n, **opt)
        gates.append(g)
    return gates

#-------------------------------------------------------------------------------

class Wire(object):
    id = 0
    markers = [0,0]
    map = dict()
    def __init__(self, source, target, **opt):
        if "/" in source:
            gate1, self.source_pin = source.split("/")
        else:
            gate1 = source
            self.source_pin = None
        if "/" in target:
            gate2, self.target_pin = target.split("/")
        else:
            gate2 = target
            self.target_pin = None

        self.source = source
        self.target = target
        self.gate1 = Gate[gate1]
        self.gate2 = Gate[gate2]
        default_name = "wire_" + str(self.id)
        self.name = opt.get("name", default_name)
        self.__checks()
        self.id = self.__class__.id
        self.__class__.id += 1
        self.__class__.map[self.name] = self
        if cfg.circd:
            cellname = [*cfg.circd.keys()][-1]
            cfg.circd[cellname][1].append(self)

    def __checks(self):
        g1 = self.gate1
        g2 = self.gate2
        p1 = self.source_pin
        p2 = self.target_pin
        if g1.type == "inp":
            if not p1 is None:
                raise Exception("input gate has no pins!")
        else:
            if p1 is None:
                if len(g1.cell.output) == 1:
                    self.source_pin = g1.cell.output[0]
                else:
                    raise Exception("Missing source_pin arg! for gate: %s" % (g1.name))
            else :
                if not p1 in g1.cell.output:
                    raise Exception("Illegal source_pin arg! for gate: %s, %s" % (g1.name, p1))

        if g2.type == "out":
            if not p2 is None:
                raise Exception("output gate has no pins!")
        else:
            if p2 is None:
                if len(g2.cell.input) == 1:
                    self.target_pin = g2.cell.input[0]
                else:
                    raise Exception("Missing source_pin arg! for gate: %s" % (g2.name))
            else :
                if not p2 in g2.cell.input:
                    raise Exception("Illegal target_pin arg! for gate: %s" % (g2.name))

    def __str__(self):
        fmt = "wire id=%d:\n  source=%s\n  target=%s\n  source=%s\n  target=%s"
        return fmt % (self.id, self.gate1, self.gate2, self.source_pin, self.target_pin)

#-------------------------------------------------------------------------------

# sources and targets can be compressed names
# Only 1_to_n, n_to_1, and n_to_n matchings
# are supported.
def WIRE(sources, targets, **opt):
    wires = list()
    S = expand(sources)
    T = expand(targets)
    n1 = len(S)
    n2 = len(T)
    n = max(n1, n2)
    if n1 == 1: S = n * S
    if n2 == 1: T = n * T
    if not len(S) == len(T):
        raise Exception("Number source pins different than number of target pins!")
    #print(S) ; print(50 * "-") ; print(T)
    for a,b in zip(S,T):
        w = Wire(a, b, **opt)
        wires.append(w)

    return wires

#-------------------------------------------------------------------------------

# Class GateFactory
# methods:
# add(cell): cell is a already a Cell object obtained by the Cell class
# add_box: shortcut to cell=Cell(box definition args) and add(cell)
# add_circ: create a cell from a circuit and add it to a lib.
#           shortcut to cell==Cell(circuit definition args) and add(cell)
class GateFactory(object):
    def __init__(self):
        self.lib = dict()

    def add(self, cell):
        name = cell.name
        self.lib[name] = cell

    def add_circ(self, circ):
        input = [g.name for g in circ.input]
        output = [g.name for g in circ.output]
        name = circ.name
        depth = circ.depth
        cell = Cell(name, operator=circ, input=input, output=output, depth=depth, type="circ")
        self.lib[name] = cell
        return cell

    def remove(self, cellname):
        del self.lib[cellname]

    def add_box(self, name, operator, input, output, depth=1, type="box"):
        if operator is None:
            raise Exception("You must provide a valid operator to add a box!")
        if input is None:
            input = []
        elif isinstance(input, str):
            input = expand(input)
        if output is None:
            raise Exception("output must be a non-empty list of names!")
        elif isinstance(output, str):
            output = expand(output)
        cell = Cell(name, operator=operator, input=input, output=output, depth=depth, type=type)
        self.lib[name] = cell
        return cell

    def get(self, name):
        if not name in self.lib:
            need(name)
            #try:
            #    load(name)
            #except:
            #raise Exception("Cell %s not found" % (name,))
        return deepcopy(self.lib[name])

    def list(self, pattern='*', type=""):
        res = []
        if type=="":
            types = ['circ', 'box']
        else:
            types = [type]
        for name in self.lib:
            if fnmatch(name, pattern):
                cell = self.lib[name]
                if cell.type in types:
                    res.append(name)
        return res

    def exists(self, name):
        if name in self.lib:
            return True
        else:
            return False

    def clear(self):
        self.lib.clear()

# We define our single library of cells for testing our classes
# Users can add more libraries if they need to.
# Future dev may enable multiple libraries ... for now this is good to start with.
pycircLib = GateFactory()

#---------------------------------------------------

# A client code must define the library path
# The library path consists of a list of directories or URL's
# from which PyCirc can find a cell.
# Example:
#   set_path([os.path.join(os.path.realpath("."), "lib"), "https://samyzaf.com/pycirc/lib", "d:/eda/pycirc/lib"]

def list_lib_circs(pat="*"):
    circs = []
    for d in cfg.path:
        if "https://" in d:
            files = list_url_files(d)
        else:
            files = os.listdir(d)
        for file in files:
            if fnmatch(file, '*.py') and fnmatch(file[:-3], pat):
                circ = file[:-3]
                circs.append(circ)
    return circs

# Find circuit file in library
def find(circ):
    if not cfg.path:
        print("Cell library path not defined")
        print("Please define cell library path: set_path([dir1, dir2, url1, ...])")
        raise Exception("Cell library path empty!")
        
    print("path =", cfg.path)

    for dir in cfg.path:
        dir = dir.rstrip("/")
        libfile = "%s/%s.py" % (dir, circ)
        if "https://" in libfile:
            try:
                u = urlopen(libfile)
                return libfile
            except:
                pass
        elif os.path.isfile(libfile):
            return os.path.abspath(libfile)

    return None

# Load circuit file to libraries libs.
def load(circ, libs=[pycircLib]):
    libfile = find(circ)
    #print("path =", cfg.path)
    if not libfile:
        raise Exception("Circuit %s not found in library path: %s" % (circ, cfg.path))

    if "https://" in libfile:
        u = urlopen(libfile)
        code = u.read().decode('utf-8')
    else:
        with open(libfile) as f:
            code = f.read()

    Define(circ)
    exec(code)
    ref = EndDef()
    print("Loaded circuit %s from: %s" % (circ, libfile))
    return ref

def unload(circ):
    pycircLib.del_cell(circ)
    PyCirc.delete(circ.name)
    del circ

def need(circname):
    if pycircLib.exists(circname):
        return
    c = load(circname)
    return c

def logcirc(name, gates, wires, register=True):
    circ = PyCirc(name, gates, wires)
    if register:
        pycircLib.add_circ(circ)
    return circ

# Start definition of a Logic Circuit
def Define(circname):
    #print("circd Def=", cfg.circd.keys(), "circname=", circname)
    sys.stdout.flush()
    if circname in cfg.circd:
        raise Exception("Looks like you already started a definition of %s but not finished?" % (circname,))
    cfg.circd[circname] = [[],[]]

# Finalize PyCirc object and add it to libraries in list libs
# Use libs = [] to not add it to any library
# Currently we have only one library pycircLib but future dev may have multiple ...
def EndDef(libs=[pycircLib]):
    #print("circd before=", cfg.circd.keys())
    circname,(gates,wires) = cfg.circd.popitem()
    #print("circd after=",cfg.circd.keys())
    #print(f"circname={circname}")
    #print([g.name for g in gates])
    #print([(w.source,w.target) for w in wires])
    circ = PyCirc(circname, gates, wires)
    for lib in libs:
        lib.add_circ(circ)
    #print("circ stack =", cfg.circd)
    return circ

#-------------------------------------------------------------------------

# These are standard logical cells which we add to pycircLib first:
def load_builtin_box_cells():
    pycircLib.clear()
    pycircLib.add_box(name="zero", operator=Zero, input=[], output=["y"], type="const", depth=0)
    pycircLib.add_box(name="one",  operator=One,  input=[], output=["y"], type="const", depth=0)
    pycircLib.add_box(name="not",  operator=Not,  input=["x"], output=["y"])
    pycircLib.add_box(name="and2", operator=And,  input="x<1:2>", output=["y"])
    pycircLib.add_box(name="and3", operator=And,  input="x<1:3>", output=["y"])
    pycircLib.add_box(name="and4", operator=And,  input="x<1:4>", output=["y"])
    pycircLib.add_box(name="and5", operator=And,  input="x<1:5>", output=["y"])
    pycircLib.add_box(name="and6", operator=And,  input="x<1:6>", output=["y"])
    pycircLib.add_box(name="and7", operator=And,  input="x<1:7>", output=["y"])
    pycircLib.add_box(name="and8", operator=And,  input="x<1:8>", output=["y"])
    pycircLib.add_box(name="and9", operator=And,  input="x<1:9>", output=["y"])
    
    # We can also use loops to add cells to our cell library
    for k in range(2,21):
        inp = "x<1:%s>" % (k,)
        name = "or" + str(k)
        pycircLib.add_box(name, operator=Or, input=inp, output=["y"])
        name = "xor" + str(k)
        pycircLib.add_box(name, operator=Xor, input=inp, output=["y"])
        name = "nor" + str(k)
        pycircLib.add_box(name, operator=Nor, input=inp, output=["y"])
        name = "nand" + str(k)
        pycircLib.add_box(name, operator=Nand, input=inp, output=["y"])
    
    pycircLib.add_box(name="mux1", operator=Mux, input=["s1", "x0", "x1"], output=["y"], depth=3)
    # The following will be defined by a PyCirc circuit:
    #pycircLib.add_box(name="mux2", operator=Mux, input=["s1", "s2", "x0", "x1", "x2", "x3"], output=["y"], depth=4)
    #pycircLib.add_box(name="mux3", operator=Mux, input=["s1", "s2", "s3", "x0", "x1", "x2", "x3", "x4", "x5", "x6", "x7"], output=["y"], depth=5)
    
    # We can can many more MUX cells with the following loop
    # for k in range(1,10):
    #     name = "mux" + str(k)
    #     inp = "x<0:%s> ; s<1:%s>" % (2**k - 1, k)
    #     pycircLib.add_box(name=name, operator=Mux, input=inp, output=["y"])

# A small utility for listing files in a url directory
def list_url_files(url):
    urlpath = urlopen(url)
    string = urlpath.read().decode('utf-8')
    pattern = re.compile('[a-zA-Z0-9_]+.py') #the pattern actually creates duplicates in the list
    filelist = list(set(pattern.findall(string)))
    return filelist

