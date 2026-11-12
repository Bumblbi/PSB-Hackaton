"""Bundle common core and an operator-built index; no credentials, real corpus by default."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("dist/submission.zip"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    files = [Path("requirements.lock"), Path("requirements.txt")]
    for root in ("packages", "adapters", "submission"):
        files.extend(p for p in Path(root).rglob("*.py") if "__pycache__" not in p.parts)
    with ZipFile(args.output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, path.as_posix())
        archive.write(args.index, "submission/index/corpus.json")
        archive.writestr(
            "solution.py",
            "from submission.solution import main, solve\n"
            "if __name__ == '__main__':\n    raise SystemExit(main())\n",
        )
    print(args.output)


if __name__ == "__main__":
    main()
