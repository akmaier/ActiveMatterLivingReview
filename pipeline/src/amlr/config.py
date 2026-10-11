"""TDM credential loading.

Looks for `tdm_api.toml` at:

1. `$ACTIVE_MATTER_TDM_CONFIG` if set,
2. `/Users/maier/Documents/code/experteye/config/tdm_api.toml` otherwise.

Credential values are never printed; the `TdmConfig.redacted()` helper
is the only interface meant for logs.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


# pipeline/src/amlr/config.py → repo root (valid for the documented editable install).
REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_CONFIG_PATH = Path(
    "/Users/maier/Documents/code/experteye/config/tdm_api.toml"
)
ENV_VAR = "ACTIVE_MATTER_TDM_CONFIG"


@dataclass
class TdmConfig:
    """Parsed TDM credentials. Values are kept opaque; use `redacted()` for logging."""

    source_path: Path
    elsevier_api_key: str | None = None
    elsevier_insttoken: str | None = None
    wiley_tdm_token: str | None = None
    springer_oa_api_key: str | None = None
    springer_meta_api_key: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def redacted(self) -> dict[str, str]:
        """Return a shape-only view for logs — never prints token material."""

        def tag(v: str | None) -> str:
            return "set" if v else "missing"

        return {
            "source_path": str(self.source_path),
            "elsevier.api_key": tag(self.elsevier_api_key),
            "elsevier.insttoken": tag(self.elsevier_insttoken),
            "wiley.tdm_token": tag(self.wiley_tdm_token),
            "springer.oa_api_key": tag(self.springer_oa_api_key),
            "springer.meta_api_key": tag(self.springer_meta_api_key),
            "ads.ads_token": tag((self.raw.get("ads") or {}).get("ads_token")),
        }


def _resolve_path() -> Path:
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override).expanduser()
    return DEFAULT_CONFIG_PATH


def load_tdm_config(path: Path | None = None) -> TdmConfig:
    """Load TDM credentials, honoring the env override.

    Raises FileNotFoundError if the resolved path does not exist.
    """

    path = path or _resolve_path()
    if not path.exists():
        raise FileNotFoundError(
            f"TDM config not found at {path}. Set {ENV_VAR} or place a "
            f"tdm_api.toml at the default experteye location."
        )
    with path.open("rb") as fh:
        data: dict[str, Any] = tomllib.load(fh)

    elsevier = data.get("elsevier", {}) or {}
    wiley = data.get("wiley", {}) or {}
    springer = data.get("springer", {}) or {}

    return TdmConfig(
        source_path=path,
        elsevier_api_key=elsevier.get("api_key"),
        elsevier_insttoken=elsevier.get("insttoken"),
        wiley_tdm_token=wiley.get("tdm_token"),
        springer_oa_api_key=springer.get("oa_api_key"),
        springer_meta_api_key=springer.get("meta_api_key"),
        raw=data,
    )
