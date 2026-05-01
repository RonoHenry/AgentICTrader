"""
services package

Exposes ``services.market_data`` as an alias for the ``services/market-data/``
directory (Python cannot import from hyphenated directory names directly).
"""
import importlib.util
import sys
import os

def _register_hyphenated_subpackage(hyphen_name: str, underscore_name: str) -> None:
    """Register a hyphenated subdirectory as an importable Python subpackage."""
    _pkg_dir = os.path.join(os.path.dirname(__file__), hyphen_name)
    _full_name = f"services.{underscore_name}"

    if _full_name in sys.modules:
        return  # already registered

    spec = importlib.util.spec_from_file_location(
        _full_name,
        os.path.join(_pkg_dir, "__init__.py"),
        submodule_search_locations=[_pkg_dir],
    )
    if spec is None:
        return

    module = importlib.util.module_from_spec(spec)
    module.__path__ = [_pkg_dir]
    module.__package__ = _full_name
    sys.modules[_full_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    # Also attach as attribute on this package
    import services as _services_pkg
    setattr(_services_pkg, underscore_name, module)


_register_hyphenated_subpackage("market-data", "market_data")
