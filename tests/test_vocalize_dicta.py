"""DICTA's menaked as a vocalizer: the skeleton, the register gate, the fetch, the
fallback, and the credit (targum-internal#148).

No test here loads the model or touches the network. The model's part is played by a
stub that answers the way its head does — one class index per token — so what is tested
is everything targum wrote around the weights, which is where the two bugs the
measurement found both lived.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unicodedata import normalize

import pytest

from targum import vocalize
from targum.catalogue import Register
from targum.models import BlockKind, Document, Segment, SegmentedDocument, Vocalization
from targum.vocalize import dicta
from targum.vocalize.base import strip_nikkud

#: The model's classes, as its config carries them: nothing, a mater, dagesh, then the
#: vowels. Enough of the real list to spell a word with.
CLASSES = ["", dicta.MAT_LECT, "ּ", "ְ", "ִ", "ֵ", "ִּ", "ָ"]
SHIN = ["ׁ", "ׂ"]


def _offsets(text: str, expand: str = "") -> list[tuple[int, int]]:
    """Token spans the way the real tokenizer reports them: the sentinels at (0, 0), one
    span per character, and a character in `expand` reported three times over, which is
    what NFKC does to an ellipsis."""
    spans: list[tuple[int, int]] = [(0, 0)]
    for at, char in enumerate(text):
        spans.extend([(at, at + 1)] * (3 if char in expand else 1))
    spans.append((0, 0))
    return spans


class TestAssemble:
    def test_every_character_is_written_once_whatever_the_tokenizer_did(self) -> None:
        """The card's `predict` wrote `…` as `………`, and the skeleton check refused the
        line. Walking the input rather than the tokens makes that impossible."""
        text = "שלום… דיבר"
        offsets = _offsets(text, expand="…")
        nikud = [0] * len(offsets)
        shin = [0] * len(offsets)
        out = dicta.assemble(text, offsets, nikud, shin, CLASSES, SHIN)
        assert strip_nikkud(out)[0] == text

    def test_a_mater_is_kept_bare_and_a_shin_gets_its_dot(self) -> None:
        text = "דיבר שם"
        offsets = _offsets(text)
        # Token 0 is [CLS]; then ד, י, ב, ר, space, ש, ם.
        nikud = [0, 6, 1, 5, 0, 0, 7, 0, 0]  # דִּ, mater, בֵ, ר bare, ..., שָ
        shin = [0, 0, 0, 0, 0, 0, 1, 0, 0]  # sin dot on the shin
        out = dicta.assemble(text, offsets, nikud, shin, CLASSES, SHIN)
        # Canonical order on both sides: the head writes dagesh before the vowel and the
        # shin dot before both, and Unicode has an opinion of its own.
        assert normalize("NFC", out) == normalize("NFC", "דִּיבֵר שָׂם")
        assert strip_nikkud(out)[0] == text

    def test_a_letter_past_the_ceiling_comes_back_bare_rather_than_lost(self) -> None:
        """Truncation drops tokens, never letters: the tail has no answer and no marks."""
        text = "אבג"
        out = dicta.assemble(text, [(0, 0), (0, 1), (0, 0)], [0, 7, 0], [0, 0, 0], CLASSES, SHIN)
        assert out == "אָבג"


class StubModel:
    """Answers like the menaked's head, from a table, so `point` runs without weights."""

    class config:  # noqa: N801 - mirrors transformers' attribute
        nikud_classes = CLASSES
        shin_classes = SHIN


def _stub_infer(answers: dict[str, list[int]]):  # type: ignore[no-untyped-def]
    def infer(model: Any, tokenizer: Any, text: str) -> tuple[Any, Any, Any]:
        offsets = _offsets(text, expand="…")
        nikud = answers.get(text, [0] * len(offsets))
        return offsets, nikud, [0] * len(offsets)

    return infer


