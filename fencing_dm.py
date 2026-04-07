import os, time, random, json, logging
from datetime import datetime
import pytz

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger(__name__)

TIMEZONE = pytz.timezone('America/New_York')

# ── Credentials — @nathanbinglefencing ────────────────────────────────────────
FENCING_IG_USER = os.getenv('FENCING_IG_USERNAME', '')
FENCING_IG_PASS = os.getenv('FENCING_IG_PASSWORD', '')

# ── Daily limits ───────────────────────────────────────────────────────────────
DMS_PER_DAY   = int(os.getenv('FENCING_DMS_PER_DAY', '10'))
DM_DELAY_MIN  = float(os.getenv('FENCING_DM_DELAY_MIN', '90'))   # seconds between DMs
DM_DELAY_MAX  = float(os.getenv('FENCING_DM_DELAY_MAX', '240'))

STATE_FILE = 'fencing_dm_state.json'
SESSION_FILE = 'fencing_ig_session.json'
IG_SESSION_ENV = os.getenv('FENCING_IG_SESSION', '')

# ── Landing page (update when live) ───────────────────────────────────────────
BOOKING_LINK = os.getenv('FENCING_BOOKING_LINK', 'https://www.nathanbinglephotography.com/usafencing')

# ── Verified US fencing accounts — clubs, colleges, athletes, media ───────────
# All handles verified via web search (Mar 2026). ~90 targets ≈ ~9 days at 10/day.
FENCING_TARGETS = [
    # Major US clubs (verified handles)
    "manhattanfencing",         # Manhattan Fencing Center, NYC
    "brooklynfencing",          # Brooklyn Fencing Center
    "morehousefencing",         # Tim Morehouse Fencing Club, NYC
    "fencersclubinc",           # Fencers Club Inc., NYC (est. 1883)
    "fencenyfa",                # New York Fencing Academy, Brooklyn
    "la.ifc",                   # LA International Fencing Center
    "laifc_oc",                 # LA IFC Orange County
    "elitefencingclubefc",      # Elite Fencing Club, LA
    "bhfencers",                # Beverly Hills Fencers' Club
    "swordsfencingstudio",      # Swords Fencing Studio, Pasadena
    "mteamfencing",             # Massialas Foundation MTeam, SF
    "bay_area_fencing",         # Bay Area Fencing Club
    "redstarfencing",           # RedStar Fencing Club, Chicago
    "fencing_chicago",          # Fencing Center of Chicago
    "lincolnsquarefencing",     # Lincoln Square Fencing, Chicago
    "windycityfencing",         # Windy City Fencing, Chicago
    "alliancefencingacademy",   # Alliance Fencing Academy, Houston (#1 epee)
    "spacecityfencing",         # Space City Fencing, Houston (#1 foil TX)
    "houstonswords",            # Houston Sword Sports
    "dcfencers",                # DC Fencers Club, DC/MD/VA
    "ncfcsaber",                # National Capital Fencers Club, DC
    "nwfencing",                # Northwest Fencing Center, Tigard OR
    "topfencingclub",           # Top Fencing Club, NJ
    "longislandfencersclub",    # Long Island Fencers Club
    "rocklandfencersclub",      # Rockland Fencers Club
    "bluegrassfencersclub",     # Bluegrass Fencers Club
    "saltcityswords",           # Salt City Swords Fencing Club
    "swordplay_la",             # Swordplay LA, Burbank

    # College fencing programs (verified handles)
    "culionsfencing",           # Columbia (16x NCAA champs)
    "harvardfencing",           # Harvard (2024 NCAA champs)
    "princetonfencing",         # Princeton
    "yalefencing",              # Yale
    "pennfencing",              # Penn
    "brownu_fencing",           # Brown
    "cornellfencing",           # Cornell
    "dartmouthfencing",         # Dartmouth
    "notredamefencing",         # Notre Dame
    "pennstatefen",             # Penn State
    "ohiostatefencing",         # Ohio State
    "stanfordfence",            # Stanford
    "dukefen",                  # Duke
    "stjohnsfencing",           # St. John's

    # Olympic/elite athletes & coaches (verified, public figures)
    "fencer",                   # Miles Chamley-Watson, Olympic bronze
    "ibtihajmuhammad",          # Ibtihaj Muhammad, Olympic bronze
    "leetothekiefer",           # Lee Kiefer, 3x Olympic gold
    "gerekmeinhardt",           # Gerek Meinhardt, Olympic medalist
    "a_massialas",              # Alexander Massialas, Olympic silver
    "nick_itkin",               # Nick Itkin, former world #1
    "monicaaksamit",            # Monica Aksamit, Olympic bronze
    "timmorehouse",             # Tim Morehouse, Olympic silver
    "gmassialas",               # Greg Massialas, legendary US coach

    # Fencing media & community (verified handles)
    "insta_fencing",            # Fencing community, ~31K followers
    "betterfencer",             # Better Fencer, educational
    "naileditfencing",          # Nailed It Fencing, content
    "sportfencingphotographyusa",  # Fencing event photographer
    "cyrusofchaos",             # Cyrus of Chaos, fencing content
    "fencing_fie",              # International Fencing Federation

    # National accounts (DM to build visibility, not cold pitch)
    "usafencing",               # USA Fencing official
    "usafencingteam",           # USA Fencing Team
]

