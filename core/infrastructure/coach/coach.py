"""The coach: turns engine facts + the player's own reasoning into a trap and a reply.

The model never evaluates the position. Everything chess-factual comes in via `MoveFacts`
(PLAN D1); the system prompt forbids inventing lines.

Two calls run in parallel (PLAN D19): the selected model writes the reply, and a fixed model
(Haiku 5.5) assigns the trap label, so the trap profile doesn't change meaning when the user
switches models. When the selected model *is* the labeller, one call does both.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.infrastructure.analysis.move_review import MoveFacts
from core.infrastructure.coach.pricing import MODELS, cost_usd
from core.infrastructure.coach.providers import chat_model
from core.infrastructure.coach.traps import DESCRIPTIONS, PRECEDENCE, Trap

DEFAULT_MODEL = "claude-sonnet-5-5"
LABELLER_MODEL = "claude-haiku-5-5"

PERSONAS = {
    "patient_teacher": (
        "You are a patient, encouraging chess coach for a beginner rated about 400. "
        "Plain language, one idea at a time, no jargon without explaining it."
    ),
}

TRAP_LIST = "\n".join(f"- {t.value}: {d}" for t, d in DESCRIPTIONS.items()) + "\n" + PRECEDENCE

FACTS_RULES = """\
The player just made a move. You asked why they played it, and they answered in their own words.
You are given ENGINE FACTS about the position. They are correct. Use only them for chess claims.
Never invent variations, threats or evaluations that are not in the facts. Use `pieces` to know
where pieces stand; do not try to read the FEN. `their_best_reply_san` is how the opponent
punishes the move, if it was bad: when explaining why a move was bad, start from it.
`free_captures_missed` lists captures the player could have made, each with the engine's
rating; only present a capture as clearly good if its engine_rating is "good".

RECENT CONVERSATION (if present) is what you already said earlier in this game, oldest first.
Entries marked same_position are earlier attempts at THIS position. Stay consistent with your
earlier replies. If the player followed one of your hints, acknowledge it. If an earlier hint
was incomplete, say so plainly ("I should have added...") rather than contradicting it.
Never steer the player back to a move they already tried here and were told was worse."""

REPLY_RULES = (
    FACTS_RULES
    + """

