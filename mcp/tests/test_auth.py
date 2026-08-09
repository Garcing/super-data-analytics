"""StaticTokenVerifier 单测（直接调 verify_token，不走 HTTP）。"""
import asyncio
import pytest
from sda_mcp import auth


def test_valid_token_returns_accesstoken(monkeypatch):
    monkeypatch.setattr(auth, "_EXPECTED", "secret-token")
    at = asyncio.run(auth.StaticTokenVerifier().verify_token("secret-token"))
    assert at is not None and at.token == "secret-token"


def test_wrong_token_returns_none(monkeypatch):
    monkeypatch.setattr(auth, "_EXPECTED", "secret-token")
    assert asyncio.run(auth.StaticTokenVerifier().verify_token("nope")) is None


def test_empty_when_unconfigured(monkeypatch):
    monkeypatch.setattr(auth, "_EXPECTED", "")
    assert asyncio.run(auth.StaticTokenVerifier().verify_token("anything")) is None
