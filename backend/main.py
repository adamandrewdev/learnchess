"""FastAPI app. Started by docker-compose (`uvicorn backend.main:app`)."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.game_service import Engines, GameService, Settings
from backend.review_service import ReviewService
from backend.routes import router
from core.infrastructure.coach.providers import available_models
from core.infrastructure.engines.maia import Opponent
from core.infrastructure.engines.stockfish import Judge
from core.infrastructure.postgresql.db import make_sessionmaker

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("learnchess")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    judge = Judge(depth=int(os.environ.get("JUDGE_DEPTH", "16")))
    opponent = Opponent(settings.bot_elo, settings.bot_temperature)  # random seed (P0-1)
    app.state.sessionmaker = make_sessionmaker()
    app.state.service = GameService(Engines(judge, opponent), settings)
    app.state.reviews = ReviewService(app.state.service)
    app.state.models = available_models()
    usable = [m.id for m in app.state.models[0]]
    log.info("coach models available: %s", usable or "NONE (check .env)")
    log.info(
        "bot: Maia-3 elo=%s temp=%s seed=%s",
        settings.bot_elo,
        settings.bot_temperature,
        opponent.seed,
    )
    yield
    opponent.close()
    judge.close()


app = FastAPI(title="learnchess", lifespan=lifespan)
app.include_router(router)
