import schedule, time, logging, os
from engager import run_engager
from fencing_dm import run_fencing_dm

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

# ── School/athletic engager — runs 3x daily (existing) ─────────────────────────
schedule.every().day.at("08:15").do(run_engager)
schedule.every().day.at("12:30").do(run_engager)
schedule.every().day.at("17:45").do(run_engager)

# ── Fencing DM agent — runs once daily at 10am ET ──────────────────────────────
# Only runs if FENCING_IG_USERNAME is set (safe to deploy before account is created)
if os.getenv('FENCING_IG_USERNAME'):
    schedule.every().day.at("10:00").do(run_fencing_dm)
    print("Fencing DM agent: ENABLED — runs daily at 10:00am ET")
else:
    print("Fencing DM agent: DISABLED — set FENCING_IG_USERNAME to enable")

print("NBP Instagram Engager — running 3x daily")
print("Schedule: 8:15am, 12:30pm, 5:45pm ET (school engager)")
print("Schedule: 10:00am ET (fencing DM agent, when enabled)")

while True:
    schedule.run_pending()
    time.sleep(30)
