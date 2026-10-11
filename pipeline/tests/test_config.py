from pathlib import Path

import pytest

from amlr.config import ENV_VAR, load_tdm_config


def test_env_override_takes_precedence(tmp_path, monkeypatch):
    cfg_file = tmp_path / "tdm.toml"
    cfg_file.write_text(
        '[elsevier]\napi_key = "els"\n'
        '[wiley]\ntdm_token = "wi"\n'
        '[springer]\noa_api_key = "sp"\nmeta_api_key = "sm"\n'
    )
    monkeypatch.setenv(ENV_VAR, str(cfg_file))
    cfg = load_tdm_config()
    assert cfg.source_path == cfg_file
    assert cfg.elsevier_api_key == "els"
    r = cfg.redacted()
    # Values are never printed:
    assert r["elsevier.api_key"] == "set"
    assert r["springer.meta_api_key"] == "set"


def test_missing_file_raises(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "nope.toml"))
    with pytest.raises(FileNotFoundError):
        load_tdm_config()
