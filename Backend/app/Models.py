from datetime import datetime
from sqlalchemy import Column, String, Text, Float, ForeignKey, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from .DB import Base
from pgvector.sqlalchemy import Vector   # en haut du fichier


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10), default="user")   # user | admin
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class News(Base):
    __tablename__ = "news"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)   # N55528
    category: Mapped[str] = mapped_column(String(50))
    subcategory: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embedding = Column(Vector(384), nullable=True)   # dans la classe News

class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)    # uuid
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("user_sessions.id"))
    news_id: Mapped[str] = mapped_column(ForeignKey("news.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20))    # click, like, share...
    weight: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class UserItemScore(Base):
    __tablename__ = "user_item_scores"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    news_id: Mapped[str] = mapped_column(ForeignKey("news.id"), primary_key=True)
    score: Mapped[float] = mapped_column(Float, default=0)
    last_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))