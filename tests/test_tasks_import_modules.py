"""Jedes src.tasks.*-Modul muss isoliert importierbar sein (kein Import-Zyklus)."""

import importlib
import pkgutil

import src.tasks as tasks_pkg


def test_each_tasks_submodule_imports_cleanly():
    failures = []
    prefix = tasks_pkg.__name__ + "."
    for mod in pkgutil.iter_modules(tasks_pkg.__path__, prefix):
        name = mod.name
        if name.endswith(".__init__"):
            continue
        try:
            importlib.import_module(name)
        except Exception as exc:
            failures.append(f"{name}: {exc}")
    assert not failures, "Import failures:\n" + "\n".join(failures)
