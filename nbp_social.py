"""
NBP Social Agent — @nathanbinglephotography
- Posts 3x daily: 10am, 1pm, 4pm ET (offset from fencing schedule)
- AI-generated captions tailored to: family portraits, weddings, branding
- Pulls images from Google Drive folder, moves to _posted after use
- Posts directly via instagrapi
"""

import os, io, json, time, base64, logging, tempfile, random
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from PIL import Image
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('nbp-social')

TIMEZONE = ZoneInfo('America/New_York')

# ── Config ─────────────────────────────────────────────────────────────────────
NBP_IG_USER        = os.getenv('NBP_IG_USERNAME', '')
NBP_IG_PASS        = os.getenv('NBP_IG_PASSWORD', '')
ANTHROPIC_API_KEY  = os.getenv('ANTHROPIC_API_KEY', '')
NBP_DRIVE_FOLDER   = os.getenv('NBP_DRIVE_FOLDER_ID', '')
OAUTH_CREDS_JSON   = os.getenv('GDRIVE_OAUTH_CREDENTIALS', '')
TOKEN_JSON         = os.getenv('GDRIVE_TOKEN', '')

SCOPES             = ['https://www.googleapis.com/auth/drive']
POSTED_FOLDER_NAME = '_posted'
IMAGE_MIME_TYPES   = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
ANTHROPIC_BASE     = 'https://api.anthropic.com/v1'

BOOKING_LINK       = os.getenv('NBP_BOOKING_LINK', 'https://www.nathanbinglephotography.com')

STATE_FILE  = 'nbp_social_state.json'
SESSION_FILE = 'nbp_ig_session.json'
IG_SESSION_ENV = os.getenv('NBP_IG_SESSION', '')

# ── State ──────────────────────────────────────────────────────────────────────

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        'total_posts': 0,
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

CAPTION_SYSTEM_PROMPT = """You write Instagram captions for @nathanbinglephotography — a Charlotte-area photographer. Family portraits, weddings, branding.

VOICE: Minimal. Dry. Cool. Think photographer's notebook, not marketing copy. 1-2 sentences max before hashtags. Say less. Let the photo do the work.

GOOD EXAMPLES:
- "Golden hour at the lake. The Johnsons."
- "Second dance was better than the first."
- "New headshots for @studio. Shot on location downtown."
- "Fall sessions are open. Link in bio."
- "She said yes. He cried first."

BAD EXAMPLES (never write like this):
- "So honored to capture this beautiful family's special day!"
- "There's nothing quite like the magic of golden hour with people you love."
- "When love is in the air and the light is just right, everything falls into place."

ABSOLUTELY BANNED: passion, love capturing, memories, timeless, stunning, breathtaking, cherish, elevate, showcase, journey, thrilled, excited, proud, dream, magic, blessed, honored, humbled, special, beautiful moment, picture-perfect, so much fun, amazing, incredible. Also banned: rhetorical questions, exclamation marks (use sparingly — max 0-1 per caption), emoji overuse (0-2 max).

ANALYZE THE IMAGE to determine session type and reference one specific detail you actually see.

WRITE:
- 1-2 short sentences. That's it. Maybe 3 if one is very short.
- No fluff. No filler. No feelings monologue.
- If there's a booking CTA, make it dead simple: "Fall sessions open." or "Link in bio."
- 8-12 hashtags. Always include #NathanBinglePhotography #CharlottePhotographer. Rotate through surrounding area tags each post: #FortMillPhotographer #RockHillPhotographer #IndianLandPhotographer #LakeNormanPhotographer #MooresvillePhotographer #HuntersvillePhotographer #CorneliusPhotographer #DavidsonPhotographer #WaxhawPhotographer #MatthewsPhotographer #MintHillPhotographer #BallantynepPhotographer #SouthCharlotte #LakeWyliePhotographer. Include 2-3 area tags per post plus session-type tags.

OUTPUT: Only the caption text including hashtags. No JSON. No preamble."""

