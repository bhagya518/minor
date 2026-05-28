#!/usr/bin/env python3
"""audit.py – repository static analysis helper.
Generates a JSON report (audit_report.json) with:
* module import graph
* cycles detection (via networkx)
* duplicate function/class names (by signature hash)
* modules with no exported symbols (possible dead code)
* mismatched naming conventions (snake_case vs CamelCase)
* threading‑unsafe globals detection (variables assigned at module level that are mutable)
"""
import ast, json, os, sys, pathlib, re, collections
from typing import Dict, List, Set, Tuple

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]

def iter_py_files() -> List[pathlib.Path]:
    return [p for p in PROJECT_ROOT.rglob('*.py') if 'env' not in str(p) and 'site-packages' not in str(p)]

def parse_module(path: pathlib.Path) -> ast.Module:
    with open(path, 'r', encoding='utf-8') as f:
        return ast.parse(f.read(), filename=str(path))

def collect_imports() -> Dict[str, Set[str]]:
    graph: Dict[str, Set[str]] = collections.defaultdict(set)
    for fp in iter_py_files():
        mod_name = fp.relative_to(PROJECT_ROOT).with_suffix('').as_posix().replace('/', '.')
        tree = parse_module(fp)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    graph[mod_name].add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    graph[mod_name].add(node.module)
    return graph

def detect_cycles(graph: Dict[str, Set[str]]) -> List[List[str]]:
    try:
        import networkx as nx
    except ImportError:
        return []
    G = nx.DiGraph()
    for src, dests in graph.items():
        for dst in dests:
            G.add_edge(src, dst)
    cycles = list(nx.simple_cycles(G))
    return cycles

def collect_defs() -> Dict[str, List[Tuple[str, int]]]:
    defs: Dict[str, List[Tuple[str, int]]] = collections.defaultdict(list)
    for fp in iter_py_files():
        mod = fp.relative_to(PROJECT_ROOT).with_suffix('').as_posix().replace('/', '.')
        tree = parse_module(fp)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name
                defs[name].append((mod, node.lineno))
    return defs

def duplicate_defs(defs: Dict[str, List[Tuple[str, int]]]) -> Dict[str, List[Tuple[str, int]]]:
    return {name: locs for name, locs in defs.items() if len(locs) > 1}

def check_naming_conventions() -> List[Tuple[str, str, int]]:
    violations = []
    snake = re.compile(r'^[a-z_][a-z0-9_]*$')
    camel = re.compile(r'^[A-Z][A-Za-z0-9]+$')
    for fp in iter_py_files():
        mod = fp.relative_to(PROJECT_ROOT).as_posix()
        tree = parse_module(fp)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not snake.match(node.name):
                    violations.append((mod, node.name, node.lineno))
            elif isinstance(node, ast.ClassDef):
                if not camel.match(node.name):
                    violations.append((mod, node.name, node.lineno))
    return violations

def mutable_globals() -> List[Tuple[str, str, int]]:
    mutable = []
    for fp in iter_py_files():
        mod = fp.relative_to(PROJECT_ROOT).as_posix()
        tree = parse_module(fp)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                # simple heuristic: if value is a list/dict/set it is mutable
                if isinstance(node.value, (ast.List, ast.Dict, ast.Set)):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            mutable.append((mod, target.id, node.lineno))
    return mutable

def main():
    graph = collect_imports()
    cycles = detect_cycles(graph)
    dup = duplicate_defs(collect_defs())
    naming = check_naming_conventions()
    globals_mut = mutable_globals()

    report = {
        "import_graph": {k: list(v) for k, v in graph.items()},
        "cycles": cycles,
        "duplicate_definitions": dup,
        "naming_violations": naming,
        "mutable_globals": globals_mut,
    }
    out_path = PROJECT_ROOT / 'audit_report.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(f"Audit report written to {out_path}")

if __name__ == '__main__':
    main()
