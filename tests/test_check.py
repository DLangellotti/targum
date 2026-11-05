"""The words check on arrival (design.md §12, "The arrival asks which words you know",
2026-11-01; targum-internal#613): its fixed lists, the rules that pick round two, what an
account keeps of it, and what the estimate makes of it."""

from __future__ import annotations

import gzip
import json
import math
import re
import unicodedata
from pathlib import Path

import pytest

from targum import check
from targum import estimate as estimate_module
from targum.accounts import Store

ANNOTATE = Path(__file__).resolve().parents[1] / "src" / "targum" / "annotate"


# -- the lists -----------------------------------------------------------------------


def test_the_lists_have_the_shape_both_rounds_need() -> None:
    """Six bands of eight, sixteen made-up words, nothing twice: three of each band and
    four made-up words in round one, five of three bands and four more in round two, and
    no word a reader sees in both."""
    assert len(check.BANDS) == 6 and all(len(band) == 8 for band in check.BANDS)
    real = [word for band in check.BANDS for word in band]
    assert len(set(real)) == len(real) == 48
    assert len(set(check.MADE_UP)) == len(check.MADE_UP) == 16
    assert not set(real) & set(check.MADE_UP)
    one_real, one_made = check.first_round()
    assert len(one_real) == 18 and len(one_made) == 4
    for at in range(len(check.BANDS)):
        # Round one's words of every band up to `at` ticked: the yeses run out there.
        ticked = [word for band in check.BANDS[: at + 1] for word in band[: check.FIRST]]
        two_real, two_made = check.second_round(ticked)
        assert check.edge(ticked) == at
        assert check.window(at) == max(0, min(at - 1, len(check.BANDS) - check.WINDOW))
        assert len(two_real) == 15 and len(two_made) == 4
        assert not set(two_real) & set(one_real)
        assert not set(two_made) & set(one_made)


def test_every_word_is_unpointed_hebrew_with_no_space() -> None:
    """Unpointed, as David decided (2026-11-01), and one word each."""
    for word in check.every_word():
        assert re.fullmatch("[א-ת]+", word), word


def _lexicon() -> tuple[set[str], list[str]]:
    """Every Hebrew form on the laptop's lists: wordfreq's whole list (names, brands and
    typos among its 592,000), the verb forms of `paradigms.json.gz` and the Tanakh's
    headwords; and wordfreq's commonest 30,000 in order."""
    wordfreq = pytest.importorskip("wordfreq")
    forms = set(wordfreq.get_frequency_dict("he"))
    if not forms:
        pytest.skip("wordfreq has no Hebrew list here")
    paradigms = json.loads(gzip.open(ANNOTATE / "paradigms.json.gz").read())
    forms |= set(paradigms["by_form"])
    tanakh = json.loads((ANNOTATE / "tanakh.json").read_text(encoding="utf-8"))
    stack: list[object] = [tanakh]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                if re.search("[א-ת]", key):
                    forms.add(re.sub("[֑-ׇ־]", "", key))
                stack.append(value)
        elif isinstance(item, list):
            stack.extend(item)
    return forms, list(wordfreq.top_n_list("he", 30_000))


def _restored(word: str) -> set[str]:
    """The word with up to two ו or י put in or taken out: how a word written short
    (כתיב חסר) is found in its full spelling, and the other way round."""
    out = {word}
    edge = {word}
    for _ in range(2):
        grown: set[str] = set()
        for one in edge:
            for at in range(1, len(one)):
                grown |= {one[:at] + "ו" + one[at:], one[:at] + "י" + one[at:]}
            grown |= {one[:at] + one[at + 1 :] for at in range(len(one)) if one[at] in "וי"}
        out |= grown
        edge = grown
    return out


def _one_apart(a: str, b: str) -> bool:
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    short, long = sorted((a, b), key=len)
    return any(long[:at] + long[at + 1 :] == short for at in range(len(long)))


