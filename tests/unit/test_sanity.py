"""M0 sanity tests — replaced by real coverage in M1+."""

from __future__ import annotations

import importlib


def test_packages_importable() -> None:
    for pkg in [
        "anpr_core",
        "anpr_core.detect",
        "anpr_core.ocr",
        "anpr_core.pipeline",
        "anpr_core.tracking",
        "anpr_core.postproc",
        "anpr_core.quality",
        "anpr_core.privacy",
        "api",
        "ingest",
        "workers",
        "db",
    ]:
        importlib.import_module(pkg)


def test_python_version() -> None:
    import sys

    assert sys.version_info >= (3, 11), "ANPR requires Python 3.11+"
