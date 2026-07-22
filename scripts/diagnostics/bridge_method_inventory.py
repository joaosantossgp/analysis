from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


def _skip_trivia(source: str, index: int) -> int:
    while index < len(source):
        if source[index].isspace():
            index += 1
        elif source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = len(source) if newline < 0 else newline + 1
        elif source.startswith("/*", index):
            end = source.find("*/", index + 2)
            index = len(source) if end < 0 else end + 2
        else:
            break
    return index


def _skip_quoted(source: str, index: int) -> int:
    quote = source[index]
    index += 1
    while index < len(source):
        if source[index] == "\\":
            index += 2
        elif source[index] == quote:
            return index + 1
        else:
            index += 1
    return index


def _typescript_interface_members(source: str, start: int) -> list[str]:
    members: list[str] = []
    member_start = start
    depths = {"(": 0, "[": 0, "{": 0}
    closing = {")": "(", "]": "[", "}": "{"}
    index = start

    while index < len(source):
        if source[index] in "'\"`":
            index = _skip_quoted(source, index)
            continue
        if source.startswith("//", index) or source.startswith("/*", index):
            index = _skip_trivia(source, index)
            continue

        char = source[index]
        if char in depths:
            depths[char] += 1
        elif char == "}" and not any(depths.values()):
            tail = source[member_start:index].strip()
            if tail:
                members.append(tail)
            return members
        elif char in closing:
            opener = closing[char]
            if depths[opener] > 0:
                depths[opener] -= 1
        elif char == ";" and not any(depths.values()):
            members.append(source[member_start:index])
            member_start = index + 1
        index += 1

    raise ValueError("BridgeApi interface closing brace not found")


def _skip_generic_parameters(member: str, index: int) -> int:
    depth = 0
    while index < len(member):
        if member[index] in "'\"`":
            index = _skip_quoted(member, index)
            continue
        if member.startswith("//", index) or member.startswith("/*", index):
            index = _skip_trivia(member, index)
            continue
        if member[index] == "<":
            depth += 1
        elif member[index] == ">" and member[index - 1 : index] != "=":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return index


def _typescript_method_name(member: str) -> str | None:
    index = _skip_trivia(member, 0)
    if index >= len(member):
        return None

    if member[index] in "'\"":
        end = _skip_quoted(member, index)
        try:
            name = ast.literal_eval(member[index:end])
        except (SyntaxError, ValueError):
            return None
        if not isinstance(name, str):
            return None
        index = end
    else:
        match = _IDENTIFIER.match(member, index)
        if match is None:
            return None
        name = match.group(0)
        index = match.end()

    index = _skip_trivia(member, index)
    if index < len(member) and member[index] == "?":
        index = _skip_trivia(member, index + 1)
    if index < len(member) and member[index] == "<":
        index = _skip_trivia(member, _skip_generic_parameters(member, index))

    if name == "new" or index >= len(member) or member[index] != "(":
        return None
    return name


def _typescript_method_names(path: Path) -> tuple[list[str], list[str]]:
    source = path.read_text(encoding="utf-8")
    marker = "export interface BridgeApi {"
    start = source.find(marker)
    if start < 0:
        raise ValueError("BridgeApi interface marker not found")

    names = [
        name
        for member in _typescript_interface_members(source, start + len(marker))
        if (name := _typescript_method_name(member)) is not None
    ]

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
