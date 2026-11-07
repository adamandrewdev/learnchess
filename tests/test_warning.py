"""The D27 blunder warning on hand-built evaluations (no engine)."""

import chess

from core.infrastructure.analysis.warning import (
    ALLOWS_MATE,
    WarningSettings,
    as_cp,
    blunder_warning,
)
from core.infrastructure.engines.stockfish import Evaluation

S = WarningSettings(mate_depth=3, min_cp_drop=250, still_winning=0.85)


def ev(win_prob, cp=None, mate=None):
    return Evaluation(chess.WHITE, win_prob, cp, mate, None, [])


def test_says_how_much_and_names_a_hanging_minor_piece():
    text = blunder_warning(ev(0.5, 0), ev(0.1, -300), ["pawn on e4", "knight on f3"], S)
    assert text == "⚠ This loses about 3 points of material. Watch your knight on f3."


def test_names_the_most_valuable_hanging_piece():
    text = blunder_warning(ev(0.5, 0), ev(0.0, -900), ["knight on f3", "queen on d1"], S)
    assert text == "⚠ This loses about 9 points of material. Watch your queen on d1."


def test_hanging_pawn_alone_is_not_named():
    # A 250+ cp drop is rarely about the pawn; naming it would point at the wrong thing.
    text = blunder_warning(ev(0.5, 0), ev(0.1, -300), ["pawn on e4"], S)
    assert text == "⚠ This loses about 3 points of material."


def test_small_drop_is_silent():
    assert blunder_warning(ev(0.5, 0), ev(0.3, -200), ["knight on f3"], S) is None


def test_allowing_mate_warns_shallow_and_deep():
    assert blunder_warning(ev(0.5, 0), ev(0.0, None, -3), [], S) == ALLOWS_MATE
    assert blunder_warning(ev(0.5, 0), ev(0.0, None, -5), [], S) == ALLOWS_MATE


def test_already_being_mated_is_not_a_new_warning_about_mate():
    assert blunder_warning(ev(0.0, None, -4), ev(0.0, None, -2), [], S) is None


def test_missing_a_mate_while_still_winning_is_silent():
    assert blunder_warning(ev(1.0, None, 3), ev(0.99, 800), [], S) is None


# Game 47: 6.Bd3 lost a piece on d4 (-327), the bot never took it, and the next moves were each
# warned about the same d4 problem again because best play (dxe5) would have fixed it.


def test_problem_already_on_the_board_is_not_warned_again():
    # 7.O-O: best play +63, but the player's last move already left them at -327.
    assert blunder_warning(ev(0.6, 63), ev(0.0, -345), [], S, accepted_cp=-327) is None


def test_making_an_accepted_problem_worse_still_warns():
    text = blunder_warning(ev(0.6, 63), ev(0.0, -1250), [], S, accepted_cp=-327)
    assert text == "⚠ This loses about 9 points of material."


def test_kept_mate_is_not_warned_again():
    assert blunder_warning(ev(0.5, 0), ev(0.0, None, -2), [], S, accepted_cp=-9997) is None


def test_first_move_measures_from_best_play():
    assert blunder_warning(ev(0.5, 0), ev(0.1, -300), [], S, accepted_cp=None)


def test_as_cp_orders_mates_beyond_material():
    assert as_cp(ev(1.0, None, 2)) > as_cp(ev(1.0, None, 5)) > as_cp(ev(1.0, 2000))
    assert as_cp(ev(0.0, None, -2)) < as_cp(ev(0.0, -2000))
