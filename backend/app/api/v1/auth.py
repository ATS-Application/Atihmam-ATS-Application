# backend/app/api/v1/auth.py
from app.config import get_settings
# from backend.app.tasks.celery import get_settings
from fastapi import APIRouter, HTTPException, status
from app.models.user import UserLogin, UserRegister, TokenResponse, PasswordResetRequest, PasswordResetConfirm
from app.core.security import create_access_token
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

    access_token = create_access_token({"sub": user.id, "email": user.email})
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
    except Exception as e:
        # Temporarily expose error for debugging
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "If this email is registered, a reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(payload: PasswordResetConfirm):
    supabase_admin = get_supabase_admin()
    try:
        # Decode user id from the access token
        user = get_supabase().auth.get_user(payload.access_token)
        if not user or not user.user:
            raise ValueError("Invalid token")
        supabase_admin.auth.admin.update_user_by_id(
            user.user.id,
            {"password": payload.new_password}
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Lien invalide ou expiré.")
    return {"message": "Password updated successfully."}


@router.get("/me")
async def get_me():
    # Implemented via Depends(get_current_user) in protected routes.
    # This stub exists for Swagger visibility.
    pass