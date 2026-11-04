import pytest

from core.infrastructure.rating import (
    K_ESTABLISHED,
    K_PROVISIONAL,
    bot_elo_for,
    expected_score,
    takeback_weight,
    update,
)


def test_expected_score_even_and_200_gap():
    assert expected_score(400, 400) == pytest.approx(0.5)
    assert expected_score(600, 400) == pytest.approx(0.76, abs=0.01)


def test_win_against_equal_bot_provisional():
    c = update(400, 400, 1.0, rated_games_so_far=0, takebacks=0)
    assert c.after == 400 + K_PROVISIONAL // 2  # 48 * (1 - 0.5) = 24


def test_k_settles_after_provisional_period():
    c = update(400, 400, 1.0, rated_games_so_far=10, takebacks=0)
    assert c.after == 400 + K_ESTABLISHED // 2


def test_takebacks_shrink_a_win():
    clean = update(400, 400, 1.0, 0, takebacks=0).delta
    coached = update(400, 400, 1.0, 0, takebacks=2).delta
    assert coached == round(clean * 0.5)


def test_takebacks_do_not_soften_a_loss():
    assert update(400, 400, 0.0, 0, takebacks=3).delta == update(400, 400, 0.0, 0, 0).delta


def test_draw_against_stronger_bot_gains():
    assert update(400, 600, 0.5, 0, 0).delta > 0


@pytest.mark.parametrize(("n", "w"), [(0, 1.0), (1, 2 / 3), (2, 0.5), (4, 1 / 3)])
def test_takeback_weight(n, w):
    assert takeback_weight(n) == pytest.approx(w)


def test_bot_elo_clamped():
    assert bot_elo_for(37) == 100
    assert bot_elo_for(812.4) == 812
    assert bot_elo_for(9000) == 2500
