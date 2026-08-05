from modbot.rules import rule_signals


def test_clean_message_has_no_triggers():
    assert rule_signals("just a normal friendly message") == []


def test_detects_url():
    assert "url" in rule_signals("check this out https://example.com")


def test_detects_invite_link():
    assert "invite_link" in rule_signals("join us at discord.gg/abcd")


def test_detects_mention_everyone():
    assert "mention_everyone" in rule_signals("hey @everyone look here")


def test_plain_domain_is_not_a_url():
    # URL rule only matches http(s):// or www. prefixes.
    assert "url" not in rule_signals("i like discord.gg as a domain name")
