import importlib

import service_config


def test_enabled_flag(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    assert importlib.reload(service_config).DEBUG is True
