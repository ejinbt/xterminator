"""Tests for TokenTracker and TokenStats."""
import pytest
import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from token_tracker import TokenStats, TokenTracker


# ── TokenStats Tests ──

class TestTokenStats:

    def make_stats(self, minutes_ago=0, **kwargs):
        """Helper to create a TokenStats with controlled start_time."""
        defaults = dict(
            token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            token_name="TestToken",
            ticker="$TEST",
            chat_ids={123},
            start_time=datetime.datetime.now() - datetime.timedelta(minutes=minutes_ago),
        )
        defaults.update(kwargs)
        return TokenStats(**defaults)

    # ── Display / formatting ──

    def test_display_name_ticker(self):
        s = self.make_stats(ticker="$PEPE")
        assert s.get_display_name() == "$PEPE"

    def test_display_name_fallback_to_name(self):
        s = self.make_stats(ticker=None, token_name="Pepe Coin")
        assert s.get_display_name() == "Pepe Coin"

    def test_display_name_fallback_to_unknown(self):
        s = self.make_stats(ticker=None, token_name=None)
        assert s.get_display_name() == "Unknown"

    def test_short_ca_long(self):
        s = self.make_stats(token_address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
        short = s.get_short_ca()
        assert short.startswith("EPjFWdd5")
        assert short.endswith("Dt1v")
        assert "..." in short

    def test_short_ca_short(self):
        s = self.make_stats(token_address="shortaddr")
        assert s.get_short_ca() == "shortaddr"

    # ── Monitoring time ──

    def test_monitoring_minutes(self):
        s = self.make_stats(minutes_ago=45)
        assert 44 <= s.get_monitoring_minutes() <= 46

    def test_monitoring_time_str_minutes(self):
        s = self.make_stats(minutes_ago=30)
        assert s.get_monitoring_time_str() == "30m"

    def test_monitoring_time_str_hours(self):
        s = self.make_stats(minutes_ago=90)
        result = s.get_monitoring_time_str()
        assert result == "1h 30m"

    # ── Time factor / scoring ──

    def test_time_factor_zero_minutes(self):
        s = self.make_stats(minutes_ago=0)
        assert s.get_time_factor() == pytest.approx(1.0, abs=0.05)

    def test_time_factor_15_minutes(self):
        s = self.make_stats(minutes_ago=15)
        assert s.get_time_factor() == pytest.approx(1.25, abs=0.05)

    def test_time_factor_1_hour(self):
        s = self.make_stats(minutes_ago=60)
        assert s.get_time_factor() == pytest.approx(2.0, abs=0.05)

    def test_time_factor_3_hours(self):
        s = self.make_stats(minutes_ago=180)
        assert s.get_time_factor() == pytest.approx(4.0, abs=0.05)

    # ── Average tweet count ──

    def test_average_tweet_count(self):
        s = self.make_stats(minutes_ago=60, total_tweets=100)
        # time_factor ~2.0, so avg ~50.0
        assert s.get_average_tweet_count() == pytest.approx(50.0, abs=2.0)

    def test_average_tweet_count_zero_tweets(self):
        s = self.make_stats(minutes_ago=60, total_tweets=0)
        assert s.get_average_tweet_count() == 0.0

    # ── New tweets count ──

    def test_new_tweets_count(self):
        s = self.make_stats(initial_tweets=50, total_tweets=120)
        assert s.get_new_tweets_count() == 70

    def test_new_tweets_count_no_new(self):
        s = self.make_stats(initial_tweets=50, total_tweets=50)
        assert s.get_new_tweets_count() == 0


# ── TokenTracker Tests ──

class TestTokenTracker:

    @pytest.fixture(autouse=True)
    def reset_tracker(self):
        """Reset the singleton before each test."""
        TokenTracker._instance = None
        self.tracker = TokenTracker()
        yield
        TokenTracker._instance = None

    # ── Singleton ──

    def test_singleton(self):
        t1 = TokenTracker()
        t2 = TokenTracker()
        assert t1 is t2

    # ── Mode ──

    def test_default_mode(self):
        assert self.tracker.mode == "leaderboard"

    def test_set_mode_legacy(self):
        assert self.tracker.set_mode("legacy") is True
        assert self.tracker.mode == "legacy"

    def test_set_mode_leaderboard(self):
        self.tracker.set_mode("legacy")
        assert self.tracker.set_mode("leaderboard") is True
        assert self.tracker.mode == "leaderboard"

    def test_set_mode_invalid(self):
        assert self.tracker.set_mode("invalid") is False
        assert self.tracker.mode == "leaderboard"

    # ── Add token ──

    def test_add_token(self):
        stats = self.tracker.add_token("TOKEN1", "Test", "$TEST", 123)
        assert stats.token_address == "TOKEN1"
        assert stats.token_name == "Test"
        assert 123 in stats.chat_ids
        assert stats.is_active is True

    def test_add_token_duplicate_adds_channel(self):
        self.tracker.add_token("TOKEN1", "Test", "$TEST", 123)
        stats = self.tracker.add_token("TOKEN1", "Test", "$TEST", 456)
        assert 123 in stats.chat_ids
        assert 456 in stats.chat_ids
        # Should still be one token, not two
        assert len(self.tracker.tokens) == 1

    def test_add_channel_to_token(self):
        self.tracker.add_token("TOKEN1", "Test", "$TEST", 123)
        self.tracker.add_channel_to_token("TOKEN1", 789)
        assert 789 in self.tracker.tokens["TOKEN1"].chat_ids

    def test_add_channel_to_nonexistent(self):
        """Should not crash when token doesn't exist."""
        self.tracker.add_channel_to_token("NONEXISTENT", 123)

    # ── Update initial ──

    def test_update_initial(self):
        self.tracker.add_token("TOKEN1", "Test", "$TEST", 123)
        self.tracker.update_initial("TOKEN1", 100, 30, 70)
        stats = self.tracker.get_stats("TOKEN1")
        assert stats.initial_tweets == 100
        assert stats.initial_verified == 30
        assert stats.initial_non_verified == 70
        assert stats.total_tweets == 100

    def test_update_initial_nonexistent(self):
        """Should not crash when token doesn't exist."""
        self.tracker.update_initial("NONEXISTENT", 100, 30, 70)

    # ── Update poll ──

    def test_update_poll(self):
        self.tracker.add_token("TOKEN1", "Test", "$TEST", 123)
        self.tracker.update_initial("TOKEN1", 100, 30, 70)
        self.tracker.update_poll("TOKEN1", 10, 3, 7)
        stats = self.tracker.get_stats("TOKEN1")
        assert stats.total_tweets == 110
        assert stats.total_verified == 33
        assert stats.total_non_verified == 77
        assert stats.last_poll_tweets == 10

    def test_update_poll_multiple(self):
        self.tracker.add_token("TOKEN1", "Test", "$TEST", 123)
        self.tracker.update_poll("TOKEN1", 5, 2, 3)
        self.tracker.update_poll("TOKEN1", 10, 4, 6)
        stats = self.tracker.get_stats("TOKEN1")
        assert stats.total_tweets == 15
        assert stats.last_poll_tweets == 10  # Only last poll

    def test_update_poll_nonexistent(self):
        self.tracker.update_poll("NONEXISTENT", 10, 3, 7)

    # ── Mark complete / remove ──

    def test_mark_complete(self):
        self.tracker.add_token("TOKEN1", "Test", "$TEST", 123)
        self.tracker.mark_complete("TOKEN1")
        assert self.tracker.tokens["TOKEN1"].is_active is False

    def test_mark_complete_nonexistent(self):
        self.tracker.mark_complete("NONEXISTENT")

    def test_remove_token(self):
        self.tracker.add_token("TOKEN1", "Test", "$TEST", 123)
        self.tracker.remove_token("TOKEN1")
        assert "TOKEN1" not in self.tracker.tokens

    def test_remove_nonexistent(self):
        self.tracker.remove_token("NONEXISTENT")

    # ── Get active tokens ──

    def test_get_active_tokens(self):
        self.tracker.add_token("T1", "A", "$A", 123)
        self.tracker.add_token("T2", "B", "$B", 123)
        self.tracker.mark_complete("T2")
        active = self.tracker.get_active_tokens()
        assert len(active) == 1
        assert active[0].token_address == "T1"

    def test_get_active_tokens_by_channel(self):
        self.tracker.add_token("T1", "A", "$A", 123)
        self.tracker.add_token("T2", "B", "$B", 456)
        active_123 = self.tracker.get_active_tokens(chat_id=123)
        active_456 = self.tracker.get_active_tokens(chat_id=456)
        assert len(active_123) == 1
        assert len(active_456) == 1
        assert active_123[0].token_address == "T1"

    def test_get_active_tokens_empty(self):
        assert self.tracker.get_active_tokens() == []

    # ── Get top tokens ──

    def test_get_top_tokens_sorted(self):
        """Tokens should be sorted by average tweet count descending."""
        self.tracker.add_token("T1", "Low", "$LOW", 123)
        self.tracker.add_token("T2", "High", "$HIGH", 123)
        self.tracker.update_initial("T1", 10, 5, 5)
        self.tracker.update_initial("T2", 200, 100, 100)
        top = self.tracker.get_top_tokens(limit=10)
        assert top[0].token_address == "T2"
        assert top[1].token_address == "T1"

    def test_get_top_tokens_limit(self):
        for i in range(5):
            self.tracker.add_token(f"T{i}", f"N{i}", f"${i}", 123)
        top = self.tracker.get_top_tokens(limit=3)
        assert len(top) == 3

    def test_get_top_tokens_by_channel(self):
        self.tracker.add_token("T1", "A", "$A", 123)
        self.tracker.add_token("T2", "B", "$B", 456)
        top = self.tracker.get_top_tokens(chat_id=123)
        assert len(top) == 1
        assert top[0].token_address == "T1"

    # ── Get stats ──

    def test_get_stats_exists(self):
        self.tracker.add_token("TOKEN1", "Test", "$TEST", 123)
        assert self.tracker.get_stats("TOKEN1") is not None

    def test_get_stats_not_found(self):
        assert self.tracker.get_stats("NONEXISTENT") is None
