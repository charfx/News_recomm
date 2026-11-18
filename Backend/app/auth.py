import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET = os.environ["JWT_SECRET"]
ALGO = "HS256"
TOKEN_HOURS = 8

bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed or hashed == "-":          # anciens comptes sans mot de passe
        return False
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_token(user_id: int, role: str, session_id: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "sid": session_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def get_current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if cred is None:
        raise HTTPException(401, "Non authentifié")
    try:
        p = jwt.decode(cred.credentials, SECRET, algorithms=[ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expirée")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Jeton invalide")
    return {"user_id": int(p["sub"]), "role": p["role"], "session_id": p["sid"]}


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Réservé à l'administrateur")
    return user