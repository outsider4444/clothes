from datetime import datetime, timedelta
from typing import Optional

import databases
import enum

import jwt
import sqlalchemy
from jwt import ExpiredSignatureError, InvalidTokenError

from pydantic import BaseModel, validator

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from decouple import config

from email_validator import validate_email as validate_e, EmailNotValidError

from passlib.context import CryptContext
from starlette.requests import Request

DATABASE_URL = f"postgresql://{config('DB_USER')}:{config('DB_PASSWORD')}@localhost:5432/clothes"

database = databases.Database(DATABASE_URL)

metadata = sqlalchemy.MetaData()


class UserRole(enum.Enum):
    super_admin = "super admin"
    admin = "admin"
    user = "user"


users = sqlalchemy.Table(
    "users",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("email", sqlalchemy.String(120), unique=True),
    sqlalchemy.Column("password", sqlalchemy.String(255)),
    sqlalchemy.Column("full_name", sqlalchemy.String(200)),
    sqlalchemy.Column("phone", sqlalchemy.String(13)),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now()),
    sqlalchemy.Column(
        "last_modified_at",
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    ),
    sqlalchemy.Column("role", sqlalchemy.Enum(UserRole), nullable=False, server_default=UserRole.user.name)
)


class ColorEnum(enum.Enum):
    pink = "pink"
    black = "black"
    white = "white"
    yellow = "yellow"


class SizeEnum(enum.Enum):
    xs = "xs"
    s = "s"
    m = "m"
    l = "l"
    xl = "xl"
    xxl = "xxl"


clothes = sqlalchemy.Table(
    "clothes",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("name", sqlalchemy.String(255)),
    sqlalchemy.Column("color", sqlalchemy.Enum(ColorEnum), nullable=False),
    sqlalchemy.Column("size", sqlalchemy.Enum(SizeEnum), nullable=False),
    sqlalchemy.Column("photo_url", sqlalchemy.String(255)),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime, nullable=False, server_default=sqlalchemy.func.now()),
    sqlalchemy.Column(
        "last_modified_at",
        sqlalchemy.DateTime,
        nullable=False,
        server_default=sqlalchemy.func.now(),
        onupdate=sqlalchemy.func.now(),
    ),
)


class EmailField(str):  # ???????????????? ??????????
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    def validate(cls, value) -> str:
        try:
            validate_e(value)
            return value
        except EmailNotValidError:
            raise ValueError("?????????? ?????????????? ???? ??????????")


class BaseUser(BaseModel):
    email: EmailField
    full_name: Optional[str]

    @validator("full_name")
    def validate_full_name(cls, value):  # cls - class
        try:
            first_name, last_name = value.split()
            return value
        except Exception:
            raise ValueError("?? ?????? ???????????? ???????? ???????????????????? ?????? ?? ??????????????")


class UserSignIn(BaseUser):
    password: str


class UserSignOut(BaseUser):
    phone: Optional[str]
    created_at: datetime
    last_modified_at: datetime


app = FastAPI()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class CustomHttpBearer(HTTPBearer):
    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials]:
        res = await super().__call__(request)
        try:
            payload = jwt.decode(res.credentials, config("JWT_SECRET"), algorithms=["HS256"])
            user = await database.fetch_one(users.select().where(users.c.id == payload["sub"]))
            request.state.user = user
            return payload
        except ExpiredSignatureError:
            raise HTTPException(401, "?????????? ???? ????????????????")
        except InvalidTokenError:
            raise HTTPException(401, "???? ???????????? ??????????")


oauth2_scheme = CustomHttpBearer()


def is_admin(request: Request):
    user = request.state.user
    if not user or user["role"] not in (UserRole.admin, UserRole.super_admin):
        raise HTTPException(403, "?? ?????? ?????? ?????????????? ?? ???????? ????????????????")


@app.get("/clothes/", dependencies=[Depends(oauth2_scheme)])
async def get_all_clothes():
    return await database.fetch_all(clothes.select())


class ClotheBase(BaseModel):
    name: str
    size: SizeEnum
    color: ColorEnum


class ClothesIn(ClotheBase):
    pass


class ClotheOut(ClotheBase):
    id: int
    created_at: datetime
    last_modified_at = datetime


@app.post("/clothes/",
          response_model=ClotheOut,
          dependencies=[Depends(oauth2_scheme),
                        Depends(is_admin)],
          status_code=201
          )
async def create_clothes(clothes_data: ClothesIn):
    id_ = await database.execute(clothes.insert().values(**clothes_data.dict()))
    return await database.fetch_one(clothes.select().where(clothes.c.id == id_))


def create_access_token(user):
    try:
        payload = {"sub": user["id"], "exp": datetime.utcnow() + timedelta(minutes=120)}
        return jwt.encode(payload, config("JWT_SECRET"), algorithm="HS256")
    except Exception as ex:
        raise ex


@app.on_event("startup")
async def startup():
    await database.connect()


@app.on_event("shutdown")
async def shutdown():
    await database.connect()


@app.get("/users/")
async def users_list():
    return await database.fetch_all(users.select())


@app.post("/register/", status_code=201)
async def create_user(user: UserSignIn):
    user.password = pwd_context.hash(user.password)
    query = users.insert().values(**user.dict())
    id = await database.execute(query)
    created_user = await database.fetch_one(users.select().where(users.c.id == id))
    token = create_access_token(created_user)
    return {
        "token": token
    }
