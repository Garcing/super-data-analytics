from sda_mcp import config


def test_get_env_prefers_nonempty_process_environment(monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: {
        "env": {"HOLOGRES_HOST": "local-host", "HOLOGRES_PORT": "5432"}
    })
    monkeypatch.setenv("HOLOGRES_HOST", "server-host")
    monkeypatch.setenv("HOLOGRES_PORT", "31223")

    assert config.get_env("HOLOGRES_HOST", "HOLOGRES_PORT") == {
        "HOLOGRES_HOST": "server-host",
        "HOLOGRES_PORT": "31223",
    }


def test_get_env_empty_override_falls_back_to_config(monkeypatch):
    monkeypatch.setattr(config, "load_config", lambda: {
        "env": {"HOLOGRES_HOST": "local-host"}
    })
    monkeypatch.setenv("HOLOGRES_HOST", "")

    assert config.get_env("HOLOGRES_HOST") == {"HOLOGRES_HOST": "local-host"}
