"""HTTP API. Turn-based and single-user, so plain REST (PLAN D18)."""

from __future__ import annotations

from typing import Literal

import anthropic
import openai
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.game_service import GameError, GameService
from core.infrastructure.coach.coach import DEFAULT_MODEL
from core.infrastructure.postgresql.db import month_spend_usd
from core.infrastructure.postgresql.models import Game

router = APIRouter(prefix="/api")


def get_session(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


def get_service(request: Request) -> GameService:
    return request.app.state.service


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


class Reason(BaseModel):
    text: str
    model: str = DEFAULT_MODEL


class Continue(BaseModel):
    retry: bool
    force: bool = False  # take back even a good move, after the confirmation


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
    _run(service.player_move, session, game, body.uci)
    return service.state(session, game)


@router.post("/games/{game_id}/reason")
def reason(
    body: Reason,
    request: Request,
    game: Game = Depends(get_game),
    session: Session = Depends(get_session),
    service: GameService = Depends(get_service),
):
    usable_ids = {m.id for m in request.app.state.models[0]}
    if body.model not in usable_ids:
        raise HTTPException(400, f"model {body.model} is not available")
    try:
        _run(service.submit_reason, session, game, body.text, body.model)
    except (anthropic.APIError, openai.APIError, ValueError) as exc:
        session.rollback()
        raise HTTPException(502, f"coach call failed ({body.model}): {exc}") from exc
    return service.state(session, game)


class RevealBody(BaseModel):
    model: str = DEFAULT_MODEL


@router.post("/games/{game_id}/reveal")
def reveal(
    body: RevealBody,
    request: Request,
    game: Game = Depends(get_game),
    session: Session = Depends(get_session),
    service: GameService = Depends(get_service),
):
    if body.model not in {m.id for m in request.app.state.models[0]}:
        raise HTTPException(400, f"model {body.model} is not available")
    try:
        _run(service.reveal, session, game, body.model)
    except (anthropic.APIError, openai.APIError, ValueError) as exc:
        session.rollback()
        raise HTTPException(502, f"coach call failed ({body.model}): {exc}") from exc
    return service.state(session, game)


@router.post("/games/{game_id}/continue")
def continue_game(
    body: Continue,
    game: Game = Depends(get_game),
    session: Session = Depends(get_session),
    service: GameService = Depends(get_service),
):
    _run(service.continue_game, session, game, body.retry, body.force)
    return service.state(session, game)


@router.post("/games/{game_id}/resign")
def resign(
    game: Game = Depends(get_game),
    session: Session = Depends(get_session),
    service: GameService = Depends(get_service),
):
    _run(service.resign, session, game)
    return service.state(session, game)
