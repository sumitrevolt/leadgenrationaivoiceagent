"""
JWT Key Versioning and Rotation
P0-5 Fix: Support graceful JWT secret key rotation without invalidating all tokens
"""

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from jose import JWTError, jwt

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class JWTKeyManager:
    """Manages JWT keys with version support for graceful rotation"""

    def __init__(self, primary_secret: str, algorithm: str = "HS256"):
        """
        Initialize JWT key manager.

        Args:
            primary_secret: The active JWT secret key
            algorithm: JWT algorithm (default: HS256)
        """
        self.algorithm = algorithm
        self.primary_key = {
            "id": "v1",
            "secret": primary_secret,
            "active": True,
            "created_at": datetime.utcnow().isoformat(),
        }
        self.secondary_keys = {}  # id -> {"secret", "active", "created_at"}
        self._load_secondary_keys()

    def _load_secondary_keys(self):
        """Load secondary keys from environment (for rotation)"""
        try:
            # Check for rotation key file or env var
            rotation_keys_json = os.getenv("JWT_ROTATION_KEYS", "{}")
            if rotation_keys_json:
                try:
                    keys = json.loads(rotation_keys_json)
                    for key_id, key_data in keys.items():
                        self.secondary_keys[key_id] = key_data
                    logger.info(
                        f"✅ Loaded {len(self.secondary_keys)} secondary JWT keys for rotation"
                    )
                except json.JSONDecodeError:
                    logger.warning("JWT_ROTATION_KEYS is not valid JSON")
        except Exception as e:
            logger.warning(f"Failed to load secondary JWT keys: {e}")

    def encode(self, payload: dict[str, Any], expires_delta: timedelta | None = None) -> str:
        """
        Create a JWT token using the primary (active) key.

        Args:
            payload: Token payload
            expires_delta: Expiration delta (will be added to current time)

        Returns:
            Encoded JWT token
        """
        if expires_delta:
            payload["exp"] = datetime.utcnow() + expires_delta

        # Add key version to token so decoder knows which key to try first
        payload["kid"] = self.primary_key["id"]

        token = jwt.encode(
            payload,
            self.primary_key["secret"],
            algorithm=self.algorithm,
        )
        return token

    def decode(self, token: str) -> dict[str, Any] | None:
        """
        Decode a JWT token, trying keys in order: primary, then secondaries.

        Args:
            token: Encoded JWT token

        Returns:
            Decoded payload, or None if all keys fail

        Raises:
            JWTError: If token is malformed (not just invalid signature)
        """
        keys_to_try = []

        # Try to extract key ID from token header to prioritize
        try:
            # Decode without verification to get the key ID hint
            unverified = jwt.get_unverified_claims(token)
            hint_kid = unverified.get("kid")
            if hint_kid == self.primary_key["id"]:
                keys_to_try.append(self.primary_key)
            elif hint_kid and hint_kid in self.secondary_keys:
                keys_to_try.append(self.secondary_keys[hint_kid])
        except Exception:
            pass  # If we can't extract header, just try all keys

        # Add remaining keys
        keys_to_try.append(self.primary_key)
        for key_data in self.secondary_keys.values():
            if key_data not in keys_to_try:
                keys_to_try.append(key_data)

        # Try each key in order
        last_error = None
        for key_data in keys_to_try:
            try:
                payload = jwt.decode(
                    token,
                    key_data["secret"],
                    algorithms=[self.algorithm],
                )

                # Log if we had to use a secondary key (indicates old token)
                if key_data["id"] != self.primary_key["id"]:
                    logger.debug(f"Token validated with secondary key {key_data['id']}")

                return payload
            except JWTError as e:
                last_error = e
                continue  # Try next key

        # All keys failed
        if last_error:
            raise last_error
        return None

    def add_secondary_key(self, key_id: str, secret: str) -> None:
        """
        Add a secondary key for rotation support.

        During key rotation:
        1. Add the new key as secondary: add_secondary_key("v2", new_secret)
        2. Update primary to new key: rotate_to_key("v2")
        3. Old tokens (signed with v1) still validate via secondary key
        """
        self.secondary_keys[key_id] = {
            "id": key_id,
            "secret": secret,
            "active": True,
            "created_at": datetime.utcnow().isoformat(),
        }
        logger.info(f"Added secondary JWT key: {key_id}")

    def rotate_to_key(self, key_id: str) -> None:
        """
        Promote a secondary key to primary (after key rotation).

        Args:
            key_id: ID of the secondary key to promote
        """
        if key_id == self.primary_key["id"]:
            logger.warning(f"Key {key_id} is already primary")
            return

        if key_id not in self.secondary_keys:
            raise ValueError(f"Secondary key {key_id} not found")

        # Archive old primary as secondary (for decoding old tokens)
        old_primary_id = self.primary_key["id"]
        self.secondary_keys[old_primary_id] = self.primary_key.copy()
        self.secondary_keys[old_primary_id]["active"] = False  # Mark as inactive

        # Promote secondary to primary
        self.primary_key = self.secondary_keys.pop(key_id).copy()
        self.primary_key["active"] = True

        logger.warning(f"🔄 JWT key rotated: {old_primary_id} → {key_id}")

    def revoke_key(self, key_id: str) -> None:
        """
        Revoke a secondary key (e.g., after compromise).
        """
        if key_id == self.primary_key["id"]:
            raise ValueError("Cannot revoke the primary key; rotate first")

        if key_id in self.secondary_keys:
            del self.secondary_keys[key_id]
            logger.warning(f"🚫 JWT key revoked: {key_id}")

    def export_keys(self) -> dict[str, Any]:
        """Export all keys (for backup/rotation setup)"""
        return {
            "primary": self.primary_key,
            "secondary": self.secondary_keys,
        }


# Process-wide singleton
_jwt_manager: JWTKeyManager | None = None


def get_jwt_manager(primary_secret: str = None, algorithm: str = "HS256") -> JWTKeyManager:
    """Get or create the JWT key manager singleton"""
    global _jwt_manager
    if _jwt_manager is None:
        from app.config import settings

        secret = primary_secret or settings.jwt_secret_key
        _jwt_manager = JWTKeyManager(secret, algorithm)
    return _jwt_manager


__all__ = [
    "JWTKeyManager",
    "get_jwt_manager",
]
