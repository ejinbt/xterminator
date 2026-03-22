"""Tests for leaderboard message generation in TokenTracker.send_leaderboard."""
import pytest
import datetime
import sys
import os
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from token_tracker import TokenTracker


@pytest.fixture(autouse=True)
def reset_tracker():
    TokenTracker._instance = None
    yield
    TokenTracker._instance = None


@pytest.fixture
def tracker():
    t = TokenTracker()
    return t


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


class TestSendLeaderboard:

    @pytest.mark.asyncio
    async def test_no_active_tokens(self, tracker, mock_bot):
        """Should not send when no tokens."""
        await tracker.send_leaderboard(bot=mock_bot, chat_id=123)
        mock_bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_message(self, tracker, mock_bot):
        tracker.add_token("T1", "Pepe", "$PEPE", 123)
        tracker.update_initial("T1", 100, 50, 50)
        await tracker.send_leaderboard(bot=mock_bot, chat_id=123)
        mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_contains_token_info(self, tracker, mock_bot):
        tracker.add_token("T1", "Pepe", "$PEPE", 123)
        tracker.update_initial("T1", 100, 50, 50)
        await tracker.send_leaderboard(bot=mock_bot, chat_id=123)

        text = mock_bot.send_message.call_args[1]["text"]
        assert "$PEPE" in text
        assert "T1" in text
        assert "100" in text

    @pytest.mark.asyncio
    async def test_ranking_emojis(self, tracker, mock_bot):
        """Top 3 should get medal emojis."""
        for i in range(4):
            tracker.add_token(f"T{i}", f"N{i}", f"${i}", 123)
            tracker.update_initial(f"T{i}", (4 - i) * 100, 0, 0)

        await tracker.send_leaderboard(bot=mock_bot, chat_id=123)
        text = mock_bot.send_message.call_args[1]["text"]
        assert "🥇" in text
        assert "🥈" in text
        assert "🥉" in text

    @pytest.mark.asyncio
    async def test_dynamic_interval_text_default(self, tracker, mock_bot):
        tracker.add_token("T1", "Pepe", "$PEPE", 123)
        tracker.update_initial("T1", 100, 50, 50)
        await tracker.send_leaderboard(bot=mock_bot, chat_id=123, interval_sec=900)

        text = mock_bot.send_message.call_args[1]["text"]
        assert "Updates every 15 min" in text

    @pytest.mark.asyncio
    async def test_dynamic_interval_text_custom(self, tracker, mock_bot):
        tracker.add_token("T1", "Pepe", "$PEPE", 123)
        tracker.update_initial("T1", 100, 50, 50)
        await tracker.send_leaderboard(bot=mock_bot, chat_id=123, interval_sec=300)

        text = mock_bot.send_message.call_args[1]["text"]
        assert "Updates every 5 min" in text

    @pytest.mark.asyncio
    async def test_interval_in_per_token_line(self, tracker, mock_bot):
        tracker.add_token("T1", "Pepe", "$PEPE", 123)
        tracker.update_initial("T1", 100, 50, 50)
        await tracker.send_leaderboard(bot=mock_bot, chat_id=123, interval_sec=600)

        text = mock_bot.send_message.call_args[1]["text"]
        assert "(10m)" in text

    @pytest.mark.asyncio
    async def test_channel_filtering(self, tracker, mock_bot):
        """Leaderboard for channel 123 should not include channel 456 tokens."""
        tracker.add_token("T1", "A", "$A", 123)
        tracker.add_token("T2", "B", "$B", 456)

        await tracker.send_leaderboard(bot=mock_bot, chat_id=123)
        text = mock_bot.send_message.call_args[1]["text"]
        assert "$A" in text
        assert "$B" not in text

    @pytest.mark.asyncio
    async def test_no_bot_no_crash(self, tracker):
        await tracker.send_leaderboard(bot=None, chat_id=None)

    @pytest.mark.asyncio
    async def test_limit_30_tokens(self, tracker, mock_bot):
        """Should cap at 30 tokens."""
        for i in range(40):
            tracker.add_token(f"T{i}", f"N{i}", f"${i}", 123)
            tracker.update_initial(f"T{i}", i * 10, 0, 0)

        await tracker.send_leaderboard(bot=mock_bot, chat_id=123)
        text = mock_bot.send_message.call_args[1]["text"]
        assert "TOP 30" in text

    @pytest.mark.asyncio
    async def test_completed_tokens_excluded(self, tracker, mock_bot):
        tracker.add_token("T1", "Active", "$ACT", 123)
        tracker.add_token("T2", "Done", "$DONE", 123)
        tracker.update_initial("T1", 100, 50, 50)
        tracker.update_initial("T2", 200, 100, 100)
        tracker.mark_complete("T2")

        await tracker.send_leaderboard(bot=mock_bot, chat_id=123)
        text = mock_bot.send_message.call_args[1]["text"]
        assert "$ACT" in text
        assert "$DONE" not in text
