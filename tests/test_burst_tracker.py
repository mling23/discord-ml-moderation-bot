from modbot.burst_tracker import BurstTracker

HASH = "abc123"
USER = 1


def test_same_message_across_channels_is_a_burst():
    tracker = BurstTracker(burst_channels=2, burst_window_seconds=60)
    tracker.record(USER, HASH, channel_id=10, message_id=100, now=0.0)
    tracker.record(USER, HASH, channel_id=11, message_id=101, now=1.0)
    assert tracker.is_burst(USER, HASH, now=1.0)


def test_single_channel_is_not_a_burst():
    tracker = BurstTracker(burst_channels=2)
    tracker.record(USER, HASH, channel_id=10, message_id=100, now=0.0)
    tracker.record(USER, HASH, channel_id=10, message_id=101, now=1.0)
    assert not tracker.is_burst(USER, HASH, now=1.0)


def test_repeat_in_one_channel_is_detected():
    tracker = BurstTracker(repeat_count=2)
    tracker.record(USER, HASH, channel_id=10, message_id=100, now=0.0)
    tracker.record(USER, HASH, channel_id=10, message_id=101, now=1.0)
    assert tracker.is_repeat(USER, HASH, now=1.0)


def test_old_events_fall_outside_the_window():
    tracker = BurstTracker(burst_channels=2, burst_window_seconds=60)
    tracker.record(USER, HASH, channel_id=10, message_id=100, now=0.0)
    # Second copy arrives well after the burst window.
    tracker.record(USER, HASH, channel_id=11, message_id=101, now=120.0)
    assert not tracker.is_burst(USER, HASH, now=120.0)


def test_occurrences_return_message_references_for_deletion():
    tracker = BurstTracker()
    tracker.record(USER, HASH, channel_id=10, message_id=100, now=0.0)
    tracker.record(USER, HASH, channel_id=11, message_id=101, now=1.0)
    refs = {(o.channel_id, o.message_id) for o in tracker.occurrences(USER, HASH, now=1.0)}
    assert refs == {(10, 100), (11, 101)}


def test_clear_forgets_a_fingerprint():
    tracker = BurstTracker()
    tracker.record(USER, HASH, channel_id=10, message_id=100, now=0.0)
    tracker.clear(USER, HASH)
    assert tracker.occurrences(USER, HASH, now=0.0) == []


def test_retention_prunes_stale_events_on_record():
    tracker = BurstTracker(retention_seconds=120)
    tracker.record(USER, HASH, channel_id=10, message_id=100, now=0.0)
    tracker.record(USER, HASH, channel_id=11, message_id=101, now=200.0)
    # The first event is older than retention and should have been pruned.
    refs = {(o.channel_id, o.message_id) for o in tracker.occurrences(USER, HASH, now=200.0)}
    assert refs == {(11, 101)}
