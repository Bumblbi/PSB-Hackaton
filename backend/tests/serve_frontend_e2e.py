"""Dedicated E2E server: temporary SQLite and test-only evidence gateway."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from conftest import EvidenceLLM

from adapters.ingest import ingest_manifest
from apps.api.app.main import create_app
from apps.api.app.settings import Settings

if __name__ == "__main__":
    with TemporaryDirectory(prefix="legal-e2e-") as directory:
        settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{Path(directory) / 'test.db'}",
            index_path=None,
            llm_provider="organizer",
        )
        corpus = ingest_manifest(Path("data/demo/manifest.json"))
        # Production configuration deliberately cannot select this gateway.
        app = create_app(settings, corpus=corpus, llm=EvidenceLLM())
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=int(os.environ.get("E2E_PORT", "8001")),
            access_log=False,
            log_level="warning",
        )
