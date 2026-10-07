"""Write the API's OpenAPI spec to copilot-studio/openapi.json.

Import that file into Copilot Studio (Tools > Add a tool > REST API) or a
Power Platform custom connector. Run after any API change; a test fails if
the committed spec is out of date.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402

out = ROOT / "copilot-studio" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print(f"Wrote {out.relative_to(ROOT)}")