def test_no_made_up_word_is_a_word() -> None:
    """The check before this one let מסגפת through, which is מְסַגֶּפֶת, a real word
    (ling-he, 2026-11-01). So each made-up word is held to what that review held it to:

    - not on any list as written;
    - not a word with a ו or a י restored or dropped (מרגזת is מרוגזת written short);
    - not a word once a prefix letter goes (ו ה ב כ ל מ ש);
    - not one letter from a word in the commonest 30,000 a reader would take it for —
      the few accepted neighbours were judged and are named here;
    - not מ + three letters + ת, the feminine participle written short, which is a real
      word for nearly every root that has a pi'el, a pu'al or a hif'il.
    """
    forms, common = _lexicon()
    judged = {
        # A rare construct form; תעלומה itself is two letters away, and ב is not ע.
        ("תבלומת", "תעלומת"),
        # Uncommon, and ג is not ד.
        ("תשגורת", "תשדורת"),
        # Its own verb form without the ending (every taCCuCa noun has one: תחבורה is
        # תחבור + ה); the noun pattern is what a reader sees.
        ("תזרוקה", "תזרוק"),
    }
    for word in check.MADE_UP:
        assert word not in forms, f"{word} is a word"
        for spelled in _restored(word):
            assert spelled not in forms, f"{word} is {spelled} written short"
        for prefix in "והבכלמש":
            if word.startswith(prefix) and len(word) > 3:
                assert word[1:] not in forms, f"{word} is {prefix} + {word[1:]}"
        assert not re.fullmatch("מ[א-ת]{3}ת", word), f"{word} has the participle's shape"
        for near in common:
            if _one_apart(word, near):
                assert (word, near) in judged, f"{word} is one letter from {near}"
    for rejected in ("מסגפת", "מרגזת", "מקרסת", "מכדרת", "תשתוקה", "תמרוכה", "גרפון"):
        assert rejected not in check.MADE_UP, f"{rejected} was rejected (ling-he, 2026-11-01)"


def test_the_bands_climb_the_frequency_list() -> None:
    """Every real word is ranked, and every word of a band is rarer than every word of
    the band before: what round two's choice of band means rests on it."""
    from targum.annotate import frequency

    if not frequency.ranks("he"):
        pytest.skip("wordfreq has no Hebrew list here")
    previous = 0
    for band in check.BANDS:
        places = [frequency.rank(word, "he") for word in band]
        assert all(place is not None for place in places), band
        ranked = [place for place in places if place is not None]
        assert min(ranked) > previous, band
        previous = max(ranked)


# -- the rules -----------------------------------------------------------------------


def test_round_two_is_drawn_around_where_the_yeses_ran_out() -> None:
    """The last band in which at least two of round one's three were ticked, and one band
    each side, kept inside the six."""
    first = [band[: check.FIRST] for band in check.BANDS]
    assert check.edge([]) == 0 and check.window(0) == 0
    knows_two = [*first[0], *first[1], *first[2][:2]]
    assert check.edge(knows_two) == 2 and check.window(2) == 1
    real, _ = check.second_round(knows_two)
    assert set(real) == {word for band in check.BANDS[1:4] for word in band[3:]}
    everything = [word for band in first for word in band]
    assert check.edge(everything) == 5 and check.window(5) == 3
    # One yes in three is not half.
    assert check.edge([first[4][0]]) == 0


def test_what_is_kept_is_only_what_could_have_been_shown() -> None:
    """A word round two would not have shown this reader, or that no round has, is
    dropped: the page and the store agree on the rules, and anything else did not come
    from the page."""
    first_real, first_made = check.first_round()
    hidden_band = check.BANDS[5][3]  # round two shows band 5 only to a reader near it
    kept = check.kept([first_real[0], first_made[0], hidden_band, "שלום", first_real[0]])
    assert kept == [first_real[0], first_made[0]]


def test_the_guess_rate_comes_from_the_made_up_words() -> None:
    """None of eight ticked is a careful reader; all eight is a reader who ticks anything."""
    assert check.guess(0, 8) == pytest.approx(0.03)
    assert check.guess(8, 8) == pytest.approx(0.83)
    assert check.guess(0, 0) == pytest.approx(check.GUESS_PRIOR)
    known, unknown, rate = check.answers([*check.BANDS[0][:3], check.MADE_UP[0]])
    assert known == list(check.BANDS[0][:3])
    assert len(unknown) == 18 + 15 - 3
    assert rate == pytest.approx((1 + 0.3) / 10)


