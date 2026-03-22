"""Tests for manager.py - command handlers, leaderboard loop, token info fetching."""
import pytest
import datetime
import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import manager
import config
from token_tracker import TokenTracker


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset manager globals and tracker singleton before each test."""
    TokenTracker._instance = None
    manager.TOKEN_INFO_CACHE.clear()
    manager.CHAT_POLL_INTERVAL.clear()
    manager.CHAT_MONITORS.clear()
    manager.CHAT_LEADERBOARD_LAST_SENT.clear()
    manager.PROCESSED_CAS.clear()
    manager.SLEEP_UNTIL = None
    manager.CHANNEL_IDS = set()
    manager.BOT_START_TIME = datetime.datetime.utcnow()
    yield
    TokenTracker._instance = None


def make_update(text="hello", chat_id=123, msg_date=None):
    """Create a mock Telegram Update object."""
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.text = text
    update.message.caption = None
    update.message.date = msg_date or datetime.datetime.utcnow()
    update.message.reply_text = AsyncMock()
    update.channel_post = None
    return update


def make_context(*args):
    """Create a mock context with args."""
    ctx = MagicMock()
    ctx.args = list(args)
    return ctx


# ── Sleep / Wake ──

class TestSleepWake:

    def test_is_sleeping_false_by_default(self):
        assert manager.is_sleeping() is False

    def test_is_sleeping_true(self):
        manager.SLEEP_UNTIL = datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
        assert manager.is_sleeping() is True

    def test_is_sleeping_expired(self):
        manager.SLEEP_UNTIL = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)
        assert manager.is_sleeping() is False

    def test_sleep_until_str_not_sleeping(self):
        result = manager.sleep_until_str()
        assert "not sleeping" in result.lower() or result == "not sleeping"

    @pytest.mark.asyncio
    async def test_cmd_sleep_default(self):
        update = make_update()
        ctx = make_context()  # no args = default 60 min
        await manager.cmd_sleep(update, ctx)
        assert manager.SLEEP_UNTIL is not None
        assert manager.is_sleeping() is True
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_cmd_sleep_custom(self):
        update = make_update()
        ctx = make_context("30")
        await manager.cmd_sleep(update, ctx)
        assert manager.is_sleeping() is True

    @pytest.mark.asyncio
    async def test_cmd_wake(self):
        manager.SLEEP_UNTIL = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        update = make_update()
        ctx = make_context()
        await manager.cmd_wake(update, ctx)
        assert manager.is_sleeping() is False


# ── /interval command ──

class TestCmdInterval:

    @pytest.mark.asyncio
    async def test_show_current(self):
        update = make_update(chat_id=123)
        ctx = make_context()  # no args
        await manager.cmd_interval(update, ctx)
        update.message.reply_text.assert_called_once()
        call_text = update.message.reply_text.call_args[0][0]
        assert "15 min" in call_text  # default

    @pytest.mark.asyncio
    async def test_set_interval(self):
        update = make_update(chat_id=123)
        ctx = make_context("5")
        await manager.cmd_interval(update, ctx)
        assert manager.CHAT_POLL_INTERVAL[123] == 300

    @pytest.mark.asyncio
    async def test_set_interval_resets_leaderboard_timer(self):
        manager.CHAT_LEADERBOARD_LAST_SENT[123] = datetime.datetime.now()
        update = make_update(chat_id=123)
        ctx = make_context("10")
        await manager.cmd_interval(update, ctx)
        assert 123 not in manager.CHAT_LEADERBOARD_LAST_SENT

    @pytest.mark.asyncio
    async def test_reset_interval(self):
        manager.CHAT_POLL_INTERVAL[123] = 300
        update = make_update(chat_id=123)
        ctx = make_context("reset")
        await manager.cmd_interval(update, ctx)
        assert 123 not in manager.CHAT_POLL_INTERVAL

    @pytest.mark.asyncio
    async def test_invalid_interval(self):
        update = make_update(chat_id=123)
        ctx = make_context("abc")
        await manager.cmd_interval(update, ctx)
        assert 123 not in manager.CHAT_POLL_INTERVAL

    @pytest.mark.asyncio
    async def test_interval_minimum(self):
        update = make_update(chat_id=123)
        ctx = make_context("0")
        await manager.cmd_interval(update, ctx)
        assert 123 not in manager.CHAT_POLL_INTERVAL


# ── /mode command ──

class TestCmdMode:

    @pytest.mark.asyncio
    async def test_switch_to_legacy(self):
        update = make_update()
        ctx = make_context("legacy")
        await manager.cmd_mode(update, ctx)
        from token_tracker import tracker
        assert tracker.mode == "legacy"

    @pytest.mark.asyncio
    async def test_switch_to_leaderboard(self):
        update = make_update()
        ctx = make_context("leaderboard")
        await manager.cmd_mode(update, ctx)
        from token_tracker import tracker
        assert tracker.mode == "leaderboard"

    @pytest.mark.asyncio
    async def test_invalid_mode(self):
        update = make_update()
        ctx = make_context("invalid")
        await manager.cmd_mode(update, ctx)
        call_text = update.message.reply_text.call_args[0][0]
        assert "Invalid" in call_text


# ── Token info fetching ──

class TestGetTokenInfo:

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        manager.TOKEN_INFO_CACHE["TOKEN1"] = ("TestCoin", "$TC", "solana")
        result = await manager.get_token_info("TOKEN1")
        assert result == ("TestCoin", "$TC", "solana")

    @pytest.mark.asyncio
    async def test_gecko_success(self):
        with patch("manager._fetch_from_geckoterminal", return_value=("Pepe", "$PEPE", "solana")):
            result = await manager.get_token_info("TOKEN2")
            assert result == ("Pepe", "$PEPE", "solana")
            assert "TOKEN2" in manager.TOKEN_INFO_CACHE

    @pytest.mark.asyncio
    async def test_gecko_fail_dex_fallback(self):
        with patch("manager._fetch_from_geckoterminal", return_value=(None, None, None)), \
             patch("manager._fetch_from_dexscreener", return_value=("Doge", "$DOGE", "ethereum")):
            result = await manager.get_token_info("TOKEN3")
            assert result == ("Doge", "$DOGE", "ethereum")

    @pytest.mark.asyncio
    async def test_both_fail(self):
        with patch("manager._fetch_from_geckoterminal", return_value=(None, None, None)), \
             patch("manager._fetch_from_dexscreener", return_value=(None, None, None)):
            result = await manager.get_token_info("TOKEN4")
            assert result == (None, None, None)


# ── GeckoTerminal API ──

class TestFetchFromGeckoterminal:

    @pytest.mark.asyncio
    async def test_success(self):
        mock_response = {
            "data": [{
                "attributes": {"name": "PEPE / SOL"},
                "relationships": {
                    "base_token": {"data": {"id": "solana_abc123"}}
                }
            }]
        }
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=mock_response)
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.get = MagicMock(return_value=mock_resp)
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_session

            name, ticker, chain = await manager._fetch_from_geckoterminal("TOKEN")
            assert name == "PEPE"
            assert ticker == "$PEPE"
            assert chain == "solana"

    @pytest.mark.asyncio
    async def test_empty_pools(self):
        mock_response = {"data": []}
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=mock_response)
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.get = MagicMock(return_value=mock_resp)
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_session

            name, ticker, chain = await manager._fetch_from_geckoterminal("TOKEN")
            assert name is None

    @pytest.mark.asyncio
    async def test_rate_limited(self):
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_resp = AsyncMock()
            mock_resp.status = 429
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.get = MagicMock(return_value=mock_resp)
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value = mock_session

            name, ticker, chain = await manager._fetch_from_geckoterminal("TOKEN")
            assert name is None


# ── handle_message ──

class TestHandleMessage:

    @pytest.mark.asyncio
    async def test_ignores_pre_startup_messages(self):
        manager.BOT_START_TIME = datetime.datetime.utcnow()
        update = make_update(
            text="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            msg_date=datetime.datetime.utcnow() - datetime.timedelta(hours=1)
        )
        ctx = make_context()
        with patch("manager.extract_token") as mock_extract:
            await manager.handle_message(update, ctx)
            mock_extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_wrong_channel(self):
        manager.CHANNEL_IDS = {999}
        update = make_update(text="some token", chat_id=123)
        ctx = make_context()
        with patch("manager.extract_token") as mock_extract:
            await manager.handle_message(update, ctx)
            mock_extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_during_sleep(self):
        manager.SLEEP_UNTIL = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        update = make_update(text="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
        ctx = make_context()
        with patch("manager.extract_token", return_value="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"), \
             patch("manager.start_monitoring") as mock_start:
            await manager.handle_message(update, ctx)
            mock_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_empty_text(self):
        update = make_update(text=None)
        update.message.caption = None
        ctx = make_context()
        with patch("manager.extract_token") as mock_extract:
            await manager.handle_message(update, ctx)
            mock_extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_no_token(self):
        update = make_update(text="just chatting")
        ctx = make_context()
        with patch("manager.start_monitoring") as mock_start:
            await manager.handle_message(update, ctx)
            mock_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_duplicate_ca_same_channel(self):
        """Second post of same CA in same channel should be ignored."""
        manager.PROCESSED_CAS["TOKEN1"] = {123}
        update = make_update(text="TOKEN1", chat_id=123)
        ctx = make_context()
        with patch("manager.extract_token", return_value="TOKEN1"), \
             patch("manager.start_monitoring") as mock_start:
            await manager.handle_message(update, ctx)
            mock_start.assert_not_called()


# ── Leaderboard loop ──

class TestLeaderboardLoop:

    @pytest.mark.asyncio
    async def test_skips_legacy_mode(self):
        from token_tracker import tracker
        tracker.set_mode("legacy")
        app = MagicMock()

        # Run one iteration then cancel
        with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError]):
            with pytest.raises(asyncio.CancelledError):
                await manager.leaderboard_loop(app)

    @pytest.mark.asyncio
    async def test_skips_when_sleeping(self):
        from token_tracker import tracker
        tracker.set_mode("leaderboard")
        manager.SLEEP_UNTIL = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        app = MagicMock()

        with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError]):
            with pytest.raises(asyncio.CancelledError):
                await manager.leaderboard_loop(app)

    @pytest.mark.asyncio
    async def test_respects_per_channel_interval(self):
        """Channel with recent send should be skipped."""
        from token_tracker import tracker
        tracker.set_mode("leaderboard")
        tracker.add_token("T1", "Test", "$T", 123)
        manager.CHANNEL_IDS = {123}
        manager.CHAT_POLL_INTERVAL[123] = 600  # 10 min
        manager.CHAT_LEADERBOARD_LAST_SENT[123] = datetime.datetime.now()  # just sent

        app = MagicMock()
        tracker.send_leaderboard = AsyncMock()

        with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError]):
            with pytest.raises(asyncio.CancelledError):
                await manager.leaderboard_loop(app)

        tracker.send_leaderboard.assert_not_called()


# ── /reset command ──

class TestCmdReset:

    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        from token_tracker import tracker
        tracker.add_token("T1", "A", "$A", 123)
        manager.TOKEN_INFO_CACHE["T1"] = ("A", "$A", "sol")

        update = make_update()
        ctx = make_context()
        await manager.cmd_reset(update, ctx)

        assert len(tracker.tokens) == 0
        assert len(manager.TOKEN_INFO_CACHE) == 0
        update.message.reply_text.assert_called_once()


# ── /status command ──

class TestCmdStatus:

    @pytest.mark.asyncio
    async def test_status_no_monitors(self):
        update = make_update(chat_id=123)
        ctx = make_context()
        await manager.cmd_status(update, ctx)
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_with_monitors(self):
        from token_tracker import tracker
        tracker.add_token("T1", "TestCoin", "$TC", 123)
        tracker.update_initial("T1", 50, 20, 30)

        update = make_update(chat_id=123)
        ctx = make_context()
        await manager.cmd_status(update, ctx)
        text = update.message.reply_text.call_args[0][0]
        assert "1" in text  # at least 1 active token


# ── /top command ──

class TestCmdTop:

    @pytest.mark.asyncio
    async def test_top_calls_leaderboard(self):
        from token_tracker import tracker
        tracker.send_leaderboard = AsyncMock()
        update = make_update(chat_id=123)
        ctx = make_context()
        await manager.cmd_top(update, ctx)
        tracker.send_leaderboard.assert_called_once()
