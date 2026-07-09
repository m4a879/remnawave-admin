"""Tests for preview_backup_file (metadata shown before restore)."""
import gzip
import json
from unittest.mock import patch

import pytest

from web.backend.core import backup_service as bs


def test_preview_config(tmp_path):
    with patch.object(bs, "BACKUP_DIR", tmp_path):
        f = tmp_path / "config_backup_x.json"
        f.write_text(
            json.dumps({
                "exported_at": "2026-07-09T00:00:00",
                "version": "1.0",
                "settings": [{"key": "a"}, {"key": "b"}, {"key": "c"}],
            }),
            encoding="utf-8",
        )
        info = bs.preview_backup_file("config_backup_x.json")
        assert info["type"] == "config"
        assert info["settings_count"] == 3
        assert info["schema_version"] == "1.0"


def test_preview_database(tmp_path):
    with patch.object(bs, "BACKUP_DIR", tmp_path):
        f = tmp_path / "db_backup_x.sql.gz"
        with gzip.open(f, "wt", encoding="utf-8") as g:
            g.write(
                "-- PostgreSQL database dump\n"
                "-- Dumped from database version 17.2\n"
                "CREATE TABLE users();\n"
            )
        info = bs.preview_backup_file("db_backup_x.sql.gz")
        assert info["type"] == "database"
        assert info["pg_version"] == "17.2"


def test_preview_missing_raises(tmp_path):
    with patch.object(bs, "BACKUP_DIR", tmp_path):
        with pytest.raises(FileNotFoundError):
            bs.preview_backup_file("nope.sql.gz")
