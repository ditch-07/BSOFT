import os
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.conf import settings
from school.models import BackupConfig
from school.utils.backups import BackupError, create_backup, timestamped_name


class Command(BaseCommand):
    help = "Create a daily backup and clean old backups"

    def handle(self, *args, **options):
        config = BackupConfig.get_config()
        if not config.auto_backup_enabled:
            self.stdout.write("Auto-backup is disabled.")
            return

        backup_dir = config.get_backup_path()
        if not backup_dir:
            self.stdout.write("No backup path configured.")
            return

        # Ensure backup directory exists
        os.makedirs(backup_dir, exist_ok=True)

        # 1. Create new backup (consistent copy + SQLite integrity check)
        db_path = settings.DATABASES['default']['NAME']
        backup_name = timestamped_name("auto_backup")
        backup_path = os.path.join(backup_dir, backup_name)

        try:
            create_backup(db_path, backup_path)
            self.stdout.write(
                self.style.SUCCESS(f"Backup created and verified: {backup_name}")
            )
        except BackupError as exc:
            self.stdout.write(self.style.ERROR(f"Backup failed: {exc}"))
            return

        # 2. Clean old backups
        retention = config.retention_days
        cutoff = datetime.now() - timedelta(days=retention)

        for filename in os.listdir(backup_dir):
            if filename.startswith('auto_backup_') and filename.endswith('.sqlite3'):
                filepath = os.path.join(backup_dir, filename)
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if mtime < cutoff:
                        os.remove(filepath)
                        self.stdout.write(f"Removed old backup: {filename}")
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Could not remove {filename}: {e}"))