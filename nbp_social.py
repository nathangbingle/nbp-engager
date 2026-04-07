"""
NBP Social Agent — @nathanbinglephotography
- Posts 3x daily: 10am, 1pm, 4pm ET (offset from fencing schedule)
- AI-generated captions tailored to: family portraits, weddings, branding
- Pulls images from Google Drive folder, moves to _posted after use
- Posts via Publer API (no direct IG login needed)
"""

import os, io, json, base64, logging
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
PUBLER_API_KEY     = os.getenv('NBP_PUBLER_API_KEY', '')
ANTHROPIC_API_KEY  = os.getenv('ANTHROPIC_API_KEY', '')
NBP_DRIVE_FOLDER   = os.getenv('NBP_DRIVE_FOLDER_ID', '')
OAUTH_CREDS_JSON   = os.getenv('GDRIVE_OAUTH_CREDENTIALS', '')
TOKEN_JSON         = os.getenv('GDRIVE_TOKEN', '')

# Target account name in Publer — used to filter which account to post to
NBP_PUBLER_ACCOUNT = os.getenv('NBP_PUBLER_ACCOUNT_NAME', 'nathanbinglephotography')

SCOPES             = ['https://www.googleapis.com/auth/drive']
POSTED_FOLDER_NAME = '_posted'
IMAGE_MIME_TYPES   = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
ANTHROPIC_BASE     = 'https://api.anthropic.com/v1'
PUBLER_BASE        = 'https://app.publer.com/api/v1'

STATE_FILE = 'nbp_social_state.json'

# ── State ──────────────────────────────────────────────────────────────────────

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {'total_posts': 0, 'last_run_key': None}

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

def prepare_image(buf, mime_type, max_bytes=2_000_000):
    data = buf.read()
    if len(data) <= max_bytes:
        return data, mime_type
    img = Image.open(io.BytesIO(data)).convert('RGB')
    out, quality = io.BytesIO(), 85
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
    if w == h:
        return image_bytes
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    out = io.BytesIO()
    img.save(out, format='JPEG', quality=90)
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

# ── Publer ─────────────────────────────────────────────────────────────────────

def get_publer_headers():
    return {'Authorization': f'Bearer-API {PUBLER_API_KEY}', 'Content-Type': 'application/json'}

def get_publer_workspace():
    resp = requests.get(f'{PUBLER_BASE}/workspaces', headers=get_publer_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    workspaces = data if isinstance(data, list) else data.get('workspaces', [data])
    wid = workspaces[0].get('id') or workspaces[0].get('_id')
    log.info(f'Publer workspace: {wid}')
    return wid

def get_publer_ig_account(workspace_id):
    """Find the Instagram account in Publer matching NBP_PUBLER_ACCOUNT_NAME."""
    headers = get_publer_headers()
    headers['Publer-Workspace-Id'] = workspace_id
    resp = requests.get(f'{PUBLER_BASE}/accounts', headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    accounts = data if isinstance(data, list) else data.get('accounts', [])
    log.info(f'Publer accounts: {[a.get("name","?") for a in accounts]}')

    # Find the matching IG account
    target = NBP_PUBLER_ACCOUNT.lower()
    for a in accounts:
        name = (a.get('name') or '').lower()
        platform = (a.get('type') or a.get('platform') or '').lower()
        if target in name and ('ig' in platform or 'instagram' in platform):
            account_id = a.get('id') or a.get('_id')
            log.info(f'Matched Publer IG account: {a.get("name")} (id={account_id})')
            return a

    # Fallback: just find any IG account with matching name
    for a in accounts:
        name = (a.get('name') or '').lower()
        if target in name:
            account_id = a.get('id') or a.get('_id')
            log.info(f'Matched Publer account (fallback): {a.get("name")} (id={account_id})')
            return a

    log.error(f'No Publer account matching "{NBP_PUBLER_ACCOUNT}" found.')
    return None

def upload_media_to_publer(image_bytes, filename, mime_type, workspace_id):
    headers = {'Authorization': f'Bearer-API {PUBLER_API_KEY}', 'Publer-Workspace-Id': workspace_id}
    files = {'file': (filename, image_bytes, mime_type)}
    resp = requests.post(f'{PUBLER_BASE}/media', headers=headers, files=files, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    media_id = data.get('id') or data.get('_id') or data.get('media_id')
    log.info(f'Uploaded media to Publer: {media_id}')
    return media_id

def post_via_publer(account, caption, image_bytes, filename, workspace_id):
    """Post a square image to Instagram via Publer."""
    square_bytes = make_square(image_bytes)
    media_id = upload_media_to_publer(square_bytes, filename, 'image/jpeg', workspace_id)

    account_id = account.get('id') or account.get('_id')
    headers = get_publer_headers()
    headers['Publer-Workspace-Id'] = workspace_id

    payload = {'bulk': {'state': 'published', 'posts': [{
        'networks': {'instagram': {
            'type': 'photo',
            'text': caption,
            'media': [{'id': media_id, 'type': 'image'}]
        }},
        'accounts': [{'id': account_id}]
    }]}}

    resp = requests.post(f'{PUBLER_BASE}/posts/schedule/publish', headers=headers, json=payload, timeout=30)
    if resp.ok:
        log.info(f'Posted to {account.get("name")} via Publer')
        return True
    else:
        log.error(f'Publer post failed: {resp.status_code} {resp.text}')
        return False

# ── Main job ────────────────────────────────────────────────────────────────────

def run_nbp_social():
    if not PUBLER_API_KEY:
        log.error('[NBP SOCIAL] NBP_PUBLER_API_KEY not set.')
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

    # Set up Publer
    workspace_id = get_publer_workspace()
    account = get_publer_ig_account(workspace_id)
    if not account:
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

    log.info('[NBP SOCIAL] Generating caption...')
    caption = generate_caption(img_bytes, mime, f['name'])
    log.info(f'[NBP SOCIAL] Caption preview: {caption[:100]}...')

    success = post_via_publer(account, caption, img_bytes, f['name'], workspace_id)

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
