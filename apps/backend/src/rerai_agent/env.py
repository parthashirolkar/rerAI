from pathlib import Path

from dotenv import load_dotenv


def _find_project_env_files() -> list[Path]:
    env_files: list[Path] = []
    for candidate in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
        directory = candidate if candidate.is_dir() else candidate.parent
        env_file = directory / ".env"
        if env_file.exists():
            env_files.append(env_file)

    cwd_env_file = Path.cwd() / ".env"
    if cwd_env_file.exists():
        env_files.append(cwd_env_file)

    env_files = list(dict.fromkeys(env_files))
    return list(reversed(env_files))


def _find_project_env_file() -> Path:
    env_files = _find_project_env_files()
    if env_files:
        return env_files[-1]
    return Path.cwd() / ".env"


def load_project_env() -> None:
    for env_file in _find_project_env_files():
        load_dotenv(dotenv_path=env_file, override=False)
