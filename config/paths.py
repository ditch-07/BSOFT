from pathlib import Path
import os
import sys


def get_app_dir():
    """
    Directory containing the application.

    Development:
        Project directory

    Packaged:
        Directory containing the EXE
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


APP_DIR = get_app_dir()


def get_internal_dir():
    """
    Directory containing bundled application resources.

    Development:
        Project directory

    PyInstaller:
        PyInstaller's extracted/bundled resource directory
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)

    return APP_DIR


INTERNAL_DIR = get_internal_dir()


# ---------------------------------------------------------
# Persistent application data
# ---------------------------------------------------------

# Optional override.
# Otherwise, packaged application uses:
#
# USB:\NRZ Student Management\data\
#
DATA_DIR = Path(
    os.environ.get(
        "NRZ_DATA_DIR",
        APP_DIR / "data"
    )
)


# ---------------------------------------------------------
# Bundled resources
# ---------------------------------------------------------

STATIC_DIR = INTERNAL_DIR / "static"
TEMPLATES_DIR = INTERNAL_DIR / "templates"