# -- what an account keeps -------------------------------------------------------------


def _reader(tmp_path: Path) -> tuple[Store, object]:
    store = Store(tmp_path / "words.db")
    signed = store.finish_sign_in(store.start_sign_in("new@example.com"))
    assert signed is not None
    return store, signed[0]


def test_a_check_is_kept_as_its_ticks_and_never_reaches_the_list(tmp_path: Path) -> None:
    """One row a reader and language, replaced by a second check; exported with the rest;
    and no word ticked on it is on the reader's list."""
    store, person = _reader(tmp_path)
    assert store.checked(person.id, "he") is None  # type: ignore[attr-defined]
    store.set_checked(person, "he", check.VERSION, ["עכשיו", "תמיד"])  # type: ignore[arg-type]
    store.set_checked(person, "he", check.VERSION, ["דרך"])  # type: ignore[arg-type]
    assert store.checked(person.id, "he") == (check.VERSION, ["דרך"])  # type: ignore[attr-defined]
    words, _, _ = store.knowledge(person.id, "he")  # type: ignore[attr-defined]
    assert words == [], "a tick is evidence, not a word on the list"
    exported = store.everything(person)  # type: ignore[arg-type]
    assert exported["checked"][0]["ticked"] == ["דרך"]
    assert exported["checked"][0]["version"] == check.VERSION


# -- what the estimate makes of it ------------------------------------------------------


def _theta(tmp_path: Path, ticked: list[str] | None) -> float:
    estimate_module.forget()
    store, person = _reader(tmp_path)
    if ticked is not None:
        store.set_checked(person, "he", check.VERSION, check.kept(ticked))  # type: ignore[arg-type]
    return estimate_module.for_reader(store, person.id, "he").theta  # type: ignore[attr-defined]


def test_the_check_moves_the_estimate_and_made_up_ticks_weaken_it(tmp_path: Path) -> None:
    """A reader who knows the first four bands is placed well past aleph. The same reader
    ticking every made-up word as well is placed far lower — under where they started,
    because their yeses count for little and the words they left still count in full. And
    a check against lists this targum no longer has says nothing at all."""
    pytest.importorskip("wordfreq")
    from targum.annotate import frequency

    if not frequency.ranks("he"):
        pytest.skip("wordfreq has no Hebrew list here")
    prior = _theta(tmp_path / "a", None)
    four = [word for band in check.BANDS[:4] for word in band]
    careful = _theta(tmp_path / "b", four)
    careless = _theta(tmp_path / "c", [*four, *check.MADE_UP])
    assert careful > prior + 1
    assert careless < careful - 1
    nobody = _theta(tmp_path / "d", [])
    assert nobody < prior, "a check with nothing ticked says they know little"

    estimate_module.forget()
    store, person = _reader(tmp_path / "e")
    store.set_checked(person, "he", "1999-01-01", four)  # type: ignore[arg-type]
    old = estimate_module.for_reader(store, person.id, "he")  # type: ignore[attr-defined]
    assert old.theta == pytest.approx(prior) and old.evidence == 0


def test_the_check_measures_the_claim_grids_guess_too() -> None:
    """A reader whose check says they tick no word they cannot know has their claim-grid
    ticks read with that rate, not the 15% assumed of everybody."""
    items, rate = estimate_module.checked_evidence((check.VERSION, list(check.BANDS[0])))
    assert rate == pytest.approx(0.03)
    assert all(item.guess == pytest.approx(0.03) for item in items if item.known)
    # A word marked since is the mark's alone.
    marked_items, _ = estimate_module.checked_evidence(
        (check.VERSION, list(check.BANDS[0])), {check.BANDS[0][0]: 9}
    )
    assert check.BANDS[0][0] not in {item.lemma for item in marked_items}
    assert estimate_module.checked_evidence(None) == ([], None)


