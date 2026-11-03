"""A package's door: the names its `__init__.py` exports, each read from the child module that defines it.

A door never binds an exported name. It looks the name up in its child on every access, through the module's
`__getattr__` (PEP 562), so:

- a test that patches the name where it is defined (`mock.patch.object(child, "name")`) reaches every caller that goes
  through the door, as CONTRIBUTING's patch rule needs;
- importing the package loads none of its children until a caller uses one of their names, so the guard hook loads
  only the modules it runs.

A door's `__init__.py` names each export twice: once for the type checker, as `from aidd.p.child import name as export`
under `TYPE_CHECKING`, and once here, in the map this module turns into `__getattr__` and `__dir__`. The type checker
reads the import as an alias of the child's own name, so it needs no type inferred through the cycle every package
and its children form.
`tests/test_package_doors.py` checks that the two agree, that every name resolves, and that no child module is named
like an export (importing a child sets the package attribute of its name, which would hide the export).
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Mapping


def exports(package: str, names: Mapping[str, str]) -> tuple[Callable[[str], object], Callable[[], list[str]]]:
    """`__getattr__` and `__dir__` for `package`'s door. `names` maps each exported name to the child module that
    defines it under that same name, so a search for the name finds the door and the child alike."""

    def __getattr__(name: str) -> object:
        child = names.get(name)
        if child is None:
            raise AttributeError(f"module {package!r} has no attribute {name!r}")
        return getattr(importlib.import_module(f"{package}.{child}"), name)

    def __dir__() -> list[str]:
        return sorted({*vars(sys.modules[package]), *names})

    return __getattr__, __dir__
