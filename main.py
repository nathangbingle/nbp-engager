"""
NBP Engager — unified entry point.
Runs Flask API (web) + all scheduled agents (background thread).
"""
import threading
import logging
import os
import schedule
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

from engager import run_engager
from fencing_dm import run_fencing_dm
from fencing_social import run_fencing_social
from nbp_inbox_agent import run_inbox_agent
from inbox_api import app

# ── Schedule all agents ────────────────────────────────────────────────────────
schedule.every().day.at("08:15").do(run_engager)
schedule.every().day.at("12:30").do(run_engager)
schedule.every().day.at("17:45").do(run_engager)

schedule.every(30).minutes.do(run_inbox_agent)

if os.getenv('FENCING_IG_USERNAME'):
    schedule.every().day.at("09:00").do(run_fencing_social)
    schedule.every().day.at("12:00").do(run_fencing_social)
    schedule.every().day.at("15:00").do(run_fencing_social)
    schedule.every().day.at("10:00").do(run_fencing_dm)
    print("Fencing agents: ENABLED")
else:
    print("Fencing agents: DISABLED — set FENCING_IG_USERNAME to enable")

def run_scheduler():
    # Run inbox agent immediately on startup
    run_inbox_agent()
    while True:
        schedule.run_pending()
        time.sleep(30)

# ── Start scheduler in background thread ──────────────────────────────────────
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()
print("Scheduler thread started.")

# ── Flask runs in main thread (Railway web process) ───────────────────────────
if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    print(f"API starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
