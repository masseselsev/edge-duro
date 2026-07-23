import os
from datetime import datetime, timedelta
from typing import Union, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
import jwt
import bcrypt
from sqlalchemy.orm import Session

from database import get_db, log_user_action
import models
import schemas
from version import VERSION

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secret-key-change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 24 hours

router = APIRouter()


def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)


def get_current_auth(request: Request = None, db: Session = Depends(get_db)) -> models.User:
    token = None
    if request:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
        else:
            token = request.cookies.get("admin_session")
            if not token:
                token = request.query_params.get("token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

        user = db.query(models.User).filter(models.User.username == username).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")


def require_admin(current_user: models.User = Depends(get_current_auth)) -> models.User:
    return current_user


def require_superadmin(current_user: models.User = Depends(get_current_auth)) -> models.User:
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires Superadmin privilege."
        )
    return current_user


# Auth & Session routes

@router.post("/api/auth/login")
def login(payload: schemas.LoginPayload, response: Response, request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    access_token = create_access_token(data={"sub": user.username})
    response.set_cookie(
        key="admin_session",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )

    log_user_action(db, user.username, "USER_LOGIN", f"Successful login for user '{user.username}'", request)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": schemas.UserResponse.model_validate(user)
    }


@router.post("/api/auth/logout")
def logout(response: Response, request: Request, current_user: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    response.delete_cookie(key="admin_session")
    log_user_action(db, current_user.username, "USER_LOGOUT", f"User '{current_user.username}' logged out", request)
    return {"status": "success", "message": "Logged out successfully"}


@router.get("/api/auth/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(require_admin)):
    return current_user


@router.get("/api/version")
def get_version():
    return {"version": VERSION, "server_name": "Edge-D.U.R.O."}


# User Management Endpoints

@router.get("/api/users", response_model=List[schemas.UserResponse], dependencies=[Depends(require_admin)])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).all()


@router.post("/api/users", response_model=schemas.UserResponse, dependencies=[Depends(require_superadmin)])
def create_user(payload: schemas.UserCreate, request: Request, current_user: models.User = Depends(require_superadmin), db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Username '{payload.username}' already exists.")

    db_user = models.User(
        username=payload.username,
        hashed_password=get_password_hash(payload.password),
        name=payload.name,
        phone=payload.phone,
        telegram_id=payload.telegram_id,
        comment=payload.comment,
        is_admin_plus=payload.is_admin_plus or False,
        is_superadmin=False
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    log_user_action(db, current_user.username, "CREATE_USER", f"Created user '{db_user.username}'", request)
    return db_user


@router.put("/api/users/profile", response_model=schemas.UserResponse)
def update_own_profile(
    payload: schemas.UserSelfUpdate,
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    if payload.name is not None:
        current_user.name = payload.name
    if payload.phone is not None:
        current_user.phone = payload.phone
    if payload.telegram_id is not None:
        current_user.telegram_id = payload.telegram_id
    if payload.password:
        current_user.hashed_password = get_password_hash(payload.password)

    db.commit()
    db.refresh(current_user)
    log_user_action(db, current_user.username, "UPDATE_PROFILE", "Updated own user profile", request)
    return current_user


@router.put("/api/users/{user_id}", response_model=schemas.UserResponse, dependencies=[Depends(require_superadmin)])
def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    request: Request,
    current_user: models.User = Depends(require_superadmin),
    db: Session = Depends(get_db)
):
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    if payload.name is not None:
        target.name = payload.name
    if payload.phone is not None:
        target.phone = payload.phone
    if payload.telegram_id is not None:
        target.telegram_id = payload.telegram_id
    if payload.comment is not None:
        target.comment = payload.comment
    if payload.is_admin_plus is not None:
        target.is_admin_plus = payload.is_admin_plus
    if payload.password:
        target.hashed_password = get_password_hash(payload.password)

    db.commit()
    db.refresh(target)
    log_user_action(db, current_user.username, "UPDATE_USER", f"Updated user ID {user_id} ('{target.username}')", request)
    return target


@router.delete("/api/users/{user_id}", dependencies=[Depends(require_superadmin)])
def delete_user(
    user_id: int,
    request: Request,
    current_user: models.User = Depends(require_superadmin),
    db: Session = Depends(get_db)
):
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.is_superadmin:
        raise HTTPException(status_code=400, detail="Cannot delete superadmin user account.")

    username = target.username
    db.delete(target)
    db.commit()
    log_user_action(db, current_user.username, "DELETE_USER", f"Deleted user '{username}'", request)
    return {"status": "success", "message": f"User '{username}' deleted successfully"}
