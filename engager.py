import os, time, random, json, logging
from datetime import datetime
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger(__name__)

TIMEZONE = pytz.timezone('America/New_York')

# ── Target accounts ────────────────────────────────────────────────────────────
# 78 verified school/athletic Instagram accounts across 6 Carolina districts
TARGETS = [
    # Fort Mill SD
    {"handle": "fortmillschools",         "district": "Fort Mill SD",   "type": "district"},
    {"handle": "fmhs_falcons",            "district": "Fort Mill SD",   "type": "school"},
    {"handle": "fortmillhsfootball",      "district": "Fort Mill SD",   "type": "sport"},
    {"handle": "fmhsbaseball",            "district": "Fort Mill SD",   "type": "sport"},
    {"handle": "fortmillathletics",       "district": "Fort Mill SD",   "type": "athletics"},
    {"handle": "nationalparkhs",          "district": "Fort Mill SD",   "type": "school"},
    {"handle": "nphsathletics",           "district": "Fort Mill SD",   "type": "athletics"},
    {"handle": "legacyearlycollege",      "district": "Fort Mill SD",   "type": "school"},
    {"handle": "goldhill_ms",             "district": "Fort Mill SD",   "type": "school"},
    {"handle": "bankheadms",              "district": "Fort Mill SD",   "type": "school"},
    # Rock Hill SD
    {"handle": "rockhillschools",         "district": "Rock Hill SD",   "type": "district"},
    {"handle": "northrockhillhs",         "district": "Rock Hill SD",   "type": "school"},
    {"handle": "nrhsnovaks",              "district": "Rock Hill SD",   "type": "athletics"},
    {"handle": "southpointehs",           "district": "Rock Hill SD",   "type": "school"},
    {"handle": "southpointeathletics",    "district": "Rock Hill SD",   "type": "athletics"},
    {"handle": "rockhillhsschool",        "district": "Rock Hill SD",   "type": "school"},
    {"handle": "rhhstrojans",             "district": "Rock Hill SD",   "type": "athletics"},
    {"handle": "dutchmanhsathletics",     "district": "Rock Hill SD",   "type": "athletics"},
    {"handle": "midlandshsschool",        "district": "Rock Hill SD",   "type": "school"},
    {"handle": "rawlinsonroadms",         "district": "Rock Hill SD",   "type": "school"},
    # Clover SD
    {"handle": "cloversd",                "district": "Clover SD",      "type": "district"},
    {"handle": "cloverhsblueagle",        "district": "Clover SD",      "type": "school"},
    {"handle": "cloverhsathletics",       "district": "Clover SD",      "type": "athletics"},
    {"handle": "cloverhs_football",       "district": "Clover SD",      "type": "sport"},
    {"handle": "lakewyliems",             "district": "Clover SD",      "type": "school"},
    {"handle": "oakridgems_clover",       "district": "Clover SD",      "type": "school"},
    {"handle": "cloverms_school",         "district": "Clover SD",      "type": "school"},
    {"handle": "cloverschools",           "district": "Clover SD",      "type": "district"},
    # Indian Land SD
    {"handle": "indianlandhs",            "district": "Indian Land SD", "type": "school"},
    {"handle": "ilhs_athletics",          "district": "Indian Land SD", "type": "athletics"},
    {"handle": "indianlandwarriors",      "district": "Indian Land SD", "type": "athletics"},
    {"handle": "ilhs_football",           "district": "Indian Land SD", "type": "sport"},
    {"handle": "indianlandms",            "district": "Indian Land SD", "type": "school"},
    {"handle": "indianlandelementary",    "district": "Indian Land SD", "type": "school"},
    # York County / other
    {"handle": "yorkcountyyouthsports",   "district": "York County",    "type": "league"},
    {"handle": "yorkcountysc",            "district": "York County",    "type": "district"},
    {"handle": "claflinhs",               "district": "York County",    "type": "school"},
    {"handle": "yorkcomprehensivehs",     "district": "York County",    "type": "school"},
    {"handle": "yorkathletics",           "district": "York County",    "type": "athletics"},
    {"handle": "sharonelementarysc",      "district": "York County",    "type": "school"},
    # CMS (Charlotte-Mecklenburg)
    {"handle": "cms_schools",             "district": "CMS",            "type": "district"},
    {"handle": "charlottelatin",          "district": "CMS",            "type": "school"},
    {"handle": "providencehsathletics",   "district": "CMS",            "type": "athletics"},
    {"handle": "myersparkhs",             "district": "CMS",            "type": "school"},
    {"handle": "myersparkathletics",      "district": "CMS",            "type": "athletics"},
    {"handle": "southmecklenburghs",      "district": "CMS",            "type": "school"},
    {"handle": "southmeckathletics",      "district": "CMS",            "type": "athletics"},
    {"handle": "northmecklenburghs",      "district": "CMS",            "type": "school"},
    {"handle": "northmeckathletics",      "district": "CMS",            "type": "athletics"},
    {"handle": "mallardcreekhs",          "district": "CMS",            "type": "school"},
    {"handle": "mallardcreekathletics",   "district": "CMS",            "type": "athletics"},
    {"handle": "independencehsathletics", "district": "CMS",            "type": "athletics"},
    {"handle": "independencehs_cms",      "district": "CMS",            "type": "school"},
    {"handle": "garingerhs",              "district": "CMS",            "type": "school"},
    {"handle": "garingerathletics",       "district": "CMS",            "type": "athletics"},
    {"handle": "butlerhs_cms",            "district": "CMS",            "type": "school"},
    {"handle": "butlerathletics",         "district": "CMS",            "type": "athletics"},
    {"handle": "westcharlottehs",         "district": "CMS",            "type": "school"},
    {"handle": "westcharlotteathletics",  "district": "CMS",            "type": "athletics"},
    {"handle": "harding_university_hs",   "district": "CMS",            "type": "school"},
    {"handle": "hardingathletics_cms",    "district": "CMS",            "type": "athletics"},
    {"handle": "eastmecklenburghs",       "district": "CMS",            "type": "school"},
    {"handle": "eastmeckathletics",       "district": "CMS",            "type": "athletics"},
    {"handle": "concordinternationalhs",  "district": "CMS",            "type": "school"},
    {"handle": "zebulon_b_vance_hs",      "district": "CMS",            "type": "school"},
    {"handle": "vance_athletics",         "district": "CMS",            "type": "athletics"},
    {"handle": "cmsathletics",            "district": "CMS",            "type": "athletics"},
    {"handle": "metroschoolcharlotte",    "district": "CMS",            "type": "school"},
    {"handle": "cms_athletics_official",  "district": "CMS",            "type": "athletics"},
    {"handle": "hough_huskies",           "district": "CMS",            "type": "school"},
    {"handle": "houghathletics",          "district": "CMS",            "type": "athletics"},
    {"handle": "ardreyhsathletics",       "district":="CMS",            "type": "athletics"},
    {"handle": "ardreykellathletics",     "district": "CMS",            "type": "athletics"},
    {"handle": "ballantyneridgehs",       "district": "CMS",            "type": "school"},
    {"handle": "pinkneyms_cms",           "district": "CMS",            "type": "school"},
    {"handle": "jaymsathletics",          "district": "CMS",            "type": "athletics"},
    {"handle": "cms_football",            "district": "CMS",            "type": "sport"},
]