def test_the_page_carries_the_lists_it_needs() -> None:
    """`/welcome` is handed the lists and the round sizes, and nothing about the reader."""
    from targum.render.builder import welcome_page

    page = welcome_page("k")
    assert "window.TARGUM_CHECKS = " in page
    data = check.page_data()
    assert data["version"] == check.VERSION and data["madeUp"] == list(check.MADE_UP)
    assert set(check.pages()) == {"he", "fr", "ru"}
    for code in check.LISTS:
        assert check.pages()[code]["language"] == code
        for word in check.first_round(code)[0]:
            assert json.dumps(word)[1:-1] in page or word in page, (code, word)


# -- French and Russian (targum-internal#631, 2026-11-05) -------------------------------
#
# The lists are ling-fr's and ling-ru's (#632). Russian's are a draft awaiting David's
# read. Each language is held to the checks its linguist ran that can run here; the
# lexicons behind the rest (Morphalou, OpenRussian, pymorphy3) are on the laptop or not
# at all, and a test that needs one skips without it.

OTHERS = ("fr", "ru")


@pytest.mark.parametrize("code", OTHERS)
def test_each_language_s_lists_have_the_shape_both_rounds_need(code: str) -> None:
    lists = check.LISTS[code]
    assert lists.language == code and lists.version
    assert len(lists.bands) == 6 and all(len(band) == 8 for band in lists.bands)
    real = [word for band in lists.bands for word in band]
    assert len(set(real)) == len(real) == 48
    assert len(set(lists.made_up)) == len(lists.made_up) == 16
    assert not set(real) & set(lists.made_up)
    assert not set(real) & check.every_word("he"), "no word is in two languages' lists"
    one_real, one_made = check.first_round(code)
    assert len(one_real) == 18 and one_made == list(lists.made_up[:4])
    for at in range(6):
        ticked = [word for band in lists.bands[: at + 1] for word in band[: check.FIRST]]
        two_real, two_made = check.second_round(ticked, code)
        assert check.edge(ticked, code) == at
        assert len(two_real) == 15 and len(two_made) == 4
        assert not set(two_real) & set(one_real)
        assert not set(two_made) & set(one_made)
    # The rules are Hebrew's: a reader's ticks are read by their own language's lists.
    assert check.kept([one_real[0], "עכשיו", "שלום"], code) == [one_real[0]]
    known, unknown, rate = check.answers([*one_real[:3], one_made[0]], code)
    assert known == one_real[:3] and len(unknown) == 18 + 15 - 3
    assert rate == pytest.approx((1 + 0.3) / 10)


def test_a_language_with_no_check_has_none() -> None:
    assert check.lists_for("it") is None and check.lists_for("") is None
    assert check.lists_for("ru-RU") is check.LISTS["ru"]
    with pytest.raises(ValueError):
        check.first_round("it")


def test_french_words_are_lowercase_latin_with_french_accents() -> None:
    for word in check.every_word("fr"):
        assert unicodedata.normalize("NFC", word) == word, word
        assert re.fullmatch("[a-zàâäçéèêëîïôöùûüÿœæ]+", word), word


def test_russian_words_are_lowercase_cyrillic_with_no_yo() -> None:
    for word in check.every_word("ru"):
        assert re.fullmatch("[а-яё]+", word) and "ё" not in word, word


@pytest.mark.parametrize("code", OTHERS)
def test_each_language_s_bands_climb_its_frequency_list(code: str) -> None:
    from targum.annotate import frequency

    if not frequency.ranks(code):
        pytest.skip(f"wordfreq has no {code} list here")
    previous = 0
    for band in check.LISTS[code].bands:
        places = [frequency.rank(word, code) for word in band]
        assert all(place is not None for place in places), band
        ranked = [place for place in places if place is not None]
        assert min(ranked) > previous, band
        previous = max(ranked)


def _bare(word: str) -> str:
    """A word with its accents folded and ё read as е, as both linguists compared."""
    folded = unicodedata.normalize("NFD", word.replace("ё", "е").replace("Ё", "Е"))
    return unicodedata.normalize("NFC", "".join(c for c in folded if not unicodedata.combining(c)))