# ── 60 varied DM message templates ─────────────────────────────────────────────
# 4 angles × 15 variants each = 60 total
# {booking_link} is replaced at send time

DM_TEMPLATES = [
    # ANGLE 1 — Identity / "you earned this"
    "Hey! We're running the En Garde Portrait Project at USA Fencing Summer Nationals in Portland this July — high-end portraits for competitive fencers. 300 slots. Pre-booking is open at {booking_link} 🤺",
    "Just wanted to reach out — we're doing a curated portrait series at USA Fencing Summer Nationals in Portland. Real studio-quality portraits, not your typical event photo booth. Pre-book at {booking_link}",
    "Hey there! The En Garde Portrait Project is back for Summer Nationals in Portland 🤺 We photograph competitive fencers who've earned a real portrait. Pre-book at {booking_link}",
    "Hi! We're the official portrait photographers at USA Fencing Summer Nationals in Portland this July. Spots are limited — pre-booking open now at {booking_link}",
    "Hey — if you're heading to Portland for Summer Nationals, we're offering pre-booked portrait sessions for competing athletes. Cinematic shots, fast turnaround. {booking_link}",
    "What's up! We're doing elite athlete portraits at USA Fencing Summer Nationals in Portland. These aren't event snapshots — think editorial quality. Pre-book: {booking_link} 🤺",
    "Hey! Quick note — we run the En Garde Portrait Project at USA nationals. If you're competing in Portland, pre-booking locks in a $20 discount off walk-up price. {booking_link}",
    "Hi! We photograph athletes at USA Fencing Nationals and I wanted to reach out personally. Pre-booking for Portland just opened. Limited to 300 athletes. {booking_link}",
    "Hey! If you're going to Summer Nationals in Portland, we're doing a limited portrait series for competing athletes. You train for years — this is the photo that shows it. {booking_link} 🤺",
    "What's up! We're the photographer at USA Fencing Summer Nationals in Portland. We cap at 300 athletes. Pre-book at {booking_link} and lock in before walk-up pricing kicks in.",
    "Hey there — just a heads up, we're running athlete portraits at USA Fencing Summer Nationals in Portland this July. Pre-book and you get priority time slots. {booking_link}",
    "Hi! Wanted to let you know the En Garde Portrait Project is live for Portland. We're one of the few photographers doing real editorial portraits at nationals. {booking_link} 🤺",
    "Hey! We do high-end portraits at USA Fencing events — Summer Nationals in Portland is coming up fast. Pre-book a session: {booking_link}",
    "What's up! Quick message — we're taking pre-bookings for athlete portraits at USA Fencing Summer Nationals. Portland this July. 300 slots. {booking_link} 🤺",
    "Hey — if you compete at Summer Nationals in Portland, the En Garde Portrait Project is pre-booking now. Best portraits from every event we've done: {booking_link}",

    # ANGLE 2 — Scarcity / limited slots
    "Hey! Just a quick message — we run limited portrait sessions at USA Fencing Summer Nationals and Portland slots are filling. 300 athletes max. Pre-book at {booking_link} 🤺",
    "Hi! We cap our portrait sessions at Summer Nationals to 300 athletes so every shoot gets real time. Portland slots are open now at {booking_link}",
    "Hey! Wanted to reach out because Pre-booking for Portland closes before the event. Walk-up slots are $20 more. Lock in your spot at {booking_link} 🤺",
    "What's up! Just a heads up — we do a limited portrait series at USA Fencing Nationals. Portland this July, pre-booking open, walk-ups pay more. {booking_link}",
    "Hey there! We're already at about 1/3 of capacity for Portland pre-bookings. If you're competing, grab a slot at {booking_link} before they fill 🤺",
    "Hi! Pre-booking for the En Garde Portrait Project at Portland Summer Nationals closes about 2 weeks before the event. Secure your slot: {booking_link}",
    "Hey! Just wanted to flag — we do 300 athlete portraits max at USA Fencing nationals. Portland's pre-booking is open at {booking_link}. Walk-up is $20 more.",
    "What's up! Slots are limited for the En Garde Portrait Project at Portland Summer Nationals. Pre-book at {booking_link} and save $20 vs. walk-in 🤺",
    "Hey! We run the portrait project at USA Fencing Nationals and Portland pre-bookings are open. Once the 300 slots fill, it's walk-up only. {booking_link}",
    "Hi there! Just reaching out — we're at Summer Nationals in Portland and limiting portrait sessions to 300 athletes. Pre-book your slot: {booking_link} 🤺",
    "Hey! Quick heads up that pre-booking for Portland athlete portraits closes before the event. Walk-ups are welcome but pay $20 more. {booking_link}",
    "What's up! We photograph competing athletes at USA Fencing Nationals. Portland this July — pre-book at {booking_link} and lock in the lower rate 🤺",
    "Hey there! The En Garde Portrait Project is capped at 300 athletes for Portland. Pre-book to guarantee your time slot and save on price: {booking_link}",
    "Hi! Just a quick reach-out — we do athlete portraits at USA Fencing Nationals. Portland slots are open and filling. {booking_link} 🤺",
    "Hey! We cap at 300 sessions at Summer Nationals so every athlete gets a real shoot, not a 30-second line. Pre-book Portland: {booking_link}",

    # ANGLE 3 — Club / team / group angle
    "Hey! If your club has athletes heading to Portland for Summer Nationals, we offer group pre-booking discounts. Book 5+ athletes and everyone saves. Details: {booking_link} 🤺",
    "Hi! Quick message — we do athlete portraits at USA Fencing Summer Nationals and we have group rates for clubs. Portland this July at {booking_link}",
    "Hey! We run the En Garde Portrait Project at USA nationals. Clubs that book 5+ athletes get 15% off for the group. Portland pre-booking: {booking_link} 🤺",
    "What's up! If you have students or members heading to Portland for Summer Nationals, we have group portrait packages. Send them to {booking_link}",
    "Hey there! We work with fencing clubs at USA nationals — group bookings for Portland are open. 5+ athletes = 15% off each session. {booking_link} 🤺",
    "Hi! Reaching out because we offer club group rates at USA Fencing Summer Nationals. Portland this July. 5+ athletes from same club get a discount: {booking_link}",
    "Hey! We photograph athletes at USA nationals and clubs that bring 5+ members to our booth get a group discount. Portland pre-booking at {booking_link} 🤺",
    "What's up! Quick note on the En Garde Portrait Project — clubs pre-booking for Portland get 15% off for 5+ athletes. Share with your team: {booking_link}",
    "Hey! If your club is sending athletes to Portland for Summer Nationals, group pre-booking gets everyone a discount. Details: {booking_link} 🤺",
    "Hi there! We do athlete portraits at USA Fencing Nationals. Clubs booking 5 or more athletes get 15% off. Portland July 2026: {booking_link}",
    "Hey! Club group bookings are open for Portland Summer Nationals. Share this with your athletes — 5+ from same club saves everyone money: {booking_link} 🤺",
    "What's up! We have group rates at USA Fencing Nationals for clubs. Portland this summer — coaches share with your team: {booking_link}",
    "Hey! Just wanted to reach out — we offer portrait packages for fencing clubs at nationals. Portland group bookings at {booking_link} 🤺",
    "Hi! If your athletes are heading to Portland for Summer Nationals, we have club group rates for portraits. Pass this along: {booking_link}",
    "Hey there! Club pre-booking for the En Garde Portrait Project is open for Portland. Every club member gets a better rate when 5+ book together: {booking_link} 🤺",

    # ANGLE 4 — Value / quality / social proof
    "Hey! We've been photographing fencers at USA Nationals for years and Portland is our biggest event yet. Real studio lighting, real portraits. Pre-book: {booking_link} 🤺",
    "Hi! We do editorial-quality portraits at USA Fencing Summer Nationals — not event snapshots. Portland this July. Pre-book your session: {booking_link}",
    "Hey! Just reaching out — we've photographed hundreds of fencers at nationals and our Portland sessions are now open for pre-booking. {booking_link} 🤺",
    "What's up! We're the portrait photographers at USA Fencing Summer Nationals. We've been doing this for years — the booth in Portland is worth stopping at. Pre-book: {booking_link}",
    "Hey there! If you compete in Portland, come find us at the En Garde Portrait Project booth. Editorial lighting, your weapon, your gear, your portrait. {booking_link} 🤺",
    "Hi! We shoot athletes at USA Fencing nationals and the results speak for themselves. Portland pre-booking at {booking_link} — come see what a real fencing portrait looks like.",
    "Hey! We've been at USA Fencing nationals for years. The portraits we do aren't event photography — they're athlete portraits. Portland: {booking_link} 🤺",
    "What's up! The En Garde Portrait Project is at Portland Summer Nationals this July. We shoot fencers like the elite athletes they are. Pre-book at {booking_link}",
    "Hey! Just wanted to reach out — we photograph competing fencers at USA nationals. These are the portraits athletes actually hang up. Portland: {booking_link} 🤺",
    "Hi there! We've been at USA Fencing Nationals for years. Portland this July — the En Garde Portrait Project. Pre-book at {booking_link} and skip walk-up pricing.",
    "Hey! We do real athlete portraits at USA Fencing Summer Nationals — dramatic lighting, full gear, cinematic quality. Portland pre-booking: {booking_link} 🤺",
    "What's up! Just a heads up we're at USA Fencing Summer Nationals in Portland. We've photographed hundreds of fencers at nationals. Pre-book at {booking_link}",
    "Hey! The En Garde Portrait Project is back at Summer Nationals. We've been doing this long enough that past clients come back every year. Portland: {booking_link} 🤺",
    "Hi! We photograph competitive fencers at USA nationals — not a typical photo booth. Portland this July, pre-booking open: {booking_link}",
    "Hey there! Just reaching out ahead of Portland. We shoot athlete portraits at Summer Nationals every year. 300 slots. Pre-book at {booking_link} 🤺",
]

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        'dmed': [],          # handles already DMed
        'queue': [],         # targets not yet reached
        'total_sent': 0,
        'runs': 0,
        'template_index': 0  # cycles through templates in order, varied
    }

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def get_next_template(state):
    """Rotate through templates and add slight randomness."""
    idx = state.get('template_index', 0)
    template = DM_TEMPLATES[idx % len(DM_TEMPLATES)]
    state['template_index'] = (idx + 1) % len(DM_TEMPLATES)
    return template.replace('{booking_link}', BOOKING_LINK)

