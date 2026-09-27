"""4150 资产 manifest 的最小测试与命令行断言入口。"""

import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

from ..common.manifest_4150 import array_meta, build_manifest


def test_manifest_has_explicit_conf_and_categories():
    manifest = build_manifest("4150")
    assert manifest["conf_id"] == "4150"
    assert {"input", "reference_output", "reference_code"} <= set(manifest)
    assert manifest["input"]["gauge"]["exists"] is True


def test_array_meta_does_not_require_full_load(tmp_path):
    path = tmp_path / "x.npy"
    np.save(path, np.zeros((2, 3), dtype=np.complex128))
    meta = array_meta(str(path))
    assert meta["shape"] == [2, 3]
    assert meta["dtype"] == "complex128"


def test_manifest_is_non_destructive():
    before = os.path.exists("/public/group/lqcd/configurations")
    manifest = build_manifest("4150")
    assert isinstance(manifest, dict)
    assert os.path.exists("/public/group/lqcd/configurations") == before


def test_datalib_configure_selects_conf_and_clears_cache(tmp_path):
    from ..common import datalib

    datalib._memo["stale"] = object()
    datalib.configure(4150, cache_dir=str(tmp_path))
    assert datalib.CONF == 4150
    assert datalib.CACHE == str(tmp_path)
    assert datalib._memo == {}


def main():
    test_manifest_has_explicit_conf_and_categories()

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(prefix="pyqcd_manifest_test_") as tmp:
        test_array_meta_does_not_require_full_load(Path(tmp))
    test_manifest_is_non_destructive()
    with tempfile.TemporaryDirectory(prefix="pyqcd_manifest_cache_") as tmp:
        test_datalib_configure_selects_conf_and_clears_cache(Path(tmp))
    print("verify_manifest_4150: PASS 4/4")


if __name__ == "__main__":
    main()
