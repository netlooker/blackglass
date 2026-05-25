from pathlib import Path

import pytest
from pydantic import ValidationError

from blackglass.config import DomainPolicy, RetrievalSettings, Settings, load_settings
from blackglass.schemas import RetrievalBackend, RetrievalMode

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_defaults_load_without_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BLACKGLASS_CONFIG", raising=False)

    settings = load_settings()

    assert isinstance(settings, Settings)
    assert settings.server.host == "127.0.0.1"
    assert settings.server.port == 8010
    assert settings.retrieval.default_mode == RetrievalMode.AUTO
    assert settings.retrieval.default_backends == [RetrievalBackend.SCRAPLING_HTTP]
    assert settings.config_path is None


def test_loads_toml_config(tmp_path: Path) -> None:
    config_path = tmp_path / "blackglass.toml"
    config_path.write_text(
        """
[server]
host = "0.0.0.0"
port = 9000

[retrieval]
default_backends = ["scrapling_http"]
artifact_dir = "~/blackglass-test"

[domains."example.com"]
allow = true
allowed_backends = ["scrapling_http"]
""".strip(),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert settings.server.host == "0.0.0.0"
    assert settings.server.port == 9000
    assert settings.retrieval.artifact_dir == Path("~/blackglass-test").expanduser()
    assert settings.domains["example.com"].allow is True
    assert settings.domains["example.com"].allowed_backends == [
        RetrievalBackend.SCRAPLING_HTTP
    ]


def test_env_config_path_is_honored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "blackglass.toml"
    config_path.write_text("[server]\nport = 9001\n", encoding="utf-8")
    monkeypatch.setenv("BLACKGLASS_CONFIG", str(config_path))

    settings = load_settings()

    assert settings.server.port == 9001
    assert settings.config_path == config_path


def test_explicit_config_path_wins_over_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / "env.toml"
    explicit_path = tmp_path / "explicit.toml"
    env_path.write_text("[server]\nport = 9001\n", encoding="utf-8")
    explicit_path.write_text("[server]\nport = 9002\n", encoding="utf-8")
    monkeypatch.setenv("BLACKGLASS_CONFIG", str(env_path))

    settings = load_settings(explicit_path)

    assert settings.server.port == 9002
    assert settings.config_path == explicit_path


def test_missing_config_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "missing.toml")


def test_non_file_config_path_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_settings(tmp_path)


def test_container_config_matches_sidecar_defaults() -> None:
    settings = load_settings(PROJECT_ROOT / "config.container.toml")

    assert settings.server.host == "0.0.0.0"
    assert settings.server.port == 8010
    assert settings.retrieval.artifact_dir == Path("/data/artifacts")
    assert settings.policy.browser_enabled is True
    assert settings.policy.cloakbrowser_enabled is True
    assert settings.policy.deny_local_networks is True
    assert settings.retrieval.default_backends == [
        RetrievalBackend.SCRAPLING_HTTP,
        RetrievalBackend.CLOAKBROWSER,
    ]


def test_domain_keys_are_lowercased(tmp_path: Path) -> None:
    config_path = tmp_path / "blackglass.toml"
    config_path.write_text(
        """
[domains."Example.COM"]
allow = false
""".strip(),
        encoding="utf-8",
    )

    settings = load_settings(config_path)

    assert "example.com" in settings.domains
    assert "Example.COM" not in settings.domains
    assert settings.domains["example.com"].allow is False


def test_domain_policy_only_exposes_allow_and_backends() -> None:
    assert set(DomainPolicy.model_fields) == {"allow", "allowed_backends"}


def test_default_backends_rejects_empty_list() -> None:
    with pytest.raises(ValidationError):
        RetrievalSettings(default_backends=[])
