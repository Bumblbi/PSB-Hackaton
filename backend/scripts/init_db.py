"""Create/upgrade the configured database and optionally bootstrap an empty corpus."""

import argparse
from pathlib import Path

from sqlalchemy.orm import Session

from adapters.ingest import ingest_manifest
from adapters.storage.database import ActiveCorpusRow, load_corpus, make_engine, persist_corpus
from adapters.storage.migrations import upgrade_database
from apps.api.app.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, help="Bootstrap corpus (only if none is stored)")
    args = parser.parse_args()
    settings = Settings()
    engine = make_engine(settings.database_url)
    try:
        upgrade_database(engine)
        with Session(engine) as session, session.begin():
            if args.manifest and session.get(ActiveCorpusRow, 1) is None:
                persist_corpus(session, ingest_manifest(args.manifest))
                session.flush()
            corpus = load_corpus(session)
            print(
                f"Database ready: {engine.dialect.name}; "
                f"versions={len(corpus.versions)}; "
                f"chunks={sum(len(v.chunks) for v in corpus.versions)}"
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
