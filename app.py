from flask import Flask, request, jsonify
import requests
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# التوكنات (UID: password)
tokens1 = {
    "3703466495": "799FAF292960B85062BCD462FD8116871F99B4A0505C09FFC6985AA1C32F31EA",
    "3570958179": "C15AB416AB9FFF0D33F1C7950C75D950135A4DA42692D9433FF736BD5385F7B3",
    "3571002164": "3D253727E7D7D4EC5CCC188398EABB9A94539579D7F7A041FDE5B268362AFF67",
    "3571009024": "E8A128C48AC975A71A2F1B77A76D7332C94E6383719F8B56CF491A0DFAF4580F",
    "3571068251": "7BE9F640DA9CF587165E7FC3E19D84D508434D854940C657DAC716681762DC58"
}

tokens_groups = {
    'sv1': tokens1,
}

jwt_tokens = {}
jwt_tokens_lock = threading.Lock()

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
        print("[INFO] Starting token refresh...")
        for group_name, tokens in tokens_groups.items():
            for uid, password in tokens.items():
                token = get_jwt_token(uid, password)
                if token:
                    with jwt_tokens_lock:
                        jwt_tokens[uid] = token
                        print(f"[INFO] Token updated for UID {uid}")
                else:
                    print(f"[WARN] Failed to refresh token for UID {uid}")
        print("[INFO] Token refresh done. Sleeping 1 hour...")
        time.sleep(3600)

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

def get_player_info(uid, region='me'):
    url = f"https://razor-info.vercel.app/player-info?uid={uid}&region={region}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Error fetching player info: {e}")
    return None

def extract_likes(player_info):
    if not player_info or not isinstance(player_info, dict):
        return None
    for key in ['likes', 'like', 'favorite_count', 'favs', 'hearts']:
        if key in player_info and isinstance(player_info[key], int):
            return player_info[key]
    for container in ['data', 'profile', 'player', 'stats']:
        if container in player_info and isinstance(player_info[container], dict):
            inner = player_info[container]
            for key in ['likes', 'like', 'favorite_count', 'favs', 'hearts']:
                if key in inner and isinstance(inner[key], int):
                    return inner[key]
    return None

def extract_name_and_id(player_info):
    if not player_info or not isinstance(player_info, dict):
        return None, None
    name = player_info.get('name') or player_info.get('nickname') or player_info.get('playerName')
    pid = player_info.get('id') or player_info.get('uid') or player_info.get('playerId')
    for container in ['data', 'profile', 'player']:
        if container in player_info and isinstance(player_info[container], dict):
            inner = player_info[container]
            name = name or inner.get('name') or inner.get('nickname') or inner.get('playerName')
            pid = pid or inner.get('id') or inner.get('uid') or inner.get('playerId')
    return name, pid

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

    before_info = get_player_info(target_id)
    before_likes = extract_likes(before_info)
    player_name, player_uid = extract_name_and_id(before_info)

    if sv_number is not None:
        group_name = f'sv{sv_number}'
        if group_name in tokens_groups:
            selected_tokens = list(tokens_groups[group_name].items())
        else:
            return jsonify({"error": f"Invalid group: {group_name}"}), 400
    else:
        selected_tokens = list(tokens1.items())

    with jwt_tokens_lock:
        tokens_ready = {uid: jwt_tokens.get(uid) for uid, _ in selected_tokens}

    valid_tokens = {uid: token for uid, token in tokens_ready.items() if token}

    if not valid_tokens:
        return jsonify({"error": "No valid JWT tokens available"}), 500

    max_workers = min(30, len(valid_tokens))
    results = {}

    def send_like(uid_token):
        uid, token = uid_token
        res = FOX_RequestAddingFriend(token, target_id)
        try:
            content = res.json()
        except Exception:
            content = res.text
        return uid, {
            "ok": res.status_code == 200,
            "status_code": res.status_code,
            "content": content
        }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(send_like, item) for item in valid_tokens.items()]
        for future in as_completed(futures):
            uid, result = future.result()
            results[uid] = result

    after_info = get_player_info(target_id)
    after_likes = extract_likes(after_info)

    added_likes = None
    if before_likes is not None and after_likes is not None:
        added_likes = after_likes - before_likes

    response = {
        "player": {
            "name": player_name,
            "id": player_uid or target_id,
        },
        "likes": {
            "before": before_likes,
            "after": after_likes,
            "added": added_likes
        },
        "requests": {
            "total_accounts": len(valid_tokens),
            "success": sum(1 for r in results.values() if r['ok']),
            "failed": sum(1 for r in results.values() if not r['ok']),
            "details": results
        },
        "message": "done"
    }

    return jsonify(response)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
