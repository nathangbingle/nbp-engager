import schedule, time, logging
from engager import run_engager

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

# Run 3 times a day — spread out to look natural
schedule.every().day.at("08:15").do(run_engager)
schedule.every().day.at("12:30").do(run_engager)
schedule.every().day.at("17:45").do(run_engager)

print("NBP Instagram Engager — running 3x daily")
print("Schedule: 8:15am, 12:30pm, 5:45pm ET")
print("Likes per run: ~8 accounts x 3 posts = ~24 likes")

while True:
    schedule.run_pending()
    time.sleep(30)