class TestTheVocalizer:
    def test_it_is_a_vocalizer_and_keeps_the_skeleton_on_every_segment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dicta, "infer", _stub_infer({}))
        engine = dicta.DictaVocalizer()
        monkeypatch.setattr(engine, "load", lambda: (StubModel(), object()))
        segments = [
            Segment(id="s0", block_id="b", block_index=0, index=0, text="שלום… עולם"),
            Segment(id="s1", block_id="b", block_index=0, index=1, text="לאט־לאט"),
            Segment(id="s2", block_id="b", block_index=0, index=2, text="   "),
        ]
        out = engine.vocalize(segments, "he")
        assert set(out) == {"s0", "s1"}, "a blank segment is not pointed"
        for segment in segments[:2]:
            assert strip_nikkud(out[segment.id])[0] == segment.text
        assert "־" in out["s1"], "the maqaf survived"

    def test_the_name_says_dicta_and_the_model_is_named_in_full(self) -> None:
        engine = dicta.DictaVocalizer()
        assert engine.name.startswith("dicta/")
        assert engine.model == dicta.MODEL
        assert engine.name in vocalize.names()

    def test_it_is_unavailable_without_the_weights(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dicta, "downloaded", lambda: False)
        usable, why = dicta.DictaVocalizer().available()
        assert not usable
        assert "targum models fetch menaked" in why


class TestDownloaded:
    def test_it_looks_beside_the_annotator_s_weights(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path))
        assert not dicta.downloaded()
        snapshot = dicta.snapshot_dir() / "abc123"
        snapshot.mkdir(parents=True)
        (snapshot / "model.safetensors").write_bytes(b"0" * 10)
        assert not dicta.downloaded(), "weights without the tokenizer are not a model"
        (snapshot / "tokenizer.json").write_text("{}")
        assert dicta.downloaded()
        assert dicta.size() == 12
        assert dicta.hub_root() == tmp_path / "hf"


