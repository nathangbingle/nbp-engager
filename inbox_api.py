import os
import json
import logging
import requests as http_requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

QUEUE_FILE = '/tmp/unsub_queue.json'
logger = logging.getLogger(__name__)

def load_queue():
    try:
        with open(QUEUE_FILE) as f:
            return json.load(f)
    except:
        return []

def save_queue(q):
    with open(QUEUE_FILE, 'w') as f:
        json.dump(q, f, indent=2)

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.utcnow().isoformat()})

@app.route('/api/queue')
def get_queue():
    queue = load_queue()
    status_filter = request.args.get('status', 'pending')
    if status_filter != 'all':
        queue = [q for q in queue if q.get('status') == status_filter]
    return jsonify(queue)

@app.route('/api/stats')
def get_stats():
    queue = load_queue()
    stats = {'pending': 0, 'unsubscribed': 0, 'skipped': 0, 'error': 0, 'total': len(queue)}
    for item in queue:
        s = item.get('status', 'pending')
        if s in stats:
            stats[s] += 1
    return jsonify(stats)

@app.route('/api/unsubscribe', methods=['POST'])
def unsubscribe():
    data = request.json or {}
    msg_ids = set(data.get('msg_ids', []))
    queue = load_queue()
    results = []

    for item in queue:
        if item['msg_id'] not in msg_ids or item['status'] != 'pending':
            continue
        link = item.get('unsub_link', '')
        try:
            if link.startswith('http'):
                resp = http_requests.get(link, timeout=15, allow_redirects=True,
                    headers={'User-Agent': 'Mozilla/5.0'})
                item['status'] = 'unsubscribed'
                item['unsub_at'] = datetime.utcnow().isoformat()
                results.append({'id': item['msg_id'], 'success': True, 'code': resp.status_code})
            elif link.startswith('mailto:'):
                # Flag for manual action — auto-mailto not supported
                item['status'] = 'mailto_pending'
                results.append({'id': item['msg_id'], 'success': True, 'note': 'mailto — open manually'})
            else:
                item['status'] = 'error'
                results.append({'id': item['msg_id'], 'success': False, 'error': 'Unknown link format'})
        except Exception as e:
            item['status'] = 'error'
            item['error'] = str(e)
            results.append({'id': item['msg_id'], 'success': False, 'error': str(e)})

    save_queue(queue)
    return jsonify({'results': results})

@app.route('/api/skip', methods=['POST'])
def skip():
    data = request.json or {}
    msg_ids = set(data.get('msg_ids', []))
    queue = load_queue()
    for item in queue:
        if item['msg_id'] in msg_ids and item['status'] == 'pending':
            item['status'] = 'skipped'
    save_queue(queue)
    return jsonify({'ok': True})

@app.route('/api/clear', methods=['POST'])
def clear_processed():
    """Remove completed/skipped items older than 7 days."""
    queue = load_queue()
    now = datetime.utcnow()
    kept = []
    for item in queue:
        if item.get('status') == 'pending':
            kept.append(item)
        else:
            # Keep recent completed items for display
            added = item.get('unsub_at') or item.get('added', '')
            try:
                age = (now - datetime.fromisoformat(added)).days
                if age < 7:
                    kept.append(item)
            except:
                pass
    save_queue(kept)
    return jsonify({'removed': len(queue) - len(kept)})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
