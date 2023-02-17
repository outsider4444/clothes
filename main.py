from datetime import datetime
from typing import Optional

import databases
import enum
import sqlalchemy

from pydantic import BaseModel, validator

from fastapi import FastAPI
from decouple import config

from email_validator import validate_email as validate_e, EmailNotValidError

DATABASE_URL = f"postgresql://{config('DB_USER')}:{config('DB_PASSWORD')}@localhost:5432/clothes"

database = databases.Database(DATABASE_URL)

metadata = sqlalchemy.MetaData()

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


class EmailField(str):  # Проверка почты
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    def validate(cls, value) -> str:
        try:
            validate_e(value)
            return value
        except EmailNotValidError:
            raise ValueError("Почта указана не верно")


class BaseUser(BaseModel):
    email: EmailField
    full_name: Optional[str]

    @validator("full_name")
    def validate_full_name(cls, value):  # cls - class
        try:
            first_name, last_name = value.split()
            return value
        except Exception:
            raise ValueError("У вас должны быть корректные имя и фамилия")


class UserSignIn(BaseUser):
    password: str


class UserSignOut(BaseUser):
    phone: Optional[str]
    created_at: datetime
    last_modified_at: datetime


app = FastAPI()


@app.on_event("startup")
async def startup():
    await database.connect()


@app.on_event("shutdown")
async def shutdown():
    await database.connect()


@app.post("/register/", response_model=UserSignOut)
async def create_user(user: UserSignIn):
    query = users.insert().values(**user.dict())
    id = await database.execute(query)
    created_user = await database.fetch_one(users.select().where(users.c.id == id))
    return created_user


@app.get("/users/")
async def users_list():
    query = users.select()
    return await database.fetch_all(query)
