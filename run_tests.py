#!/usr/bin/env python3
"""Stdlib-only test runner (the suite is also pytest-compatible).

Usage: python3 run_tests.py
"""
import importlib.util
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    tests_dir = os.path.join(ROOT, "tests")
    total = passed = 0
    failures = []
    for fname in sorted(os.listdir(tests_dir)):
        if not (fname.startswith("test_") and fname.endswith(".py")):
            continue
        mod = load_module(os.path.join(tests_dir, fname), fname[:-3])
        for attr in sorted(dir(mod)):
            if not attr.startswith("test_"):
                continue
            fn = getattr(mod, attr)
            if not callable(fn):
                continue
            total += 1
            try:
                fn()
                passed += 1
                print(f"pass {attr}")
            except Exception:
                failures.append(attr)
                print(f"FAIL {attr}")
                traceback.print_exc()
    print(f"\n{passed}/{total} tests passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
