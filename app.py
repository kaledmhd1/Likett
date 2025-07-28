from flask import Flask, request, jsonify
import requests
import threading
import time
import json
import os
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
app = Flask(__name__)

ACCS_FILE = "accs.txt"  # ملف التوكنات الخارجي

tokens_groups = {
    'sv1': {}
}

jwt_tokens = {}
jwt_tokens_lock = threading.Lock()

def load_tokens():
    if os.path.exists(ACCS_FILE):
        try:
            with open(ACCS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    tokens_groups['sv1'] = data
                    print(f"[INFO] Loaded {len(data)} tokens from {ACCS_FILE}")
                else:
                    print(f"[ERROR] {ACCS_FILE} content is not a dict")
        except Exception as e:
            print(f"[ERROR] Failed to load tokens from {ACCS_FILE}: {e}")
    else:
        print(f"[WARN] {ACCS_FILE} not found")

def get_jwt_token(uid, password):
    url = f"https://jwt-gen-api-v2.onrender.com/token?uid={uid}&password={password}"
    try:
        response = requests.get(url, timeout=10)
        print(f"[DEBUG] JWT API Response [{uid}]: {response.status_code} -> {response.text}")
        if response.status_code == 200:
            data = response.json()
            if data.get('status') in ('success', 'live'):
                return data.get('token')
            else:
                print(f"Failed to get JWT token for UID {uid}: status={data.get('status')}")
        else:
            print(f"Failed to get JWT token for UID {uid}: HTTP {response.status_code}")
    except Exception as e:
        print(f"Error getting JWT token for UID {uid}: {e}")
    return None

def refresh_tokens():
    while True:
        for group_name, tokens in tokens_groups.items():
            for uid, password in tokens.items():
                token = get_jwt_token(uid, password)
                if token:
                    with jwt_tokens_lock:
                        jwt_tokens[uid] = token
        time.sleep(3600)

def refresh_tokens_once():
    for group_name, tokens in tokens_groups.items():
        for uid, password in tokens.items():
            token = get_jwt_token(uid, password)
            if token:
                with jwt_tokens_lock:
                    jwt_tokens[uid] = token

token_refresh_thread = threading.Thread(target=refresh_tokens)
token_refresh_thread.daemon = True
token_refresh_thread.start()

def FOX_RequestAddingFriend(token, target_id):
    url = "https://arifi-like-token.vercel.app/like"
    params = {
        "token": token,
        "id": target_id
    }
    headers = {
        "Accept": "*/*",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Free Fire/2019117061 CFNetwork/1399 Darwin/22.1.0",
        "X-GA": "v1 1",
        "ReleaseVersion": "OB49",
    }
    response = requests.get(url, params=params, headers=headers)
    return response

@app.route('/add_likes', methods=['GET'])
@app.route('/sv<int:sv_number>/add_likes', methods=['GET'])
def send_friend_requests(sv_number=None):
    target_id = request.args.get('uid')
    if not target_id:
        return jsonify({"error": "target_id is required"}), 400

    try:
        target_id = int(target_id)
    except ValueError:
        return jsonify({"error": "target_id must be an integer"}), 400

    if sv_number is not None:
        group_name = f'sv{sv_number}'
        if group_name in tokens_groups:
            selected_tokens = list(tokens_groups[group_name].items())
        else:
            return jsonify({"error": f"Invalid group: {group_name}"}), 400
    else:
        selected_tokens = list(tokens_groups['sv1'].items())

    results = {}
    for uid, password in selected_tokens:
        with jwt_tokens_lock:
            token = jwt_tokens.get(uid)
        if not token:
            # إذا التوكن غير موجود في الذاكرة نعيد طلبه (اختياري)
            token = get_jwt_token(uid, password)
            if token:
                with jwt_tokens_lock:
                    jwt_tokens[uid] = token
            else:
                results[uid] = {"ok": False, "error": "failed_to_get_jwt"}
                continue

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

    return jsonify({"message": "done", "results": results})

if __name__ == "__main__":
    load_tokens()
    refresh_tokens_once()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
