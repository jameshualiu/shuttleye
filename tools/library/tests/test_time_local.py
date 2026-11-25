from library import time_local


def test_estimate_full_match():
    # 50 min at 30 fps = 90000 frames; 1800-frame chunks advancing 1740 -> 52 chunks
    est = time_local.estimate_full_match(20.0)
    assert est["chunks"] == 52
    assert est["seconds"] == 20.0 * 52
    assert round(est["minutes"], 2) == round(20.0 * 52 / 60, 2)


def test_agreement_within_tolerance():
    assert time_local.agreement([10, 100, 200, 300], [12, 98, 207, 300]) == 75.0
    assert time_local.agreement([], [1, 2]) is None
