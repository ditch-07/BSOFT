def run_startup_commands():
    """
    Run application-specific Django commands required
    during normal NRZ startup.

    These commands are safe to run on every application start,
    provided the commands themselves are idempotent.
    """

    print()
    print("=" * 50)
    print("NRZ STARTUP COMMANDS")
    print("=" * 50)

    # ---------------------------------------------------------
    # Seed academic years
    # ---------------------------------------------------------

    print("Running seed_academic_years...")

    call_command(
        "seed_academic_years",
        back=5,
        forward=10,
    )

    print("seed_academic_years completed.")

    # ---------------------------------------------------------
    # Setup roles / permissions
    # ---------------------------------------------------------

    print("Running setup_roles...")

    call_command("setup_roles")

    print("setup_roles completed.")

    print("=" * 50)
    print("NRZ STARTUP COMMANDS COMPLETE")
    print("=" * 50)
    print()