class TestTheRegisterGate:
    """The menaked's card: not for biblical, rabbinic or premodern Hebrew."""

    @pytest.mark.parametrize("register", [Register.biblical, Register.rabbinic, Register.medieval])
    def test_the_study_house_stays_on_nakdimon(self, register: Register) -> None:
        assert vocalize.name_for("wikisource:x", register) == vocalize.NakdimonVocalizer.name

    @pytest.mark.parametrize("register", [Register.revival, Register.modern, Register.none])
    def test_modern_hebrew_and_an_upload_go_to_the_menaked(self, register: Register) -> None:
        assert vocalize.name_for("upload:x", register) == dicta.DictaVocalizer.name

    def test_the_register_is_read_off_the_catalogue(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from targum import catalogue

        class Entry:
            register = Register.rabbinic

        monkeypatch.setattr(
            catalogue,
            "matching",
            lambda source: Entry() if source == "wikisource:Mishnah" else None,
        )
        assert vocalize.register_of("wikisource:Mishnah") == Register.rabbinic
        assert vocalize.register_of("https://example.com/news") == Register.none
        assert vocalize.name_for("wikisource:Mishnah") == vocalize.NakdimonVocalizer.name
        assert vocalize.name_for("https://example.com/news") == dicta.DictaVocalizer.name

    def test_scripture_and_the_pinned_editions_reach_no_model_at_all(self) -> None:
        """Unchanged by the swap, and pinned again here because the gate sits behind it."""
        from targum.models import keeps_its_own_pointing

        for source in ("sefaria:Ruth", "sefaria:Mishnah Berakhot", "siddur:Weekday, Minchah"):
            assert keeps_its_own_pointing(source), source


class TestTheFallback:
    def test_without_the_weights_nakdimon_points_and_the_reason_is_said(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dicta, "downloaded", lambda: False)
        said: list[str] = []
        engine = vocalize.for_source("upload:x", register=Register.modern, notify=said.append)
        assert engine.name == vocalize.NakdimonVocalizer.name
        assert said and "targum models fetch menaked" in said[0] and "Nakdimon" in said[0]

    def test_with_the_weights_the_menaked_is_chosen_and_not_loaded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dicta, "downloaded", lambda: True)
        # A fresh cache, not the process's: on a machine that holds the weights, an
        # earlier test in the same run may have loaded them, and this asserts about
        # this call alone.
        monkeypatch.setattr(dicta, "_LOADED", {})
        said: list[str] = []
        engine = vocalize.for_source("upload:x", register=Register.modern, notify=said.append)
        assert engine.name == dicta.DictaVocalizer.name
        assert said == []
        assert dicta.MODEL not in dicta._LOADED, "choosing is not loading"

    def test_the_study_house_never_asks_whether_the_weights_are_here(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(dicta, "downloaded", lambda: False)
        said: list[str] = []
        engine = vocalize.for_source("x", register=Register.rabbinic, notify=said.append)
        assert engine.name == vocalize.NakdimonVocalizer.name
        assert said == []


class TestTheFetch:
    def test_models_fetch_menaked_brings_the_weights(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from typer.testing import CliRunner

        from targum.cli import app

        calls: list[str] = []
        monkeypatch.setattr(dicta, "downloaded", lambda: False)
        monkeypatch.setattr(
            dicta, "fetch", lambda notify=None: calls.append("fetched") or 1_200_000_000
        )
        result = CliRunner().invoke(app, ["models", "fetch", "menaked"])
        assert result.exit_code == 0, result.output
        assert calls == ["fetched"]
        assert "Downloaded" in result.output and "1.2 GB" in result.output
        assert "CC BY 4.0" in result.output

    def test_and_says_so_when_they_are_already_here(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from typer.testing import CliRunner

        from targum.cli import app

        monkeypatch.setattr(dicta, "downloaded", lambda: True)
        monkeypatch.setattr(dicta, "fetch", lambda notify=None: pytest.fail("fetched again"))
        result = CliRunner().invoke(app, ["models", "fetch", "menaked"])
        assert result.exit_code == 0, result.output
        assert "already downloaded" in result.output

    def test_fetch_itself_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dicta, "downloaded", lambda: True)
        monkeypatch.setattr(dicta, "size", lambda: 7)
        monkeypatch.setattr(
            dicta.DictaVocalizer, "load", lambda self: pytest.fail("loaded the network")
        )
        assert dicta.fetch() == 7


class Named:
    """A vocalizer that points nothing and only has a name, for the staleness rule."""

    model = None

    def __init__(self, name: str) -> None:
        self.name = name
        self.asked = 0

    def available(self) -> tuple[bool, str]:
        return True, ""

    def vocalize(self, segments: list[Segment], language: str) -> dict[str, str]:
        self.asked += 1
        return {segment.id: segment.text.replace("א", "אַ") for segment in segments}


class TestTheNameIsTheKey:
    def test_a_pointing_by_another_vocalizer_is_redone_and_by_the_same_one_kept(
        self, tmp_path: Path, fake_segmenter: object
    ) -> None:
        """What lets the swap reach a text already built, and what stops it from doing
        so twice: a `vocalization.json` naming Nakdimon is stale under the menaked."""
        from targum.pipeline import Build

        source = tmp_path / "text.md"
        source.write_text("# כותרת\n\nאבא בא. אמא באה.\n", encoding="utf-8")

        def build(engine: Named) -> Vocalization | None:
            return (
                Build(
                    str(source),
                    provider_name="null",
                    out=tmp_path / "out",
                    segmenter=fake_segmenter,  # type: ignore[arg-type]
                    target_language="en",
                    vocalizer=engine,
                )
                .run()
                .vocalization
            )

        first = Named("nakdimon/2")
        assert build(first) is not None and first.asked == 1
        again = Named("nakdimon/2")
        build(again)
        assert again.asked == 0, "the same vocalizer's pointing was not reused"
        newer = Named("dicta/menaked/1")
        result = build(newer)
        assert newer.asked == 1, "another vocalizer's pointing was read as this one's"
        assert result is not None and result.vocalizer == "dicta/menaked/1"


class TestTheCredit:
    def test_a_reader_the_menaked_pointed_names_dicta_and_others_do_not(
        self, tmp_path: Path, segmented: SegmentedDocument, translation: Any
    ) -> None:
        from targum.render import render

        document = Document(
            source="memory", title="Declaration", language="he", blocks=[], content_hash="abc"
        )
        sid = segmented.segments[0].id

        def page(vocalizer: str, machine: list[str]) -> str:
            vocalization = Vocalization(
                document_hash="h",
                language="he",
                vocalizer=vocalizer,
                segments={sid: segmented.segments[0].text},
                machine=machine,
            )
            out = tmp_path / vocalizer.replace("/", "-") / str(len(machine))
            return render(document, segmented, [translation], out, vocalization=vocalization)[
                0
            ].read_text(encoding="utf-8")

        by_menaked = page("dicta/menaked/1", [sid])
        assert "Vowel points by" in by_menaked
        assert "https://huggingface.co/dicta-il/dictabert-large-char-menaked" in by_menaked
        assert "https://creativecommons.org/licenses/by/4.0/" in by_menaked
        assert "Vowel points by" not in page("nakdimon/2", [sid])
        assert "Vowel points by" not in page("dicta/menaked/1", []), (
            "a text its edition pointed owes the model nothing"
        )


def test_the_segment_kinds_a_label_is_are_still_never_pointed() -> None:
    """Nothing about the swap reaches the labels: a heading is not prose."""
    assert BlockKind.heading in vocalize.LABELS
