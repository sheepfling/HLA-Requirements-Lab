"""Render generated PlantUML sources through the pinned EPS-to-PDF path."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def render_sources(
    sources: tuple[Path, ...],
    output_dir: Path,
    *,
    java: str = "java",
    jar: Path,
    epstopdf: str = "epstopdf",
) -> tuple[Path, ...]:
    """Render PlantUML source files as vector PDFs."""

    output_dir.mkdir(parents=True, exist_ok=True)
    jar = jar.resolve()
    outputs: list[Path] = []
    for source in sources:
        source = source.resolve()
        eps = source.with_suffix(".eps")
        # PlantUML 1.2024.6 can return exit code 0 while writing a rendered
        # error page after Graphviz rejects a dense state chart.  Never allow
        # an old EPS to survive a failed regeneration and be mistaken for a
        # fresh release asset.
        eps.unlink(missing_ok=True)
        result = subprocess.run(
            [java, "-jar", str(jar), "-charset", "UTF-8", "-teps", str(source)],
            cwd=source.parent,
            check=True,
            capture_output=True,
            text=True,
        )
        if not eps.is_file():
            details = (result.stdout + "\n" + result.stderr).strip()
            raise RuntimeError(f"PlantUML did not produce {eps}: {details[-2000:]}")
        eps_text = eps.read_text(encoding="latin-1", errors="ignore")
        if "An error has occurred" in eps_text or "java.lang." in eps_text:
            eps.unlink(missing_ok=True)
            raise RuntimeError(f"PlantUML produced an error diagram for {source}")
        output = output_dir / f"{source.stem}.pdf"
        subprocess.run(
            [epstopdf, f"--outfile={output}", str(eps)],
            check=True,
        )
        outputs.append(output)
    return tuple(outputs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--jar", required=True, type=Path)
    parser.add_argument("--java", default="java")
    parser.add_argument("--epstopdf", default="epstopdf")
    args = parser.parse_args()
    outputs = render_sources(
        tuple(args.sources),
        args.output_dir,
        java=args.java,
        jar=args.jar,
        epstopdf=args.epstopdf,
    )
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
