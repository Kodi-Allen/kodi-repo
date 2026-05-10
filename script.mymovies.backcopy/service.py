import time
import traceback

import xbmc

from resources.lib.backcopy import (
    run_scheduled,
    setting_bool,
    setting_int,
    log,
)


CHECK_INTERVAL_SECONDS = 30


def wait_for_abort(monitor, seconds):
    return monitor.waitForAbort(max(1, int(seconds)))


def run_service():
    monitor = xbmc.Monitor()
    next_run = 0
    startup_run_planned = False

    log("Scheduler service started")

    while not monitor.abortRequested():
        try:
            schedule_enabled = setting_bool("schedule_enabled", False)
            interval_seconds = max(1, setting_int("schedule_interval_hours", 24)) * 60 * 60

            if not schedule_enabled:
                next_run = 0
                startup_run_planned = False
                if wait_for_abort(monitor, CHECK_INTERVAL_SECONDS):
                    break
                continue

            now = time.time()
            if next_run <= 0:
                if setting_bool("run_on_startup", False) and not startup_run_planned:
                    delay_seconds = max(0, setting_int("startup_delay_minutes", 2)) * 60
                    next_run = now + delay_seconds
                    startup_run_planned = True
                    log("Startup run scheduled in {} seconds".format(delay_seconds))
                else:
                    next_run = now + interval_seconds
                    log("Next scheduled run in {} seconds".format(interval_seconds))

            if now >= next_run:
                run_scheduled()
                next_run = time.time() + interval_seconds
                log("Next scheduled run in {} seconds".format(interval_seconds))

            sleep_seconds = min(CHECK_INTERVAL_SECONDS, max(1, next_run - time.time()))
            if wait_for_abort(monitor, sleep_seconds):
                break
        except Exception:
            log("Service loop error:\n{}".format(traceback.format_exc()), xbmc.LOGERROR)
            if wait_for_abort(monitor, CHECK_INTERVAL_SECONDS):
                break

    log("Scheduler service stopped")


if __name__ == "__main__":
    run_service()
