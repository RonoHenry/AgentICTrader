"""
TDD - Task 171: training/data_pipeline.py - self-generated sample collection.

RED phase: S3 upload of chart + label; fire-and-forget scheduling via
FastAPI BackgroundTasks (never awaited inline in the response path); no
embedding/training code anywhere in this module (Phase 4/5 is out of scope).

**Validates: Requirements 11.1-11.4 (.kiro/specs/visual-model/requirements.md)**
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.visual_model import training
from services.visual_model.api.router import get_vlm_reasoner, router
from services.visual_model.training import data_pipeline
from services.visual_model.training.data_pipeline import store_training_sample
from services.visual_model.tests.test_router import _candles_by_tf, _request_payload, _valid_analysis


class TestStoreTrainingSample:
    def test_store_training_sample_uploads_png_and_metadata(self) -> None:
        s3_client = MagicMock()
        store_training_sample(
            chart_png=b"fake-png-bytes",
            analysis=_valid_analysis(),
            instrument="XAUUSD",
            timestamp=datetime.now(timezone.utc),
            s3_client=s3_client,
        )
        assert s3_client.put_object.call_count == 2
        calls = s3_client.put_object.call_args_list
        content_types = {call.kwargs["ContentType"] for call in calls}
        assert content_types == {"image/png", "application/json"}

    def test_store_training_sample_never_raises_on_s3_failure(self) -> None:
        s3_client = MagicMock()
        s3_client.put_object.side_effect = RuntimeError("S3 unavailable")
        # Must not raise - this runs after the HTTP response has already
        # been sent, nothing is listening for an exception here.
        store_training_sample(
            chart_png=b"fake-png-bytes",
            analysis=_valid_analysis(),
            instrument="XAUUSD",
            timestamp=datetime.now(timezone.utc),
            s3_client=s3_client,
        )

    def test_store_training_sample_noop_when_no_client_configured(self) -> None:
        # No s3_client passed and no boto3 client configured - should be a
        # silent no-op, not an error.
        store_training_sample(
            chart_png=b"fake-png-bytes",
            analysis=_valid_analysis(),
            instrument="XAUUSD",
            timestamp=datetime.now(timezone.utc),
            s3_client=None,
        )


class TestNoEmbeddingOrTrainingCode:
    def test_data_pipeline_has_no_embedding_or_training_calls(self) -> None:
        # Check actual imports and defined function names only - the
        # module's own docstring legitimately explains what it deliberately
        # does NOT do, which would false-positive a naive prose scan.
        source_lines = inspect.getsource(data_pipeline).splitlines()
        import_lines = [
            line for line in source_lines if line.strip().startswith(("import ", "from "))
        ]
        forbidden_modules = ("torch", "sentence_transformers", "transformers", "clip")
        for line in import_lines:
            for module_name in forbidden_modules:
                assert module_name not in line, f"unexpected import in data_pipeline: {line!r}"

        function_names = {
            name
            for name, obj in vars(data_pipeline).items()
            if inspect.isfunction(obj) and obj.__module__ == data_pipeline.__name__
        }
        # "training_sample"/"training data" naming is intentional (this
        # module collects data for later training phases) - only flag names
        # that would indicate an actual embedding/model-fitting operation.
        forbidden_name_fragments = ("embed", "finetune", "fit_model", "train_model")
        for name in function_names:
            for fragment in forbidden_name_fragments:
                assert fragment not in name.lower(), (
                    f"unexpected training/embedding function defined: {name!r}"
                )

    def test_training_package_has_no_clip_or_vit_modules(self) -> None:
        import os

        training_dir = os.path.dirname(training.__file__)
        files = set(os.listdir(training_dir))
        assert "clip_trainer.py" not in files
        assert "vit_finetuner.py" not in files
        assert "quality_labeller.py" not in files


class TestFireAndForgetScheduling:
    def _app_client(self):
        app = FastAPI()
        app.include_router(router)
        mock_reasoner = MagicMock()
        mock_reasoner.analyse = AsyncMock(return_value=_valid_analysis())
        app.dependency_overrides[get_vlm_reasoner] = lambda: mock_reasoner
        return TestClient(app)

    def test_store_training_sample_runs_after_response_sent(self) -> None:
        """Property 12: Training Sample Persistence Never Blocks the Response Path."""
        client = self._app_client()
        with patch(
            "services.visual_model.api.router.BackgroundTasks.add_task"
        ) as add_task_spy:
            response = client.post("/visual/analyse", json=_request_payload())
        assert response.status_code == 200
        add_task_spy.assert_called_once()
        assert add_task_spy.call_args[0][0] is store_training_sample

    def test_store_training_sample_never_called_on_degraded_response(self) -> None:
        client = self._app_client()
        incomplete = _candles_by_tf()
        from pd_array_engine.models import Timeframe

        del incomplete[Timeframe.M5]
        with patch(
            "services.visual_model.api.router.BackgroundTasks.add_task"
        ) as add_task_spy:
            response = client.post("/visual/analyse", json=_request_payload(incomplete))
        assert response.status_code == 200
        assert response.json()["degraded"] is True
        add_task_spy.assert_not_called()
