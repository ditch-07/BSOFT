import os
import sys
import time
import socket
import threading
import webbrowser
from django.core.management import call_command

from django.core.management import execute_from_command_line


HOST = "127.0.0.1"
PORT = 8000


def get_data_dir():
    """
    Determine the persistent data directory.

    Packaged application:
        data/ beside the EXE

    Development:
        data/ beside the project

    NRZ_DATA_DIR can override the default location.
    """

    # Explicit override
    if os.environ.get("NRZ_DATA_DIR"):
        return os.environ["NRZ_DATA_DIR"]

    # Packaged application
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(
            os.path.abspath(sys.executable)
        )

        return os.path.join(
            app_dir,
            "data"
        )

    # Development
    base_dir = os.path.dirname(
        os.path.abspath(__file__)
    )

    return os.path.join(
        base_dir,
        "data"
    )

def setup_django():
    data_dir = get_data_dir()

    os.makedirs(data_dir, exist_ok=True)

    # Verify that the data directory is writable
    test_file = os.path.join(
        data_dir,
        ".write_test"
    )

    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("test")

        os.remove(test_file)

    except OSError as e:
        print()
        print("ERROR: NRZ cannot write to its data directory.")
        print(f"Data directory: {data_dir}")
        print(f"Reason: {e}")
        print()
        input("Press ENTER to exit...")
        sys.exit(1)

    os.environ["NRZ_DATA_DIR"] = data_dir

    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        "config.settings"
    )

def wait_for_server(host, port, timeout=30):
    start = time.time()

    while time.time() - start < timeout:
        try:
            with socket.create_connection(
                (host, port),
                timeout=1
            ):
                return True

        except OSError:
            time.sleep(0.5)

    return False


def run_migrations():
    """
    Run Django migrations.
    """
    print("Running database migrations...")

    execute_from_command_line([
        "manage.py",
        "migrate",
        "--noinput",
    ])

    print("Migrations complete.")

def run_management_command():
    setup_django()

    command = sys.argv[1]

    commands_without_auto_migrate = {
        "makemigrations",
        "startapp",
        "startproject",
        "help",
    }

    if command not in commands_without_auto_migrate:
        print("Checking database migrations...")
        run_migrations()

    execute_from_command_line([
        "manage.py",
        *sys.argv[1:],
    ])

def start_django():
    """
    Start the Django development server.
    """

    execute_from_command_line([
        "manage.py",
        "runserver",
        f"{HOST}:{PORT}",
        "--noreload",
    ])
    
def start_application():
    """
    Normal application startup.
    """
    setup_django()

    # Run database migrations first
    run_migrations()

    # Run NRZ startup commands
    run_startup_commands()

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

def run_startup_commands():
    """
    Run application-specific Django commands required
    during normal NRZ startup.
    """

    print()
    print("=" * 50)
    print("NRZ STARTUP COMMANDS")
    print("=" * 50)

    print("Running seed_academic_years...")

    call_command(
        "seed_academic_years",
        back=5,
        forward=10,
    )

    print("seed_academic_years completed.")

    print("=" * 50)
    print()
    
def main():
    """
    Decide whether we're launching the application normally
    or executing a Django management command.
    """

    # Arguments after the executable name.
    #
    # Example:
    #
    # NRZ Student Management.exe createsuperuser
    #
    # sys.argv[1:] == ["createsuperuser"]

    if len(sys.argv) > 1:
        run_management_command()
    else:
        start_application()


if __name__ == "__main__":
    main()