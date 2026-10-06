"""Build a self-contained cognitive_statework wheel.

The Python module lives in scripts/ while workflow bundles are source data at
the repository root. This build command carries the trusted compiled bundle
contents into the wheel package and recompiles their registry for that root.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import types
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


ROOT = Path(__file__).resolve().parent


class BuildPy(build_py):
    _asset_outputs: list[str] = []

    def run(self) -> None:
        super().run()
        source_root = ROOT
        package_root = Path(self.build_lib) / "cognitive_statework"
        shutil.copytree(source_root / "schemas", package_root / "schemas", dirs_exist_ok=True)

        package_name = "csw_build_" + hashlib.sha256(str(source_root).encode()).hexdigest()[:12]
        scripts_root = source_root / "scripts"
        package = types.ModuleType(package_name)
        package.__path__ = [str(scripts_root)]
        sys.modules[package_name] = package
        spec = importlib.util.spec_from_file_location(
            package_name + ".control_plane", scripts_root / "control_plane.py")
        control = importlib.util.module_from_spec(spec)
        sys.modules[package_name + ".control_plane"] = control
        spec.loader.exec_module(control)
        compiled = control.RegistryCompiler(source_root).compile(write=False)

        statework_ids = []
        for entry in compiled.get("stateworks") or ():
            source_root_ref = str(entry.get("source_root") or ".")
            bundle_source = (source_root if source_root_ref == "." else
                             Path(source_root_ref) if Path(source_root_ref).is_absolute()
                             else source_root / source_root_ref)
            bundle_source = (bundle_source / str(entry.get("bundle_ref") or ".")).resolve()
            statework_id = str(entry["id"])
            bundle_target = package_root / statework_id
            if bundle_target.exists():
                shutil.rmtree(bundle_target)
            shutil.copytree(bundle_source, bundle_target)
            statework_ids.append(statework_id)

        (package_root / "registry.yaml").write_text(
            "version: 2.0.0\nstateworks:\n" + "".join(
                f"  - {json.dumps(statework_id)}\n" for statework_id in statework_ids)
            + "extension_roots: []\n", encoding="utf-8")
        control.RegistryCompiler(package_root).compile(write=True)
        self._asset_outputs = [str(path) for path in package_root.rglob("*") if path.is_file()]

    def get_outputs(self, include_bytecode: int = 1) -> list[str]:
        return sorted(set(super().get_outputs(include_bytecode)) | set(self._asset_outputs))


setup(cmdclass={"build_py": BuildPy})
