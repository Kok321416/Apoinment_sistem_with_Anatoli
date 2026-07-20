from passlib.hash import django_argon2, django_pbkdf2_sha256, pbkdf2_sha256


def hash_password(password: str) -> str:
    return pbkdf2_sha256.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False

    verifiers = []
    if hashed.startswith("argon2"):
        verifiers = [django_argon2]
    elif "pbkdf2" in hashed:
        verifiers = [django_pbkdf2_sha256, pbkdf2_sha256]
    else:
        verifiers = [django_pbkdf2_sha256, pbkdf2_sha256]

    for verifier in verifiers:
        try:
            return verifier.verify(password, hashed)
        except Exception:
            continue
    return False


def has_usable_password(hashed: str | None) -> bool:
    if not hashed:
        return False
    return not hashed.startswith("!")
