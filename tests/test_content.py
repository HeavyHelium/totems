import random

from totems.content import (
    BlockContent,
    ContentError,
    LAST_RESORT_QUOTE,
    load_quotes,
    load_quotes_from_items,
    load_user_content_json,
    load_wisdom,
    load_wisdom_from_items,
    pick_quote,
    pick_wisdom,
    pick_wisdom_to_fit,
)


def test_load_quotes_includes_bundled_defaults():
    quotes = load_quotes(user_text=None)
    assert len(quotes) >= 3
    assert all(isinstance(q, str) and q for q in quotes)


def test_load_quotes_merges_user_text():
    quotes = load_quotes(user_text="My personal quote\nAnother personal quote\n")
    assert "My personal quote" in quotes
    assert "Another personal quote" in quotes


def test_load_quotes_can_replace_bundled_defaults():
    quotes = load_quotes(user_text="Only mine\n", mode="replace")
    assert quotes == ["Only mine"]


def test_load_quotes_from_json_items_can_replace_bundled_defaults():
    quotes = load_quotes_from_items(["Only mine"], mode="replace")
    assert quotes == ["Only mine"]


def test_load_quotes_dedupes():
    user_text = "The cure for boredom is curiosity. There is no cure for curiosity.\n"
    quotes = load_quotes(user_text=user_text)
    matches = [q for q in quotes if q.startswith("The cure for boredom")]
    assert len(matches) == 1


def test_load_quotes_strips_blank_and_comment_lines():
    quotes = load_quotes(user_text="  \n# this is a comment\nReal quote\n")
    assert "Real quote" in quotes
    assert "" not in quotes
    assert not any(q.startswith("#") for q in quotes)


def test_load_wisdom_can_replace_bundled_defaults():
    wisdom = load_wisdom(user_text="Only my reminder\n", mode="replace")
    assert wisdom == ["Only my reminder"]


def test_load_wisdom_from_json_items_can_replace_bundled_defaults():
    wisdom = load_wisdom_from_items(["Only my reminder"], mode="replace")
    assert wisdom == ["Only my reminder"]


def test_replace_mode_empty_user_pool_returns_empty_list():
    assert load_wisdom(user_text=None, mode="replace") == []


def test_load_user_content_json_parses_arrays(tmp_path):
    p = tmp_path / "content.json"
    p.write_text(
        '{'
        '"quotes": ["Q"], '
        '"wisdom": ["W"], '
        '"duties": ["D"]'
        '}',
        encoding="utf-8",
    )

    content = load_user_content_json(p)

    assert content is not None
    assert content.quotes == ["Q"]
    assert content.wisdom == ["W"]
    assert content.duties == ["D"]


def test_load_user_content_json_missing_file_returns_none(tmp_path):
    assert load_user_content_json(tmp_path / "missing.json") is None


def test_load_user_content_json_rejects_non_string_items(tmp_path):
    p = tmp_path / "content.json"
    p.write_text('{"quotes": ["Q", 123]}', encoding="utf-8")

    try:
        load_user_content_json(p)
    except ContentError as e:
        assert "quotes[1]" in str(e)
    else:
        raise AssertionError("expected ContentError")


def test_pick_quote_deterministic_with_seed():
    quotes = ["a", "b", "c", "d"]
    rng1 = random.Random(42)
    rng2 = random.Random(42)
    assert pick_quote(quotes, rng1) == pick_quote(quotes, rng2)


def test_pick_quote_falls_back_to_last_resort_when_empty():
    assert pick_quote([], random.Random(0)) == LAST_RESORT_QUOTE


def test_pick_wisdom_returns_n_unique():
    wisdom = ["a", "b", "c", "d", "e"]
    picked = pick_wisdom(wisdom, random.Random(1), n=3)
    assert len(picked) == 3
    assert len(set(picked)) == 3


def test_pick_wisdom_caps_at_pool_size():
    wisdom = ["a", "b"]
    picked = pick_wisdom(wisdom, random.Random(1), n=5)
    assert len(picked) == 2


def test_pick_wisdom_to_fit_adds_multiple_small_items_without_repeats():
    wisdom = ["one", "two", "three", "four"]
    picked = pick_wisdom_to_fit(wisdom, random.Random(1), max_lines=3, wrap_width=70)

    assert len(picked) == 3
    assert len(set(picked)) == 3


def test_pick_wisdom_to_fit_skips_items_that_would_exceed_budget():
    wisdom = [
        "short one",
        "this item is long enough to wrap onto several estimated visual lines",
        "short two",
    ]
    picked = pick_wisdom_to_fit(wisdom, random.Random(1), max_lines=2, wrap_width=24)

    assert len(picked) >= 1
    assert all(item in wisdom for item in picked)
    assert sum(_estimated_test_lines(item, width=24) for item in picked) <= 2


def test_pick_wisdom_to_fit_keeps_one_large_item_when_first_pick_is_large():
    wisdom = ["one two three four five six seven eight nine ten"]
    picked = pick_wisdom_to_fit(wisdom, random.Random(0), max_lines=1, wrap_width=10)

    assert picked == wisdom


def test_pick_wisdom_to_fit_default_budget_has_room_after_medium_item():
    medium = "\n".join(f"line {i}" for i in range(12))
    wisdom = [medium, "small follow-up"]

    picked = pick_wisdom_to_fit(wisdom, random.Random(0), wrap_width=70)

    assert set(picked) == {medium, "small follow-up"}


def test_load_wisdom_includes_faults_and_antidotes_defaults():
    wisdom = load_wisdom(user_text=None)
    assert any("shamatha outline" in item for item in wisdom)
    assert any("Five faults" in item and "laziness" in item for item in wisdom)
    assert any("Eight antidotes" in item and "mindfulness" in item for item in wisdom)
    assert any("Mapping:" in item and "over-application -> equanimity" in item for item in wisdom)


def test_block_content_is_a_dataclass():
    bc = BlockContent(quote="q", wisdom=["w"], duties=[], symbol_path=None)
    assert bc.quote == "q"
    assert bc.symbol_path is None


def _estimated_test_lines(text: str, *, width: int) -> int:
    import textwrap

    lines = 0
    for line in text.splitlines() or [""]:
        if not line.strip():
            lines += 1
            continue
        lines += max(
            1,
            len(
                textwrap.wrap(
                    line,
                    width=width,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
            ),
        )
    return lines
