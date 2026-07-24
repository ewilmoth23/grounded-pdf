from __future__ import annotations

import shutil
from pathlib import Path

from generate_sample_pdf import main as generate_sample_pdf


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    target = (root / "data" / "e2e").resolve()
    expected_parent = (root / "data").resolve()
    if target.parent != expected_parent or target.name != "e2e":
        raise RuntimeError("Refusing to reset an unexpected end-to-end data path")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    generate_sample_pdf()
    print(f"Prepared isolated end-to-end data in {target}")


if __name__ == "__main__":
    main()
