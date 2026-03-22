"""Tests for TokenMonitor."""
import pytest
import datetime
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from token_tracker import TokenTracker


@pytest.fixture(autouse=True)
def reset_tracker():
    """Reset the singleton before each test."""
    TokenTracker._instance = None
    yield
    TokenTracker._instance = None


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


# Patch get_api before importing TokenMonitor
@pytest.fixture
def monitor(mock_bot):
    with patch("monitor.get_api") as mock_get_api:
        mock_api = MagicMock()
        mock_get_api.return_value = mock_api
        from monitor import TokenMonitor
        m = TokenMonitor(
            token_keyword="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            bot=mock_bot,
            chat_id=123,
            token_name="$TEST",
            poll_interval_seconds=300,
        )
        m.api = mock_api
        yield m


class TestTokenMonitorInit:

    def test_init_fields(self, monitor):
        assert monitor.token == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        assert monitor.token_name == "$TEST"
        assert monitor.chat_id == 123
        assert monitor.poll_interval_seconds == 300
        assert monitor.initial_count_value == 0
        assert monitor.new_mentions_count == 0
        assert len(monitor.seen_ids) == 0

    def test_end_time_set(self, monitor):
        import config
        expected = monitor.start_time + datetime.timedelta(hours=config.MONITOR_DURATION_HOURS)
        assert abs((monitor.end_time - expected).total_seconds()) < 2

    def test_csv_filename(self, monitor):
        assert monitor.filename.startswith("monitor_")
        assert monitor.filename.endswith(".csv")

    def test_registered_with_tracker(self, monitor):
        from token_tracker import tracker
        stats = tracker.get_stats(monitor.token)
        assert stats is not None
        assert stats.is_active is True


class TestDisplayName:

    def test_with_name(self, monitor):
        name = monitor.get_display_name()
        assert "$TEST" in name

    def test_without_name(self, mock_bot):
        with patch("monitor.get_api") as mock_get_api:
            mock_get_api.return_value = MagicMock()
            from monitor import TokenMonitor
            m = TokenMonitor("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", bot=mock_bot, chat_id=123)
            name = m.get_display_name()
            assert "EPjFWdd5" in name


class TestElapsedTime:

    def test_elapsed_minutes(self, monitor):
        monitor.start_time = datetime.datetime.now() - datetime.timedelta(minutes=45)
        result = monitor.get_elapsed_time()
        assert result == "45m"

    def test_elapsed_hours(self, monitor):
        monitor.start_time = datetime.datetime.now() - datetime.timedelta(hours=2, minutes=15)
        result = monitor.get_elapsed_time()
        assert result == "2h 15m"


class TestSetPollInterval:

    def test_set_interval(self, monitor):
        monitor.set_poll_interval(600)
        assert monitor.poll_interval_seconds == 600

    def test_minimum_60_seconds(self, monitor):
        monitor.set_poll_interval(10)
        assert monitor.poll_interval_seconds == 60

    def test_event_signaled(self, monitor):
        monitor.set_poll_interval(600)
        assert monitor._interval_changed.is_set()


class TestInitialCount:

    @pytest.mark.asyncio
    async def test_initial_count_with_tweets(self, monitor):
        """Mocks tweet search and verifies counting."""
        mock_tweet1 = MagicMock()
        mock_tweet1.id = 1
        mock_tweet1.user.verified = True
        mock_tweet1.user.blue = False

        mock_tweet2 = MagicMock()
        mock_tweet2.id = 2
        mock_tweet2.user.verified = False
        mock_tweet2.user.blue = False

        async def mock_search(query, limit=500):
            for t in [mock_tweet1, mock_tweet2]:
                yield t

        monitor.api.search = mock_search

        count, verified, non_verified = await monitor.initial_count()
        assert count == 2
        assert verified == 1
        assert non_verified == 1
        assert monitor.initial_count_value == 2
        assert 1 in monitor.seen_ids
        assert 2 in monitor.seen_ids

    @pytest.mark.asyncio
    async def test_initial_count_empty(self, monitor):
        async def mock_search(query, limit=500):
            return
            yield  # make it an async generator

        monitor.api.search = mock_search
        count, verified, non_verified = await monitor.initial_count()
        assert count == 0

    @pytest.mark.asyncio
    async def test_initial_count_timeout(self, monitor):
        async def mock_search(query, limit=500):
            raise asyncio.TimeoutError()
            yield  # make it an async generator

        monitor.api.search = mock_search
        count, verified, non_verified = await monitor.initial_count()
        assert count == 0


