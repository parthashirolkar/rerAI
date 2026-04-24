from pathlib import Path

from dotenv import load_dotenv


def _find_project_env_file() -> Path:
    for candidate in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
        env_file = candidate.parent / ".env"
        if env_file.exists():
            return env_file

    return Path.cwd() / ".env"


def load_project_env() -> None:
    load_dotenv(dotenv_path=_find_project_env_file(), override=False)