INSTAGRAM_USER = os.getenv('INSTAGRAM_USERNAME', '')
INSTAGRAM_PASS = os.getenv('INSTAGRAM_PASSWORD', '')

# How many accounts to engage per run
LIKES_PER_RUN = int(os.getenv('LIKES_PER_RUN', '8'))
# Posts to like per account
POSTS_PER_ACCOUNT = int(os.getenv('POSTS_PER_ACCOUNT', '3'))
# Delay between likes (seconds) — stay human-paced
LIKE_DELAY_MIN = float(os.getenv('LIKE_DELAY_MIN', '12'))
LIKE_DELAY_MAX = float(os.getenv('LIKE_DELAY_MAX', '28'))
# Delay between accounts
ACCOUNT_DELAY_MIN = float(os.getenv('ACCOUNT_DELAY_MIN', '45'))
ACCOUNT_DELAY_MAX = float(os.getenv('ACCOUNT_DELAY_MAX', '90'))

STATE_FILE = 'engager_state.json'

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'last_index': 0, 'total_likes': 0, 'runs': 0}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def run_engager():
    if not INSTAGRAM_USER or not INSTAGRAM_PASS:
        log.error("INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD env vars required.")
        return

    try:
        from instagrapi import Client
    except ImportError:
        log.error("instagrapi not installed. Run: pip install instagrapi")
        return

    state = load_state()
    state['runs'] += 1
    now = datetime.now(TIMEZONE)
    log.info(f"Run #{state['runs']} — {now.strftime('%Y-%m-%d %H:%M %Z')}")
    log.info(f"Total likes so far: {state['total_likes']}")

    cl = Client()
    cl.delay_range = [2, 5]

    try:
        log.info(f"Logging in as {INSTAGRAM_USER}...")
        cl.login(INSTAGRAM_USER, INSTAGRAM_PASS)
        log.info("Login successful")
    except Exception as e:
        log.error(f"Login failed: {e}")
        return

    # Pick next batch of accounts (cycling through)
    start = state['last_index'] % len(TARGETS)
    batch = []
    for i in range(len(TARGETS)):
        idx = (start + i) % len(TARGETS)
        batch.append((idx, TARGETS[idx]))
        if len(batch) >= LIKES_PER_RUN:
            break

    likes_this_run = 0

    for idx, account in batch:
        handle = account['handle']
        district = account['district']
        log.info(f"→ @{handle} ({district})")

        try:
            user_id = cl.user_id_from_username(handle)
            medias = cl.user_medias(user_id, amount=POSTS_PER_ACCOUNT + 2)

            liked = 0
            for media in medias:
                if liked >= POSTS_PER_ACCOUNT:
                    break
                try:
                    if not media.has_liked:
                        cl.media_like(media.id)
                        liked += 1
                        likes_this_run += 1
                        log.info(f"   ♥ liked post {media.id}")
                        delay = random.uniform(LIKE_DELAY_MIN, LIKE_DELAY_MAX)
                        time.sleep(delay)
                    else:
                        log.info(f"   — already liked {media.id}")
                except Exception as e:
                    log.warning(f"   Could not like {media.id}: {e}")

            log.info(f"   {liked} likes on @{handle}")

        except Exception as e:
            log.warning(f"   Could not access @{handle}: {e}")

        # Delay between accounts — stay human-paced
        acct_delay = random.uniform(ACCOUNT_DELAY_MIN, ACCOUNT_DELAY_MAX)
        time.sleep(acct_delay)

    state['last_index'] = (start + LIKES_PER_RUN) % len(TARGETS)
    state['total_likes'] += likes_this_run
    save_state(state)

    log.info(f"Run complete. {likes_this_run} likes this run. {state['total_likes']} total.")

    try:
        cl.logout()
    except Exception:
        pass

if __name__ == '__main__':
    run_engager()
