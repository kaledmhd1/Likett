import json
import os
import time
import threading
import requests
from flask import Flask, request, jsonify
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

ACCOUNTS_FILE = 'accs.txt'  # يحتوي على JSON: { "uid": "password", ... }

# سيتم تعبئتها من accs.txt
tokens_groups = {
    'sv1': {}
}

jwt_tokens = {}
jwt_tokens_lock = threading.Lock()

def load_accounts(path=ACCOUNTS_FILE):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            else:
                print("[ERROR] accs.txt must contain a JSON object {uid: password}")
                return {}
    except Exception as e:
        print(f"[ERROR] Unable to load accounts from {path}: {e}")
        return {}

def get_jwt_token(uid, password):
    url = f"https://jwt-gen-api-v2.onrender.com/token?uid={uid}&password={password}"
    try:
        response = requests.get(url, timeout=10)
        print(f"[DEBUG] JWT API Response [{uid}]: {response.status_code} -> {response.text}")
        if response.status_code == 200:
            data = response.json()
            if data.get('status') in ('success', 'live'):
                return data.get('token')
    except Exception as e:
        print(f"Error getting JWT token for UID {uid}: {e}")
    return None

def refresh_tokens():
    while True:
        print("[INFO] Reloading accounts & refreshing JWT tokens...")
        new_accounts = load_accounts()
        with jwt_tokens_lock:
            if new_accounts:
                tokens_groups['sv1'] = new_accounts  # حدث القائمة من الملف
            # جدد كل التوكنات
            for uid, password in tokens_groups['sv1'].items():
                token = get_jwt_token(uid, password)
                if token:
                    jwt_tokens[uid] = token
        print("[INFO] Done refreshing.")
        time.sleep(3600)  # كل ساعة

token_refresh_thread = threading.Thread(target=refresh_tokens, daemon=True)
token_refresh_thread.start()

def encrypt_api(plain_text):
    plain_text = bytes.fromhex(plain_text)
    key = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
    iv = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
    cipher = AES.new(key, AES.MODE_CBC, iv)
    cipher_text = cipher.encrypt(pad(plain_text, AES.block_size))
    return cipher_text.hex()

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
    return requests.get(url, params=params, headers=headers)

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

    group_name = f'sv{sv_number}' if sv_number is not None else 'sv1'

    with jwt_tokens_lock:
        accounts = tokens_groups.get(group_name)
        if not accounts:
            return jsonify({"error": f"Invalid or empty group: {group_name}"}), 400

        results = {}
        for uid in accounts.keys():
            token = jwt_tokens.get(uid)
            if not token:
                results[uid] = {"ok": False, "error": "no_token_available"}
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
    # تحميل أولي للحسابات قبل بدء السيرفر
    tokens_groups['sv1'] = load_accounts()
    app.run(host='0.0.0.0', port=5000)
