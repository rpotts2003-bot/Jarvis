"""CI safety: never hit HuggingFace for real GGUF downloads during pytest."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_real_model_download(monkeypatch, tmp_path):
    """Redirect models dir + block download worker unless a test opts in."""
    import assistant.llm.local_model as lm

    models = tmp_path / "jarvis_models"
    models.mkdir(exist_ok=True)
    monkeypatch.setattr(lm, "models_dir", lambda: models)
    monkeypatch.setattr(
        lm,
        "_download_worker",
        lambda url, dest: (_ for _ in ()).throw(
            RuntimeError("real GGUF download blocked in tests")
        ),
    )
    lm.reset_for_tests()
    yield
    lm.reset_for_tests()
