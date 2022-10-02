path = list()
circd = dict()

def set_path(pathlist):
    path.clear()
    for d in pathlist:
        path_add(d)

def path_add(d):
    if not d in path:
        path.append(d)

def path_del(d):
    if d in path:
        path.remove(d)