def generate_caption(image_bytes, mime_type, filename):
    payload = {
        'model': 'claude-sonnet-4-20250514',
        'max_tokens': 600,
        'system': CAPTION_SYSTEM_PROMPT,
        'messages': [{'role': 'user', 'content': [
            {'type': 'image', 'source': {
                'type': 'base64',
                'media_type': mime_type,
                'data': base64.standard_b64encode(image_bytes).decode()
            }},
            {'type': 'text', 'text': f'Write an Instagram caption for this photo. File: {filename}'}
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
    try:
        from instagrapi import Client
    except ImportError:
        log.error('instagrapi not installed.')
        return None

    cl = Client()
    cl.delay_range = [2, 5]

    session_loaded = False

    if IG_SESSION_ENV:
        try:
            settings = json.loads(IG_SESSION_ENV)
            cl.set_settings(settings)
            cl.login(NBP_IG_USER, NBP_IG_PASS)
            log.info(f'Resumed session for @{NBP_IG_USER}')
            session_loaded = True
        except Exception as e:
            log.warning(f'Could not resume session from env: {e}')

    if not session_loaded and os.path.exists(SESSION_FILE):
        try:
            cl.load_settings(SESSION_FILE)
            cl.login(NBP_IG_USER, NBP_IG_PASS)
            log.info(f'Resumed session from file for @{NBP_IG_USER}')
            session_loaded = True
        except Exception as e:
            log.warning(f'Could not resume session from file: {e}')

    if not session_loaded:
        try:
            cl.login(NBP_IG_USER, NBP_IG_PASS)
            log.info(f'Fresh login as @{NBP_IG_USER}')
        except Exception as e:
            log.error(f'Instagram login failed: {e}')
            return None

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

def run_nbp_social():
    if not NBP_IG_USER or not NBP_IG_PASS:
        log.error('[NBP SOCIAL] NBP_IG_USERNAME/PASSWORD not set.')
        return

    if not NBP_DRIVE_FOLDER:
        log.error('[NBP SOCIAL] NBP_DRIVE_FOLDER_ID not set.')
        return

    state = load_state()

    log.info(f'[NBP SOCIAL] Running — total posts so far: {state.get("total_posts", 0)}')

    svc = get_drive_service()
    if not svc:
        log.error('[NBP SOCIAL] No Drive service available.')
        return

    posted_id = get_or_create_folder(svc, NBP_DRIVE_FOLDER, POSTED_FOLDER_NAME)
    images = list_images(svc, NBP_DRIVE_FOLDER)

    if not images:
        log.warning('[NBP SOCIAL] No images in Drive folder — skipping.')
        return

    f = images[0]
    log.info(f"[NBP SOCIAL] Using image: {f['name']}")

    buf = download_image(svc, f['id'])
    img_bytes, mime = prepare_image(buf, f['mimeType'])
    square_bytes = make_square(img_bytes)

    log.info('[NBP SOCIAL] Generating caption...')
    caption = generate_caption(img_bytes, mime, f['name'])
    log.info(f'[NBP SOCIAL] Caption preview: {caption[:100]}...')

    success = post_to_instagram(square_bytes, caption)

    if success:
        move_to_posted(svc, f['id'], posted_id)
        state['total_posts'] = state.get('total_posts', 0) + 1
        log.info(f"[NBP SOCIAL] Done. Total posts: {state['total_posts']}")
    else:
        log.error('[NBP SOCIAL] Post failed — will retry next scheduled run.')

    save_state(state)

# ── Dry run ────────────────────────────────────────────────────────────────────

def dry_run():
    log.info('[DRY RUN] Generating post preview...')

    if not NBP_DRIVE_FOLDER:
        log.error('[DRY RUN] NBP_DRIVE_FOLDER_ID not set.')
        return

    svc = get_drive_service()
    if not svc:
        log.error('[DRY RUN] No Drive service.')
        return

    images = list_images(svc, NBP_DRIVE_FOLDER)
    if not images:
        log.warning('[DRY RUN] No images in Drive folder.')
        return

    f = images[0]
    log.info(f"[DRY RUN] Image: {f['name']}")

    buf = download_image(svc, f['id'])
    img_bytes, mime = prepare_image(buf, f['mimeType'])
    square_bytes = make_square(img_bytes)

    caption = generate_caption(img_bytes, mime, f['name'])

    preview_path = 'nbp_preview_post.jpg'
    with open(preview_path, 'wb') as pf:
        pf.write(square_bytes)

    print('\n' + '=' * 60)
    print('NBP SOCIAL — POST PREVIEW')
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
        run_nbp_social()