def _wordfreq(code: str) -> tuple[set[str], list[str]]:
    wordfreq = pytest.importorskip("wordfreq")
    forms = {_bare(form) for form in wordfreq.get_frequency_dict(code)}
    if not forms:
        pytest.skip(f"wordfreq has no {code} list here")
    return forms, [_bare(form) for form in wordfreq.top_n_list(code, 30_000)]


def test_no_french_made_up_word_is_a_word() -> None:
    """ling-fr's tests (2026-11-05) that run on wordfreq: not a French or English word as
    written or with its accents folded, not an inflection once -s, -x, -e or -es goes, and
    not one letter from any of the commonest 30,000 French words, accents folded."""
    forms, common = _wordfreq("fr")
    english, _ = _wordfreq("en")
    for word in check.MADE_UP_FR:
        bare = _bare(word)
        assert bare not in forms, f"{word} is a French word"
        assert bare not in english, f"{word} is an English word"
        for ending in ("s", "x", "e", "es"):
            if bare.endswith(ending):
                assert bare[: -len(ending)] not in forms, f"{word} is an inflection"
        for near in common:
            assert not _one_apart(bare, near), f"{word} is one letter from {near}"
    rejected = ("pimeau", "budouille", "chirnier", "sarnette", "ternage", "gaffon")
    rejected += ("chounard", "moutrade", "fourlard", "clapeau", "goubron", "sémeau")
    for word in rejected:
        assert word not in check.MADE_UP_FR, f"{word} was rejected (ling-fr, 2026-11-05)"


MORPHALOU = Path.home() / ".cache" / "targum" / "models" / "morphalou" / "3.1"


def test_no_french_made_up_word_is_in_morphalou() -> None:
    """Morphalou 3.1's 976,000 forms (LGPL-LR, read as a lookup only), accents folded.
    It is on the laptop and not in the repo, so the test skips where it is absent."""
    found = MORPHALOU / "Morphalou3.1_CSV.csv"
    if not found.exists():
        pytest.skip("Morphalou is not on this machine")
    forms: set[str] = set()
    with found.open(encoding="utf-8") as lines:
        for line in lines:
            cells = line.split(";")
            for at in (0, 9):
                if len(cells) > at and cells[at]:
                    forms.add(_bare(cells[at].strip().lower()))
    assert len(forms) > 100_000
    for word in check.MADE_UP_FR:
        assert _bare(word) not in forms, f"{word} is in Morphalou"


#: ling-ru's case-ending swap (2026-11-05): take one ending off and put each other on.
RUSSIAN_ENDINGS = ("а", "у", "ы", "е", "ой", "ом", "ам", "и", "ями", "ов", "ь", "о", "я")


def test_no_russian_made_up_word_is_a_word() -> None:
    """ling-ru's tests (2026-11-05) that run on wordfreq: not in wordfreq's Russian list
    with ё folded, not a case form of a word, and not one letter from any of the
    commonest 30,000. DRAFT lists, awaiting David's read."""
    forms, common = _wordfreq("ru")
    for word in check.MADE_UP_RU:
        assert word not in forms, f"{word} is a word"
        stems = {word} | {word[: -len(e)] for e in RUSSIAN_ENDINGS if word.endswith(e)}
        for stem in stems:
            for ending in ("", *RUSSIAN_ENDINGS):
                swapped = stem + ending
                if swapped != word and len(swapped) > 3:
                    assert swapped not in forms, f"{word} is a form of {swapped}"
        for near in common:
            assert not _one_apart(word, near), f"{word} is one letter from {near}"
    rejected = ("полонька", "шмутка", "воброта", "жмелость", "мурдость", "глудость")
    rejected += ("дольница", "прутина", "тусклота", "колдание")
    for word in rejected:
        assert word not in check.MADE_UP_RU, f"{word} was rejected (ling-ru, 2026-11-05)"


