from core.log_throttle import RepeatCollapser


def test_passes_distinct_lines_through_unchanged():
    c = RepeatCollapser()
    assert c.feed("a") == ["a"]
    assert c.feed("b") == ["b"]
    assert c.flush() == []


def test_swallows_consecutive_duplicates():
    c = RepeatCollapser()
    assert c.feed("same") == ["same"]
    assert c.feed("same") == []
    assert c.feed("same") == []


def test_emits_a_summary_when_the_run_ends():
    c = RepeatCollapser()
    c.feed("same")
    c.feed("same")
    c.feed("same")
    assert c.feed("other") == ["[repeated 2 more times]", "other"]


def test_flush_reports_a_run_still_open_at_the_end():
    c = RepeatCollapser()
    c.feed("same")
    c.feed("same")
    assert c.flush() == ["[repeated 1 more time]"]
    assert c.flush() == []


def test_singular_and_plural_wording():
    c = RepeatCollapser()
    c.feed("x")
    c.feed("x")
    assert c.feed("y")[0] == "[repeated 1 more time]"

    c = RepeatCollapser()
    c.feed("x")
    c.feed("x")
    c.feed("x")
    assert c.feed("y")[0] == "[repeated 2 more times]"


def test_periodic_heartbeat_keeps_a_long_run_visible():
    """
    Полностью немой лог на получасовом цикле не даёт понять, жив ли билд,
    поэтому длинный повтор отмечается -- но с геометрическим шагом.
    """
    c = RepeatCollapser(heartbeat=5)
    c.feed("same")
    out = []
    for _ in range(60):
        out.extend(c.feed("same"))
    assert out == [
        "[still repeating, 5 times]",
        "[still repeating, 50 times]",
    ]


def test_heartbeat_stays_bounded_on_a_runaway_loop():
    """
    Наблюдалось 6.4 млн повторов одной строки. С линейным шагом это дало бы
    почти 13 тысяч строк в базу на один пакет.
    """
    c = RepeatCollapser(heartbeat=500)
    c.feed("same")
    emitted = 0
    for _ in range(6_500_000):
        emitted += len(c.feed("same"))
    assert emitted <= 6, f"runaway loop produced {emitted} heartbeat lines"


def test_repeat_counter_resets_between_runs():
    c = RepeatCollapser()
    c.feed("a")
    c.feed("a")
    c.feed("b")
    assert c.feed("b") == []
    assert c.feed("c") == ["[repeated 1 more time]", "c"]
