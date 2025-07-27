import json
import time
import threading
import requests
from flask import Flask, request, jsonify
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

ACCOUNTS_FILE = 'accs.txt'  # { "uid": "password", ... }

accounts_lock = threading.Lock()
jwt_lock = threading.Lock()

accounts = {}               # أحدث حسابات (uid -> password)
jwt_tokens_current = {}     # تُستخدم الآن من الراوت
last_refresh_at = 0

def load_accounts(path=ACCOUNTS_FILE):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[ERROR] load_accounts: {e}")
        return {}

def get_jwt_token(uid, password):
    url = f"https://jwt-gen-api-v2.onrender.com/token?uid={uid}&password={password}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get('status') in ('success', 'live'):
                return data.get('token')
    except Exception as e:
        print(f"[ERROR] get_jwt_token({uid}): {e}")
    return None

def initial_refresh():
    global accounts, jwt_tokens_current, last_refresh_at
    accs = load_accounts()
    new_tokens = {}
    for uid, pwd in accs.items():
        tok = get_jwt_token(uid, pwd)
        if tok:
            new_tokens[uid] = tok

    with accounts_lock:
        accounts = accs
    with jwt_lock:
        jwt_tokens_current = new_tokens
        last_refresh_at = time.time()

    print(f"[INFO] initial_refresh: loaded {len(jwt_tokens_current)} tokens")

def refresh_tokens_background(interval_seconds=3600):
    global accounts, jwt_tokens_current, last_refresh_at
    while True:
        try:
            print("[INFO] background refresh started")
            accs = load_accounts()

            # نبني التوكنات الجديدة في Buffer منفصل
            new_tokens = {}
            for uid, pwd in accs.items():
                tok = get_jwt_token(uid, pwd)
                if tok:
                    new_tokens[uid] = tok

            # سواتش ذري: لا نمس jwt_tokens_current حتى ننتهي
            with accounts_lock:
                accounts = accs
            with jwt_lock:
                if new_tokens:  # لا نستبدل إلا لو عندنا توكنات صالحة
                    jwt_tokens_current.clear()
                    jwt_tokens_current.update(new_tokens)
                    last_refresh_at = time.time()

            print(f"[INFO] background refresh done - active tokens: {len(jwt_tokens_current)}")
        except Exception as e:
            print(f"[ERROR] refresh_tokens_background: {e}")

        time.sleep(interval_seconds)

def FOX_RequestAddingFriend(token, target_id):
    url = "https://arifi-like-token.vercel.app/like"
    params = {"token": token, "id": target_id}
    headers = {
        "Accept": "*/*",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Free Fire/2019117061 CFNetwork/1399 Darwin/22.1.0",
        "X-GA": "v1 1",
        "ReleaseVersion": "OB49",
    }
    return requests.get(url, params=params, headers=headers, timeout=10)

@app.route('/add_likes', methods=['GET'])
def add_likes():
    target_id = request.args.get('uid')
    if not target_id:
        return jsonify({"error": "target_id is required"}), 400
    try:
        target_id = int(target_id)
    except ValueError:
        return jsonify({"error": "target_id must be an integer"}), 400

    # استخدم دائمًا النسخة الحالية (الجاهزة)
    with jwt_lock:
        active_tokens = dict(jwt_tokens_current)  # snapshot

    if not active_tokens:
        return jsonify({"error": "no_ready_tokens_yet"}), 503

    results = {}
    for uid, token in active_tokens.items():
        try:
            res = FOX_RequestAddingFriend(token, target_id)
            try:
                content = res.json()
            except Exception:
                content = res.text
            results[uid] = {
                "ok": res.status_code == 200,
                "status_code": res.status_code,
                "content": content
            }
        except Exception as e:
            results[uid] = {"ok": False, "error": str(e)}

    return jsonify({
        "message": "done",
        "last_refresh_at": last_refresh_at,
        "results": results
    })

if __name__ == "__main__":
    initial_refresh()
    t = threading.Thread(target=refresh_tokens_background, kwargs={'interval_seconds': 3600}, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=5000)
