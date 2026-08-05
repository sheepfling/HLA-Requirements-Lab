"""Template document build script."""

import shutil
from pathlib import Path

ROOT = Path(__file__).parent
OUTPUT = ROOT / "output"


def build() -> None:
    OUTPUT.mkdir(exist_ok=True)
    # Add Python preprocessing and LaTeX compilation here.
    # Example: subprocess.run(
    #     ["latexmk", "-pdf", "-outdir=output", "main.tex"], cwd=ROOT, check=True
    # )
    print("Template document has no build steps yet.")


def clean() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "clean"))
    args = parser.parse_args()
    (build if args.action == "build" else clean)()
