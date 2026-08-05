from modbot.scoring import score_message


def test_clean_message_scores_zero():
    result = score_message("hello everyone, how is your day going")
    assert result.score == 0
    assert result.triggers == []


def test_url_adds_expected_weight():
    result = score_message("check https://example.com")
    assert "url" in result.triggers
    assert result.score == 2


def test_invite_link_weight():
    result = score_message("join discord.gg/abcd")
    assert "invite_link" in result.triggers
    assert result.score == 4


def test_mention_everyone_weight():
    result = score_message("hey @everyone look")
    assert "mention_everyone" in result.triggers
    assert result.score == 4


def test_known_spam_match_dominates():
    result = score_message("buy now", matched_known_spam=True)
    assert "match_known_spam" in result.triggers
    assert result.score >= 10


def test_attachment_alone_is_weak():
    result = score_message("", has_attachment=True)
    assert result.triggers == ["attachment"]
    assert result.score == 2


def test_attachment_combined_with_link():
    # attachment(2) + attachment_combo(2) + url(2) = 6
    result = score_message("see https://shop.example", has_attachment=True)
    assert "attachment" in result.triggers
    assert "attachment_combo" in result.triggers
    assert result.score == 6


def test_repeated_message_signal():
    result = score_message("same thing again", repeated=True)
    assert "repeated_message" in result.triggers
    assert result.score == 5


def test_combined_signals_sum():
    # mention_everyone(4) + invite_link(4) + url(2) = 10
    result = score_message("@everyone join discord.gg/x see https://y.com")
    assert result.score == 10


def test_classic_advert_reaches_delete_threshold():
    # @everyone(4) + url(2) + attachment(2) + attachment_combo(2) = 10
    result = score_message("@everyone buy this https://shop.example", has_attachment=True)
    assert result.score == 10
