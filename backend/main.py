import json
import os
import boto3
import uuid
import urllib.error
import urllib.request
from urllib.parse import urlparse

from datetime import datetime, timedelta, timezone

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Header,
    UploadFile,
    File,
)

from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from pydantic import BaseModel

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from botocore.config import Config
from jose import jwt
from pwdlib import PasswordHash

from database import SessionLocal, engine
from models import Base, User, Article, Comment, Like, OneIDLink


# =========================================================
# DATABASE
# =========================================================

Base.metadata.create_all(bind=engine)


# =========================================================
# BANNED WORD TABLE
# =========================================================

with engine.begin() as connection:
    if engine.dialect.name == "sqlite":
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS banned_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word VARCHAR(100) NOT NULL UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
    else:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS banned_words (
                    id SERIAL PRIMARY KEY,
                    word VARCHAR(100) NOT NULL UNIQUE,
                    created_at TIMESTAMP WITH TIME ZONE
                )
                """
            )
        )


# =========================================================
# FASTAPI
# =========================================================

app = FastAPI(
    title="INKVOID API",
    description="INKVOID Fiction Writing API",
    version="1.0.0",
)


# =========================================================
# CORS
# =========================================================

# Set CORS_ORIGINS to comma-separated deployed frontend origins in production.
# Wildcard remains the local-development default; bearer tokens do not use cookies.
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# CONFIG
# =========================================================

SECRET_KEY = os.getenv("SECRET_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

if ENVIRONMENT == "production" and not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY must be set for a production deployment."
    )

if not SECRET_KEY:
    SECRET_KEY = "inkvoid-local-development-key-change-before-deploy"

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

ONEID_API_URL = os.getenv("ONEID_API_URL", "https://oneid-icvq.onrender.com").rstrip("/")


# =========================================================
# PASSWORD
# =========================================================

pwd_context = PasswordHash.recommended()


def hash_password(
    password: str,
) -> str:

    return pwd_context.hash(
        password
    )


def verify_password(
    password: str,
    password_hash: str,
) -> bool:

    return pwd_context.verify(
        password,
        password_hash,
    )


# =========================================================
# AUTH
# =========================================================

security = HTTPBearer()


class RejectOneIDRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def verify_oneid_access_token(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="ONEID 로그인이 필요합니다.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="ONEID 로그인이 필요합니다.")

    endpoint = urlparse(ONEID_API_URL)
    if endpoint.scheme != "https" and endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(status_code=503, detail="운영 환경의 ONEID 주소는 HTTPS여야 합니다.")

    request = urllib.request.Request(
        f"{ONEID_API_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        opener = urllib.request.build_opener(RejectOneIDRedirects)
        with opener.open(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(status_code=401, detail="ONEID 로그인이 만료되었습니다.") from exc
        raise HTTPException(status_code=503, detail="ONEID 계정 확인에 실패했습니다.") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="ONEID 서버에 연결할 수 없습니다.") from exc

    if not isinstance(payload, dict) or not payload.get("id"):
        raise HTTPException(status_code=401, detail="ONEID 계정을 확인할 수 없습니다.")
    return payload


def create_access_token(
    user_id: int,
):

    expire = (
        datetime.now(timezone.utc)
        + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    payload = {
        "sub": str(user_id),
        "mode": "oneid",
        "exp": expire,
    }

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def get_db():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(
        security
    ),
    db: Session = Depends(get_db),
):

    token = credentials.credentials

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        if payload.get("mode") != "oneid":
            raise HTTPException(status_code=401, detail="ONEID로 다시 로그인해 주세요.")

        user_id = payload.get("sub")

        if not user_id:

            raise HTTPException(
                status_code=401,
                detail="유효하지 않은 토큰입니다.",
            )

    except jwt.ExpiredSignatureError:

        raise HTTPException(
            status_code=401,
            detail="로그인이 만료되었습니다.",
        )

    except jwt.JWTError:

        raise HTTPException(
            status_code=401,
            detail="유효하지 않은 토큰입니다.",
        )

    try:

        user_id = int(user_id)

    except ValueError:

        raise HTTPException(
            status_code=401,
            detail="유효하지 않은 사용자입니다.",
        )

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=401,
            detail="사용자를 찾을 수 없습니다.",
        )

    if user.is_banned == 1:

        raise HTTPException(
            status_code=403,
            detail="정지된 계정입니다.",
        )

    return user


def get_admin_user(
    current_user: User = Depends(
        get_current_user
    ),
):
    if current_user.is_admin != 1:
        raise HTTPException(
            status_code=403,
            detail="ONEID 관리자 권한이 필요합니다.",
        )
    return current_user


# =========================================================
# BANNED WORD HELPERS
# =========================================================

def get_banned_words(
    db: Session,
):

    rows = db.execute(
        text(
            """
            SELECT
                id,
                word,
                created_at
            FROM banned_words
            ORDER BY id ASC
            """
        )
    ).mappings().all()

    return rows


def find_banned_word(
    db: Session,
    title: str = "",
    subtitle: str = "",
    content: str = "",
):

    combined_text = " ".join(
        [
            title or "",
            subtitle or "",
            content or "",
        ]
    ).casefold()

    rows = get_banned_words(db)

    for row in rows:

        banned_word = (
            row["word"] or ""
        ).strip()

        if not banned_word:
            continue

        if (
            banned_word.casefold()
            in combined_text
        ):
            return banned_word

    return None


def delete_articles_containing_word(
    db: Session,
    banned_word: str,
):

    articles = (
        db.query(Article)
        .all()
    )

    target = banned_word.casefold()

    deleted_count = 0

    for article in articles:

        combined_text = " ".join(
            [
                article.title or "",
                article.subtitle or "",
                article.content or "",
            ]
        ).casefold()

        if target in combined_text:

            db.query(Comment).filter(
                Comment.article_id
                == article.id
            ).delete(
                synchronize_session=False
            )

            db.delete(article)

            deleted_count += 1

    return deleted_count


# =========================================================
# REQUEST MODELS
# =========================================================

class RegisterRequest(BaseModel):

    nickname: str
    password: str


class LoginRequest(BaseModel):

    nickname: str
    password: str


class OneIDCompleteRequest(BaseModel):
    legacy_nickname: str | None = None
    legacy_password: str | None = None
    create_new: bool = False


class ArticleRequest(BaseModel):

    title: str
    subtitle: str = ""
    author: str = ""
    date: str = ""
    content: str = ""
    image: str | None = None


class CommentRequest(BaseModel):

    content: str


class BannedWordRequest(BaseModel):

    word: str


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():

    return {
        "message": "INKVOID API is running"
    }


# =========================================================
# REGISTER
# =========================================================

@app.post("/auth/register")
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=410, detail="ONEID 로그인으로 통합되었습니다.")

    nickname = request.nickname.strip()
    password = request.password

    if not nickname:

        raise HTTPException(
            status_code=400,
            detail="닉네임을 입력해주세요.",
        )

    if len(nickname) > 20:

        raise HTTPException(
            status_code=400,
            detail="닉네임은 20자 이하로 입력해주세요.",
        )

    if not password:

        raise HTTPException(
            status_code=400,
            detail="비밀번호를 입력해주세요.",
        )

    existing = (
        db.query(User)
        .filter(
            User.nickname == nickname
        )
        .first()
    )

    if existing:

        raise HTTPException(
            status_code=400,
            detail="이미 존재하는 닉네임입니다.",
        )

    user = User(
        nickname=nickname,
        password_hash=hash_password(
            password
        ),
        is_admin=0,
        is_banned=0,
    )

    db.add(user)

    db.commit()

    db.refresh(user)

    return {
        "message": "회원가입이 완료되었습니다.",
        "user": {
            "id": user.id,
            "nickname": user.nickname,
            "is_admin": user.is_admin,
            "is_banned": user.is_banned,
        },
    }


# =========================================================
# LOGIN
# =========================================================

@app.post("/auth/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=410, detail="ONEID 로그인으로 통합되었습니다.")

    nickname = request.nickname.strip()

    user = (
        db.query(User)
        .filter(
            User.nickname == nickname
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=401,
            detail="닉네임 또는 비밀번호가 올바르지 않습니다.",
        )

    if not verify_password(
        request.password,
        user.password_hash,
    ):

        raise HTTPException(
            status_code=401,
            detail="닉네임 또는 비밀번호가 올바르지 않습니다.",
        )

    if user.is_banned == 1:

        raise HTTPException(
            status_code=403,
            detail="정지된 계정입니다.",
        )

    token = create_access_token(
        user.id
    )

    return {
        "message": "로그인되었습니다.",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "nickname": user.nickname,
            "is_admin": user.is_admin,
            "is_banned": user.is_banned,
        },
    }


# =========================================================
# CURRENT USER
# =========================================================

@app.get("/auth/me")
def me(
    current_user: User = Depends(get_current_user),
    oneid_authorization: str | None = Header(default=None, alias="X-ONEID-Authorization"),
    db: Session = Depends(get_db),
):
    if oneid_authorization:
        try:
            oneid_user = verify_oneid_access_token(oneid_authorization)
            expected_admin = 1 if oneid_user.get("is_admin") else 0
            if current_user.is_admin != expected_admin:
                current_user.is_admin = expected_admin
                db.commit()
                db.refresh(current_user)
        except Exception:
            pass

    return {
        "id": current_user.id,
        "nickname": current_user.nickname,
        "is_admin": current_user.is_admin,
        "is_banned": current_user.is_banned,
        "created_at": current_user.created_at,
    }


@app.post("/auth/link-oneid")
def link_oneid(
    current_user: User = Depends(get_current_user),
    oneid_authorization: str | None = Header(default=None, alias="X-ONEID-Authorization"),
    db: Session = Depends(get_db),
):
    """Link an authenticated local account to its authenticated ONEID account."""
    oneid_user = verify_oneid_access_token(oneid_authorization)
    oneid_user_id = str(oneid_user["id"])
    nickname = str(oneid_user.get("nickname") or "").strip()
    if not nickname or len(nickname) > 20:
        raise HTTPException(status_code=409, detail="ONEID 닉네임은 1~20자로 맞춘 뒤 연결해 주세요.")

    if db.query(OneIDLink).filter(OneIDLink.user_id == current_user.id).first():
        raise HTTPException(status_code=409, detail="이 사이트 계정은 이미 ONEID에 연결되어 있습니다.")
    if db.query(OneIDLink).filter(OneIDLink.oneid_user_id == oneid_user_id).first():
        raise HTTPException(status_code=409, detail="이 ONEID 계정은 이미 다른 사이트 계정에 연결되어 있습니다.")

    nickname_owner = db.query(User).filter(User.nickname == nickname, User.id != current_user.id).first()
    if nickname_owner:
        raise HTTPException(status_code=409, detail="ONEID 닉네임이 이 사이트의 다른 계정에서 사용 중입니다.")

    current_user.nickname = nickname
    current_user.is_admin = 1 if oneid_user.get("is_admin") else 0
    db.add(OneIDLink(oneid_user_id=oneid_user_id, user_id=current_user.id))
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="계정 연결을 저장하지 못했습니다. 이미 연결되었는지 새로고침해 확인해 주세요.") from exc

    return {"message": "ONEID 계정이 연결되었습니다.", "user": {"id": current_user.id, "nickname": nickname, "oneid_user_id": oneid_user_id}}


@app.post("/auth/oneid/complete")
def complete_oneid_login(
    request: OneIDCompleteRequest = OneIDCompleteRequest(),
    oneid_authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    oneid_user = verify_oneid_access_token(oneid_authorization)
    oneid_user_id = str(oneid_user["id"])
    nickname = str(oneid_user.get("nickname") or "").strip()
    if not nickname or len(nickname) > 20:
        raise HTTPException(status_code=409, detail="ONEID 닉네임을 1~20자로 정한 뒤 로그인해 주세요.")

    link = db.query(OneIDLink).filter(OneIDLink.oneid_user_id == oneid_user_id).first()
    user = db.query(User).filter(User.id == link.user_id).first() if link else None

    # 기존 계정 명시적 연결 요청인 경우
    if not user and request.legacy_nickname and request.legacy_password:
        user = db.query(User).filter(User.nickname == request.legacy_nickname.strip()).first()
        if not user or not verify_password(request.legacy_password, user.password_hash):
            raise HTTPException(status_code=401, detail="기존 사이트 닉네임 또는 비밀번호가 올바르지 않습니다.")
        if user.is_banned == 1:
            raise HTTPException(status_code=403, detail="이 사이트에서 이용 정지된 계정입니다.")
        nickname_owner = db.query(User).filter(User.nickname == nickname, User.id != user.id).first()
        if nickname_owner:
            raise HTTPException(status_code=409, detail="ONEID 닉네임이 다른 기존 회원과 겹칩니다. 사이트 관리자의 확인이 필요합니다.")
        user.nickname = nickname
        user.is_admin = 1 if oneid_user.get("is_admin") else 0
        db.add(OneIDLink(oneid_user_id=oneid_user_id, user_id=user.id))

    # 아직 연결되지 않은 경우: FAKEPRESS/PIGSTY처럼 자동 매핑 또는 자동 생성 (원클릭 SSO)
    if not user:
        existing_user = db.query(User).filter(User.nickname == nickname).first()
        if existing_user and not db.query(OneIDLink).filter(OneIDLink.user_id == existing_user.id).first():
            user = existing_user
            db.add(OneIDLink(oneid_user_id=oneid_user_id, user_id=user.id))
        else:
            candidate = nickname[:20]
            while db.query(User).filter(User.nickname == candidate).first():
                suffix = "_" + uuid.uuid4().hex[:4]
                candidate = nickname[:20 - len(suffix)] + suffix

            user = User(
                nickname=candidate,
                password_hash=hash_password(uuid.uuid4().hex + uuid.uuid4().hex),
                is_admin=1 if oneid_user.get("is_admin") else 0,
                is_banned=0,
            )
            db.add(user)
            db.flush()
            db.add(OneIDLink(oneid_user_id=oneid_user_id, user_id=user.id))

    if user.is_banned == 1:
        raise HTTPException(status_code=403, detail="이 사이트에서 이용 정지된 계정입니다.")

    expected_admin = 1 if oneid_user.get("is_admin") else 0
    if user.is_admin != expected_admin:
        user.is_admin = expected_admin

    try:
        db.commit()
        db.refresh(user)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="ONEID 계정을 이 사이트에 연결하지 못했습니다.") from exc

    return {"access_token": create_access_token(user.id), "token_type": "bearer", "user": {"id": user.id, "nickname": user.nickname, "is_admin": user.is_admin, "is_banned": user.is_banned}}


# =========================================================
# NEON OBJECT STORAGE
# =========================================================

STORAGE_BUCKET = os.getenv("NEON_STORAGE_BUCKET", "inkvoid-images")


def get_storage_client():
    endpoint = os.getenv("AWS_ENDPOINT_URL_S3")
    if not endpoint or not os.getenv("AWS_ACCESS_KEY_ID") or not os.getenv("AWS_SECRET_ACCESS_KEY"):
        raise HTTPException(status_code=503, detail="Neon 이미지 저장소 설정이 없습니다.")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def create_banner_url(key: str | None):
    if not key:
        return None
    try:
        return get_storage_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": STORAGE_BUCKET, "Key": key},
            ExpiresIn=3600,
        )
    except Exception as error:
        print("NEON IMAGE URL ERROR:", error)
        return None


# =========================================================
# IMAGE UPLOAD
# =========================================================

@app.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    allowed_types = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
    }
    extension = allowed_types.get(file.content_type or "")
    if not extension:
        raise HTTPException(status_code=400, detail="JPG, PNG, WEBP, GIF 이미지 파일만 업로드할 수 있습니다.")

    contents = await file.read(5 * 1024 * 1024 + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="이미지는 5MB 이하로 업로드해 주세요.")

    key = f"banners/{current_user.id}/{uuid.uuid4().hex}.{extension}"
    try:
        client = get_storage_client()
        client.put_object(
            Bucket=STORAGE_BUCKET,
            Key=key,
            Body=contents,
            ContentType=file.content_type,
            CacheControl="private, max-age=3600",
        )
        return {
            "message": "배너 이미지가 업로드되었습니다.",
            "image": key,
            "banner_url": create_banner_url(key),
        }
    except HTTPException:
        raise
    except Exception as error:
        print("NEON IMAGE UPLOAD ERROR:", error)
        raise HTTPException(status_code=500, detail="배너 이미지 업로드에 실패했습니다.")


# =========================================================
# PUBLICATION HELPERS
# =========================================================

def article_is_public(article: Article) -> bool:
    try:
        payload = json.loads(article.content or "")
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("is_public") is True


def serialize_article(article: Article):
    return {
        "id": article.id,
        "title": article.title,
        "subtitle": article.subtitle,
        "author": article.author,
        "date": article.date,
        "content": article.content,
        "image": article.image,
        "banner_url": create_banner_url(article.image),
        "owner_id": article.owner_id,
        "created_at": article.created_at,
        "updated_at": article.updated_at,
    }


# =========================================================
# GET PUBLIC ARTICLES
# =========================================================

@app.get("/articles")
def get_articles(
    db: Session = Depends(get_db),
):
    articles = (
        db.query(Article)
        .order_by(Article.created_at.desc())
        .all()
    )
    return [serialize_article(article) for article in articles if article_is_public(article)]


# =========================================================
# GET OWNER'S ARTICLES
# =========================================================

@app.get("/my/articles")
def get_my_articles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    articles = (
        db.query(Article)
        .filter(Article.owner_id == current_user.id)
        .order_by(Article.updated_at.desc())
        .all()
    )
    return [serialize_article(article) for article in articles]


# =========================================================
# GET ARTICLE
# =========================================================

@app.get("/articles/{article_id}")
def get_article(
    article_id: int,
    db: Session = Depends(get_db),
):

    article = (
        db.query(Article)
        .filter(
            Article.id == article_id
        )
        .first()
    )

    if not article or not article_is_public(article):

        raise HTTPException(
            status_code=404,
            detail="기사를 찾을 수 없습니다.",
        )

    return serialize_article(article)


# =========================================================
# CREATE ARTICLE
# =========================================================

@app.post("/articles")
def create_article(
    request: ArticleRequest,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):

    if request.image and not request.image.startswith(f"banners/{current_user.id}/"):
        raise HTTPException(status_code=403, detail="다른 계정의 배너 이미지는 연결할 수 없습니다.")

    # -----------------------------------------------------
    # 금지어 검사
    # -----------------------------------------------------

    banned_word = find_banned_word(
        db,
        request.title,
        request.subtitle,
        request.content,
    )

    if banned_word:

        raise HTTPException(
            status_code=400,
            detail=(
                f'금지어 "{banned_word}"가 포함되어 있어 '
                "기사를 등록할 수 없습니다."
            ),
        )

    # -----------------------------------------------------
    # 기사 작성 쿨타임
    # -----------------------------------------------------

    now = datetime.now(
        timezone.utc
    )

    # -----------------------------------------------------
    # 기사 생성
    # -----------------------------------------------------

    article = Article(
        title=request.title,
        subtitle=request.subtitle,
        author=request.author,
        date=request.date,
        content=request.content,
        image=request.image,
        owner_id=current_user.id,
    )

    db.add(article)

    current_user.last_article_created_at = now

    db.commit()

    db.refresh(article)

    return {
        "message": "기사가 저장되었습니다.",
        "article": {
            "id": article.id,
            "title": article.title,
            "subtitle": article.subtitle,
            "author": article.author,
            "date": article.date,
            "content": article.content,
            "image": article.image,
            "owner_id": article.owner_id,
            "created_at": article.created_at,
            "updated_at": article.updated_at,
        },
    }


# =========================================================
# UPDATE ARTICLE
# =========================================================

@app.put("/articles/{article_id}")
def update_article(
    article_id: int,
    request: ArticleRequest,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):

    article = (
        db.query(Article)
        .filter(
            Article.id == article_id
        )
        .first()
    )

    if not article:

        raise HTTPException(
            status_code=404,
            detail="기사를 찾을 수 없습니다.",
        )

    if (
        article.owner_id
        != current_user.id
        and current_user.is_admin != 1
    ):

        raise HTTPException(
            status_code=403,
            detail="수정 권한이 없습니다.",
        )

    if request.image and not request.image.startswith(f"banners/{current_user.id}/"):
        raise HTTPException(status_code=403, detail="다른 계정의 배너 이미지는 연결할 수 없습니다.")

    # -----------------------------------------------------
    # 금지어 검사
    # -----------------------------------------------------

    banned_word = find_banned_word(
        db,
        request.title,
        request.subtitle,
        request.content,
    )

    if banned_word:

        raise HTTPException(
            status_code=400,
            detail=(
                f'금지어 "{banned_word}"가 포함되어 있어 '
                "기사를 수정할 수 없습니다."
            ),
        )

    article.title = request.title
    article.subtitle = request.subtitle
    article.author = request.author
    article.date = request.date
    article.content = request.content

    if request.image is not None:

        article.image = request.image

    db.commit()

    db.refresh(article)

    return {
        "message": "기사가 수정되었습니다.",
        "article": {
            "id": article.id,
            "title": article.title,
            "subtitle": article.subtitle,
            "author": article.author,
            "date": article.date,
            "content": article.content,
            "image": article.image,
            "owner_id": article.owner_id,
            "created_at": article.created_at,
            "updated_at": article.updated_at,
        },
    }


# =========================================================
# DELETE ARTICLE
# =========================================================

@app.delete("/articles/{article_id}")
def delete_article(
    article_id: int,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):

    article = (
        db.query(Article)
        .filter(
            Article.id == article_id
        )
        .first()
    )

    if not article:

        raise HTTPException(
            status_code=404,
            detail="기사를 찾을 수 없습니다.",
        )

    if (
        article.owner_id
        != current_user.id
        and current_user.is_admin != 1
    ):

        raise HTTPException(
            status_code=403,
            detail="삭제 권한이 없습니다.",
        )

    db.query(Comment).filter(
        Comment.article_id == article_id
    ).delete(
        synchronize_session=False
    )

    db.query(Like).filter(Like.article_id == article_id).delete(synchronize_session=False)

    db.delete(article)

    db.commit()

    return {
        "message": "기사가 삭제되었습니다."
    }


# =========================================================
# GET COMMENTS
# =========================================================

@app.get("/articles/{article_id}/comments")
def get_comments(
    article_id: int,
    db: Session = Depends(get_db),
):

    article = (
        db.query(Article)
        .filter(
            Article.id == article_id
        )
        .first()
    )

    if not article or not article_is_public(article):

        raise HTTPException(
            status_code=404,
            detail="기사를 찾을 수 없습니다.",
        )

    comments = (
        db.query(Comment, User)
        .join(
            User,
            Comment.owner_id == User.id,
        )
        .filter(
            Comment.article_id
            == article_id
        )
        .order_by(
            Comment.created_at.asc()
        )
        .all()
    )

    return [
        {
            "id": comment.id,
            "content": comment.content,
            "article_id":
                comment.article_id,
            "owner_id":
                comment.owner_id,
            "nickname":
                user.nickname,
            "created_at":
                comment.created_at,
        }
        for comment, user in comments
    ]


# =========================================================
# CREATE COMMENT
# =========================================================

@app.post("/articles/{article_id}/comments")
def create_comment(
    article_id: int,
    request: CommentRequest,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):

    article = (
        db.query(Article)
        .filter(
            Article.id == article_id
        )
        .first()
    )

    if not article or not article_is_public(article):

        raise HTTPException(
            status_code=404,
            detail="기사를 찾을 수 없습니다.",
        )

    content = request.content.strip()

    if not content:

        raise HTTPException(
            status_code=400,
            detail="댓글 내용을 입력해주세요.",
        )

    if len(content) > 1000:

        raise HTTPException(
            status_code=400,
            detail="댓글은 1000자 이하로 입력해주세요.",
        )

    # -----------------------------------------------------
    # 최근 댓글 조회
    # -----------------------------------------------------

    last_comment = (
        db.query(Comment)
        .filter(
            Comment.owner_id
            == current_user.id
        )
        .order_by(
            Comment.created_at.desc()
        )
        .first()
    )

    now = datetime.now(
        timezone.utc
    )

    # -----------------------------------------------------
    # 댓글 10초 쿨타임
    # -----------------------------------------------------

    if (
        last_comment
        and last_comment.created_at
    ):

        last_time = (
            last_comment.created_at
        )

        if last_time.tzinfo is None:

            last_time = last_time.replace(
                tzinfo=timezone.utc
            )

        elapsed = (
            now - last_time
        )

        cooldown = timedelta(
            seconds=10
        )

        if elapsed < cooldown:

            remaining_seconds = int(
                (
                    cooldown - elapsed
                ).total_seconds()
            )

            raise HTTPException(
                status_code=429,
                detail=(
                    "댓글 도배 방지를 위해 "
                    f"{remaining_seconds}초 후 "
                    "다시 작성할 수 있습니다."
                ),
            )

    comment = Comment(
        content=content,
        article_id=article_id,
        owner_id=current_user.id,
    )

    db.add(comment)

    db.commit()

    db.refresh(comment)

    return {
        "message": "댓글이 작성되었습니다.",
        "comment": {
            "id": comment.id,
            "content": comment.content,
            "article_id":
                comment.article_id,
            "owner_id":
                comment.owner_id,
            "nickname":
                current_user.nickname,
            "created_at":
                comment.created_at,
        },
    }


# =========================================================
# DELETE COMMENT
# =========================================================

@app.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: int,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):

    comment = (
        db.query(Comment)
        .filter(
            Comment.id == comment_id
        )
        .first()
    )

    if not comment:

        raise HTTPException(
            status_code=404,
            detail="댓글을 찾을 수 없습니다.",
        )

    if (
        comment.owner_id
        != current_user.id
        and current_user.is_admin != 1
    ):

        raise HTTPException(
            status_code=403,
            detail="댓글 삭제 권한이 없습니다.",
        )

    db.delete(comment)

    db.commit()

    return {
        "message": "댓글이 삭제되었습니다."
    }


# =========================================================
# ARTICLE LIKES
# =========================================================

@app.get("/articles/{article_id}/likes")
def get_article_likes(
    article_id: int,
    db: Session = Depends(get_db),
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article or not article_is_public(article):
        raise HTTPException(status_code=404, detail="작품을 찾을 수 없습니다.")
    count = db.query(Like).filter(Like.article_id == article_id).count()
    return {"count": count}


@app.get("/articles/{article_id}/likes/me")
def get_my_article_like(
    article_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article or not article_is_public(article):
        raise HTTPException(status_code=404, detail="작품을 찾을 수 없습니다.")
    liked = db.query(Like).filter(
        Like.article_id == article_id,
        Like.owner_id == current_user.id,
    ).first() is not None
    return {"liked": liked}


@app.post("/articles/{article_id}/likes")
def like_article(
    article_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article or not article_is_public(article):
        raise HTTPException(status_code=404, detail="작품을 찾을 수 없습니다.")

    existing = db.query(Like).filter(
        Like.article_id == article_id,
        Like.owner_id == current_user.id,
    ).first()
    if not existing:
        db.add(Like(article_id=article_id, owner_id=current_user.id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    count = db.query(Like).filter(Like.article_id == article_id).count()
    return {"liked": True, "count": count}


@app.delete("/articles/{article_id}/likes")
def unlike_article(
    article_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article or not article_is_public(article):
        raise HTTPException(status_code=404, detail="작품을 찾을 수 없습니다.")

    db.query(Like).filter(
        Like.article_id == article_id,
        Like.owner_id == current_user.id,
    ).delete(synchronize_session=False)
    db.commit()
    count = db.query(Like).filter(Like.article_id == article_id).count()
    return {"liked": False, "count": count}


# =========================================================
# ADMIN USERS
# =========================================================

@app.get("/admin/users")
def admin_users(
    admin: User = Depends(
        get_admin_user
    ),
    db: Session = Depends(get_db),
):

    users = (
        db.query(User)
        .order_by(
            User.id.asc()
        )
        .all()
    )

    return [
        {
            "id": user.id,
            "nickname": user.nickname,
            "is_admin": user.is_admin,
            "is_banned": user.is_banned,
            "created_at": user.created_at,
        }
        for user in users
    ]


# =========================================================
# MAKE ADMIN
# =========================================================

@app.post("/admin/make-admin/{user_id}")
def make_admin(
    user_id: int,
    admin: User = Depends(
        get_admin_user
    ),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=410, detail="전체 관리자 권한은 ONEID에서 관리합니다.")

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="사용자를 찾을 수 없습니다.",
        )

    user.is_admin = 1

    db.commit()

    db.refresh(user)

    return {
        "message":
            "관리자로 지정되었습니다.",
        "user": {
            "id": user.id,
            "nickname": user.nickname,
            "is_admin": user.is_admin,
        },
    }


# =========================================================
# REMOVE ADMIN
# =========================================================

@app.post("/admin/remove-admin/{user_id}")
def remove_admin(
    user_id: int,
    admin: User = Depends(
        get_admin_user
    ),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=410, detail="전체 관리자 권한은 ONEID에서 관리합니다.")

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="사용자를 찾을 수 없습니다.",
        )

    if user.id == admin.id:

        raise HTTPException(
            status_code=400,
            detail="자기 자신의 관리자 권한은 해제할 수 없습니다.",
        )

    user.is_admin = 0

    db.commit()

    db.refresh(user)

    return {
        "message":
            "관리자 권한이 해제되었습니다.",
        "user": {
            "id": user.id,
            "nickname": user.nickname,
            "is_admin": user.is_admin,
        },
    }


# =========================================================
# BAN USER
# =========================================================

@app.post("/admin/ban/{user_id}")
def ban_user(
    user_id: int,
    admin: User = Depends(
        get_admin_user
    ),
    db: Session = Depends(get_db),
):

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="사용자를 찾을 수 없습니다.",
        )

    if user.id == admin.id:

        raise HTTPException(
            status_code=400,
            detail="자기 자신을 정지할 수 없습니다.",
        )

    user.is_banned = 1

    db.commit()

    db.refresh(user)

    return {
        "message":
            "사용자가 정지되었습니다.",
        "user": {
            "id": user.id,
            "nickname": user.nickname,
            "is_banned": user.is_banned,
        },
    }


# =========================================================
# UNBAN USER
# =========================================================

@app.post("/admin/unban/{user_id}")
def unban_user(
    user_id: int,
    admin: User = Depends(
        get_admin_user
    ),
    db: Session = Depends(get_db),
):

    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .first()
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="사용자를 찾을 수 없습니다.",
        )

    user.is_banned = 0

    db.commit()

    db.refresh(user)

    return {
        "message":
            "사용자 정지가 해제되었습니다.",
        "user": {
            "id": user.id,
            "nickname": user.nickname,
            "is_banned": user.is_banned,
        },
    }


# =========================================================
# ADMIN BANNED WORDS
# =========================================================

@app.get("/admin/banned-words")
def admin_get_banned_words(
    admin: User = Depends(
        get_admin_user
    ),
    db: Session = Depends(get_db),
):

    rows = get_banned_words(db)

    return [
        {
            "id": row["id"],
            "word": row["word"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


# =========================================================
# ADD BANNED WORD
# =========================================================

@app.post("/admin/banned-words")
def admin_add_banned_word(
    request: BannedWordRequest,
    admin: User = Depends(
        get_admin_user
    ),
    db: Session = Depends(get_db),
):

    word = request.word.strip()

    if not word:

        raise HTTPException(
            status_code=400,
            detail="금지어를 입력해주세요.",
        )

    if len(word) > 100:

        raise HTTPException(
            status_code=400,
            detail="금지어는 100자 이하로 입력해주세요.",
        )

    # -----------------------------------------------------
    # 중복 검사
    # -----------------------------------------------------

    existing_rows = get_banned_words(db)

    for row in existing_rows:

        existing_word = (
            row["word"] or ""
        ).strip()

        if (
            existing_word.casefold()
            == word.casefold()
        ):

            raise HTTPException(
                status_code=400,
                detail="이미 등록된 금지어입니다.",
            )

    # -----------------------------------------------------
    # 금지어 저장
    # -----------------------------------------------------

    try:

        db.execute(
            text(
                """
                INSERT INTO banned_words
                (
                    word,
                    created_at
                )
                VALUES
                (
                    :word,
                    :created_at
                )
                """
            ),
            {
                "word": word,
                "created_at":
                    datetime.now(
                        timezone.utc
                    ),
            },
        )

        db.commit()

    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=400,
            detail="금지어 저장에 실패했습니다.",
        )

    # -----------------------------------------------------
    # 기존 기사 자동 삭제
    # -----------------------------------------------------

    deleted_count = (
        delete_articles_containing_word(
            db,
            word,
        )
    )

    db.commit()

    return {
        "message": (
            f'"{word}" 금지어가 등록되었습니다.'
        ),
        "word": word,
        "deleted_articles":
            deleted_count,
    }


# =========================================================
# DELETE BANNED WORD
# =========================================================

@app.delete("/admin/banned-words/{word_id}")
def admin_delete_banned_word(
    word_id: int,
    admin: User = Depends(
        get_admin_user
    ),
    db: Session = Depends(get_db),
):

    row = db.execute(
        text(
            """
            SELECT
                id,
                word
            FROM banned_words
            WHERE id = :id
            """
        ),
        {
            "id": word_id
        },
    ).mappings().first()

    if not row:

        raise HTTPException(
            status_code=404,
            detail="금지어를 찾을 수 없습니다.",
        )

    db.execute(
        text(
            """
            DELETE FROM banned_words
            WHERE id = :id
            """
        ),
        {
            "id": word_id
        },
    )

    db.commit()

    return {
        "message": (
            f'"{row["word"]}" 금지어가 삭제되었습니다.'
        )
    }


# =========================================================
# ADMIN ARTICLES
# =========================================================

@app.get("/admin/articles")
def admin_articles(
    admin: User = Depends(
        get_admin_user
    ),
    db: Session = Depends(get_db),
):

    articles = (
        db.query(Article)
        .order_by(
            Article.created_at.desc()
        )
        .all()
    )

    return [
        {
            "id": article.id,
            "title": article.title,
            "subtitle": article.subtitle,
            "author": article.author,
            "date": article.date,
            "content": article.content,
            "image": article.image,
            "owner_id": article.owner_id,
            "created_at": article.created_at,
            "updated_at": article.updated_at,
        }
        for article in articles
    ]


# =========================================================
# ADMIN DELETE ARTICLE
# =========================================================

@app.delete("/admin/articles/{article_id}")
def admin_delete_article(
    article_id: int,
    admin: User = Depends(
        get_admin_user
    ),
    db: Session = Depends(get_db),
):

    article = (
        db.query(Article)
        .filter(
            Article.id == article_id
        )
        .first()
    )

    if not article:

        raise HTTPException(
            status_code=404,
            detail="기사를 찾을 수 없습니다.",
        )

    db.query(Comment).filter(
        Comment.article_id == article_id
    ).delete(
        synchronize_session=False
    )

    db.query(Like).filter(Like.article_id == article_id).delete(synchronize_session=False)

    db.delete(article)

    db.commit()

    return {
        "message": "기사가 삭제되었습니다."
    }


# =========================================================
# ADMIN DELETE ALL ARTICLES
# =========================================================

@app.delete("/admin/articles")
def admin_delete_all_articles(
    admin: User = Depends(
        get_admin_user
    ),
    db: Session = Depends(get_db),
):

    articles = (
        db.query(Article)
        .all()
    )

    deleted_count = len(
        articles
    )

    db.query(Comment).delete(
        synchronize_session=False
    )

    db.query(Like).delete(synchronize_session=False)

    db.query(Article).delete(
        synchronize_session=False
    )

    db.commit()

    return {
        "message":
            "모든 뉴스가 삭제되었습니다.",
        "deleted_count":
            deleted_count,
    }
