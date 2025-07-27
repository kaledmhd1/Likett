import json
import os
import time
import threading
import requests
from flask import Flask, request, jsonify
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# =========================
# الإعدادات
# =========================
ACCOUNTS_FILE = os.getenv('ACCOUNTS_FILE', 'accs.txt')   # { "uid": "password", ... }
REFRESH_INTERVAL = int(os.getenv('REFRESH_INTERVAL', '3600'))  # كل كم ثانية ننعش التوكنات

# =========================
# أقفال وذاكرة مشتركة
# =========================
accounts_lock = threading.Lock()
jwt_lock = threading.Lock()

accounts = {}               # أحدث حسابات (uid -> password)
jwt_tokens_current = {}     # التوكنات الجاهزة للاستخدام
last_refresh_at = 0

# =========================
# Utilities
# =========================
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
        r = requests.get(url, timeout=15, verify=False)
        if r.status_code == 200:
            data = r.json()
            if data.get('status') in ('success', 'live'):
                return data.get('token')
    except Exception as e:
        print(f"[ERROR] get_jwt_token({uid}): {e}")
    return None

def initial_refresh():
    """تحديث أولي عند بدء السيرفر."""
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
    """لووب خلفي لتحديث التوكنات بشكل دوري."""
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
    """طلب إرسال لايك باستخدام التوكن."""
    url = "https://arifi-like-token.vercel.app/like"
    params = {"token": token, "id": target_id}
    headers = {
        "Accept": "*/*",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Free Fire/2019117061 CFNetwork/1399 Darwin/22.1.0",
        "X-GA": "v1 1",
        "ReleaseVersion": "OB49",
    }
    return requests.get(url, params=params, headers=headers, timeout=15, verify=False)

def get_player_info(uid):
    """جلب اسم اللاعب وعدد اللايكات من API الخارجي."""
    url = f"https://razor-info.vercel.app/player-info?uid={uid}&region=me"
    try:
        r = requests.get(url, timeout=15, verify=False)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "success":
                player = data.get("player", {})
                # العدّاد قد يأتي كسترنج
                likes = player.get("likes", 0)
                try:
                    likes = int(likes)
                except Exception:
                    likes = 0
                return {
                    "name": player.get("nickname"),
                    "uid": str(player.get("id") or uid),
                    "likes": likes
                }
    except Exception as e:
        print(f"[ERROR] get_player_info({uid}): {e}")
    return None

# =========================
# Routes
# =========================
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "active_tokens": len(jwt_tokens_current)})

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "active_tokens": len(jwt_tokens_current),
        "last_refresh_at": last_refresh_at
    })

@app.route('/refresh_now', methods=['POST'])
def refresh_now():
    """تحديث يدوي (Sync) - مفيد للاختبار فقط."""
    try:
        initial_refresh()
        return jsonify({"status": "refreshed", "active_tokens": len(jwt_tokens_current)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/add_likes', methods=['GET'])
def add_likes():
    """
    ?uid=<target_uid>
    تُرجع:
    - اسم اللاعب
    - uid
    - عدد اللايكات قبل وبعد
    - اللايكات المُضافة
    - نتائج كل توكن
    """
    target_id = request.args.get('uid')
    if not target_id:
        return jsonify({"error": "target_id is required"}), 400
    try:
        target_id_int = int(target_id)
    except ValueError:
        return jsonify({"error": "target_id must be an integer"}), 400

    # جلب بيانات اللاعب قبل
    player_before = get_player_info(target_id_int)
    if not player_before:
        return jsonify({"error": "failed_to_fetch_player_before"}), 502

    # snapshot للتوكنات النشطة
    with jwt_lock:
        active_tokens = dict(jwt_tokens_current)

    if not active_tokens:
        return jsonify({"error": "no_ready_tokens_yet"}), 503

    results = {}
    success_calls = 0
    for uid, token in active_tokens.items():
        try:
            res = FOX_RequestAddingFriend(token, target_id_int)
            try:
                content = res.json()
            except Exception:
                content = res.text

            is_ok = (res.status_code == 200)
            if is_ok:
                success_calls += 1

            results[uid] = {
                "ok": is_ok,
                "status_code": res.status_code,
                "content": content
            }
        except Exception as e:
            results[uid] = {"ok": False, "error": str(e)}

    # نعطي مهلة بسيطة حتى ينعكس العدد في السيرفر الخارجي
    time.sleep(2)

    # جلب بيانات اللاعب بعد
    player_after = get_player_info(target_id_int)
    if not player_after:
        return jsonify({"error": "failed_to_fetch_player_after"}), 502

    likes_before = player_before["likes"]
    likes_after = player_after["likes"]
    likes_added = max(0, likes_after - likes_before)

    return jsonify({
        "message": "done",
        "player": {
            "name": player_after["name"],
            "uid": player_after["uid"],
            "likes_before": likes_before,
            "likes_after": likes_after,
            "likes_added": likes_added
        },
        "calls": {
            "total_tokens": len(active_tokens),
            "success_calls": success_calls
        },
        "last_refresh_at": last_refresh_at,
        "results": results
    })

# =========================
# التشغيل
# =========================
def start_background_thread():
    t = threading.Thread(
        target=refresh_tokens_background,
        kwargs={'interval_seconds': REFRESH_INTERVAL},
        daemon=True
    )
    t.start()

initial_refresh()
start_background_thread()

if __name__ == "__main__":
    # للتشغيل المحلي
    port = int(os.getenv("PORT", "5000"))
    app.run(host='0.0.0.0', port=port)
