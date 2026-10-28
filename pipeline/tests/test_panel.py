from amlr import llm


def test_panel_defaults_without_config(tmp_path, monkeypatch):
    monkeypatch.setenv("AMLR_LLM_CONFIG", str(tmp_path / "missing.toml"))
    for rv in ("R1", "R2", "R3"):
        monkeypatch.delenv(f"AMLR_PANEL_{rv}", raising=False)
    assert llm.load_panel() == llm.DEFAULT_PANEL


def test_panel_from_config_then_env(tmp_path, monkeypatch):
    cfg = tmp_path / "llm_api.toml"
    cfg.write_text('[llm]\napi_key = "x"\n[panel]\nR1 = "model-a"\nR2 = ""\nR9 = "ignored"\n')
    monkeypatch.setenv("AMLR_LLM_CONFIG", str(cfg))
    monkeypatch.setenv("AMLR_PANEL_R3", "model-c")
    monkeypatch.delenv("AMLR_PANEL_R1", raising=False)
    monkeypatch.delenv("AMLR_PANEL_R2", raising=False)
    panel = llm.load_panel()
    assert panel == {"R1": "model-a", "R2": llm.DEFAULT_PANEL["R2"], "R3": "model-c"}


def test_credentials_from_generic_env(monkeypatch):
    for name in ("RRZE_LLM_API_KEY", "NHR_LLM_API_KEY", "RRZE_LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AMLR_LLM_API_KEY", "k")
    monkeypatch.setenv("AMLR_LLM_BASE_URL", "http://localhost:8000/v1")
    assert llm._credentials() == ("http://localhost:8000/v1", "k")
