import tomllib
from pathlib import Path


def test_docker_runtime_requirements_match_project_metadata() -> None:
    api_root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((api_root / "pyproject.toml").read_text())
    project_dependencies = project["project"]["dependencies"]
    docker_dependencies = [
        line.strip()
        for line in (api_root / "requirements.runtime.txt").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert docker_dependencies == project_dependencies
