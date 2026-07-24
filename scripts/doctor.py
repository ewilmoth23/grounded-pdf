from __future__ import annotations

import shutil
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    checks = {
        "Python 3.12+": sys.version_info >= (3, 12),
        "Node.js": shutil.which("node") is not None,
        "npm": shutil.which("npm") is not None,
        "API environment": (root / ".venv" / "bin" / "python").exists()
        or (root / ".venv" / "Scripts" / "python.exe").exists(),
        "Web dependencies": (root / "apps" / "web" / "node_modules").is_dir(),
        "Environment template": (root / ".env.example").is_file(),
    }
    print("GroundedPDF startup check")
    for name, passed in checks.items():
        print(f"  {'OK' if passed else 'MISSING':7} {name}")
    missing = [name for name, passed in checks.items() if not passed]
    if missing:
        print("\nRun `make install`, then copy `.env.example` to `.env` if needed.")
        return 1
    print("\nDevelopment prerequisites are ready. Ollama availability is shown in the app health check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

