import json
from pathlib import Path
import pytest
from app.feeds import load_sources


def test_fresh_checkout_registry_is_empty():
    root = Path(__file__).resolve().parents[1]
    assert load_sources(root / 'config/sources.json') == []
    assert all('example' in row['url'] for row in load_sources(root / 'config/sources.example.json'))


def test_explicit_registry_replaces_defaults_and_fails_closed(tmp_path, monkeypatch):
    registry = tmp_path / 'sources.json'
    registry.write_text('[]')
    monkeypatch.setenv('CALENDAR_SOURCES_FILE', str(registry))
    assert load_sources() == []
    registry.write_text('invalid')
    with pytest.raises(ValueError):
        load_sources()
    registry.unlink()
    with pytest.raises(FileNotFoundError):
        load_sources()
