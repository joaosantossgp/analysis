from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_build_inventory():
    module_path = ROOT / "scripts/diagnostics/bridge_method_inventory.py"
    assert module_path.is_file()
    spec = importlib.util.spec_from_file_location("bridge_method_inventory", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_inventory


def test_build_inventory_compares_cvmbridge_mixins_with_typescript(
    tmp_path: Path,
) -> None:
    (tmp_path / "desktop/bridge_api").mkdir(parents=True)
    (tmp_path / "apps/desktop-web/src/lib/bridge").mkdir(parents=True)
    (tmp_path / "desktop/bridge.py").write_text(
        "from desktop.bridge_api.alpha import AlphaMixin\n"
        "class CVMBridge(AlphaMixin):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "desktop/bridge_api/alpha.py").write_text(
        "class AlphaMixin:\n"
        "    def ping(self, params=None):\n"
        "        return params\n"
        "    def _private(self):\n"
        "        return None\n",
        encoding="utf-8",
    )
    (tmp_path / "apps/desktop-web/src/lib/bridge/types.ts").write_text(
        "export interface BridgeApi {\n"
        "  ping(params?: Record<string, unknown>): Promise<unknown>;\n"
        "  generic<T>(params: T): Promise<T>;\n"
        '  "quoted-method"(params?: Record<string, unknown>): Promise<unknown>;\n'
        "  multiline\n"
        "    (params?: Record<string, unknown>): Promise<unknown>;\n"
        "  ping(params?: Record<string, unknown>): Promise<unknown>;\n"
        "  status: string;\n"
        "  handler: (params: string) => Promise<void>;\n"
        "  (params: string): Promise<void>;\n"
        "}\n",
        encoding="utf-8",
    )

    inventory = _load_build_inventory()(tmp_path)

    assert inventory["python_methods"] == ["ping"]
    assert inventory["typescript_methods"] == [
        "generic",
        "multiline",
        "ping",
        "quoted-method",
    ]
    assert inventory["typescript_duplicates"] == ["ping"]
    assert inventory["python_only"] == []
    assert inventory["typescript_only"] == ["generic", "multiline", "quoted-method"]
