"""
NBP Fencing Social Agent — @nathanbinglefencing
- Posts 3x daily: 9am, 12pm, 3pm ET
- Alternates between PHOTO posts (portrait + descriptive caption)
  and HYPE posts (portrait + Portland countdown/scarcity caption)
- Pulls images from Google Drive folder, moves to _posted after use
- Posts directly via instagrapi (no Publer required)
"""

import os, io, json, time, base64, logging, tempfile, random
from datetime import datetime, date
from zoneinfo import ZoneInfo
import requests
from PIL import Image
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('fencing-social')

TIMEZONE = ZoneInfo('America/New_York')

# ── Config ─────────────────────────────────────────────────────────────────────
FENCING_IG_USER    = os.getenv('FENCING_IG_USERNAME', '')
FENCING_IG_PASS    = os.getenv('FENCING_IG_PASSWORD', '')
ANTHROPIC_API_KEY  = os.getenv('ANTHROPIC_API_KEY', '')
DRIVE_FOLDER_ID    = os.getenv('FENCING_DRIVE_FOLDER_ID', '1D6kThv7SWr6vwSUFqRWyyMUtcQStjjBv')
OAUTH_CREDS_JSON   = os.getenv('GDRIVE_OAUTH_CREDENTIALS', '')
TOKEN_JSON         = os.getenv('GDRIVE_TOKEN', '')

SCOPES             = ['https://www.googleapis.com/auth/drive']
POSTED_FOLDER_NAME = '_posted'
IMAGE_MIME_TYPES   = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
ANTHROPIC_BASE     = 'https://api.anthropic.com/v1'

EVENT_DATE         = date(2026, 7, 1)  # USA Fencing Summer Nationals Portland
BOOKING_LINK       = os.getenv('FENCING_BOOKING_LINK', 'nathanbinglephotography.com/fencing')
TOTAL_SLOTS        = 300

STATE_FILE = 'fencing_social_state.json'
SESSION_FILE = 'fencing_ig_session.json'
IG_SESSION_ENV = os.getenv('FENCING_IG_SESSION', '')  # persisted session JSON

# ── State ──────────────────────────────────────────────────────────────────────

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        'next_post_type': 'photo',   # alternates: 'photo' | 'hype'
        'total_posts': 0,
        'slots_claimed': 127,        # starts at 127, increments for scarcity
        'last_run_key': None
    }

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

# ── Google Drive ────────────────────────────────────────────────────────────────

def get_drive_service():
    creds = None
    if TOKEN_JSON:
        try:
            creds = Credentials.from_authorized_user_info(json.loads(TOKEN_JSON), SCOPES)
        except Exception as e:
            log.warning(f'Could not parse GDRIVE_TOKEN: {e}')
    if os.path.exists('token.json') and not creds:
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        log.info('Drive token refreshed.')
    if not creds or not creds.valid:
        log.error('No valid Drive credentials. Set GDRIVE_TOKEN env var.')
        return None
    return build('drive', 'v3', credentials=creds, cache_discovery=False)

def get_or_create_folder(svc, parent_id, name):
    q = (f"'{parent_id}' in parents and name='{name}' "
         f"and mimeType='application/vnd.google-apps.folder' and trashed=false")
    res = svc.files().list(q=q, fields='files(id)').execute()
    files = res.get('files', [])
    if files:
        return files[0]['id']
    folder = svc.files().create(
        body={'name': name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]},
        fields='id'
    ).execute()
    log.info(f"Created Drive folder '{name}'")
    return folder['id']

def list_images(svc, folder_id):
    mime_q = ' or '.join(f"mimeType='{m}'" for m in IMAGE_MIME_TYPES)
    q = f"'{folder_id}' in parents and ({mime_q}) and trashed=false"
    res = svc.files().list(q=q, fields='files(id,name,mimeType)', orderBy='name').execute()
    return res.get('files', [])

def download_image(svc, file_id):
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.seek(0)
    return buf

