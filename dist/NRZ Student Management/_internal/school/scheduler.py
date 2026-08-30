"""
APScheduler configuration for automatic student progression.
Runs the progression check every 6 hours when the Django app is running.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def run_auto_progression():
    """Run the auto-progression management command."""
    from django.core.management import call_command
    try:
        logger.info("Running automatic student progression check...")
        call_command('progress_students_by_date')
        logger.info("Automatic student progression completed.")
    except Exception as e:
        logger.error(f"Error in automatic progression: {e}")


def start_scheduler():
    """Start the background scheduler for automatic tasks."""
    if not scheduler.running:
        # Add the progression job - runs every 6 hours
        scheduler.add_job(
            run_auto_progression,
            trigger=IntervalTrigger(hours=6),
            id='auto_student_progression',
            name='Automatic Student Progression',
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        
        # Also run once on startup (after a short delay to let DB settle)
        scheduler.add_job(
            run_auto_progression,
            trigger=IntervalTrigger(seconds=30),
            id='auto_student_progression_startup',
            name='Automatic Student Progression (Startup)',
            replace_existing=True,
            max_instances=1,
        )
        
        scheduler.start()
        logger.info("APScheduler started - automatic student progression enabled (every 6 hours)")
    else:
        logger.info("APScheduler already running")


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler shut down")