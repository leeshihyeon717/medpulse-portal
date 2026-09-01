"""
Authentication & Role-Based Access Control Module for MedPulse Portal
"""
import hashlib
import secrets

SESSION_EXPIRY_SECONDS = 86400 * 7  # 7 days

def hash_password(password: str, salt: str = None) -> tuple:
    """Hash a password using PBKDF2-HMAC-SHA256."""
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return key.hex(), salt

def verify_password(password: str, hashed: str, salt: str) -> bool:
    """Verify a password against stored hash and salt."""
    key, _ = hash_password(password, salt)
    return secrets.compare_digest(key, hashed)

def generate_session_token() -> str:
    """Generate a secure, random session token."""
    return secrets.token_urlsafe(32)
