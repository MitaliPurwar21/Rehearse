"""Config parsing — CORS origins come in as a comma-separated string (easy to set in a
hosting dashboard) and split into a clean list."""

from rehearse_core.config import Settings


def test_cors_origins_split_from_csv() -> None:
    s = Settings(cors_origins="https://a.com, https://b.com ,https://c.com")
    assert s.cors_origin_list == ["https://a.com", "https://b.com", "https://c.com"]


def test_cors_origins_default() -> None:
    assert "http://localhost:3000" in Settings().cors_origin_list


def test_cors_origins_ignores_blanks() -> None:
    assert Settings(cors_origins="https://a.com,, ,").cors_origin_list == ["https://a.com"]
