"""Write the OpenAPI spec to a file for the portal's generated client.

    python scripts/export_openapi.py ../frontend/openapi/openapi.json
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The spec needs no database: give settings a placeholder if none is configured (for example in CI).
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://openapi@127.0.0.1:5432/none")
os.environ.setdefault("DOCS_ENABLED", "true")

from app.main import app  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "openapi.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
