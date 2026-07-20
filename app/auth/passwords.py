from passlib.hash import django_pbkdf2_sha256, pbkdf2_sha256


def hash_password(password: str) -> str:
    return pbkdf2_sha256.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False
    if hashed.startswith("pbkdf2_sha256$") or hashed.startswith("argon2"):
        return pbkdf2_sha256.verify(password, hashed)
    if hashed.startswith("pbkdf2_sha256$") or "pbkdf2" in hashed:
        try:
            return django_pbkdf2_sha256.verify(password, hashed)
        except Exception:
            return False
    try:
        return django_pbkdf2_sha256.verify(password, hashed)
    except Exception:
        return pbkdf2_sha256.verify(password, hashed)


def has_usable_password(hashed: str | None) -> bool:
    if not hashed:
        return False
    return not hashed.startswith("!")
