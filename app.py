import os
import json
import asyncio
import httpx
from fastapi import FastAPI, Query, HTTPException
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional

app = FastAPI()

ACCS_FILE = "accs.txt"
tokens_groups = {}

jwt_tokens: Dict[str, str] = {}
jwt_tokens_lock = asyncio.Lock()

def load_tokens():
    if os.path.exists(ACCS_FILE):
        with open(ACCS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                tokens_groups['sv1'] = data
                return data
    tokens_groups['sv1'] = {}
    return {}

tokens1 = load_tokens()

async def get_jwt_token(uid: str, password: str) -> Optional[str]:
    url = f"https://jwt-gen-api-v2.onrender.com/token?uid={uid}&password={password}"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                if data.get('status') in ('success', 'live'):
                    token = data.get('token')
                    async with jwt_tokens_lock:
                        jwt_tokens[uid] = token
                    return token
        except Exception as e:
            print(f"Error getting JWT token for {uid}: {e}")
    return None

async def refresh_tokens_periodically():
    while True:
        for group_name, tokens in tokens_groups.items():
            for uid, password in tokens.items():
                token = await get_jwt_token(uid, password)
                if token:
                    print(f"[INFO] Refreshed JWT for {uid}")
        await asyncio.sleep(3600)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(refresh_tokens_periodically())

async def FOX_RequestAddingFriend(token: str, target_id: int):
    url = "https://arifi-like-token.vercel.app/like"
    headers = {
        "Accept": "*/*",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Free Fire/2019117061 CFNetwork/1399 Darwin/22.1.0",
        "X-GA": "v1 1",
        "ReleaseVersion": "OB49",
    }
    async with httpx.AsyncClient(timeout=8) as client:
        return await client.get(url, params={"token": token, "id": target_id}, headers=headers)

async def get_player_info(uid: int, region: str = 'me'):
    url = f"https://razor-info.vercel.app/player-info?uid={uid}&region={region}"
    async with httpx.AsyncClient(timeout=8) as client:
        try:
            r = await client.get(url)
            if r.status_code == 200:
                return r.json()
            print(f"[WARN] player-info API HTTP {r.status_code}: {r.text}")
        except Exception as e:
            print(f"[ERROR] get_player_info: {e}")
    return None

def extract_name_and_id(data: dict):
    name = None
    pid = None
    if isinstance(data, dict):
        name = data.get('name') or data.get('playerName') or data.get('nickname')
        pid = data.get('id') or data.get('uid') or data.get('playerId')
        profile = data.get('profile') or data.get('data') or data.get('player')
        if profile:
            name = name or profile.get('name') or profile.get('playerName') or profile.get('nickname')
            pid = pid or profile.get('id') or profile.get('uid') or profile.get('playerId')
    return name, pid

def extract_likes(data: dict):
    if not isinstance(data, dict):
        return None
    for key in ['likes', 'like', 'favorite_count', 'favourite_count', 'favs', 'hearts']:
        if key in data and isinstance(data[key], (int, float)):
            return int(data[key])
    for container_key in ['profile', 'data', 'player', 'stats']:
        if container_key in data and isinstance(data[container_key], dict):
            inner = data[container_key]
            for key in ['likes', 'like', 'favorite_count', 'favourite_count', 'favs', 'hearts']:
                if key in inner and isinstance(inner[key], (int, float)):
                    return int(inner[key])
    return None

@app.get("/add_likes")
async def add_likes(uid: int = Query(...), region: str = Query("me"), sv_number: Optional[int] = Query(None)):
    # تحقق من وجود الحسابات
    if sv_number is not None:
        group_name = f"sv{sv_number}"
        if group_name not in tokens_groups:
            raise HTTPException(status_code=400, detail=f"Invalid group: {group_name}")
        selected_tokens = list(tokens_groups[group_name].items())
    else:
        selected_tokens = list(tokens1.items())

    # جلب بيانات اللاعب قبل اللايكات
    before_info = await get_player_info(uid, region=region)
    before_likes = extract_likes(before_info) if before_info else None
    player_name, player_uid = extract_name_and_id(before_info or {})

    tasks = []
    for user_id, password in selected_tokens:
        token = jwt_tokens.get(user_id)
        if not token:
            token = await get_jwt_token(user_id, password)
        if token:
            tasks.append(FOX_RequestAddingFriend(token, uid))

    responses = await asyncio.gather(*tasks, return_exceptions=True)

    results = {}
    success_count = 0
    for i, resp in enumerate(responses):
        user_id = selected_tokens[i][0]
        if isinstance(resp, Exception):
            results[user_id] = {"ok": False, "error": str(resp)}
        elif resp.status_code == 200:
            try:
                content = resp.json()
            except Exception:
                content = resp.text
            results[user_id] = {
                "ok": True,
                "status_code": resp.status_code,
                "content": content
            }
            success_count += 1
        else:
            results[user_id] = {
                "ok": False,
                "status_code": resp.status_code,
                "content": resp.text
            }

    # جلب بيانات اللاعب بعد اللايكات
    after_info = await get_player_info(uid, region=region)
    after_likes = extract_likes(after_info) if after_info else None

    added = None
    if before_likes is not None and after_likes is not None:
        added = after_likes - before_likes

    return {
        "player": {
            "name": player_name,
            "id": player_uid or uid,
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
