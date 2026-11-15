#!/usr/bin/env python3
"""
Regression test for type annotation resolution across all SPECTRA modules.
Verifies that all annotations resolve without NameError (e.g. unimported typing symbols
such as Set, Dict, List, Optional, Any, Callable, Union).
"""

import sys
import os
import unittest
import inspect
import typing
import importlib

# Ensure repository root is on sys.path
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)


class TestAnnotationsResolve(unittest.TestCase):
    """Regression test: verify typing.get_type_hints() on all module members."""

    MANDATORY_MODULES = [
        "hmi_inspector",
        "spectra_ai",
        "spectra_probe",
        "web_server",
        "stats_collector",
    ]

    ALL_MODULES = [
        "cli",
        "gui",
        "gui_web",
        "gui_widgets",
        "hmi_inspector",
        "jura_protocol",
        "memory_mapper",
        "profiles_db",
        "serial_io",
        "spectra_ai",
        "spectra_app",
        "spectra_engine",
        "spectra_probe",
        "stats_collector",
        "version",
        "web_server",
        "wrat_engine",
        "github_auth",
    ]

    def _inspect_annotations_recursively(self, obj, full_name: str, seen: set):
        if id(obj) in seen:
            return
        seen.add(id(obj))

        try:
            typing.get_type_hints(obj)
        except NameError as ne:
            self.fail(f"Unresolved type annotation (NameError) in {full_name}: {ne}")
        except Exception:
            # Benign exceptions (e.g. non-callable or runtime types without type hints)
            pass

        if inspect.isclass(obj):
            for attr_name, attr_val in list(obj.__dict__.items()):
                actual = attr_val
                if isinstance(attr_val, (staticmethod, classmethod)):
                    actual = attr_val.__func__
                if inspect.isfunction(actual) or inspect.isclass(actual):
                    self._inspect_annotations_recursively(actual, f"{full_name}.{attr_name}", seen)

    def test_all_modules_annotations_resolve(self):
        """Test each module and recursively verify type hints."""
        for modname in self.ALL_MODULES:
            try:
                mod = importlib.import_module(modname)
            except Exception as e:
                if modname in self.MANDATORY_MODULES:
                    self.fail(f"Mandatory module '{modname}' failed to import: {e}")
                else:
                    # Optional/hardware module skipped gracefully
                    continue

            seen = set()
            for member_name, member_obj in inspect.getmembers(mod):
                # Only inspect members belonging directly to this module
                if (inspect.isfunction(member_obj) or inspect.isclass(member_obj)) and getattr(member_obj, "__module__", None) == modname:
                    self._inspect_annotations_recursively(member_obj, f"{modname}.{member_name}", seen)


if __name__ == "__main__":
    unittest.main()
