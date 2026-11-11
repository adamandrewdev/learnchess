"""HTTP API. Turn-based and single-user, so plain REST (PLAN D18)."""

from __future__ import annotations

from typing import Literal

import anthropic
import openai
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.game_service import GameError, GameService
from backend.profile_service import ProfileService
from backend.review_service import ReviewService
from core.infrastructure.coach.coach import DEFAULT_MODEL
from core.infrastructure.postgresql.db import month_spend_usd
from core.infrastructure.postgresql.models import Game

router = APIRouter(prefix="/api")


def get_session(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


def get_service(request: Request) -> GameService:
    return request.app.state.service


def get_reviews(request: Request) -> ReviewService:
    return request.app.state.reviews


def get_game(game_id: int, session: Session = Depends(get_session)) -> Game:
    game = session.get(Game, game_id)
    if game is None:
        raise HTTPException(404, "game not found")
    return game


class NewGame(BaseModel):
    color: Literal["white", "black", "random"] = "white"
    rated: bool = False


class PlayerMove(BaseModel):
    uci: str
    think_ms: int | None = None  # D30, measured in the browser


class WarningAnswer(BaseModel):
    take_back: bool


class ReviewAnswer(BaseModel):
    move_id: int
    text: str
    model: str = DEFAULT_MODEL


class ReviewMove(BaseModel):
    move_id: int
    model: str = DEFAULT_MODEL


class ReviewSummary(BaseModel):
    model: str = DEFAULT_MODEL


def _run(fn, *args):
    try:
        return fn(*args)
    except GameError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/models")
def models(request: Request, session: Session = Depends(get_session)):
    usable, problems = request.app.state.models
    ids = [m.id for m in usable]
    return {
        "models": [
            {"id": m.id, "label": m.label, "provider": m.provider, "note": m.note} for m in usable
        ],
        "default": DEFAULT_MODEL if DEFAULT_MODEL in ids else (ids[0] if ids else None),
        "unavailable": problems,
        "spend": {
            "month_usd": round(month_spend_usd(session), 4),
            "cap_usd": request.app.state.service.settings.spend_cap_usd,
        },
        "player_rating": request.app.state.service.rating(session),
    }


@router.get("/profile")
def profile(session: Session = Depends(get_session)):
    """Playstyle profile (PLAN D31): computed numbers only, no LLM call."""
    return ProfileService().profile(session)


@router.post("/games")
def new_game(
    body: NewGame,
    session: Session = Depends(get_session),
    service: GameService = Depends(get_service),
):
    game = _run(service.new_game, session, body.color, body.rated)
    return service.state(session, game)


@router.get("/games/{game_id}")
def get_state(
    game: Game = Depends(get_game),
    session: Session = Depends(get_session),
    service: GameService = Depends(get_service),
):
    return service.state(session, game)


@router.post("/games/{game_id}/moves")
def move(
    body: PlayerMove,
    game: Game = Depends(get_game),
    session: Session = Depends(get_session),
    service: GameService = Depends(get_service),
):
    _run(service.player_move, session, game, body.uci, body.think_ms)
    return service.state(session, game)


@router.post("/games/{game_id}/warning")
def answer_warning(
    body: WarningAnswer,
    game: Game = Depends(get_game),
    session: Session = Depends(get_session),
    service: GameService = Depends(get_service),
):
    _run(service.answer_warning, session, game, body.take_back)
    return service.state(session, game)


@router.post("/games/{game_id}/resign")
def resign(
    game: Game = Depends(get_game),
    session: Session = Depends(get_session),
    service: GameService = Depends(get_service),
):
    _run(service.resign, session, game)
    return service.state(session, game)


# --- end-of-game review (PLAN D28) -------------------------------------------------------


def _usable(request: Request, model: str) -> None:
    if model not in {m.id for m in request.app.state.models[0]}:
        raise HTTPException(400, f"model {model} is not available")


def _coach_call(session: Session, model: str, fn, *args):
    try:
        _run(fn, *args)
    except (anthropic.APIError, openai.APIError, ValueError) as exc:
        session.rollback()
        raise HTTPException(502, f"coach call failed ({model}): {exc}") from exc


@router.get("/games/{game_id}/review")
def get_review(
    game: Game = Depends(get_game),
    session: Session = Depends(get_session),
    reviews: ReviewService = Depends(get_reviews),
):
    return _run(reviews.review, session, game)


@router.post("/games/{game_id}/review/answer")
def review_answer(
    body: ReviewAnswer,
    request: Request,
    game: Game = Depends(get_game),
    session: Session = Depends(get_session),
    reviews: ReviewService = Depends(get_reviews),
):
    _usable(request, body.model)
    _coach_call(
        session, body.model, reviews.answer, session, game, body.move_id, body.text, body.model
    )
    return reviews.review(session, game)


@router.post("/games/{game_id}/review/skip")
def review_skip(
    body: ReviewMove,
    game: Game = Depends(get_game),
    session: Session = Depends(get_session),
    reviews: ReviewService = Depends(get_reviews),
):
    _run(reviews.skip, session, game, body.move_id)
    return reviews.review(session, game)


@router.post("/games/{game_id}/review/reveal")
def review_reveal(
    body: ReviewMove,
    request: Request,
    game: Game = Depends(get_game),
    session: Session = Depends(get_session),
    reviews: ReviewService = Depends(get_reviews),
):
    _usable(request, body.model)
    _coach_call(session, body.model, reviews.reveal, session, game, body.move_id, body.model)
    return reviews.review(session, game)


@router.post("/games/{game_id}/review/summary")
def review_summary(
    body: ReviewSummary,
    request: Request,
    game: Game = Depends(get_game),
    session: Session = Depends(get_session),
    reviews: ReviewService = Depends(get_reviews),
):
    _usable(request, body.model)
    _coach_call(session, body.model, reviews.summarise, session, game, body.model)
    return reviews.review(session, game)
