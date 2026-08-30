import os
import sys
import time
import socket
import threading
import webbrowser

from django.core.management import execute_from_command_line


HOST = "127.0.0.1"
PORT = 8000


def get_data_dir():
    """
    Determine the data directory for the application.
    Priority:
    1. NRZ_DATA_DIR environment variable (set by installer)
    2. ProgramData/NRZ Student Management (Windows installed location)
    3. Local data/ folder (development)
    """
    # Check if explicitly set by installer
    if os.environ.get('NRZ_DATA_DIR'):
        return os.environ['NRZ_DATA_DIR']
    
    # Check for installed location (ProgramData)
    if os.name == 'nt':
        program_data = os.environ.get('ALLUSERSPROFILE', r'C:\ProgramData')
        installed_data = os.path.join(program_data, 'NRZ Student Management')
        if os.path.exists(installed_data):
            return installed_data
    
    # Fall back to local data folder (development)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, 'data')


def wait_for_server(host, port, timeout=30):
    start = time.time()

    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)

    return False


def run_migrations():
    """Run Django migrations to ensure database tables exist."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    execute_from_command_line([
        "manage.py",
        "migrate",
        "--noinput",
    ])


def start_django():
    # Set the data directory before Django settings are loaded
    data_dir = get_data_dir()
    os.environ['NRZ_DATA_DIR'] = data_dir
    
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    execute_from_command_line([
        "manage.py",
        "runserver",
        f"{HOST}:{PORT}",
        "--noreload",
    ])


def main():
    # Run migrations first (idempotent, safe to run every time)
    print("Running database migrations...")
    run_migrations()
    print("Migrations complete.")
    
    django_thread = threading.Thread(
        target=start_django,
        daemon=True,
    )

    django_thread.start()

    if wait_for_server(HOST, PORT):
        webbrowser.open(
            f"http://{HOST}:{PORT}"
        )
    else:
        print("Could not start Django server.")

    django_thread.join()


if __name__ == "__main__":
    main()