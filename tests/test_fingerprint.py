from modbot.fingerprint import content_hash, normalize_text


def test_normalize_lowercases_and_trims():
    assert normalize_text("  Hello   World  ") == "hello world"


def test_normalize_collapses_internal_whitespace():
    assert normalize_text("buy\n\nnow\tcheap") == "buy now cheap"


def test_hash_is_stable_across_case_and_spacing():
    assert content_hash("Buy NOW  cheap") == content_hash("buy now cheap")


def test_hash_differs_for_different_text():
    assert content_hash("buy now") != content_hash("sell later")


def test_normalize_strips_zero_width_characters():
    assert normalize_text("buy\u200b now") == "buy now"


def test_hash_ignores_zero_width_evasion():
    assert content_hash("join now") == content_hash("join\u200d now")


def test_normalize_lowercases_urls_without_rewriting_them():
    a = normalize_text("Visit HTTPS://Example.COM/path?A=1")
    b = normalize_text("visit https://example.com/path?a=1")
    assert a == b
