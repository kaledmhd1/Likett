import json
import os
import time
import threading
import requests
from flask import Flask, request, jsonify
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

ACCOUNTS_FILE = os.getenv('ACCOUNTS_FILE', 'accs.txt')
REFRESH_INTERVAL = int(os.getenv('REFRESH_INTERVAL', '3600'))  # 1 ساعة

# الحالة المشتركة
jwt_tokens_current = {}          # النسخة الجاهزة للاستعمال
last_refresh_at = 0              # آخر وقت *ناجح* للتحديث
last_refresh_attempt_at = 0      # آخر محاولة تحديث (قد تفشل)
is_refreshing = False            # فلاغ لمعرفة إن كان هناك تحديث جارٍ
tokens_lock = threading.Lock()

# ---------------- Utilities ----------------
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
                token = data.get('token')
                print(f"[JWT] UID: {uid} - TOKEN: {token}")
                return token
    except Exception as e:
        print(f"[ERROR] get_jwt_token({uid}): {e}")
    return None

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
    return requests.get(url, params=params, headers=headers, timeout=15, verify=False)

def get_player_info(uid):
    url = f"https://razor-info.vercel.app/player-info?uid={uid}&region=me"
    try:
        r = requests.get(url, timeout=15, verify=False)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "success":
                player = data.get("player", {})
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

# ---------------- Refresh logic ----------------
def refresh_tokens():
    """
    يبني new_tokens في Buffer منفصل.
    لا يستبدل jwt_tokens_current إلا إذا كان لدينا توكنات صالحة.
    """
    global jwt_tokens_current, last_refresh_at, last_refresh_attempt_at, is_refreshing
    last_refresh_attempt_at = time.time()
    is_refreshing = True
    try:
        accounts = load_accounts()
        if not accounts:
            print("[WARN] No accounts loaded!")
            return 0

        new_tokens = {}
        for uid, pwd in accounts.items():
            tok = get_jwt_token(uid, pwd)
            if tok:
                new_tokens[uid] = tok

        if new_tokens:
            with tokens_lock:
                # **Atomic swap**: لا نفرغ القديمة، فقط نستبدل عندما تكون الجديدة جاهزة
                jwt_tokens_current = new_tokens
                last_refresh_at = time.time()
            print(f"[INFO] Tokens refreshed. Count: {len(new_tokens)}")
        else:
            print("[WARN] refresh_tokens: got 0 valid tokens, keeping old ones.")
        return len(new_tokens)
    finally:
        is_refreshing = False

def refresh_tokens_background():
    while True:
        try:
            print("[INFO] Background token refresh started.")
            count = refresh_tokens()
            print(f"[INFO] Background token refresh done. New valid tokens: {count} (current in use: {len(jwt_tokens_current)})")
        except Exception as e:
            print(f"[ERROR] refresh_tokens_background: {e}")
        time.sleep(REFRESH_INTERVAL)

# ---------------- Routes ----------------
@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "active_tokens": len(jwt_tokens_current),
        "last_refresh_at": last_refresh_at,
        "last_refresh_attempt_at": last_refresh_attempt_at,
        "is_refreshing": is_refreshing
    })

@app.route('/refresh_now', methods=['POST'])
def refresh_now():
    count = refresh_tokens()
    return jsonify({
        "status": "refreshed",
        "new_tokens": count,
        "active_tokens": len(jwt_tokens_current),
        "last_refresh_at": last_refresh_at,
        "last_refresh_attempt_at": last_refresh_attempt_at,
        "is_refreshing": is_refreshing
    })

@app.route('/add_likes', methods=['GET'])
def add_likes():
    """
    يستخدم دائمًا النسخة الجاهزة (jwt_tokens_current) حتى لو التحديث جارٍ.
    """
    target_id = request.args.get('uid')
    if not target_id:
        return jsonify({"error": "target_id is required"}), 400
    try:
        target_id_int = int(target_id)
    except ValueError:
        return jsonify({"error": "target_id must be an integer"}), 400

    player_before = get_player_info(target_id_int)
    if not player_before:
        return jsonify({"error": "failed_to_fetch_player_before"}), 502

    # Snapshot سريع بدون انتظار انتهاء التحديث
    with tokens_lock:
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

    time.sleep(2)  # انتظار بسيط لتحديث العدّاد

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
        "last_refresh_attempt_at": last_refresh_attempt_at,
        "is_refreshing": is_refreshing,
        "results": results
    })

# ---------------- Boot ----------------
if __name__ == "__main__":
    # تحديث أولي (إن فشل، سنظل بدون توكنات لكن /add_likes لن يكسر النسخة الحالية لأنها فارغة أصلاً)
    refresh_tokens()

    # بدء الثريد الخلفي للتحديث كل ساعة
    t = threading.Thread(target=refresh_tokens_background, daemon=True)
    t.start()

    port = int(os.getenv("PORT", "5000"))
    app.run(host='0.0.0.0', port=port)
