"""How much Hebrew you understand, the server half (targum-internal#575).

`/account/reading` carries, per yardstick with a snapshot, the exact percentage now and
the base and daily gains the page draws the line from. A yardstick with no snapshot is
left out, never sent as 0. The page half is `test_progress_understand_js.py`; the
yardsticks themselves are `test_yardstick.py`. Every lemma is a placeholder.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import test_serve
from test_serve import Postbox, call, sign_in

KNOWN = 9

served = test_serve.served
postbox = test_serve.postbox


def snapshot(register: str, weights: dict[str, float]) -> None:
    """A yardstick file where the server looks for one, as `tables snapshot` writes it."""
    folder = Path(os.environ["TARGUM_TABLES_DIR"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"yardstick-{register}-v1.json").write_text(
        json.dumps(
            {"register": register, "version": 1, "made_at": "2026-10-30", "weights": weights}
        ),
        encoding="utf-8",
    )


def test_each_yardstick_with_a_list_is_sent_with_its_own_percentage(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, _ = served
    cookie = sign_in(port, postbox)
    snapshot("news", {"ספר": 0.5, "בית": 0.3, "ים": 0.2})
    snapshot("bible", {"ים": 0.996, "אור": 0.004})
    words = [
        {"language": "he", "lemma": "ספר", "status": KNOWN, "at": 1, "seen": 1},
        {"language": "he", "lemma": "ים", "status": KNOWN, "at": 1, "seen": 1},
        {"language": "he", "lemma": "בית", "status": 2, "at": 1, "seen": 1},
        # A name is not vocabulary, whatever list it would be on.
        {"language": "he", "lemma": "משה", "status": KNOWN, "at": 1, "seen": 1, "band": "name"},
    ]
    status, answer, _ = call(port, "POST", f"/sync?k={token}", {"words": words}, cookie=cookie)
    assert status == 200 and answer["signedIn"], answer

    status, said, _ = call(port, "GET", f"/account/reading?k={token}", cookie=cookie)
    assert status == 200, said
    mine = said["understand"]["he"]
    assert set(mine["registers"]) == {"news", "bible"}, "no list, no entry: never a 0%"
    news = mine["registers"]["news"]
    assert news["percent"] == 70 and abs(news["base"] - 0.7) < 1e-9 and news["days"] == []
    assert mine["registers"]["bible"]["percent"] == 99, "under all of it is never 100%"
    assert isinstance(mine["began"], int)


def test_a_word_become_known_since_the_record_began_is_a_days_gain(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, _ = served
    cookie = sign_in(port, postbox)
    snapshot("news", {"ספר": 0.5, "בית": 0.5})
    status, said, _ = call(port, "GET", f"/account/reading?k={token}", cookie=cookie)
    # Nothing known yet: sent as it is, and the page draws no card for it.
    assert said["understand"]["he"]["registers"]["news"] == {"percent": 0, "base": 0, "days": []}
    import time

    now = int(time.time() * 1000)
    word = {"language": "he", "lemma": "ספר", "status": KNOWN, "at": now, "seen": now}
    call(port, "POST", f"/sync?k={token}", {"words": [word]}, cookie=cookie)
    status, said, _ = call(port, "GET", f"/account/reading?k={token}&tz=UTC", cookie=cookie)
    news = said["understand"]["he"]["registers"]["news"]
    assert news["base"] == 0 and len(news["days"]) == 1 and news["days"][0]["gain"] == 0.5
    assert news["percent"] == 50
