from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "bambu_rfid_diag"
TOOLS = ROOT / "tools"
MAX_LINE_LENGTH = 100
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
REEXPORT_MODULES = {
    "__init__.py",
    "models.py",
    "ndef.py",
    "parsers.py",
    "proxmark.py",
    "reporting.py",
}


def has_non_ascii(text: str) -> bool:
    return any(ord(character) > 127 for character in text)


def main() -> int:
    errors: list[str] = []
    source_paths = [
        *PACKAGE.rglob("*.py"),
        *TOOLS.rglob("*.py"),
        ROOT / "Bambu_RFID_Writer.pyw",
    ]
    for path in sorted(source_paths):
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        for line_number, line in enumerate(source.splitlines(), start=1):
            if len(line) > MAX_LINE_LENGTH:
                errors.append(
                    f"{relative}:{line_number}: line exceeds "
                    f"{MAX_LINE_LENGTH} characters"
                )

        try:
            tree = ast.parse(source, filename=str(relative))
        except SyntaxError as exc:
            errors.append(f"{relative}:{exc.lineno}: syntax error: {exc.msg}")
            continue

        if path.is_relative_to(PACKAGE) and path.name not in REEXPORT_MODULES:
            used_names = {
                node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
            }
            exported_names: set[str] = set()
            for node in tree.body:
                if (
                    isinstance(node, ast.Assign)
                    and any(
                        isinstance(target, ast.Name) and target.id == "__all__"
                        for target in node.targets
                    )
                    and isinstance(node.value, (ast.List, ast.Tuple))
                ):
                    exported_names.update(
                        element.value
                        for element in node.value.elts
                        if isinstance(element, ast.Constant)
                        and isinstance(element.value, str)
                    )

            for node in tree.body:
                if isinstance(node, ast.Import):
                    imported = [
                        (alias.asname or alias.name.split(".")[0], node.lineno)
                        for alias in node.names
                    ]
                elif isinstance(node, ast.ImportFrom):
                    imported = [
                        (alias.asname or alias.name, node.lineno)
                        for alias in node.names
                        if alias.name != "*"
                    ]
                else:
                    continue
                for binding, line_number in imported:
                    if binding == "annotations":
                        continue
                    if binding not in used_names and binding not in exported_names:
                        errors.append(
                            f"{relative}:{line_number}: unused import {binding}"
                        )

        for node in ast.walk(tree):
            if (
                relative.parts[:2] == ("bambu_rfid_diag", "ui")
                and relative.name != "theme.py"
                and isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and HEX_COLOR.fullmatch(node.value)
            ):
                errors.append(
                    f"{relative}:{node.lineno}: UI colors must be defined in ui/theme.py"
                )
            if isinstance(node, ast.Assert):
                errors.append(
                    f"{relative}:{node.lineno}: runtime assert is not allowed in production code"
                )
            if isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                docstring = ast.get_docstring(node, clean=False)
                if docstring and has_non_ascii(docstring):
                    errors.append(
                        f"{relative}:{getattr(node, 'lineno', 1)}: "
                        "developer docstring must use English ASCII text"
                    )

        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT and has_non_ascii(token.string):
                errors.append(
                    f"{relative}:{token.start[0]}: "
                    "developer comment must use English ASCII text"
                )

    if errors:
        print("Source quality validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(
        "Source quality validation passed: syntax, line length, comments, "
        "docstrings, imports, assertions, UI colors"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
