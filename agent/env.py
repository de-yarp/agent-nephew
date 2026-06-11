from pathlib import Path

from dotenv import load_dotenv


def load_env(project_root: Path) -> None:
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)
