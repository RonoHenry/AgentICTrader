"""
Shared fixtures for the ml/ test tree.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_mlflow_store(tmp_path, monkeypatch):
    """
    Give every ml/ test its own throwaway MLflow store under ``tmp_path``.

    MLflowTracker, ml.inference.main.ModelRegistry and ModelVersionRegistry
    all call ``mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", ...))``
    in their constructors, and ``mlflow.set_tracking_uri`` also writes the URI
    back into ``os.environ["MLFLOW_TRACKING_URI"]``. So a URI set by one test
    stays in place for every later test in the process. That is how a
    ``./false`` file store kept appearing at the repo root: A/B-testing tests
    patched ``os.getenv`` to return ``"false"``, which became the tracking
    URI, and a later unmocked ``register_model("pattern-detector")`` call
    wrote a registry into it. Without isolation, unmocked lookups also go to
    http://localhost:5000, where MLflow retries for minutes when no server is
    running.

    With a per-test file store, nothing is written into the repo, and lookups
    for models that were never registered fail immediately, so the code under
    test takes its stub-model fallback. MLflow's global tracking URI and the
    environment variables are restored after each test.
    """
    import mlflow
    from mlflow.tracking._tracking_service import utils as tracking_utils

    prev_tracking_uri = tracking_utils._tracking_uri

    store_uri = (tmp_path / "mlruns").as_uri()
    monkeypatch.setenv("MLFLOW_TRACKING_URI", store_uri)
    # The model registry follows the tracking store unless overridden.
    monkeypatch.delenv("MLFLOW_REGISTRY_URI", raising=False)
    mlflow.set_tracking_uri(store_uri)

    yield

    # Runs before monkeypatch's own teardown, which then restores the
    # original MLFLOW_TRACKING_URI value (or removes it if it was unset).
    mlflow.set_tracking_uri(prev_tracking_uri)
