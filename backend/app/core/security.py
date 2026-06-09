# backend/app/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from postgrest.exceptions import APIError

from app.config import get_settings
from app.db.supabase_client import get_supabase, get_supabase_admin

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def create_access_token(data: dict[str, Any]) -> str:
    settings = get_settings()
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    payload = decode_access_token(token)
    user_id: str | None = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )

    supabase = get_supabase()

    try:
        response = (
            supabase.table("profiles")
            .select("id, email, full_name, role")
            .eq("id", user_id)
            .single()
            .execute()
        )
        return response.data

    except APIError as e:
        if e.code != "PGRST116":
            # Not a "0 rows" error — something else went wrong at the DB level
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {e.message}",
            )

    # PGRST116: profile row is missing for a valid auth user.
    # Auto-create it using the admin client (anon client cannot call auth.admin).
    supabase_admin = get_supabase_admin()
    try:
        auth_response = supabase_admin.auth.admin.get_user_by_id(user_id)
        email = (
            auth_response.user.email
            if auth_response and auth_response.user
            else payload.get("email", "unknown@example.com")
        )
        insert_resp = (
            supabase.table("profiles")
            .insert({
                "id": user_id,
                "email": email,
                "full_name": email.split("@")[0].capitalize(),
                # Safe default — never auto-elevate to admin
                "role": "recruiter",
            })
            .execute()
        )
        return insert_resp.data[0]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user has no profile record.",
        ) from exc


def require_role(*roles: str):
    """
    Role-based access control dependency.

    Usage:
        @router.get("/admin-only")
        async def admin_route(user: dict = Depends(require_role("admin"))):
            ...

        @router.get("/staff")
        async def staff_route(user: dict = Depends(require_role("admin", "recruiter"))):
            ...
    """
    async def _check(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access requires one of roles: {roles}",
            )
        return user
    return _check