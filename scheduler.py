from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import config

_scheduler = AsyncIOScheduler(timezone=config.LOCAL_TZ_NAME)


def start(morning_job_func, matcha_job_func=None):
    if _scheduler.running:
        return
    _scheduler.add_job(
        morning_job_func,
        "cron",
        hour=config.MORNING_HOUR,
        minute=config.MORNING_MINUTE,
        id="send_morning_brief",
        replace_existing=True,
    )
    # MATCHA_CHECK_INTERVAL_MINUTES 設 0（或負數）＝暫停抹茶監控，不註冊這個排程；
    # 頻道裡手動打「查抹茶」還是可以即時查。
    if matcha_job_func and config.MATCHA_CHECK_INTERVAL_MINUTES > 0:
        _scheduler.add_job(
            matcha_job_func,
            "interval",
            minutes=config.MATCHA_CHECK_INTERVAL_MINUTES,
            id="check_matcha_restock",
            replace_existing=True,
            next_run_time=datetime.now(),  # 開機時先跑一次，建立庫存基準值
        )
    _scheduler.start()


def stop():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