def test_no_russian_made_up_word_is_in_pymorphy3_s_dictionary() -> None:
    """pymorphy3's OpenCorpora dictionary (CC BY-SA, a lookup only), which ling-ru could
    not run (2026-11-05). Skips where pymorphy3 is not installed."""
    pymorphy3 = pytest.importorskip("pymorphy3")
    analyzer = pymorphy3.MorphAnalyzer()
    for word in check.MADE_UP_RU:
        assert not analyzer.word_is_known(word), f"{word} is in pymorphy3's dictionary"


# -- the rung, per language ----------------------------------------------------------


def test_the_check_s_rung_is_on_the_language_s_own_ladder() -> None:
    """Hebrew's on the ulpan ladder by vocabulary, French's and Russian's on the CEFR's
    by known words among the commonest five thousand; under the first rung, none."""
    from targum import level as level_module

    def at(code: str, words: int) -> estimate_module.Estimate:
        theta = math.log(words) + estimate_module.FORMS_PER_LEMMA
        return estimate_module.Estimate(code, theta, {})

    assert check.rung_after(at("he", 2000)) == level_module.ULPAN[2]  # bet
    assert check.rung_after(at("he", 100)) is None
    assert check.rung_after(at("ru", 10)) is None
    beginner = check.rung_after(at("fr", 300))
    assert beginner is not None and beginner.name == "A1"
    strong = check.rung_after(at("ru", 20_000))
    assert strong is not None and strong.name in ("C1", "C2")
    # Expected known among the commonest 5,000 climbs with the vocabulary and never
    # passes 5,000.
    counts = [check.common_known(at("fr", words)) for words in (300, 1000, 3000, 30_000)]
    assert counts == sorted(counts) and counts[-1] < check.COMMON_DEPTH
    assert check.rung_id(level_module.ULPAN[1]) == "aleph-plus"
    assert check.rung_id(level_module.CEFR[1]) == "a2"


def test_the_estimate_reads_a_check_by_its_own_language_s_lists(tmp_path: Path) -> None:
    """A French check moves the French estimate and says nothing of the Hebrew one; a
    French check held against Hebrew's version says nothing at all."""
    pytest.importorskip("wordfreq")
    from targum.annotate import frequency

    if not frequency.ranks("fr"):
        pytest.skip("wordfreq has no French list here")
    lists = check.LISTS["fr"]
    four = [word for band in lists.bands[:4] for word in band]
    items, rate = estimate_module.checked_evidence(
        (lists.version, check.kept(four, "fr")), None, "fr"
    )
    assert items and rate is not None
    assert estimate_module.checked_evidence((check.VERSION, four), None, "fr") == ([], None)

    estimate_module.forget()
    store, person = _reader(tmp_path)
    prior = estimate_module.for_reader(store, person.id, "fr").theta  # type: ignore[attr-defined]
    store.set_checked(person, "fr", lists.version, check.kept(four, "fr"))  # type: ignore[arg-type]
    estimate_module.forget()
    after = estimate_module.for_reader(store, person.id, "fr")  # type: ignore[attr-defined]
    assert after.theta > prior + 1
    hebrew = estimate_module.for_reader(store, person.id, "he")  # type: ignore[attr-defined]
    assert hebrew.evidence == 0, "a French check says nothing of a reader's Hebrew"


def test_a_declared_rung_seeds_only_its_own_ladder() -> None:
    """One column holds the rung last named: a CEFR rung seeds French and Russian, an
    ulpan rung seeds Hebrew, and neither seeds the other or a language with no check."""
    from dataclasses import replace

    from targum import level as level_module

    def seeded(code: str, said: str) -> str:
        found = level_module.seed(replace(level_module.EMPTY, language=code, declared=said))
        return found.name if found else ""

    assert seeded("ru", "a2") == "A2" and seeded("fr", "c1") == "C1"
    assert seeded("he", "bet-plus") == "bet plus"
    assert seeded("ru", "gimel") == "" and seeded("he", "a1") == ""
    assert seeded("it", "a2") == "", "Italian is not asked"
    assert Store.declared_of("b1") == "b1" and Store.declared_of("z9") == ""
