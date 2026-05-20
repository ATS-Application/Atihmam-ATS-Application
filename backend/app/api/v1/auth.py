from fastapi import APIRouter, HTTPException, status
from app.models.user import UserLogin, UserRegister, TokenResponse
from app.core.security import create_access_token
from app.db.supabase_client import get_supabase

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


@router.get("/me")
async def get_me():
    # Implemented via Depends(get_current_user) in protected routes.
    # This stub exists for Swagger visibility.
    pass