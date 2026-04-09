from __future__ import annotations

from . import _common as _common_module
from . import audit_prompt as _audit_prompt_module
from . import table_prompt as _table_prompt_module
from . import verify_prompt as _verify_prompt_module


def __getattr__(name: str):
    for module in (
        _common_module,
        _audit_prompt_module,
        _table_prompt_module,
        _verify_prompt_module,
    ):
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(name)


def __dir__() -> list[str]:
    names = set(globals())
    for module in (
        _common_module,
        _audit_prompt_module,
        _table_prompt_module,
        _verify_prompt_module,
    ):
        names.update(getattr(module, "__all__", []))
    return sorted(names)


__all__ = __dir__()