class TestPollNewMentions:

    @pytest.mark.asyncio
    async def test_poll_finds_new_tweets(self, monitor):
        mock_tweet = MagicMock()
        mock_tweet.id = 99
        mock_tweet.user.username = "testuser"
        mock_tweet.user.verified = False
        mock_tweet.user.blue = True
        mock_tweet.rawContent = "Hello $TEST"
        mock_tweet.date = datetime.datetime.now()
        mock_tweet.likeCount = 5
        mock_tweet.replyCount = 1
        mock_tweet.retweetCount = 2
        mock_tweet.url = "https://x.com/testuser/status/99"

        async def mock_search(query, limit=50):
            yield mock_tweet

        monitor.api.search = mock_search

        with patch.object(monitor, "save_batch"):
            await monitor.poll_new_mentions()

        assert monitor.new_mentions_count == 1
        assert 99 in monitor.seen_ids

    @pytest.mark.asyncio
    async def test_poll_skips_seen_tweets(self, monitor):
        """Already-seen tweets should not be counted again."""
        monitor.seen_ids.add(99)

        mock_tweet = MagicMock()
        mock_tweet.id = 99

        async def mock_search(query, limit=50):
            yield mock_tweet

        monitor.api.search = mock_search

        await monitor.poll_new_mentions()
        assert monitor.new_mentions_count == 0

    @pytest.mark.asyncio
    async def test_poll_no_new(self, monitor):
        async def mock_search(query, limit=50):
            return
            yield

        monitor.api.search = mock_search
        await monitor.poll_new_mentions()
        assert monitor.new_mentions_count == 0


class TestSaveBatch:

    def test_save_creates_csv(self, monitor, tmp_path):
        monitor.filename = str(tmp_path / "test_output.csv")
        data = [
            {"id": 1, "username": "user1", "text": "hello", "date": "2026-01-01",
             "likes": 5, "replies": 1, "retweets": 2, "url": "https://x.com/1", "verified": False}
        ]
        monitor.save_batch(data)
        assert os.path.exists(monitor.filename)

    def test_save_appends(self, monitor, tmp_path):
        monitor.filename = str(tmp_path / "test_output.csv")
        data1 = [{"id": 1, "username": "u1", "text": "a", "date": "2026-01-01",
                   "likes": 0, "replies": 0, "retweets": 0, "url": "", "verified": False}]
        data2 = [{"id": 2, "username": "u2", "text": "b", "date": "2026-01-02",
                   "likes": 0, "replies": 0, "retweets": 0, "url": "", "verified": False}]
        monitor.save_batch(data1)
        monitor.save_batch(data2)

        import pandas as pd
        df = pd.read_csv(monitor.filename)
        assert len(df) == 2


class TestFinalSummary:

    @pytest.mark.asyncio
    async def test_sends_summary_in_legacy_mode(self, monitor):
        from token_tracker import tracker
        tracker.set_mode("legacy")
        monitor.initial_count_value = 100
        monitor.new_mentions_count = 25
        monitor.initial_verified = 30
        monitor.new_verified = 10

        await monitor.send_final_summary()
        monitor.bot.send_message.assert_called_once()
        call_kwargs = monitor.bot.send_message.call_args[1]
        assert "MONITORING COMPLETE" in call_kwargs["text"]
        assert "125" in call_kwargs["text"]  # total

    @pytest.mark.asyncio
    async def test_no_summary_without_bot(self, monitor):
        monitor.bot = None
        await monitor.send_final_summary()
        # Should not crash


class TestNotifyNewMentions:

    @pytest.mark.asyncio
    async def test_sends_notification(self, monitor):
        tweets = [
            {"username": "u1", "text": "Great token!", "likes": 100, "retweets": 50,
             "url": "https://x.com/1", "verified": True},
            {"username": "u2", "text": "Meh", "likes": 1, "retweets": 0,
             "url": "https://x.com/2", "verified": False},
        ]
        await monitor.notify_new_mentions(tweets)
        monitor.bot.send_message.assert_called_once()
        text = monitor.bot.send_message.call_args[1]["text"]
        assert "2 New Mentions" in text
        # Top tweet by engagement should be first
        assert text.index("u1") < text.index("u2")

    @pytest.mark.asyncio
    async def test_truncates_long_text(self, monitor):
        tweets = [
            {"username": "u1", "text": "x" * 200, "likes": 1, "retweets": 0,
             "url": "https://x.com/1", "verified": False},
        ]
        await monitor.notify_new_mentions(tweets)
        text = monitor.bot.send_message.call_args[1]["text"]
        assert "..." in text

    @pytest.mark.asyncio
    async def test_no_bot_no_crash(self, monitor):
        monitor.bot = None
        await monitor.notify_new_mentions([{"username": "u", "text": "t"}])
