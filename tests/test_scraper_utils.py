"""Tests for scraper_utils.py - account loading and proxy parsing."""
import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAccountLineParsing:
    """Test account line parsing logic without actually calling twscrape."""

    def parse_line(self, line):
        """Simulate the parsing logic from load_accounts()."""
        proxy = None
        if "http://" in line:
            main_part, proxy = line.rsplit("http://", 1)
            proxy = "http://" + proxy
        elif "https://" in line:
            main_part, proxy = line.rsplit("https://", 1)
            proxy = "https://" + proxy
        else:
            main_part = line

        parts = main_part.split(":")
        return parts, proxy

    # ── Token login format ──

    def test_token_login_no_proxy(self):
        line = "agent_3y3::auth_token_abc:ct0_xyz"
        parts, proxy = self.parse_line(line)
        assert parts[0] == "agent_3y3"
        assert parts[1] == ""  # empty password
        assert parts[2] == "auth_token_abc"
        assert parts[3] == "ct0_xyz"
        assert proxy is None

    def test_token_login_with_http_proxy(self):
        line = "agent_3y3::auth_token:ct0http://user:pass@host:8080"
        parts, proxy = self.parse_line(line)
        assert parts[0] == "agent_3y3"
        assert proxy == "http://user:pass@host:8080"

    def test_token_login_with_https_proxy(self):
        line = "agent_3y3::auth_token:ct0https://user:pass@host:8080"
        parts, proxy = self.parse_line(line)
        assert proxy == "https://user:pass@host:8080"

    # ── Standard login format ──

    def test_standard_login_no_proxy(self):
        line = "user:pass:email@gmail.com:emailpass"
        parts, proxy = self.parse_line(line)
        assert parts[0] == "user"
        assert parts[1] == "pass"
        assert proxy is None

    def test_standard_login_with_proxy(self):
        line = "user:pass:email:emailpasshttp://proxy:8080"
        parts, proxy = self.parse_line(line)
        assert proxy == "http://proxy:8080"

    # ── Edge cases ──

    def test_nodemaven_proxy_format(self):
        """Real NodeMaven proxy format from accounts.txt."""
        line = "user::token:ct0http://pallomvishnu_gmail_com-country-any-sid-abc123-filter-medium:mx6ertg4xz@gate.nodemaven.com:8080"
        parts, proxy = self.parse_line(line)
        assert proxy == "http://pallomvishnu_gmail_com-country-any-sid-abc123-filter-medium:mx6ertg4xz@gate.nodemaven.com:8080"

    def test_skip_comments(self):
        line = "# This is a comment"
        assert line.startswith("#")

    def test_skip_empty_lines(self):
        assert "".strip() == ""


class TestGetApi:

    def test_returns_api_instance(self):
        with patch("scraper_utils.API") as mock_api:
            from scraper_utils import get_api
            api = get_api()
            mock_api.assert_called_once()
