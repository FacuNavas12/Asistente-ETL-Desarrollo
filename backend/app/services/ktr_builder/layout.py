"""Auto-layout: calcula x/y para steps sin posición, vía orden topológico por columnas."""
from __future__ import annotations


def _auto_layout(steps: list, hops: list) -> list:
    """Compute x/y for any step missing them, using topological column ordering."""
    # Build in-degree map
    in_degree = {s["name"]: 0 for s in steps}
    for hop in hops:
        to = hop.get("to")
        if to in in_degree:
            in_degree[to] += 1

    queue   = [name for name, deg in in_degree.items() if deg == 0]
    columns = {}
    col     = 0

    while queue:
        for name in queue:
            if name not in columns:
                columns[name] = col
        next_q = []
        for name in queue:
            for hop in hops:
                if hop.get("from") == name:
                    to = hop.get("to")
                    if to in in_degree:
                        in_degree[to] -= 1
                        if in_degree[to] == 0:
                            next_q.append(to)
        queue = next_q
        col += 1

    for s in steps:
        if s["name"] not in columns:
            columns[s["name"]] = col
            col += 1

    col_used: dict[int, int] = {}
    result = []
    for step in steps:
        name  = step["name"]
        c     = columns.get(name, 0)
        row   = col_used.get(c, 0)
        col_used[c] = row + 1
        new_step    = dict(step)
        if not step.get("x") or not step.get("y"):
            new_step["x"] = 100 + c * 200
            new_step["y"] = 100 + row * 120
        result.append(new_step)

    return result
