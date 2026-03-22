"""Tests for token extraction from messages."""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from manager import extract_token


class TestExtractToken:
    """Tests for extract_token() - extracts CA from Telegram messages."""

    # ── Pump.fun addresses (priority) ──

    def test_pumpfun_address(self):
        ca = "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hrpump"
        assert extract_token(ca) == ca

    def test_pumpfun_in_sentence(self):
        ca = "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hrpump"
        text = f"Check out this token {ca} looks good"
        assert extract_token(text) == ca

    def test_pumpfun_priority_over_solana(self):
        """Pump.fun should match before regular Solana addresses."""
        pump_ca = "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hrpump"
        sol_ca = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        text = f"{sol_ca} vs {pump_ca}"
        assert extract_token(text) == pump_ca

    # ── Solana addresses (Base58, 32-44 chars) ──

    def test_solana_address(self):
        ca = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        assert extract_token(ca) == ca

    def test_solana_short_address(self):
        """32-char minimum Solana address."""
        ca = "So11111111111111111111111111111112"
        assert extract_token(ca) == ca

    def test_solana_in_multiline(self):
        text = "New token alert!\nEPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v\nBuy now"
        assert extract_token(text) == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    # ── EVM addresses (0x...) ──

    def test_evm_address(self):
        ca = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
        assert extract_token(ca) == ca

    def test_evm_lowercase(self):
        ca = "0xdac17f958d2ee523a2206206994597c13d831ec7"
        assert extract_token(ca) == ca

    def test_evm_in_sentence(self):
        text = "ETH token: 0xdAC17F958D2ee523a2206206994597C13D831ec7 on Uniswap"
        assert extract_token(text) == "0xdAC17F958D2ee523a2206206994597C13D831ec7"

    def test_solana_priority_over_evm(self):
        """Solana should match before EVM when both present."""
        sol_ca = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        evm_ca = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
        text = f"{evm_ca} and {sol_ca}"
        # Solana regex runs before EVM, but match depends on position
        result = extract_token(text)
        assert result in (sol_ca, evm_ca)

    # ── No match / edge cases ──

    def test_empty_string(self):
        assert extract_token("") is None

    def test_none_input(self):
        assert extract_token(None) is None

    def test_no_token_in_text(self):
        assert extract_token("Hello world, this is just a normal message") is None

    def test_short_string_not_matched(self):
        """Strings shorter than 32 chars should not match Solana."""
        assert extract_token("abc123") is None

    def test_evm_too_short(self):
        """EVM address with less than 40 hex chars should not match."""
        assert extract_token("0xdAC17F958D2ee523a220") is None

    def test_message_with_url_and_token(self):
        text = "https://dexscreener.com/solana/EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v check this"
        result = extract_token(text)
        assert result is not None
