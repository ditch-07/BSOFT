from pathlib import Path
import sys


def application_dir():
    """
    Directory containing the actual application.
    Works both during development and when packaged.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


APP_DIR = application_dir()

DATA_DIR = APP_DIR / "data"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"