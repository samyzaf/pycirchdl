from .util import *

# Logic Operators to be used for building Logic Cells
# a = an Assign object with input name like: x1, x2, ..., xn
# o = an Assign object with input name like: x1, x2, ..., xn
# but it can be changed to whatever key names a client user chooses

def Zero(a=None, output="y"):
    o = Assign(output)
    for y in o: o[y] = 0
    return o

def One(a=None, output="y"):
    o = Assign(output)
    for y in o: o[y] = 1
    return o

def Not(a=Assign("x"), output="y"):
    o = Assign(output)
    for x,y in zip(a.names, o.names):
        o[y] = 1 - a[x]
    return o

def And(a, output="y"):
    o = Assign(output)
    for x in a:
        if a[x] == 0:
            for y in o: o[y] = 0
            return o
    for y in o: o[y] = 1
    return o

def Or(a, output="y"):
    o = Assign(output)
    for x in a:
        if a[x] == 1:
            for y in o: o[y] = 1
            return o
    for y in o: o[y] = 0
    return o

def Nor(a, output="y"):
    o = Or(a, "y")
    b = Assign("x", o["y"])
    return Not(b, output)

def Nand(a, output="y"):
    o = And(a, "y")
    b = Assign("x", o["y"])
    return Not(b, output)

def Xor(a, output="y"):
    o = Assign(output)
    if sum(a[x] for x in a) == 1:
        for y in o: o[y] = 1
        return o
    else:
        for y in o: o[y] = 0
        return o

def Xnor(a, output="y"):
    o = Xor(a, "y")
    b = Assign("x", o["y"])
    return Not(b, output)

def Mux(a, output="y"):
    sel = [name for name in a if name[0]=="s"]
    bits = [name for name in a if name[0]=="x"]
    sel.sort(key=lambda x: int(x[1:]))
    bits.sort(key=lambda x: int(x[1:]))
    s = [str(a[k]) for k in sel]
    s = "".join(s)
    i = int(s, 2)
    o = Assign(output, a[bits[i]])
    return o