def run_fencing_dm():
    if not FENCING_IG_USER or not FENCING_IG_PASS:
        log.error("FENCING_IG_USERNAME and FENCING_IG_PASSWORD env vars required.")
        return

    try:
        from instagrapi import Client
    except ImportError:
        log.error("instagrapi not installed.")
        return

    state = load_state()
    state['runs'] += 1
    now = datetime.now(TIMEZONE)
    log.info(f"[FENCING DM] Run #{state['runs']} — {now.strftime('%Y-%m-%d %H:%M %Z')}")

    # Build queue from targets not yet DMed
    dmed_set = set(state.get('dmed', []))
    queue = [t for t in FENCING_TARGETS if t not in dmed_set]

    if not queue:
        log.info("[FENCING DM] All targets have been DMed. Campaign complete.")
        return

    log.info(f"[FENCING DM] {len(queue)} accounts remaining. Sending {DMS_PER_DAY} today.")

    cl = Client()
    cl.delay_range = [3, 7]

    session_loaded = False

    # Try loading saved session (shared with fencing_social.py)
    if IG_SESSION_ENV:
        try:
            settings = json.loads(IG_SESSION_ENV)
            cl.set_settings(settings)
            cl.login(FENCING_IG_USER, FENCING_IG_PASS)
            log.info(f"[FENCING DM] Resumed session for @{FENCING_IG_USER}")
            session_loaded = True
        except Exception as e:
            log.warning(f"[FENCING DM] Could not resume session from env: {e}")

    if not session_loaded and os.path.exists(SESSION_FILE):
        try:
            cl.load_settings(SESSION_FILE)
            cl.login(FENCING_IG_USER, FENCING_IG_PASS)
            log.info(f"[FENCING DM] Resumed session from file for @{FENCING_IG_USER}")
            session_loaded = True
        except Exception as e:
            log.warning(f"[FENCING DM] Could not resume session from file: {e}")

    if not session_loaded:
        try:
            cl.login(FENCING_IG_USER, FENCING_IG_PASS)
            log.info(f"[FENCING DM] Fresh login as @{FENCING_IG_USER}")
        except Exception as e:
            log.error(f"[FENCING DM] Login failed: {e}")
            return

    # Save session for next run
    try:
        cl.dump_settings(SESSION_FILE)
    except Exception:
        pass

    sent_today = 0
    batch = queue[:DMS_PER_DAY]

    for handle in batch:
        if sent_today >= DMS_PER_DAY:
            break

        message = get_next_template(state)

        try:
            user_id = cl.user_id_from_username(handle)
            cl.direct_send(message, [user_id])
            state['dmed'].append(handle)
            state['total_sent'] += 1
            sent_today += 1
            log.info(f"[FENCING DM] ✉ DM sent to @{handle} ({sent_today}/{DMS_PER_DAY})")

            delay = random.uniform(DM_DELAY_MIN, DM_DELAY_MAX)
            log.info(f"[FENCING DM] Waiting {delay:.0f}s before next DM...")
            time.sleep(delay)

        except Exception as e:
            log.warning(f"[FENCING DM] Could not DM @{handle}: {e}")
            # Still mark as attempted to avoid retrying broken accounts
            state['dmed'].append(handle)

        save_state(state)

    log.info(f"[FENCING DM] Run complete. {sent_today} DMs sent today. {state['total_sent']} total.")

    try:
        cl.logout()
    except Exception:
        pass

if __name__ == '__main__':
    run_fencing_dm()
