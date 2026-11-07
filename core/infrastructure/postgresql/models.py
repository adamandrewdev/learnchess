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
    # D31: skipped by every playstyle statistic (profile, review patterns, session focus).
    # For test or deliberately random games; set at the player's request.
    exclude_from_profile: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

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
    # D30: browser-measured thinking time, tab-hidden time excluded. None for bot moves and for
    # games played before P2a.
    think_ms: Mapped[int | None] = mapped_column(Integer)
    # D27: the one-line blunder warning shown for this move, and what the player did about it.
    warning: Mapped[str | None] = mapped_column(String(120))
    warning_outcome: Mapped[str | None] = mapped_column(String(10))  # "took_back" | "kept"
    # D27: engine eval after this move, centipawns for the mover (mates mapped by `as_cp`). The
    # next warning measures from here, so a problem already on the board isn't warned again.
    eval_cp_after: Mapped[int | None] = mapped_column(Integer)

    game: Mapped[Game] = relationship(back_populates="moves")
    exchange: Mapped[CoachExchange | None] = relationship(back_populates="move", uselist=False)


class CoachExchange(Base):
    __tablename__ = "coach_exchanges"

    id: Mapped[int] = mapped_column(primary_key=True)
    move_id: Mapped[int] = mapped_column(ForeignKey("moves.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # "review" (D28); P1 games also have "mistake" | "good_move_check" from the mid-game coach.
    reason_asked: Mapped[str] = mapped_column(String(20))
    player_reason: Mapped[str | None] = mapped_column(Text)
    reply: Mapped[str | None] = mapped_column(Text)
    reply_model: Mapped[str | None] = mapped_column(String(40))
    trap: Mapped[str | None] = mapped_column(String(30), index=True)
    proposed_trap_name: Mapped[str | None] = mapped_column(String(80))
    offered_retry: Mapped[bool | None] = mapped_column(Boolean)
    outcome: Mapped[str | None] = mapped_column(String(10))  # retried / continued / skipped
    # The best move was shown: by the "show me" button, or automatically after repeated retries.
    revealed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    reveal_reply: Mapped[str | None] = mapped_column(Text)

    move: Mapped[Move] = relationship(back_populates="exchange")


class GameReview(Base):
    """The end-of-game summary (PLAN D28), written once and cached so reopening is free."""

    __tablename__ = "game_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    model: Mapped[str] = mapped_column(String(40))
    summary: Mapped[dict] = mapped_column(JSON)  # GameSummary fields
    numbers: Mapped[dict] = mapped_column(JSON)  # what the summary was written from (risk R3)


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
    purpose: Mapped[str] = mapped_column(String(10))  # reply / label / reveal / summary
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float)
