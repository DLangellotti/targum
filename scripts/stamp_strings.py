"""Record which English each translation was made from (targum-internal#337).

`strings.text()` says a key in English only where another language has not filled it. A
key it *has* filled is said in that language whatever the English has since become — so
an English sentence that changes while its Russian stays is served stale, and nothing
warns. `tests/test_strings.py` compares every translated key's English against the
fingerprint recorded here, and fails until the translation has been looked at again.

Run it after changing a translation to match new English:

    uv run python scripts/stamp_strings.py

It stamps every language beside `en.json`. It does not translate anything and it does not
check the translation: it records that somebody looked.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

STRINGS = Path(__file__).resolve().parent.parent / "src" / "targum" / "strings"


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def main() -> None:
    english = json.loads((STRINGS / "en.json").read_text(encoding="utf-8"))
    for path in sorted(STRINGS.glob("*.json")):
        if path.name == "en.json":
            continue
        said = json.loads(path.read_text(encoding="utf-8"))
        # A plural form English does not have ("few", "many") answers to the English
        # plural it was written beside.
        stamps = {}
        for key in said:
            source = key if key in english else key.rsplit(".", 1)[0] + ".other"
            if source in english:
                stamps[key] = fingerprint(english[source])
        # In a folder of their own: `strings.languages()` reads every `*.json` beside the
        # module as a language, and a file of fingerprints is not one.
        out = STRINGS / "from" / path.name
        out.parent.mkdir(exist_ok=True)
        text = json.dumps(stamps, ensure_ascii=False, indent=0, sort_keys=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"from/{out.name}: {len(stamps)} keys")


if __name__ == "__main__":
    main()
