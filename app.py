from flask import Flask, request, jsonify
import requests
import threading
import time
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
app = Flask(__name__)

tokens1 = {"3703466495": "799FAF292960B85062BCD462FD8116871F99B4A0505C09FFC6985AA1C32F31EA", "3570958179": "C15AB416AB9FFF0D33F1C7950C75D950135A4DA42692D9433FF736BD5385F7B3", "3571002164": "3D253727E7D7D4EC5CCC188398EABB9A94539579D7F7A041FDE5B268362AFF67", "3571009024": "E8A128C48AC975A71A2F1B77A76D7332C94E6383719F8B56CF491A0DFAF4580F", "3571068251": "7BE9F640DA9CF587165E7FC3E19D84D508434D854940C657DAC716681762DC58"}


tokens_groups = {
    'sv1': tokens1,
}

# قاموس لتخزين JWT Tokens
jwt_tokens = {}
jwt_tokens_lock = threading.Lock()  # قفل لحماية الوصول إلى jwt_tokens

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
        time.sleep(3600)  # تحديث التوكنات كل ساعة

# بدء عملية تحديث التوكنات في خلفية
token_refresh_thread = threading.Thread(target=refresh_tokens)
token_refresh_thread.daemon = True
token_refresh_thread.start()

def Encrypt_ID(x):
    x = int(x)
    dec = ['80', '81', '82', '83', '84', '85', '86', '87', '88', '89', '8a', '8b', '8c', '8d', '8e', '8f', '90', '91', '92', '93', '94', '95', '96', '97', '98', '99', '9a', '9b', '9c', '9d', '9e', '9f', 'a0', 'a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7', 'a8', 'a9', 'aa', 'ab', 'ac', 'ad', 'ae', 'af', 'b0', 'b1', 'b2', 'b3', 'b4', 'b5', 'b6', 'b7', 'b8', 'b9', 'ba', 'bb', 'bc', 'bd', 'be', 'bf', 'c0', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'c8', 'c9', 'ca', 'cb', 'cc', 'cd', 'ce', 'cf', 'd0', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6', 'd7', 'd8', 'd9', 'da', 'db', 'dc', 'dd', 'de', 'df', 'e0', 'e1', 'e2', 'e3', 'e4', 'e5', 'e6', 'e7', 'e8', 'e9', 'ea', 'eb', 'ec', 'ed', 'ee', 'ef', 'f0', 'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'fa', 'fb', 'fc', 'fd', 'fe', 'ff']
    xxx = ['1', '01', '02', '03', '04', '05', '06', '07', '08', '09', '0a', '0b', '0c', '0d', '0e', '0f', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '1a', '1b', '1c', '1d', '1e', '1f', '20', '21', '22', '23', '24', '25', '26', '27', '28', '29', '2a', '2b', '2c', '2d', '2e', '2f', '30', '31', '32', '33', '34', '35', '36', '37', '38', '39', '3a', '3b', '3c', '3d', '3e', '3f', '40', '41', '42', '43', '44', '45', '46', '47', '48', '49', '4a', '4b', '4c', '4d', '4e', '4f', '50', '51', '52', '53', '54', '55', '56', '57', '58', '59', '5a', '5b', '5c', '5d', '5e', '5f', '60', '61', '62', '63', '64', '65', '66', '67', '68', '69', '6a', '6b', '6c', '6d', '6e', '6f', '70', '71', '72', '73', '74', '75', '76', '77', '78', '79', '7a', '7b', '7c', '7d', '7e', '7f']
    x = x / 128
    if x > 128:
        x = x / 128
        if x > 128:
            x = x / 128
            if x > 128:
                x = x / 128
                strx = int(x)
                y = (x - int(strx)) * 128
                stry = str(int(y))
                z = (y - int(stry)) * 128
                strz = str(int(z))
                n = (z - int(strz)) * 128
                strn = str(int(n))
                m = (n - int(strn)) * 128
                return dec[int(m)] + dec[int(n)] + dec[int(z)] + dec[int(y)] + xxx[int(x)]
            else:
                strx = int(x)
                y = (x - int(strx)) * 128
                stry = str(int(y))
                z = (y - int(stry)) * 128
                strz = str(int(z))
                n = (z - int(strz)) * 128
                strn = str(int(n))
                return dec[int(n)] + dec[int(z)] + dec[int(y)] + xxx[int(x)]
    return "".join([dec[int((x - int(x)) * 128)]])

def encrypt_api(plain_text):
    plain_text = bytes.fromhex(plain_text)
    key = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
    iv = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
    cipher = AES.new(key, AES.MODE_CBC, iv)
    cipher_text = cipher.encrypt(pad(plain_text, AES.block_size))
    return cipher_text.hex()

import requests

def FOX_RequestAddingFriend(token, target_id):
    url = "https://arifi-like-token.vercel.app/like?id={uid}&token={token}"
    params = {
        "token": token,
        "uid": target_id
    }
    headers = {
        "Accept": "*/*",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Free Fire/2019117061 CFNetwork/1399 Darwin/22.1.0",
        "X-GA": "v1 1",
        "ReleaseVersion": "OB49",
        # أي هيدرز إضافية تحتاجها
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
        selected_tokens = list(tokens1.items())

    results = {}
    for uid, password in selected_tokens:
        token = get_jwt_token(uid, password)
        if not token:
            results[uid] = {"ok": False, "error": "failed_to_get_jwt"}
            continue

        res = FOX_RequestAddingFriend(token, target_id)
        results[uid] = res

    return jsonify({"message": "done", "results": results})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
