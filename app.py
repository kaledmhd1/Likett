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

ACCS_FILE = "accs.txt"  # الملف الخارجي الذي يحتوي على اليوزرات والباسووردات

def load_tokens():
    """تحميل التوكنات من الملف accs.txt (على شكل dict: {uid: password})."""
    if os.path.exists(ACCS_FILE):
        with open(ACCS_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                print(f"[ERROR] Failed to load tokens from {ACCS_FILE}: {e}")
    return {}

tokens1 = load_tokens()
tokens_groups = {
    'sv1': tokens1,
}

jwt_tokens = {}  # نخزن هنا التوكنات الجاهزة
jwt_tokens_lock = threading.Lock()

def get_jwt_token(uid, password):
    """يحصل على التوكن ويقوم بتسجيله في jwt_tokens إذا نجح."""
    url = f"https://jwt-gen-api-v2.onrender.com/token?uid={uid}&password={password}"
    try:
        response = requests.get(url, timeout=10)
        print(f"[DEBUG] JWT API Response [{uid}]: {response.status_code} -> {response.text}")
        if response.status_code == 200:
            data = response.json()
            if data.get('status') in ('success', 'live'):
                token = data.get('token')
                with jwt_tokens_lock:
                    jwt_tokens[uid] = token
                return token
            else:
                print(f"Failed to get JWT token for UID {uid}: status={data.get('status')}")
        else:
            print(f"Failed to get JWT token for UID {uid}: HTTP {response.status_code}")
    except Exception as e:
        print(f"Error getting JWT token for UID {uid}: {e}")
    return None

def refresh_tokens():
    """يقوم بجلب جميع التوكنات وتخزينها مرة واحدة كل ساعة."""
    while True:
        for group_name, tokens in tokens_groups.items():
            for uid, password in tokens.items():
                token = get_jwt_token(uid, password)
                if token:
                    print(f"[INFO] Stored JWT for {uid}")
        time.sleep(3600)

# تشغيل خيط التحديث
token_refresh_thread = threading.Thread(target=refresh_tokens)
token_refresh_thread.daemon = True
token_refresh_thread.start()

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
    response = requests.get(url, params=params, headers=headers)
    return response

def get_player_info(uid, region='me'):
    """يرجع JSON من API اللاعب أو None في حال الفشل."""
    url = f"https://razor-info.vercel.app/player-info?uid={uid}&region={region}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
        print(f"[WARN] player-info API HTTP {r.status_code}: {r.text}")
    except Exception as e:
        print(f"[ERROR] get_player_info: {e}")
    return None

def extract_name_and_id(data):
    """
    حاول استخراج اسم اللاعب و الـID من الريسبونس.
    عدّل هذه الدالة لو تعرف الهيكل الدقيق للـAPI.
    """
    name = None
    pid = None

    # محاولات عامة
    if isinstance(data, dict):
        name = data.get('name') or data.get('playerName') or data.get('nickname')
        pid = data.get('id') or data.get('uid') or data.get('playerId')
        # جرّب داخل حقول متداخلة
        profile = data.get('profile') or data.get('data') or data.get('player')
        if profile:
            name = name or profile.get('name') or profile.get('playerName') or profile.get('nickname')
            pid = pid or profile.get('id') or profile.get('uid') or profile.get('playerId')

    return name, pid

def extract_likes(data):
    """
    حاول استخراج عدد اللايكات من الريسبونس.
    عدّل هذه الدالة لو تعرف المفتاح الدقيق (ex: 'like', 'likes', 'favorite_count'...).
    """
    if not isinstance(data, dict):
        return None

    # احتمالات مباشرة
    for key in ['likes', 'like', 'favorite_count', 'favourite_count', 'favs', 'hearts']:
        if key in data and isinstance(data[key], (int, float)):
            return int(data[key])

    # جرّب داخل حقول متداخلة
    for container_key in ['profile', 'data', 'player', 'stats']:
        if container_key in data and isinstance(data[container_key], dict):
            inner = data[container_key]
            for key in ['likes', 'like', 'favorite_count', 'favourite_count', 'favs', 'hearts']:
                if key in inner and isinstance(inner[key], (int, float)):
                    return int(inner[key])

    return None

@app.route('/add_likes', methods=['GET'])
@app.route('/sv<int:sv_number>/add_likes', methods=['GET'])
def send_friend_requests(sv_number=None):
    target_id = request.args.get('uid')
    region = request.args.get('region', 'me')

    if not target_id:
        return jsonify({"error": "uid (target_id) is required"}), 400

    try:
        target_id_int = int(target_id)
    except ValueError:
        return jsonify({"error": "uid must be an integer"}), 400

    # احضر بيانات اللاعب قبل
    before_info = get_player_info(target_id_int, region=region)
    before_likes = extract_likes(before_info) if before_info else None
    player_name, player_uid = extract_name_and_id(before_info or {})  # قد يرجع None

    # اختيار المجموعة
    if sv_number is not None:
        group_name = f'sv{sv_number}'
        if group_name in tokens_groups:
            selected_tokens = list(tokens_groups[group_name].items())
        else:
            return jsonify({"error": f"Invalid group: {group_name}"}), 400
    else:
        selected_tokens = list(tokens1.items())

    results = {}
    success_count = 0
    for uid, password in selected_tokens:
        with jwt_tokens_lock:
            token = jwt_tokens.get(uid)  # استخدم التوكن المخزن
        if not token:
            # إذا لم يكن هناك توكن مسجل، نحاول جلبه وتسجيله
            token = get_jwt_token(uid, password)
            if not token:
                results[uid] = {"ok": False, "error": "failed_to_get_jwt"}
                continue

        res = FOX_RequestAddingFriend(token, target_id_int)
        try:
            content = res.json()
        except Exception:
            content = res.text

        ok = res.status_code == 200
        if ok:
            success_count += 1

        results[uid] = {
            "ok": ok,
            "status_code": res.status_code,
            "content": content
        }

    # احضر بيانات اللاعب بعد
    after_info = get_player_info(target_id_int, region=region)
    after_likes = extract_likes(after_info) if after_info else None

    added = None
    if before_likes is not None and after_likes is not None:
        added = after_likes - before_likes

    response = {
        "player": {
            "name": player_name,
            "id": player_uid or target_id_int,
            "region": region
        },
        "likes": {
            "before": before_likes,
            "after": after_likes,
            "added": added
        },
        "requests": {
            "total_accounts": len(selected_tokens),
            "success": success_count,
            "failed": len(selected_tokens) - success_count,
            "details": results
        },
        "message": "done"
    }

    return jsonify(response)
    
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
