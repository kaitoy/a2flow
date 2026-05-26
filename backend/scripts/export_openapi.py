"""Export the FastAPI OpenAPI spec to a YAML file.

Usage:
    uv run python -m scripts.export_openapi [output_path]

The output path defaults to ``backend/openapi.yaml`` (relative to this file),
and can be overridden by the first CLI argument or the
``OPENAPI_OUTPUT`` environment variable.

The application itself declares ``response_model=ApiResponse[T]`` on every
envelope-returning route, so the spec produced by ``app.openapi()`` already
contains the ``{meta, data, error}`` shape. No post-processing is needed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    from main import app

    if len(sys.argv) > 1:
        output = Path(sys.argv[1]).resolve()
    elif env_path := os.getenv("OPENAPI_OUTPUT"):
        output = Path(env_path).resolve()
    else:
        output = BACKEND_DIR / "openapi.yaml"

    spec = app.openapi()

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        yaml.safe_dump(spec, f, sort_keys=False, allow_unicode=True)

    print(f"Wrote OpenAPI spec to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
