"""
Password hashing and JWT token utilities.

Note: we call `bcrypt` directly rather than going through `passlib`. passlib is
effectively unmaintained and its bcrypt backend probes for an internal
`bcrypt.__about__.__version__` attribute that newer bcrypt releases removed,
which throws a confusing "(trapped) error reading bcrypt version" error. Calling
bcrypt directly sidesteps that entirely.
"""
from datetime import datetime, timedelta
import bcrypt
from jose import jwt, JWTError

SECRET_KEY = "CHANGE_THIS_SECRET_KEY_IN_PRODUCTION"  # move to env var in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12  # 12 hours

# bcrypt only uses the first 72 bytes of the input; anything beyond that is silently
# ignored by the algorithm itself, but some bcrypt versions raise on longer input -
# so we truncate explicitly to keep behavior consistent and predictable.
_BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(plain_password), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
