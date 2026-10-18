"""Small structural KiCad reader; quoted atoms remain quoted on serialization.

Adapted from the retired importer's parser. Never infer connectivity from geometry.
"""

import re


class Quoted(str):
    pass


def parse(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text)
    stack, result = [], []
    for token in tokens:
        if token == "(":
            node = []
            (stack[-1] if stack else result).append(node)
            stack.append(node)
        elif token == ")":
            if not stack:
                raise ValueError("Unbalanced KiCad expression")
            stack.pop()
        else:
            if not stack:
                raise ValueError("Atom outside KiCad expression")
            if token.startswith('"'):
                token = Quoted(re.sub(r'\\([\\"])', r"\1", token[1:-1]))
            stack[-1].append(token)
    if stack or len(result) != 1:
        raise ValueError("Unbalanced or multiple KiCad expressions")
    return result[0]


def dump(node):
    if isinstance(node, list):
        return "(" + " ".join(dump(n) for n in node) + ")"
    if isinstance(node, Quoted):
        return '"' + node.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return str(node)


def children(node, tag):
    return [n for n in node if isinstance(n, list) and n and n[0] == tag]


def child(node, tag, default=None):
    return next(iter(children(node, tag)), default)


def value(node, tag, default=""):
    found = child(node, tag)
    return found[1] if found and len(found) > 1 else default


def property_set(node, key, val, visible=False):
    found = next((p for p in children(node, "property") if p[1] == key), None)
    if found is not None:
        found[2] = Quoted(val)
    else:
        effects = ["effects", ["font", ["size", "1.27", "1.27"]]]
        if not visible:
            effects.append("hide")
        node.append(
            ["property", Quoted(key), Quoted(val), ["at", "0", "0", "0"], effects]
        )
