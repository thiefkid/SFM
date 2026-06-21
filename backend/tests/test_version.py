"""Tests for backend build-version reporting."""

from app.api.routes.refresh import _backend_version
from app.core.config import settings


class TestBackendVersion:
    def test_truncates_sha_to_7(self, monkeypatch):
        monkeypatch.setattr(settings, "git_commit", "abcdef1234567890")
        monkeypatch.setattr(settings, "git_commit_time", "2026-06-21T10:00:00+00:00")
        v = _backend_version()
        assert v.commit == "abcdef1"
        assert v.commit_time == "2026-06-21T10:00:00+00:00"

    def test_dev_default(self, monkeypatch):
        monkeypatch.setattr(settings, "git_commit", "dev")
        monkeypatch.setattr(settings, "git_commit_time", "")
        v = _backend_version()
        assert v.commit == "dev"
        assert v.commit_time is None

    def test_empty_commit_falls_back_to_dev(self, monkeypatch):
        monkeypatch.setattr(settings, "git_commit", "")
        monkeypatch.setattr(settings, "git_commit_time", "")
        v = _backend_version()
        assert v.commit == "dev"
        assert v.commit_time is None

    def test_short_sha_unchanged(self, monkeypatch):
        monkeypatch.setattr(settings, "git_commit", "abc12")
        monkeypatch.setattr(settings, "git_commit_time", "")
        v = _backend_version()
        assert v.commit == "abc12"
