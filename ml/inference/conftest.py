"""
Fixtures for the ml/inference tests.
"""
import pytest

from ml.inference.feature_flags import reset_feature_flags


@pytest.fixture(autouse=True)
def _fresh_feature_flags():
    """
    Give each test its own global FeatureFlagManager.

    ``get_feature_flags()`` caches a single manager per process and reads the
    environment only once, when the manager is created. Without a reset, the
    first test to touch the flags decides their state for the whole run, and
    tests that call ``update_flag``/``register_flag``/``_flags.clear()`` on the
    global manager change it for every later test. With the reset, an
    environment set by a test (e.g. ``patch.dict(os.environ,
    {"CONFLUENCE_SCORER_AB_TEST": "true"})``) is the one the framework sees.
    """
    reset_feature_flags()
    yield
    reset_feature_flags()
