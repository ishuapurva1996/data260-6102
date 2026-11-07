"""Economics distinguish wrong answers from accepted negative labels."""

from scripts.hw09.cache_experiments import grade, summarize


def test_cost_and_rates_do_not_confuse_label_and_answer_errors():
    rows = [
        {"is_cached": True, "correct": True, "should_hit": True, "http_latency_ms": 20},
        {
            "is_cached": True,
            "correct": False,
            "should_hit": False,
            "http_latency_ms": 30,
        },
        {
            "is_cached": True,
            "correct": True,
            "should_hit": False,
            "http_latency_ms": 40,
        },
        {
            "is_cached": False,
            "correct": False,
            "should_hit": False,
            "http_latency_ms": 1000,
        },
    ]
    result = summarize(rows, {"miss_cost": 5, "false_hit_cost": 300})
    assert result["hit_rate"] == 0.75
    assert result["false_hit_rate"] == 0.25
    assert result["negative_acceptance_rate"] == 2 / 3
    assert result["wrong_live_answers"] == 1
    assert result["total_cost"] == 305
    assert result["mean_http_latency_ms"] == 272.5


def test_listing_code_digits_are_not_a_unit_count_and_wrong_identity_fails():
    expected = {"listing_code": "S6102-R-9102", "field": "available_units", "value": 2}
    assert not grade("Listing S6102-R-9102 has no information.", expected)
    assert grade("S6102-R-9102 has two available units.", expected)
    assert not grade("S6102-R-9101 has 2 available units.", expected)
    assert not grade("S6102-R-9102 has 12 available units.", expected)
