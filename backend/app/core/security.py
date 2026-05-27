# backend/app/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Any
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.config import get_settings
from app.db.supabase_client import get_supabase
# Import the explicit exception class thrown by the Supabase client
from postgrest.exceptions import APIError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def create_access_token(data: dict[str, Any]) -> str:
    settings = get_settings()
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload.update({"exp": expire})
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
    user_id: str = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject",
        )

    supabase = get_supabase()
    
    try:
        # This will throw an APIError if 0 rows are found due to .single()
        response = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
        return response.data
        
    except APIError as e:
        # Check if it's the specific "0 rows found" PostgREST error
        if e.code == "PGRST116":
            
            # --- OPTION A: Auto-create the missing profile (Highly Recommended for local testing) ---
            try:
                # We fetch the email from auth.users to keep fields accurate
                auth_user = supabase.auth.admin.get_user_by_id(user_id)
                email = auth_user.user.email if auth_user and auth_user.user else "user@example.com"
                
                new_profile = supabase.table("profiles").insert({
                    "id": user_id,
                    "full_name": email.split("@")[0].capitalize(),
                    "role": "admin"  # Automatically makes your local session an admin
                }).execute()
                
                return new_profile.data[0]
            except Exception:
                # --- OPTION B: Fallback clean error if auto-insert fails ---
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authenticated user lacks a profile record in the database.",
                )
        else:
            # Re-raise the exception if it's a completely different database issue
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {e.message}"
            )


def require_role(*roles: str):
    """Usage: Depends(require_role("admin", "recruiter"))"""
    async def _check(user: dict = Depends(get_current_user)):
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required role: {roles}",
            )
        return user
    return _check