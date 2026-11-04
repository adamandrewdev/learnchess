"""Tables. Trap data is stored from P1 even though the profile page is P2 (PLAN D12)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    player_color: Mapped[str] = mapped_column(String(5))  # "white" | "black"
    bot_elo: Mapped[int] = mapped_column(Integer)
    bot_temperature: Mapped[float] = mapped_column(Float)
    # player_turn -> awaiting_reason -> coach_replied -> player_turn ...; finished at the end
    status: Mapped[str] = mapped_column(String(20), default="player_turn")
    result: Mapped[str | None] = mapped_column(String(10))  # "1-0" | "0-1" | "1/2-1/2"
    end_reason: Mapped[str | None] = mapped_column(String(30))
    # Rating (PLAN D26). Only rated games change it; filled in when a rated game finishes.
    rated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    rating_before: Mapped[int | None] = mapped_column(Integer)
    rating_after: Mapped[int | None] = mapped_column(Integer)
    rating_weight: Mapped[float | None] = mapped_column(Float)  # take-back discount applied

    moves: Mapped[list[Move]] = relationship(
        back_populates="game", order_by="Move.id", cascade="all, delete-orphan"
    )


class Move(Base):
    __tablename__ = "moves"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    by: Mapped[str] = mapped_column(String(6))  # "player" | "bot"
    uci: Mapped[str] = mapped_column(String(5))
    san: Mapped[str] = mapped_column(String(10))
    fen_before: Mapped[str] = mapped_column(String(100))
    quality: Mapped[str | None] = mapped_column(String(12))  # player moves only
    win_prob_before: Mapped[float | None] = mapped_column(Float)
    win_prob_after: Mapped[float | None] = mapped_column(Float)
    facts: Mapped[dict | None] = mapped_column(JSON)  # MoveFacts, player moves only
    taken_back: Mapped[bool] = mapped_column(Boolean, default=False)

    game: Mapped[Game] = relationship(back_populates="moves")
    exchange: Mapped[CoachExchange | None] = relationship(back_populates="move", uselist=False)


class CoachExchange(Base):
    __tablename__ = "coach_exchanges"

    id: Mapped[int] = mapped_column(primary_key=True)
    move_id: Mapped[int] = mapped_column(ForeignKey("moves.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reason_asked: Mapped[str] = mapped_column(String(20))  # "mistake" | "good_move_check"
    player_reason: Mapped[str | None] = mapped_column(Text)
    reply: Mapped[str | None] = mapped_column(Text)
    reply_model: Mapped[str | None] = mapped_column(String(40))
    trap: Mapped[str | None] = mapped_column(String(30), index=True)
    proposed_trap_name: Mapped[str | None] = mapped_column(String(80))
    offered_retry: Mapped[bool | None] = mapped_column(Boolean)
    outcome: Mapped[str | None] = mapped_column(String(10))  # "retried" | "continued"
    # The best move was shown: by the "show me" button, or automatically after repeated retries.
    revealed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    reveal_reply: Mapped[str | None] = mapped_column(Text)

    move: Mapped[Move] = relationship(back_populates="exchange")


class LlmUsage(Base):
    """One row per LLM call. The spend cap (PLAN D11) is the sum of cost_usd this month."""

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    exchange_id: Mapped[int | None] = mapped_column(
        ForeignKey("coach_exchanges.id", ondelete="SET NULL")
    )
    model: Mapped[str] = mapped_column(String(40))
    purpose: Mapped[str] = mapped_column(String(10))  # "reply" | "label"
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float)
