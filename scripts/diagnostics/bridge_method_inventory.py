from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _typescript_method_names(path: Path) -> tuple[list[str], list[str]]:
    source = path.read_text(encoding="utf-8")
    marker = "export interface BridgeApi {"
    start = source.find(marker)
    if start < 0:
        raise ValueError("BridgeApi interface marker not found")

    names: list[str] = []
    for line in source[start + len(marker) :].splitlines():
        if line == "}":
            break
        stripped = line.lstrip()
        if not line[:1].isspace() or "(" not in stripped:
            continue
        candidate = stripped.split("(", 1)[0].strip()
        if candidate.isidentifier():
            names.append(candidate)

    counts = Counter(names)
    return sorted(counts), sorted(name for name, count in counts.items() if count > 1)


def _bridge_mixin_targets(root: Path) -> list[tuple[Path, str]]:
    bridge_path = root / "desktop/bridge.py"
    tree = ast.parse(bridge_path.read_text(encoding="utf-8"), filename=str(bridge_path))
    imports: dict[str, tuple[Path, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        module_path = root / (node.module.replace(".", "/") + ".py")
        for alias in node.names:
            imports[alias.asname or alias.name] = (module_path, alias.name)

    bridge_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CVMBridge"
    )
    targets: list[tuple[Path, str]] = []
    for base in bridge_class.bases:
        if not isinstance(base, ast.Name) or base.id not in imports:
            raise ValueError(f"Unresolved CVMBridge base: {ast.unparse(base)}")
        targets.append(imports[base.id])
    return targets


def _python_method_names(root: Path) -> list[str]:
    methods: set[str] = set()
    for module_path, class_name in _bridge_mixin_targets(root):
        tree = ast.parse(
            module_path.read_text(encoding="utf-8"), filename=str(module_path)
        )
        mixin = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        for node in mixin.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    methods.add(node.name)
    return sorted(methods)


def build_inventory(root: Path) -> dict[str, Any]:
    python_methods = _python_method_names(root)
    typescript_methods, duplicates = _typescript_method_names(
        root / "apps/desktop-web/src/lib/bridge/types.ts"
    )
    python_set = set(python_methods)
    typescript_set = set(typescript_methods)
    return {
        "python_methods": python_methods,
        "typescript_methods": typescript_methods,
        "typescript_duplicates": duplicates,
        "python_only": sorted(python_set - typescript_set),
        "typescript_only": sorted(typescript_set - python_set),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(build_inventory(args.root.resolve()), indent=2))


if __name__ == "__main__":
    main()
