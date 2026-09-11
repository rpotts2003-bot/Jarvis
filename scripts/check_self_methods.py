"""Fail if a class calls self.method() that was never defined or assigned on self.

Pure AST — no tkinter. Exit 1 on problems.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Focus on UI first (the shipped crash). Core files optional via --all
UI_TARGETS = [
    ROOT / "assistant" / "ui" / "gui.py",
    ROOT / "assistant" / "ui" / "ring_timing.py",
    ROOT / "assistant" / "ui" / "orb.py",
]
ALL_TARGETS = UI_TARGETS + [
    ROOT / "assistant" / "core" / "orchestrator.py",
    ROOT / "assistant" / "actions" / "router.py",
    ROOT / "assistant" / "llm" / "builtins.py",
]


class SelfCallChecker(ast.NodeVisitor):
    def __init__(self, path: Path):
        self.path = path
        self.errors: list[str] = []
        self._defined: set[str] = set()
        self._class: str | None = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        prev_class, prev_defined = self._class, self._defined
        self._class = node.name
        self._defined = set()
        # First pass: methods + class-level assigns
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._defined.add(item.name)
                self._collect_self_assigns(item)
            elif isinstance(item, ast.Assign):
                for t in item.targets:
                    if isinstance(t, ast.Name):
                        self._defined.add(t.id)
        # Second pass: find calls
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(item):
                    if isinstance(child, ast.Call):
                        self._check_call(child)
        self._class, self._defined = prev_class, prev_defined

    def _collect_self_assigns(self, fn: ast.AST) -> None:
        for child in ast.walk(fn):
            if isinstance(child, ast.Assign):
                for t in child.targets:
                    if (
                        isinstance(t, ast.Attribute)
                        and isinstance(t.value, ast.Name)
                        and t.value.id == "self"
                    ):
                        self._defined.add(t.attr)
            elif isinstance(child, ast.AnnAssign) and child.target is not None:
                t = child.target
                if (
                    isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == "self"
                ):
                    self._defined.add(t.attr)

    def _check_call(self, node: ast.Call) -> None:
        if not self._class:
            return
        if not isinstance(node.func, ast.Attribute):
            return
        val = node.func.value
        if not (isinstance(val, ast.Name) and val.id == "self"):
            return
        name = node.func.attr
        if name.startswith("__"):
            return
        # Tkinter / widget API bound onto self.root / self.canvas — those are
        # other objects. We only care about missing methods on THIS class.
        if name in self._defined:
            return
        # Only flag our own helpers (underscore) + a few public entrypoints
        if name.startswith("_") or name in {"run", "set_state", "handle_text", "handle_utterance"}:
            self.errors.append(
                f"{self.path.name}:{node.lineno}: {self._class}.self.{name}() "
                f"not defined (would crash at runtime)"
            )


def check_file(path: Path) -> list[str]:
    if not path.exists():
        return [f"missing: {path}"]
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    c = SelfCallChecker(path)
    c.visit(tree)
    return c.errors


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    targets = ALL_TARGETS if "--all" in argv else UI_TARGETS
    errors: list[str] = []
    for p in targets:
        if p.exists():
            errors.extend(check_file(p))
    if errors:
        print("SELF-METHOD CHECK FAILED:")
        for e in errors:
            print(f"  {e}")
        return 1
    print(f"self-method check OK ({len([p for p in targets if p.exists()])} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
