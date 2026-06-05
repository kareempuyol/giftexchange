import base64
import hashlib
import hmac
import json
import os
import secrets
import time


TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60


def _secret():
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        raise RuntimeError("JWT_SECRET is required")
    return secret.encode("utf-8")


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def b64url_encode(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(value):
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def sign_token(user_id):
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"userId": user_id, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    head = b64url_encode(_json_bytes(header))
    body = b64url_encode(_json_bytes(payload))
    signing_input = f"{head}.{body}".encode("ascii")
    signature = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
    return f"{head}.{body}.{b64url_encode(signature)}"


def verify_token(token):
    try:
        head, body, signature = token.split(".")
        signing_input = f"{head}.{body}".encode("ascii")
        expected = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(b64url_decode(signature), expected):
            return None
        payload = json.loads(b64url_decode(body).decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return {"userId": int(payload["userId"])}
    except Exception:
        return None


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 150_000)
    return f"pbkdf2_sha256$150000${b64url_encode(salt)}${b64url_encode(digest)}"


def check_password(password, stored):
    try:
        algo, rounds, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            b64url_decode(salt),
            int(rounds),
        )
        return hmac.compare_digest(b64url_decode(digest), computed)
    except Exception:
        return False
