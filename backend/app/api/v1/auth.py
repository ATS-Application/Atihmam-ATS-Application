# backend/app/api/v1/auth.py
from app.config import get_settings
from fastapi import APIRouter, Depends, HTTPException, status
from app.models.user import (
    UserLogin,
    UserRegister,
    TokenResponse,
    PasswordResetRequest,
    PasswordResetConfirm,
)
from app.core.security import create_access_token, get_current_user
from app.db.supabase_client import get_supabase, get_supabase_admin

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister):
    supabase = get_supabase()

    try:
        auth_response = supabase.auth.sign_up({
            "email": payload.email,
            "password": payload.password,
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    user = auth_response.user
    if not user:
        raise HTTPException(status_code=400, detail="Registration failed")

    supabase.table("profiles").insert({
        "id": user.id,
        "email": user.email,
        "full_name": payload.full_name,
        "role": "recruiter",
    }).execute()

    return {"message": "Account created. Please verify your email."}


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin):
    supabase = get_supabase()

    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": payload.email,
            "password": payload.password,
        })
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    user = auth_response.user
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
        )

    # Fetch profile to embed full_name + role in JWT claims.
    # This allows the client to decode user info without a /me round-trip on login.
    profile_resp = (
        supabase.table("profiles")
        .select("full_name, role")
        .eq("id", user.id)
        .single()
        .execute()
    )
    profile = profile_resp.data or {}

    access_token = create_access_token({
        "sub": user.id,
        "email": user.email,
        "full_name": profile.get("full_name", ""),
        "role": profile.get("role", "recruiter"),
    })
    return TokenResponse(access_token=access_token)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(payload: PasswordResetRequest):
    supabase = get_supabase()
    settings = get_settings()

    try:
        supabase.auth.reset_password_for_email(
            payload.email,
            options={"redirect_to": f"{settings.frontend_url}/reset-password"},
        )
        return {"message": "If this email is registered, a reset link has been sent."}
    except Exception as e:
        print(f"[forgot_password] ERROR: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(payload: PasswordResetConfirm):
    supabase_admin = get_supabase_admin()

    try:
        user = get_supabase().auth.get_user(payload.access_token)
        if not user or not user.user:
            raise ValueError("Invalid token")
        supabase_admin.auth.admin.update_user_by_id(
            user.user.id,
            {"password": payload.new_password},
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Lien invalide ou expiré.")

    return {"message": "Password updated successfully."}


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    Returns the profile of the currently authenticated user.
    Used by the frontend to re-hydrate user state after page reload.
    """
    return current_user