Your job:
- Find the thinking trap behind the move from the player's explanation, using the list below.
- If the explanation states something false about the position (for example, that a move
  attacks a piece it doesn't), gently correct it using the facts.
- If the move was good and the reasoning was sound, say so briefly and use "none".
- Reply in at most 80 words. Speak to the player as "you". Point them at what to look at,
  rather than giving the answer, unless they have clearly already understood.
- Never mention trap names or ids, the words "engine facts", or win probabilities as numbers.
- Offer a retry when the move was a mistake or blunder.
- If REVEAL is true, or the player asks you directly what the right move is: name
  best_move_san and explain in one or two sentences why it works, using best_line_san. Do not
  hold the answer back; the player has had enough hints.

Thinking traps:
"""
    + TRAP_LIST
)

LABEL_RULES = (
    FACTS_RULES
    + """

Your only job is to label the thinking trap behind the move, from the player's explanation and
the facts. Be consistent: the same situation must always get the same label.

Thinking traps:
"""
    + TRAP_LIST
)


class CoachVerdict(BaseModel):
    trap: Trap
    proposed_trap_name: str | None = Field(None, description="Only when trap is 'other'.")
    reply: str = Field(description="What the coach says to the player, at most 80 words.")
    offer_retry: bool


class TrapLabel(BaseModel):
    trap: Trap
    proposed_trap_name: str | None = Field(None, description="Only when trap is 'other'.")


@dataclass
class Usage:
    model: str
    purpose: str  # "reply" | "label"
    usage: dict
    cost_usd: float


@dataclass
class CoachResult:
    reply: str
    offer_retry: bool
    trap: Trap  # from the labeller (D19)
    proposed_trap_name: str | None
    reply_model: str
    usages: list[Usage]

    @property
    def cost_usd(self) -> float:
        return sum(u.cost_usd for u in self.usages)


def _system(model: str, text: str) -> SystemMessage:
    # Stable prefix is cached. Anthropic needs an explicit breakpoint; OpenAI caches
    # long prefixes automatically.
    if MODELS[model].provider == "anthropic":
        return SystemMessage(
            content=[{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
        )
    return SystemMessage(content=text)


def _invoke(model: str, schema: type[BaseModel], system: str, human: HumanMessage):
    # json_schema = native structured output on both providers. Avoids forced tool_choice,
    # which current Sonnet/Opus models reject.
    llm = chat_model(model).with_structured_output(schema, method="json_schema", include_raw=True)
    out = llm.invoke([_system(model, system), human])
    if out.get("parsing_error") or out.get("parsed") is None:
        raise ValueError(f"{model} returned unparseable output: {out.get('parsing_error')}")
    usage = out["raw"].usage_metadata or {}
    return out["parsed"], usage


def _human(facts: MoveFacts, history: list[dict] | None, reveal: bool, tail: str) -> HumanMessage:
    parts = ["ENGINE FACTS:\n" + json.dumps(asdict(facts), indent=1)]
    if history:
        parts.append("RECENT CONVERSATION:\n" + json.dumps(history, indent=1))
    parts.append(f"REVEAL: {str(reveal).lower()}")
    parts.append(tail)
    return HumanMessage(content="\n\n".join(parts))


class Coach:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        persona: str = "patient_teacher",
        labeller: str = LABELLER_MODEL,
    ):
        if model not in MODELS:
            raise ValueError(f"unknown model {model}")
        self.model, self.labeller = model, labeller
        self._reply_system = PERSONAS[persona] + "\n\n" + REPLY_RULES

    def review(
        self,
        facts: MoveFacts,
        player_reason: str,
        history: list[dict] | None = None,
        reveal: bool = False,
    ) -> CoachResult:
        human = _human(
            facts, history, reveal, f"PLAYER'S EXPLANATION OF {facts.move_san}:\n" + player_reason
        )
        if self.model == self.labeller:
            verdict, usage = _invoke(self.model, CoachVerdict, self._reply_system, human)
            u = [Usage(self.model, "reply", usage, cost_usd(self.model, usage))]
            return CoachResult(
                verdict.reply,
                verdict.offer_retry,
                verdict.trap,
                verdict.proposed_trap_name,
                self.model,
                u,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            reply_f = pool.submit(_invoke, self.model, CoachVerdict, self._reply_system, human)
            label_f = pool.submit(_invoke, self.labeller, TrapLabel, LABEL_RULES, human)
            verdict, reply_usage = reply_f.result()
            label, label_usage = label_f.result()
        return CoachResult(
            reply=verdict.reply,
            offer_retry=verdict.offer_retry,
            trap=label.trap,
            proposed_trap_name=label.proposed_trap_name,
            reply_model=self.model,
            usages=[
                Usage(self.model, "reply", reply_usage, cost_usd(self.model, reply_usage)),
                Usage(self.labeller, "label", label_usage, cost_usd(self.labeller, label_usage)),
            ],
        )

    def explain_best(self, facts: MoveFacts, history: list[dict] | None = None) -> CoachResult:
        """'Show me' button: name the best move and say why. Reply only; no new trap label."""
        human = _human(
            facts,
            history,
            True,
            f"The player pressed 'show me the best move' after playing {facts.move_san}.",
        )
        verdict, usage = _invoke(self.model, CoachVerdict, self._reply_system, human)
        return CoachResult(
            reply=verdict.reply,
            offer_retry=True,
            trap=verdict.trap,
            proposed_trap_name=verdict.proposed_trap_name,
            reply_model=self.model,
            usages=[Usage(self.model, "reveal", usage, cost_usd(self.model, usage))],
        )
