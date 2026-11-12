import argparse
from pathlib import Path

from adapters.ingest import ingest_manifest
from adapters.search.offline_index import OfflineIndex


def main():
    parser = argparse.ArgumentParser(description="Build a reproducible offline corpus index")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    index = OfflineIndex(ingest_manifest(args.manifest))
    index.save(args.output)
    print(f"index_version={index.index_version} chunks={len(index.chunks)}")


if __name__ == "__main__":
    main()
