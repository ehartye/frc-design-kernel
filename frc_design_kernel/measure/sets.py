"""Sets of names that grow by joining: the bookkeeping behind "what is connected to what"."""


class Sets:
    """Disjoint sets of names. join() merges two sets; groups() lists them."""

    def __init__(self, names):
        self.parent = {name: name for name in names}

    def find(self, name):
        while self.parent[name] != name:
            self.parent[name] = self.parent[self.parent[name]]
            name = self.parent[name]
        return name

    def join(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[max(a, b)] = min(a, b)

    def together(self, a, b):
        return self.find(a) == self.find(b)

    def groups(self):
        """The sets as sorted lists, largest first, then by first name."""
        found = {}
        for name in sorted(self.parent):
            found.setdefault(self.find(name), []).append(name)
        return sorted(found.values(), key=lambda members: (-len(members), members[0]))
