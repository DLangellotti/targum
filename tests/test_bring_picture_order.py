"""Pictures of one text go up in the order their names count (2026-11-23).

Nine pages sent from a phone, named …104 to …112, arrived in the picker's order — 107,
108, 104, 105, 106, 109, 112, 111, 110 — and were read in it, so the book opened on its
third page. The page now sends them by name, numbers read as numbers.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from targum.render.builder import ASSETS

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

RUN = r"""
const fs = require("fs");
const begun = [];
let next = 0;
global.window = {};
global.document = { addEventListener() {} };
global.fetch = (path, init) => {
  let body = {};
  try { body = JSON.parse(init && init.body); } catch (e) {}
  let answer = {};
  if (path.startsWith("/upload/begin")) {
    begun.push(body.name);
    answer = { upload: "u" + next++, chunk: 1 << 20 };
  } else if (path.endsWith("/end")) {
    answer = { upload: path.split("/")[2] };
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve(answer) });
};
eval(fs.readFileSync(process.argv[1], "utf8"));
const files = JSON.parse(process.argv[2]).map((name) => ({
  name, size: 10, type: "image/jpeg", slice: () => "x",
}));
window.TargumBring.upload(files).then((sent) => {
  console.log(JSON.stringify({ begun, sent }));
});
"""


def sent(names: list[str]) -> dict[str, list[str]]:
    done = subprocess.run(
        ["node", "-e", RUN, str(ASSETS / "bring.js"), json.dumps(names)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_pictures_go_up_in_the_order_their_names_count() -> None:
    picked = [f"5197590390662439{n}.jpg" for n in (107, 108, 104, 105, 106, 109, 112, 111, 110)]
    got = sent(picked)
    assert got["begun"] == sorted(picked)
    assert got["sent"] == {"uploads": [f"u{n}" for n in range(9)]}


def test_numbers_in_a_name_count_as_numbers() -> None:
    got = sent(["IMG_10.png", "IMG_9.png", "IMG_100.png", "IMG_1.png"])
    assert got["begun"] == ["IMG_1.png", "IMG_9.png", "IMG_10.png", "IMG_100.png"]