def move_to_posted(svc, file_id, posted_folder_id):
    file = svc.files().get(fileId=file_id, fields='parents').execute()
    svc.files().update(
        fileId=file_id,
        addParents=posted_folder_id,
        removeParents=','.join(file.get('parents', [])),
        fields='id, parents'
    ).execute()
    log.info(f'Moved {file_id} to _posted')

def prepare_image(buf, mime_type, max_bytes=8_000_000, max_px=7900):
    data = buf.read()
    img = Image.open(io.BytesIO(data)).convert('RGB')
    w, h = img.size
    if max(w, h) > max_px:
        scale = max_px / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    out, quality = io.BytesIO(), 90
    while quality >= 40:
        out.seek(0); out.truncate()
        img.save(out, format='JPEG', quality=quality)
        if out.tell() <= max_bytes:
            break
        quality -= 10
    return out.getvalue(), 'image/jpeg'

def make_square(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    out = io.BytesIO()
    img.save(out, format='JPEG', quality=92)
    return out.getvalue()

# ── Caption generation ──────────────────────────────────────────────────────────

PHOTO_SYSTEM_PROMPT = """You write Instagram captions for @nathanbinglefencing — the official portrait photography account for USA Fencing Summer Nationals.

CAMPAIGN: The En Garde Portrait Project — elite athlete portraits at the nation's largest fencing event. Portland, Oregon. July 2026. 300 slots.

VOICE: Direct. Confident. Identity-driven. The athlete earned this portrait. Not commercial, not salesy — make them feel it.

BANNED WORDS: passion, love capturing, memories, timeless, stunning, breathtaking, cherish, elevate, showcase, journey, thrilled, excited to share, making memories, so proud.

WRITE:
- Hook line first — make a fencer stop scrolling
- 2-3 tight sentences about the athlete and the portrait
- One line about Portland pre-booking (soft, not pushy)
- 12-15 hashtags including: #EnGardePortraitProject #USAFencing #FencingPortland2026 #NathanBinglePhotography #FencingPortrait #FencingPhotography #EliteFencer #SummerNationals2026 plus weapon/style specific tags

OUTPUT: Only the caption text including hashtags. No JSON. No preamble."""

HYPE_SYSTEM_PROMPT = """You write Instagram hype posts for @nathanbinglefencing — the official portrait account for USA Fencing Summer Nationals 2026 in Portland.

CAMPAIGN: The En Garde Portrait Project. 300 slots. Pre-book at {booking_link}. Event: July 1-6, 2026, Portland Oregon.

TODAY: {today}. Days until Portland: {days_out}. Slots claimed (approximate): {slots_claimed} of 300.

POST TYPES — rotate through these:
- COUNTDOWN: days out, urgency building, slots filling
- SCARCITY: X of 300 slots claimed, pre-book before they fill
- IDENTITY: you've trained for years, this is your portrait, fencers as warriors
- EVENT HYPE: Portland is going to be electric, 6000 fencers, one summer
- PREBOOK VALUE: pre-book saves $20 vs walk-up, priority time slots

VOICE: Punchy. Athlete-to-athlete energy. Make them feel the event coming.

BANNED: passion, love capturing, memories, timeless, stunning, cherish, elevate, journey.

WRITE:
- Strong hook — one line
- 2-3 sentences of hype content
- Clear CTA with booking link
- 12-15 hashtags: #EnGardePortraitProject #USAFencing #FencingPortland2026 #SummerNationals2026 #FencingNationals #USAFencingNationals #FencingPhotography #NathanBinglePhotography #FencingPortrait #EliteFencer plus relevant tags

OUTPUT: Only the caption text including hashtags. No JSON. No preamble."""

def generate_photo_caption(image_bytes, mime_type, filename):
    payload = {
        'model': 'claude-sonnet-4-20250514',
        'max_tokens': 600,
        'system': PHOTO_SYSTEM_PROMPT,
        'messages': [{'role': 'user', 'content': [
            {'type': 'image', 'source': {
                'type': 'base64',
                'media_type': mime_type,
                'data': base64.standard_b64encode(image_bytes).decode()
            }},
            {'type': 'text', 'text': f'Write an Instagram caption for this fencing portrait. File: {filename}'}
        ]}]
    }
    headers = {
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json'
    }
    resp = requests.post(f'{ANTHROPIC_BASE}/messages', json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()['content'][0]['text'].strip()

def generate_hype_caption(image_bytes, mime_type, slots_claimed):
    today = date.today()
    days_out = (EVENT_DATE - today).days

    system = HYPE_SYSTEM_PROMPT.format(
        booking_link=BOOKING_LINK,
        today=today.strftime('%B %d, %Y'),
        days_out=days_out,
        slots_claimed=slots_claimed
    )
    payload = {
        'model': 'claude-sonnet-4-20250514',
        'max_tokens': 600,
        'system': system,
        'messages': [{'role': 'user', 'content': [
            {'type': 'image', 'source': {
                'type': 'base64',
                'media_type': mime_type,
                'data': base64.standard_b64encode(image_bytes).decode()
            }},
            {'type': 'text', 'text': 'Write a hype/countdown Instagram caption for this fencing portrait.'}
        ]}]
    }
    headers = {
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json'
    }
    resp = requests.post(f'{ANTHROPIC_BASE}/messages', json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()['content'][0]['text'].strip()

# ── Instagram posting ───────────────────────────────────────────────────────────

def get_ig_client():
    """Create an instagrapi Client with session persistence.

    Tries to reuse a saved session to avoid fresh logins (which Instagram
    rate-limits/challenges). Session is loaded from FENCING_IG_SESSION env
    var first, then from a local file as fallback.
    """
    try:
        from instagrapi import Client
    except ImportError:
        log.error('instagrapi not installed.')
        return None

    cl = Client()
    cl.delay_range = [2, 5]

    session_loaded = False

    # Try loading session from env var (survives Railway redeploys)
    if IG_SESSION_ENV:
        try:
            settings = json.loads(IG_SESSION_ENV)
            cl.set_settings(settings)
            cl.login(FENCING_IG_USER, FENCING_IG_PASS)
            log.info(f'Resumed session for @{FENCING_IG_USER}')
            session_loaded = True
        except Exception as e:
            log.warning(f'Could not resume session from env: {e}')

    # Try loading session from local file
    if not session_loaded and os.path.exists(SESSION_FILE):
        try:
            cl.load_settings(SESSION_FILE)
            cl.login(FENCING_IG_USER, FENCING_IG_PASS)
            log.info(f'Resumed session from file for @{FENCING_IG_USER}')
            session_loaded = True
        except Exception as e:
            log.warning(f'Could not resume session from file: {e}')

    # Fresh login as last resort
    if not session_loaded:
        try:
            cl.login(FENCING_IG_USER, FENCING_IG_PASS)
            log.info(f'Fresh login as @{FENCING_IG_USER}')
        except Exception as e:
            log.error(f'Instagram login failed: {e}')
            return None

    # Save session for next run
    try:
        cl.dump_settings(SESSION_FILE)
        log.info('Session saved to file.')
    except Exception as e:
        log.warning(f'Could not save session file: {e}')

    return cl


def post_to_instagram(image_bytes, caption):
    cl = get_ig_client()
    if not cl:
        return False

    # Save image to temp file (instagrapi needs a file path)
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        cl.photo_upload(tmp_path, caption=caption)
        log.info('Photo posted to Instagram')
        return True
    except Exception as e:
        log.error(f'Instagram post failed: {e}')
        return False
    finally:
        os.unlink(tmp_path)

# ── Main job ────────────────────────────────────────────────────────────────────

def run_fencing_social():
    if not FENCING_IG_USER or not FENCING_IG_PASS:
        log.error('[FENCING SOCIAL] FENCING_IG_USERNAME/PASSWORD not set.')
        return

    state = load_state()
    post_type = state.get('next_post_type', 'photo')
    slots = state.get('slots_claimed', 127)

    log.info(f'[FENCING SOCIAL] Running — post type: {post_type}, slots claimed: {slots}')

    svc = get_drive_service()
    if not svc:
        log.error('[FENCING SOCIAL] No Drive service available.')
        return

    posted_id = get_or_create_folder(svc, DRIVE_FOLDER_ID, POSTED_FOLDER_NAME)
    images = list_images(svc, DRIVE_FOLDER_ID)

    if not images:
        log.warning('[FENCING SOCIAL] No images in Drive folder — skipping.')
        return

    f = images[0]
    log.info(f"[FENCING SOCIAL] Using image: {f['name']}")

    buf = download_image(svc, f['id'])
    img_bytes, mime = prepare_image(buf, f['mimeType'])
    square_bytes = make_square(img_bytes)

    # Generate caption based on post type
    if post_type == 'photo':
        log.info('[FENCING SOCIAL] Generating PHOTO caption...')
        caption = generate_photo_caption(img_bytes, mime, f['name'])
    else:
        log.info('[FENCING SOCIAL] Generating HYPE caption...')
        caption = generate_hype_caption(img_bytes, mime, slots)
        # Increment slots claimed slightly for scarcity realism
        state['slots_claimed'] = min(slots + random.randint(1, 4), 290)

    log.info(f'[FENCING SOCIAL] Caption preview: {caption[:100]}...')

    success = post_to_instagram(square_bytes, caption)

    if success:
        move_to_posted(svc, f['id'], posted_id)
        state['total_posts'] = state.get('total_posts', 0) + 1
        # Flip post type for next run
        state['next_post_type'] = 'hype' if post_type == 'photo' else 'photo'
        log.info(f"[FENCING SOCIAL] Done. Next post type: {state['next_post_type']}")
    else:
        log.error('[FENCING SOCIAL] Post failed — will retry next scheduled run.')

    save_state(state)

# ── Scheduler entry point ───────────────────────────────────────────────────────

def start_fencing_social_scheduler():
    """Called from scheduler.py — runs at 9am, 12pm, 3pm ET."""
    run_fencing_social()

def dry_run():
    """Generate image + caption and display without posting to Instagram."""
    log.info('[DRY RUN] Generating post preview...')

    state = load_state()
    post_type = state.get('next_post_type', 'photo')
    slots = state.get('slots_claimed', 127)

    log.info(f'[DRY RUN] Post type: {post_type}, slots claimed: {slots}')

    svc = get_drive_service()
    if not svc:
        log.error('[DRY RUN] No Drive service.')
        return

    images = list_images(svc, DRIVE_FOLDER_ID)
    if not images:
        log.warning('[DRY RUN] No images in Drive folder.')
        return

    f = images[0]
    log.info(f"[DRY RUN] Image: {f['name']}")

    buf = download_image(svc, f['id'])
    img_bytes, mime = prepare_image(buf, f['mimeType'])
    square_bytes = make_square(img_bytes)

    if post_type == 'photo':
        caption = generate_photo_caption(img_bytes, mime, f['name'])
    else:
        caption = generate_hype_caption(img_bytes, mime, slots)

    # Save preview image locally
    preview_path = 'preview_post.jpg'
    with open(preview_path, 'wb') as pf:
        pf.write(square_bytes)

    print('\n' + '=' * 60)
    print(f'POST TYPE: {post_type.upper()}')
    print(f'IMAGE: {f["name"]}')
    print(f'PREVIEW SAVED: {preview_path}')
    print('=' * 60)
    print(f'\nCAPTION:\n{caption}')
    print('\n' + '=' * 60)
    print('(Not posted — dry run only)')


if __name__ == '__main__':
    import sys
    if '--dry-run' in sys.argv:
        dry_run()
    else:
        run_fencing_social()
