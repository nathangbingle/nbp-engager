import os
import json
import base64
import logging
import re
import anthropic
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

QUEUE_FILE = '/tmp/unsub_queue.json'

NBP_LABELS = {
    'client':     'NBP/Clients',
    'lead':       'NBP/Leads',
    'vendor':     'NBP/Vendors',
    'internal':   'NBP/Internal',
    'newsletter': 'NBP/Newsletters',
    'other':      'NBP/Other',
}

def load_queue():
    try:
        with open(QUEUE_FILE) as f:
            return json.load(f)
    except:
        return []

def save_queue(queue):
    with open(QUEUE_FILE, 'w') as f:
        json.dump(queue, f, indent=2)

def get_gmail_service(token_b64: str):
    token_data = json.loads(base64.b64decode(token_b64))
    creds = Credentials.from_authorized_user_info(token_data, [
        'https://www.googleapis.com/auth/gmail.modify'
    ])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build('gmail', 'v1', credentials=creds)

def get_or_create_label(service, name):
    all_labels = service.users().labels().list(userId='me').execute().get('labels', [])
    for lb in all_labels:
        if lb['name'] == name:
            return lb['id']
    result = service.users().labels().create(userId='me', body={
        'name': name,
        'labelListVisibility': 'labelShow',
        'messageListVisibility': 'show'
    }).execute()
    return result['id']

def extract_unsub_link(list_unsub_header: str):
    urls = re.findall(r'<(https?://[^>]+)>', list_unsub_header)
    if urls:
        return urls[0]
    mailto = re.findall(r'<mailto:([^>]+)>', list_unsub_header)
    if mailto:
        return f'mailto:{mailto[0]}'
    return None

def classify_with_claude(sender: str, subject: str, snippet: str) -> str:
    """Use Claude Haiku to classify the email."""
    try:
        client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=20,
            messages=[{
                'role': 'user',
                'content': f"""Classify this email for a school/sports photography business.
From: {sender}
Subject: {subject}
Preview: {snippet[:200]}

Reply with EXACTLY one word: client, lead, vendor, internal, newsletter, or other"""
            }]
        )
        category = msg.content[0].text.strip().lower()
        return category if category in NBP_LABELS else 'other'
    except Exception as e:
        logger.error(f"Claude classify error: {e}")
        return _fallback_classify(sender, subject)

def _fallback_classify(sender: str, subject: str) -> str:
    sender = sender.lower()
    subject = subject.lower()
    if any(s in sender for s in ['noreply', 'no-reply', 'newsletter', 'marketing', 'donotreply', 'notifications@', 'updates@']):
        return 'newsletter'
    if any(s in subject for s in ['unsubscribe', 'newsletter', 'digest', 'weekly', 'monthly update']):
        return 'newsletter'
    if any(s in sender for s in ['nathanbinglephotography', 'airstudio', 'gotphoto']):
        return 'internal'
    if any(s in subject for s in ['invoice', 'receipt', 'payment', 'subscription', 'billing']):
        return 'vendor'
    return 'other'

def process_account(token_b64: str, account_label: str):
    try:
        service = get_gmail_service(token_b64)
        profile = service.users().getProfile(userId='me').execute()
        email_addr = profile.get('emailAddress', account_label)
        logger.info(f"[Inbox] Processing {email_addr}")

        # Ensure labels exist
        label_ids = {}
        for key, name in NBP_LABELS.items():
            label_ids[key] = get_or_create_label(service, name)

        # Fetch inbox messages
        result = service.users().messages().list(
            userId='me', labelIds=['INBOX'], maxResults=50
        ).execute()
        messages = result.get('messages', [])

        queue = load_queue()
        queued_ids = {q['msg_id'] for q in queue}
        processed = archived = queued = 0

        for ref in messages:
            try:
                msg = service.users().messages().get(
                    userId='me', id=ref['id'], format='metadata',
                    metadataHeaders=['From', 'Subject', 'Date', 'List-Unsubscribe']
                ).execute()

                headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
                snippet = msg.get('snippet', '')
                sender  = headers.get('From', '')
                subject = headers.get('Subject', '')
                list_unsub = headers.get('List-Unsubscribe', '')

                # If List-Unsubscribe header present → newsletter
                if list_unsub:
                    category = 'newsletter'
                else:
                    category = classify_with_claude(sender, subject, snippet)

                label_id = label_ids.get(category, label_ids['other'])

                # Apply label + archive (remove from INBOX)
                service.users().messages().modify(
                    userId='me', id=ref['id'],
                    body={'addLabelIds': [label_id], 'removeLabelIds': ['INBOX']}
                ).execute()
                archived += 1

                # Queue newsletter for unsubscribe review
                if category == 'newsletter' and list_unsub and ref['id'] not in queued_ids:
                    unsub_link = extract_unsub_link(list_unsub)
                    if unsub_link:
                        queue.append({
                            'msg_id': ref['id'],
                            'account': email_addr,
                            'sender': sender,
                            'subject': subject,
                            'date': headers.get('Date', ''),
                            'unsub_link': unsub_link,
                            'status': 'pending',
                            'added': datetime.utcnow().isoformat()
                        })
                        queued_ids.add(ref['id'])
                        queued += 1

                processed += 1

            except Exception as e:
                logger.error(f"  Error on msg {ref['id']}: {e}")

        save_queue(queue)
        logger.info(f"[Inbox] {email_addr}: {processed} processed, {archived} archived, {queued} queued for unsubscribe")

    except Exception as e:
        logger.error(f"[Inbox] Fatal error on {account_label}: {e}")

def run_inbox_agent():
    logger.info("====== NBP Inbox Agent ======")

    # Support GMAIL_TOKEN_1, GMAIL_TOKEN_2, ... for multiple accounts
    found = False
    for i in range(1, 10):
        token = os.getenv(f'GMAIL_TOKEN_{i}')
        if not token:
            break
        process_account(token, f'account_{i}')
        found = True

    # Fallback: single GMAIL_TOKEN
    if not found:
        token = os.getenv('GMAIL_TOKEN')
        if token:
            process_account(token, 'primary')
        else:
            logger.warning("[Inbox] No GMAIL_TOKEN env vars found — skipping")

    logger.info("====== Inbox Agent Done ======")
