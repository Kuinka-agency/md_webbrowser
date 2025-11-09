"""API authentication and authorization middleware."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterator, Optional

if TYPE_CHECKING:
    from app.store import Store

from fastapi import Depends, Header, HTTPException, Request, status
from sqlmodel import Field, Session, SQLModel, select

from app.settings import Settings, settings as global_settings


class APIKey(SQLModel, table=True):
    """API key for authentication."""

    __tablename__ = "api_keys"

    id: int | None = Field(default=None, primary_key=True)
    key_hash: str = Field(index=True, unique=True)
    key_prefix: str = Field(index=True)  # First 12 chars for display (mdwb_XXXXXXX)
    name: str  # Human-readable name for the key
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime | None = None
    is_active: bool = Field(default=True)
    rate_limit: int | None = Field(default=None)  # Requests per minute, None = no limit
    owner: str | None = None  # Optional owner identifier


@dataclass
class AuthContext:
    """Authentication context for the current request."""

    api_key_id: int
    api_key_name: str
    api_key_prefix: str
    rate_limit: int | None
    owner: str | None


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_api_key() -> str:
    """Generate a new random API key.

    Format: mdwb_<32 random hex chars>
    Example: mdwb_a1b2c3d4e5f67890abcdef1234567890
    """
    random_part = secrets.token_hex(16)  # 32 hex chars
    return f"mdwb_{random_part}"


def create_api_key(
    session: Session,
    name: str,
    rate_limit: int | None = None,
    owner: str | None = None,
) -> tuple[str, APIKey]:
    """Create a new API key and store it in the database.

    Returns:
        tuple: (plain_text_key, db_record)

    Note: The plain text key is returned only once during creation.
    It cannot be retrieved later, only the hash is stored.
    """
    plain_key = generate_api_key()
    key_hash = hash_api_key(plain_key)
    key_prefix = plain_key[:12]  # mdwb_<first 7 hex chars>

    api_key = APIKey(
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=name,
        rate_limit=rate_limit,
        owner=owner,
    )

    session.add(api_key)
    session.commit()
    session.refresh(api_key)

    return plain_key, api_key


def verify_api_key(
    session: Session,
    api_key: str,
    update_threshold_seconds: int = 3600,
) -> Optional[APIKey]:
    """Verify an API key and return the corresponding record.

    Updates last_used_at timestamp only if it hasn't been updated recently,
    to avoid database writes on every request (performance optimization).

    Args:
        session: Database session
        api_key: API key to verify
        update_threshold_seconds: Only update timestamp if last update was
            more than this many seconds ago (default: 3600 = 1 hour)

    Returns:
        APIKey if valid and active, None otherwise
    """
    if not api_key or not api_key.startswith("mdwb_"):
        return None

    key_hash = hash_api_key(api_key)

    statement = select(APIKey).where(
        APIKey.key_hash == key_hash,
        APIKey.is_active.is_(True),
    )

    result = session.exec(statement).first()

    if result:
        # Update last used timestamp only if it's been a while since last update
        # This prevents a database write on every request (huge performance win)
        now = datetime.now(timezone.utc)
        should_update = (
            result.last_used_at is None
            or (now - result.last_used_at).total_seconds() > update_threshold_seconds
        )

        if should_update:
            result.last_used_at = now
            session.add(result)
            session.commit()

    return result


def revoke_api_key(session: Session, key_id: int) -> bool:
    """Revoke an API key by setting is_active to False.

    Returns:
        True if key was found and revoked, False otherwise
    """
    statement = select(APIKey).where(APIKey.id == key_id)
    api_key = session.exec(statement).first()

    if not api_key:
        return False

    api_key.is_active = False
    session.add(api_key)
    session.commit()

    return True


# Global store instance for database connection pooling
# Creating the engine is expensive, so we create it once and reuse it
_global_store: Optional["Store"] = None


def get_store() -> "Store":
    """Get or create the global Store instance.

    This ensures we only create one database engine for the entire application,
    enabling proper connection pooling and avoiding expensive engine initialization
    on every request.

    Returns:
        Store: Global store instance with reusable database engine
    """
    global _global_store

    if _global_store is None:
        from app.store import Store

        _global_store = Store()

    return _global_store


def get_db_session() -> Iterator[Session]:
    """FastAPI dependency to get database session.

    Uses the global Store instance to ensure database engine is reused
    across all requests, enabling proper connection pooling.

    Usage:
        @app.get("/endpoint")
        def endpoint(session: Session = Depends(get_db_session)):
            ...
    """
    store = get_store()  # Use global instance instead of creating new one
    with store.session() as session:
        yield session


async def get_auth_context(
    request: Request,
    session: Session = Depends(get_db_session),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    settings: Settings | None = None,
) -> AuthContext:
    """FastAPI dependency to get authentication context from request.

    Validates API key and returns authentication context.
    Raises HTTPException if authentication fails.

    Usage:
        @app.get("/protected")
        async def protected_endpoint(auth: AuthContext = Depends(get_auth_context)):
            return {"message": f"Authenticated as {auth.api_key_name}"}
    """
    active_settings = settings or global_settings

    # Check if authentication is required
    if not active_settings.REQUIRE_API_KEY:
        # Return a default context for unauthenticated access
        return AuthContext(
            api_key_id=0,
            api_key_name="anonymous",
            api_key_prefix="none",
            rate_limit=None,
            owner=None,
        )

    # Get API key from header
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Verify API key format
    if not x_api_key.startswith("mdwb_") or len(x_api_key) != 37:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Verify API key against database
    api_key_record = verify_api_key(session, x_api_key)
    if not api_key_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Return authentication context from database record
    # api_key_record.id should always be set for records from DB, but check for type safety
    if api_key_record.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error: API key missing ID",
        )

    return AuthContext(
        api_key_id=api_key_record.id,
        api_key_name=api_key_record.name,
        api_key_prefix=api_key_record.key_prefix,
        rate_limit=api_key_record.rate_limit,
        owner=api_key_record.owner,
    )


# CLI helper function for generating keys
def cli_generate_key(name: str, rate_limit: int | None = None, owner: str | None = None) -> None:
    """CLI function to generate a new API key.

    Usage:
        python -c "from app.auth import cli_generate_key; cli_generate_key('my-app')"
    """
    store = get_store()  # Use global store instance

    with store.session() as session:
        plain_key, api_key = create_api_key(session, name, rate_limit, owner)

        print("\n✅ API Key created successfully!")
        print(f"\nKey ID: {api_key.id}")
        print(f"Name: {api_key.name}")
        print(f"Prefix: {api_key.key_prefix}")
        print(f"Rate Limit: {api_key.rate_limit or 'None (unlimited)'}")
        print(f"Owner: {api_key.owner or 'None'}")
        print("\n🔑 API Key (save this, it won't be shown again):")
        print(f"\n  {plain_key}\n")
        print(f"Use this key in requests with header: X-API-Key: {plain_key}\n")
