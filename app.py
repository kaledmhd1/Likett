from flask import Flask, request, jsonify
import requests
import threading
import time
import json
import os
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

ACCS_FILE = "accs.txt"  # ملف الحسابات: JSON {"UID": "password", ...}

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
                    print(f"[INFO] Loaded {len(data)} accounts from {ACCS_FILE}")
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
        if response.status_code == 200:
            data = response.json()
            if data.get('status') in ('success', 'live'):
                return data.get('token')
            else:
                print(f"[WARN] JWT API failure for UID {uid}: status={data.get('status')}")
        else:
            print(f"[WARN] JWT API HTTP error for UID {uid}: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Exception while getting JWT for UID {uid}: {e}")
    return None

def refresh_tokens():
    while True:
        print("[INFO] Refreshing JWT tokens for all accounts...")
        for uid, password in tokens_groups['sv1'].items():
            token = get_jwt_token(uid, password)
            if token:
                with jwt_tokens_lock:
                    jwt_tokens[uid] = token
                print(f"[INFO] Token refreshed for UID {uid}")
            else:
                print(f"[WARN] Failed to refresh token for UID {uid}")
        time.sleep(3600)

def refresh_tokens_once():
    print("[INFO] Initial JWT tokens refresh at startup...")
    for uid, password in tokens_groups['sv1'].items():
        token = get_jwt_token(uid, password)
        if token:
            with jwt_tokens_lock:
                jwt_tokens[uid] = token
            print(f"[INFO] Token loaded for UID {uid}")
        else:
            print(f"[WARN] Failed to load token for UID {uid}")

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
    try:
        response = requests.get(url, params=params, headers=headers)
        return response
    except Exception as e:
        print(f"[ERROR] Failed to send like request: {e}")
        return None

@app.route('/')
def home():
    return "Server is running. استخدم /add_likes?uid=XXXX"

@app.route('/tokens', methods=['GET'])
def list_tokens():
    with jwt_tokens_lock:
        return jsonify(jwt_tokens)

@app.route('/add_likes', methods=['GET'])
def send_likes():
    target_id = request.args.get('uid')
    if not target_id:
        return jsonify({"error": "target_id is required"}), 400

    try:
        target_id = int(target_id)
    except ValueError:
        return jsonify({"error": "target_id must be an integer"}), 400

    results = {}
    for uid, password in tokens_groups['sv1'].items():
        with jwt_tokens_lock:
            token = jwt_tokens.get(uid)
        if not token:
            # طلب توكن جديد إذا غير موجود (اختياري)
            token = get_jwt_token(uid, password)
            if token:
                with jwt_tokens_lock:
                    jwt_tokens[uid] = token
            else:
                results[uid] = {"ok": False, "error": "failed_to_get_jwt"}
                continue

        res = FOX_RequestAddingFriend(token, target_id)
        if res:
            try:
                content = res.json()
            except Exception:
                content = res.text
            results[uid] = {
                "ok": res.status_code == 200,
                "status_code": res.status_code,
                "content": content
            }
        else:
            results[uid] = {"ok": False, "error": "request_failed"}

    return jsonify({"message": "done", "results": results})

if __name__ == "__main__":
    load_tokens()
    refresh_tokens_once()
    threading.Thread(target=refresh_tokens, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
