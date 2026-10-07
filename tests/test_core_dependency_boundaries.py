"""Keep CSW core independent of CFW and DP implementation packages."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

# CSW owns these two explicitly named CFW-facing adapters. They are the only
# CSW source modules outside the core import scan; no adapter directory or
# filename-pattern exclusion is used.
ALLOWED_BRIDGE_MODULES = frozenset({
    "scripts/cfw_authority.py",
    "scripts/cfw_provider.py",
})

# The standalone installer has optional host skill registry targets. Its
# workflow policy and runtime packages remain covered by the import scan.
HOST_REGISTRY_INSTALLERS = frozenset({"scripts/install-stateworks.py"})

# These are the installed CFW implementation modules/packages declared by its
# pyproject, plus DP's installed package and its legacy ``lib`` source path.
FORBIDDEN_IMPORT_ROOTS = frozenset({
    "cognitive_runtime",
    "codex_app_server_adapter",
    "codex_app_server_dp_bridge",
    "cohort",
    "digital_psychology",
    "digital_psychology_adapter",
    "lib",
    "operator_ui",
    "resolve_runtime",
    "resolver",
    "runtime",
    "runtime_contract",
    "runtime_host",
    "runtime_session",
    "runtime_start",
})


def _literal_dynamic_import(node: ast.Call,
                            imported_names: frozenset[str]) -> str | None:
    """Return a literal import target from common dynamic-import forms."""
    func = node.func
    is_import_module = (
        isinstance(func, ast.Name) and func.id in imported_names
    ) or (isinstance(func, ast.Attribute) and func.attr == "import_module")
    is_dunder_import = isinstance(func, ast.Name) and func.id == "__import__"
    if (is_import_module or is_dunder_import) and node.args:
        target = node.args[0]
        if isinstance(target, ast.Constant) and isinstance(target.value, str):
            return target.value
    return None


def _import_targets(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[int, str]] = []
    imported_names = {"import_module"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "importlib":
            imported_names.update(
                alias.asname or alias.name for alias in node.names
                if alias.name == "import_module"
            )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imports.append((node.lineno, node.module))
        elif isinstance(node, ast.Call):
            target = _literal_dynamic_import(node, frozenset(imported_names))
            if target is not None:
                imports.append((node.lineno, target))
    return imports


def _under_forbidden_root(module: str) -> bool:
    return any(module == root or module.startswith(root + ".")
               for root in FORBIDDEN_IMPORT_ROOTS)


def test_only_named_integration_modules_are_excluded_from_core_scan():
    source_files = {
        path.relative_to(ROOT).as_posix()
        for path in SCRIPTS.rglob("*.py")
        if path.is_file()
    }
    assert ALLOWED_BRIDGE_MODULES <= source_files
    assert HOST_REGISTRY_INSTALLERS <= source_files


def test_csw_core_does_not_import_cfw_or_dp_implementations():
    violations = []
    for path in sorted(SCRIPTS.rglob("*.py")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative in ALLOWED_BRIDGE_MODULES:
            continue
        for line, module in _import_targets(path):
            if _under_forbidden_root(module):
                violations.append(f"{relative}:{line}: {module}")

    assert not violations, (
        "CSW core imports CFW/DP implementation modules outside the explicit "
        "integration allowlist:\n" + "\n".join(violations)
    )


def test_csw_core_does_not_embed_harness_protocol_names():
    forbidden_tokens = (
        "Codex", "codex_host", "thread/start", "turn/start", "item/tool/call",
        "CODEX_HOME", "Claude", "Athena",
    )
    violations = []
    for path in sorted(SCRIPTS.rglob("*.py")):
        if not path.is_file() or path.relative_to(ROOT).as_posix() in (
                ALLOWED_BRIDGE_MODULES | HOST_REGISTRY_INSTALLERS):
            continue
        source = path.read_text(encoding="utf-8").casefold()
        for token in forbidden_tokens:
            if token.casefold() in source:
                violations.append(f"{path.relative_to(ROOT)} contains {token!r}")
    assert not violations, (
        "CSW core contains harness protocol names:\n" + "\n".join(violations))
