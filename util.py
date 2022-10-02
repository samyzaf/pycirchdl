import re
from random import randint
from itertools import product
from copy import copy

namereg = r"^[a-zA-Z][_a-zA-Z0-9]*$"
namepat = re.compile(namereg)
groupreg = r"^[a-zA-Z][_a-zA-Z0-9]*<[0-9:, ]+>$" #not fully accurate but practical
grouppat = re.compile(groupreg)

class Assign(dict):
    def __init__(self, names, bits=None):
        #super(Assign, self).__init__()
        self.names = expand(names)
        self.assign(bits)

    def assign(self, bits):
        n = len(self.names)
        if bits == 0 or bits == 1 or bits is None:
            bits = n * [bits]
        elif isinstance(bits, str):
            bits = [int(v) for v in bits]
        elif isinstance(bits, list) or isinstance(bits, tuple):
            _bits = copy(bits)
            bits = []
            for b in _bits:
                if b is None:
                    bits.append(None)
                else:
                    bits.append(int(b))
        else:
            raise Exception("Invalid Assignment bits type")

        if not n == len(bits):
            print("assign: names=", self.names, "bits=", bits)
            raise Exception("Number of names does not match the number of boolean bits")
        for n,v in zip(self.names, bits):
            if v==0 or v==1 or v==None:
                self[n] = v
            else:
                raise Exception("Invalid Assignment value")

    def bits(self, names=None, as_list=False):
        if names is None:
            names = self.names
        else:
            names = expand(names)
        b = list()
        for name in names:
            b.append(self[name])
        if as_list:
            return b
        else:
            return "".join(str(i) for i in b)

    def __add__(self, other):
        names = self.names.copy()
        for name in other.names:
            if name in names:
                continue
            names.append(name)
        bits = []
        for name in names:
            if name in self.names:
                bits.append(self[name])
            else:
                bits.append(other[name])
        return Assign(names, bits)

    def __setitem__(self, name, v):
        if not name in self.names:
            raise Exception("Invalid name for assignment (not in name domain): %s" % (name,))

        super(Assign, self).__setitem__(name, v)

    #def __getitem__(self, y):
    #    return self.o[y]

    def __call__(self, names=None):
        return self.bits(names, as_list=True)

    def __str__(self, keys=None):
        if keys is None:
            keys = self.names
        s = ""
        for key in keys:
            s += "%s=%s, " % (key, self[key])
        s = s.strip()
        s = s.strip(",")
        return s

    @classmethod
    def fromDict(cls, d):
        names = list(d.keys())
        bits = list(d.values())
        a = cls(names, bits)
        return a

    @classmethod
    def fromKeys(cls, **kwargs):
        names = list(kwargs.keys())
        bits = list(kwargs.values())
        a = cls(names, bits)
        return a

    @classmethod
    def iter(cls, names):
        a = cls(names,0)
        n = len(a.names)
        for s in product([0,1], repeat=n):
            a.assign(s)
            yield a

def random_assignment(names):
    names = expand(names)
    a = Assign(names)
    for x in names:
        a[x] = randint(0,1)
    return a

def full_run(circ):
    inp = [g.name for g in circ.input]
    for a in Assign.iter(inp):
        print("Input:")
        print(a)
        o = circ(a)
        print("Output:")
        print(o)
        print("Press <Enter> to continue or 'q' to quit")
        inpstr = input("Next? ")
        if "q" == inpstr:
            break

def random_run(circ):
    inp = [g.name for g in circ.input]
    while True:
        #inpstr = input("Enter input: ")
        #inpstr = inpstr.strip()
        a = random_assignment(inp)
        o = circ(a)
        print("input:")
        print(a)
        print("output:")
        print(o)
        print("Press <Enter> to continue or 'q' to quit")
        inpstr = input("Next? ")
        if "q" == inpstr:
            break

# this is partial, should be expanded to names
# like: "x<3:6,10:20:2,40:20:5>;p<2:5,8:12>;q<3:0>"
# todo: add checks for name validity etc...
def expand(group):
    names = list()
    if isinstance(group, list) or isinstance(group, tuple) or isinstance(group, type({}.keys())):
        for name in group:
            names.extend(expand(name))
        return names

    if ";" in group:
        for name in group.split(";"):
            name = name.strip()
            names.extend(expand(name))
        return names

    name = group.strip()

    if "/" in name:
        gates, pins = name.split("/")
        for g in expand(gates):
            for p in expand(pins):
                names.append(g + "/" + p)
        return names

    i = name.find("<")
    if i == -1:
        if not namepat.match(name):
            raise Exception("Invalid group name: %s" % (name,))
        names.append(name)
        return names

    pref = name[0:i].strip()
    if not namepat.match(pref):
        raise Exception("Invalid group name: %s" % (pref,))
    j = name.find(">")
    if j == -1:
        raise Exception("Invalid name: %s" % (pref,))
    for spec in name[i+1:j].split(","):
        if not ":" in spec:
            inp = pref + spec.strip()
            names.append(inp)
            continue
        limits = [int(x.strip()) for x in spec.split(":")]
        if [x for x in limits if x<0]:
            raise Exception("Only non-negative integers allowed: %s" % (spec,))
        if len(limits) == 2:
            m,n = limits
            d = 1
        elif len(limits) == 3:
            m,n,d = limits
        else:
            raise Exception("Invalid range spec: %s" % (spec,))
        if m>n:
            d = -d
        for k in range(m,n+d,d):
            if k<0:
                raise Exception("Invalid range spec. Indices cannot be negative! %s" % (spec,))
            inp = pref + str(k)
            names.append(inp)
    return names
