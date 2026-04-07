import schedule, time, logging, os
from engager import run_engager
from fencing_dm import run_fencing_dm
from fencing_social import run_fencing_social
from nbp_social import run_nbp_social

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

# ── School/athletic engager — runs 3x daily (existing) ─────────────────────────
schedule.every().day.at("08:15").do(run_engager)
schedule.every().day.at("12:30").do(run_engager)
schedule.every().day.at("17:45").do(run_engager)

# ── Fencing social posts — 3x daily (9am, 12pm, 3pm ET) ───────────────────────
if os.getenv('FENCING_IG_USERNAME'):
    schedule.every().day.at("09:00").do(run_fencing_social)
    schedule.every().day.at("12:00").do(run_fencing_social)
    schedule.every().day.at("15:00").do(run_fencing_social)
    print("Fencing social agent: ENABLED — 9:00am, 12:00pm, 3:00pm ET")
else:
    print("Fencing social agent: DISABLED — set FENCING_IG_USERNAME to enable")

# ── Fencing DM agent — once daily at 10am ET ───────────────────────────────────
if os.getenv('FENCING_IG_USERNAME'):
    schedule.every().day.at("10:00").do(run_fencing_dm)
    print("Fencing DM agent:     ENABLED — 10:00am ET")
else:
    print("Fencing DM agent:     DISABLED — set FENCING_IG_USERNAME to enable")

# ── NBP social posts — 3x daily (10am, 1pm, 4pm ET) — offset from fencing ────
if os.getenv('NBP_IG_USERNAME'):
    schedule.every().day.at("10:00").do(run_nbp_social)
    schedule.every().day.at("13:00").do(run_nbp_social)
    schedule.every().day.at("16:00").do(run_nbp_social)
    print("NBP social agent:     ENABLED — 10:00am, 1:00pm, 4:00pm ET")
else:
    print("NBP social agent:     DISABLED — set NBP_IG_USERNAME to enable")

print("School engager:       ENABLED — 8:15am, 12:30pm, 5:45pm ET")
print("─────────────────────────────────────────────────")
print("All agents running. Waiting for scheduled times...")

while True:
    schedule.run_pending()
    time.sleep(30)
