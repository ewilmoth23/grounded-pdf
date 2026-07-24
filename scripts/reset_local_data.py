from __future__ import annotations

import shutil
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    target = (root / "data").resolve()
    if target.parent != root.resolve() or target.name != "data":
        raise RuntimeError("Refusing to reset an unexpected path")
    answer = input(f"Delete all local GroundedPDF data in {target}? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        print("No data was removed.")
        return
    if target.exists():
        shutil.rmtree(target)
        print(f"Removed {target}. This operation is not recoverable.")
    else:
        print("No local data directory exists.")


if __name__ == "__main__":
    main()

