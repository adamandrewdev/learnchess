"""Engine and session factory. DATABASE_URL comes from docker-compose.yml."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from core.infrastructure.postgresql.models import LlmUsage


def make_sessionmaker(url: str | None = None) -> sessionmaker[Session]:
    url = url or os.environ["DATABASE_URL"]
    engine = create_engine(url, pool_pre_ping=True)
    return sessionmaker(engine, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as session:
        yield session


def month_spend_usd(session: Session, now: datetime | None = None) -> float:
    now = now or datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = session.scalar(select(func.sum(LlmUsage.cost_usd)).where(LlmUsage.created_at >= start))
    return float(total or 0.0)
