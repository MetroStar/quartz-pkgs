#!/usr/bin/env python3
"""Verify build-time scanner patches against an unmodified source checkout."""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    if not (source / "epyon.sh").is_file():
        parser.error(f"not an Epyon source checkout: {source}")
    dockerfile = Path(__file__).resolve().parents[1] / "src/quartz-evaluator/Dockerfile"
    blocks = re.findall(r"^RUN python3 - <<'PY'\n(.*?)^PY$", dockerfile.read_text(), re.M | re.S)
    if not blocks:
        raise SystemExit(f"no patch blocks found in {dockerfile}")
    with tempfile.TemporaryDirectory(prefix="quartz-evaluator-patches-") as directory:
        app = Path(directory) / "app"
        shutil.copytree(source, app, ignore=shutil.ignore_patterns(".git"))
        for index, block in enumerate(blocks, 1):
            script = Path(directory) / f"patch-{index}.py"
            script.write_text(block.replace("/app/", f"{app}/"))
            subprocess.run(["python3", str(script)], check=True)
        patched = [
            script
            for script in (app / "scripts/shell").glob("*.sh")
            if script.read_bytes() != (source / script.relative_to(app)).read_bytes()
        ]
        for script in patched:
            subprocess.run(["bash", "-n", str(script)], check=True)
    print(f"Verified {len(blocks)} patch block(s) and {len(patched)} patched shell scripts")


if __name__ == "__main__":
    main()
