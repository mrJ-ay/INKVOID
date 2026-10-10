from pydantic import BaseModel


# =========================================================
# Auth
# =========================================================

class RegisterRequest(BaseModel):
    nickname: str
    password: str


class LoginRequest(BaseModel):
    nickname: str
    password: str


# =========================================================
# Article
# =========================================================

class ArticleRequest(BaseModel):
    title: str
    subtitle: str = ""
    author: str = ""
    date: str = ""
    content: str = ""
    image: str = ""