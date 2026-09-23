"""What the chat is told about how to write, checked where it is written.

`design.md` §6 governs every English sentence the chat produces, and `test_brand.py`
cannot see a model's output: it scans stylesheets, scripts and templates, and a reply
is in none of them. So the rules live in `chat/prompts.py`, and this file holds them
there — if a rule is taken out of the prompt, this is the test that says so.
"""

from __future__ import annotations

from targum.chat import prompts
from targum.chat.tools import REGISTRY


def test_the_voice_rules_are_in_the_prompt() -> None:
    said = prompts.SYSTEM
    assert "always lowercase: targum" in said
    assert "No emoji" in said and "No exclamation marks" in said
    assert "No invented currency" in said and "not a placement" in said
    assert "Short." in said and "Warm is not long" in said
    assert "Plain text only" in said and "no markdown" in said
    assert "Second person" in said


def test_the_prompt_speaks_as_we_and_thanks_the_reader() -> None:
    """design.md §6, 2026-09-13: targum talks to the reader as "we" to "you", thanks them
    for what they bring, says what it is doing and when it will be ready, and owns what
    goes wrong."""
    said = " ".join(prompts.SYSTEM.split())
    assert 'Speak as "we" and to "you"' in said and 'never "I"' in said
    assert "Thank the reader when they hand you something" in said
    assert "in their own time" in said
    assert "we own it" in said and "Never blame the reader" in said


def test_the_prompt_keeps_price_language_out_of_the_product() -> None:
    """The reader pays by the month (design.md §6, 2026-09-13): a wait is a time and a
    cost is hours, and the model is told to say neither as a price nor to price anything."""
    said = " ".join(prompts.SYSTEM.split())
    assert "No price language" in said
    assert "never say price, cost, quote or sale" in said
    assert "minutes of your hours" in said
    assert "never in money" in said
    assert "price a" not in said and "You can price" not in said
    assert "we couldn't reach it" in prompts.shut_hosts(["example.org"])


def test_a_reply_is_capped_in_numbers_not_adjectives() -> None:
    """ "A few Hebrew sentences" was a median of 42 words over five lines, ten with their
    English, and the notes of 2026-09-10 called it too much to read (targum-internal#236).
    The cap is a number in both prompts now, and the recast does not count."""
    from targum.chat import hebrew

    assert hebrew.MOST_SENTENCES == 3 and hebrew.MOST_WORDS == 40
    said_contract = " ".join(hebrew.CONTRACT.split())
    assert (
        f"at most {hebrew.MOST_SENTENCES} Hebrew sentences and {hebrew.MOST_WORDS} Hebrew words"
        in said_contract
    )
    assert "is exactly one sentence and the door" in said_contract
    assert "a ceiling, not a target" in said_contract
    assert f"each about {hebrew.USUAL_WORDS} words" in said_contract
    assert "do not say it again or tell them to press it" in said_contract
    assert f"at most {hebrew.MOST_LISTED} lines" in hebrew.CONTRACT
    said = " ".join(prompts.SYSTEM.split())
    assert "At most three sentences in a reply" in said
    assert "one sentence before a card or a door" in said
    reply = (
        "> שלום, מה לקרוא?\n= Hello\nיש לי משהו קצר בשבילך.\n= I have\nזה סיפור על ילד.\n= story"
    )
    assert hebrew.length(reply) == 9, "the recast is the reader's line and is not counted"
    assert hebrew.length("= only English") == 0


def test_the_prompt_keeps_its_own_rules() -> None:
    """A prompt that broke §6 while teaching it would be the one place nobody checked."""
    assert "!" not in prompts.SYSTEM
    assert "Targum" not in prompts.SYSTEM.replace("targum", "")


def test_the_prompt_says_it_cannot_spend() -> None:
    assert "cannot spend" in prompts.SYSTEM and "start a build" in prompts.SYSTEM


def test_the_prompt_says_it_cannot_open_a_text_and_must_give_its_path() -> None:
    """A reader asked to read a text and was told it was open and ready, with no way in."""
    assert "cannot open a text" in prompts.SYSTEM
    assert "on a line of its own" in prompts.SYSTEM
    assert "draws that line as a door" in prompts.SYSTEM
    assert "Never say a text is open" in prompts.SYSTEM


def test_hebrew_is_content_and_graded() -> None:
    assert "Hebrew is content" in prompts.SYSTEM
    assert "one new word at most" in prompts.SYSTEM


def test_the_chat_is_offered_nothing_that_spends() -> None:
    """The seam was drawn on 2026-09-05 before any tool needed it. One does now —
    `record_turn`, for a conversation held somewhere else (#80) — and design.md §12
    ("A scope is a press that lasts") is where that is written down.

    What is unchanged is this surface. In targum's own conversation the model is given
    the registry minus anything that spends, because targum already recasts every line
    here and writes the slip itself: offering it would record the same mistake twice.
    """
    from targum.chat.tools import anthropic_tools

    by_name = {tool.name: tool for tool in REGISTRY}
    offered = [tool["name"] for tool in anthropic_tools()]
    assert not [name for name in offered if by_name[name].spends or by_name[name].needs_consent]
    # And the one that does spend carries the scope that consents to it, and nothing else.
    spending = [tool for tool in REGISTRY if tool.spends]
    assert [tool.name for tool in spending] == ["record_turn"]
    assert spending[0].scope == "check"


def test_a_question_from_inside_the_text_is_answered_in_the_conversation_s_hebrew() -> None:
    """A word tapped is a question half-asked (2026-09-06): the card's Ask sends the
    text, the sentence and the word along, and the model is told what to do with them.
    It was answered in English; since 2026-09-11 ("word note should also be written in
    Hebrew at your level. This should be a general rule") a note only narrows what the
    answer is about — the form, the sentence — and the line is answered as the
    conversation is, in Hebrew at their level. On scripture it still writes no Hebrew
    of its own."""
    said = prompts.SYSTEM
    assert "the word they tapped" in said
    assert "in Hebrew at their level with the English under every line" in said
    assert "answered in English" not in said
    assert "on scripture write no Hebrew of" in said


def test_the_ladder_a_reader_may_name_is_in_the_prompt_from_the_one_table() -> None:
    """A reader asked for "a bet plus level" and was not understood (2026-09-06). The
    rungs are written into the prompt from `level.ULPAN`, with what each is reckoned to
    want, so the model can turn a name into a search — and is still told never to hand
    the reader's own rung back as a placement."""
    from targum import level

    said = prompts.SYSTEM
    for rung in level.ULPAN:
        assert f"{rung.name} ({rung.letter}, about {rung.at:,} words)" in said
    assert "bet plus" in said and "RUNGS" not in said
    assert "max_looked_up_percent" in said
    assert "Never tell them which rung they are at" in said


def test_a_text_sent_with_a_line_is_never_asked_for_again() -> None:
    """A reader sent a picture with "open this and help me learn it" and was asked for a
    link. The prompt now says what a brought text's note means and what not to do."""
    from targum.chat.prompts import SYSTEM

    assert "never ask for it, for a link, or for its words again" in SYSTEM
    assert "You cannot open it yourself" in SYSTEM


def test_the_prompt_knows_what_the_product_takes_and_that_it_reads_pictures() -> None:
    """A reader asked, in Hebrew, whether they could send a screenshot of a WhatsApp
    conversation and was told twice that targum reads only words — then sent it, had it
    read, and was told no picture had arrived (2026-09-07). The model has to know what
    the product around it can do, and how a reader does it."""
    from targum.chat.prompts import SYSTEM

    assert "What targum takes, and how the reader gives it" in SYSTEM
    assert "The + beside the box" in SYSTEM and "press Send" in SYSTEM
    assert "a screenshot of WhatsApp" in SYSTEM and "a phone" in SYSTEM
    assert "You read pictures" in SYSTEM
    assert "Never say you cannot read a picture" in SYSTEM
    assert "never say the reader sent words when they sent a picture" in SYSTEM
    assert "What targum does not take" in SYSTEM and "Spotify" in SYSTEM
    assert "explain it from the lines you were given" in SYSTEM


def test_the_correction_says_why_once_and_never_lectures() -> None:
    """targum-internal#242: the recast was the correction and never said so. One "~ "
    line may now say what changed and the rule; the body still does not lecture."""
    from targum.chat import hebrew

    assert hebrew.WHY == "~ "
    said = " ".join(hebrew.CONTRACT.split())
    assert 'one line beginning "~ " directly under the recast\'s "= " line' in said
    assert "Never on a line that was right" in said
    assert "never a second sentence" in said
    assert "Do not lecture about a mistake in the body" in said


def test_the_gloss_line_is_in_the_language_the_reader_reads() -> None:
    """targum-internal#243: the line under each Hebrew line was English by name whatever
    the account said it read. The contract names the reader's language now, and the
    rules about the model thinking in English rather than Hebrew stay."""
    from targum.chat import hebrew

    assert hebrew.CONTRACT == hebrew.contract("English")
    russian = " ".join(hebrew.contract("Russian").split())
    assert 'The reader reads Russian: every "= " line is in Russian.' in russian
    assert "Directly under it, on the next line, its Russian" in russian
    assert "one sentence in Russian naming what changed" in russian
    assert "No Russian and no English inside a Hebrew line" in russian
    assert "Do not think of an English sentence and translate it" in russian, "still about Hebrew"
    assert hebrew.gloss_language({"ru"}) == "ru"
    # English beside Russian is still Russian since 2026-09-22 (targum-internal#286,
    # item 1): an account starts at {"en"} and Russian is added to it, so "reads English
    # too" was true of every Russian reader there is and English won for all of them.
    assert hebrew.gloss_language({"ru", "en"}) == "ru"
    assert hebrew.gloss_language(set()) == "en" and hebrew.gloss_language({"en"}) == "en"
    # Two others and nothing says which is meant.
    assert hebrew.gloss_language({"en", "ru", "fr"}) == "en"


def test_the_level_target_is_a_number_the_tools_carry() -> None:
    """targum-internal#244: level-awareness was one prompt sentence and the model's
    discretion. The tools carry known_share now and the prompt names the target."""
    said = " ".join(prompts.SYSTEM.split())
    assert "known_share of 0.8 or more" in said and "0.65 or more" in said
    assert "applies the reader's own ceiling" in said
    assert "never as a percentage or a level" in said


def test_the_cold_start_names_at_most_three_recurring_rules() -> None:
    """targum-internal#290. A model handed a list of everything a reader has ever got
    wrong writes a grammar lesson, which is the thing this must never become. Three is
    enough to drift toward a weak spot and too few to teach from."""
    from targum.chat.hebrew import RULES_BACK, recurring

    slips = [{"why": f"Rule {n}."} for n in range(8) for _ in range(2)]
    assert len(recurring(slips)) == RULES_BACK == 3


def test_a_mistake_made_once_is_not_a_rule() -> None:
    """Everybody gets a line wrong once, and a conversation that bent itself toward
    every single mistake would be a conversation about mistakes."""
    from targum.chat.hebrew import recurring

    assert recurring([{"why": "Past tense."}]) == []
    assert recurring([{"why": "Past tense."}, {"why": "Past tense."}]) == ["Past tense."]
    # Commonest first, so the three it picks are the three that recur most.
    many = [{"why": "Twice."}] * 2 + [{"why": "Five times."}] * 5 + [{"why": "Three times."}] * 3
    assert recurring(many) == ["Five times.", "Three times.", "Twice."]


def test_the_rules_steer_the_sentences_and_are_never_said() -> None:
    """ "if smth gonna ping me or bother me like duolingo I'll fucking delete it". The half
    a scheduler cannot have is the record; the way to waste it is to announce it."""
    from targum import level
    from targum.chat.hebrew import ledger_block

    block = ledger_block(level.EMPTY, ["ספר"], [], None, ["Past tense: הָלַכְתִּי, not הָלַךְ."])
    assert "corrected more than once" in block
    assert "Never mention this list" in block
    assert "never set an exercise" in block

    # And nothing at all where there is nothing recurring.
    quiet = ledger_block(level.EMPTY, ["ספר"], [])
    assert "corrected more than once" not in quiet


# -- find mode answers in the reader's language (targum-internal#286, item 2) -----------


def _a_level():  # type: ignore[no-untyped-def]
    from targum import level as level_module

    return level_module.Level("he", 400, 0, 400.0, None, None, 0, 0, 0, 0, 0)


def test_find_mode_is_told_which_language_to_write_in() -> None:
    """`SYSTEM` says which language's *texts* to offer and never which language to
    *write* in, so a Russian reader asking for something to read was answered in English
    by a product whose buttons were already Russian.

    It rides in the per-reader block and not in `SYSTEM`, which is the cached half and
    holds nothing that changes per reader.
    """
    from targum.chat import prompts

    level = _a_level()
    english = prompts.ledger(level)
    russian = prompts.ledger(level, "Russian")

    assert "Write to the reader in Russian" in russian
    assert "Hebrew you quote stays Hebrew" in russian, "the Hebrew is the thing being read"

    # And English is named too, rather than falling silent for it. That is not symmetry
    # for its own sake: `SYSTEM` stopped saying "English" in item 3, so silence here
    # would leave an English reader with no instruction anywhere at all.
    assert "Write to the reader in English" in english
    assert prompts.ledger(level, "") == english, "nothing said is English"

    # The ledger itself is the same either way; only the last line differs.
    assert english.rsplit("\n\n", 1)[0] == russian.rsplit("\n\n", 1)[0]


def test_the_answer_follows_the_same_rule_as_the_gloss_lines() -> None:
    """One rule rather than two: a reader who gets Russian meanings and an English answer
    in the same thread is being told the product has not decided."""
    from types import SimpleNamespace

    from targum.chat.hebrew import gloss_language
    from targum.chat.session import _answered_in
    from targum.strings import reading_language

    def standing_in(said: set[str] | None) -> SimpleNamespace:
        """A `Ctx` for this one question. `Level` takes eleven arguments and none of them
        are about language; `Ctx.language` is the single call below, and the real one is
        exercised against a real `Ctx` in `test_chat_tools.py`."""
        return SimpleNamespace(said_reads=said, language=reading_language(said))

    assert gloss_language({"ru"}) == "ru"
    assert _answered_in(standing_in({"ru"})) == "Russian"
    assert _answered_in(standing_in({"en", "ru"})) == "Russian", "the common case"
    assert _answered_in(standing_in(set())) == "English"
    assert _answered_in(standing_in(None)) == "English", "nobody signed in"

    # And it is the same rule the chrome answers to, which is the whole of item 1: these
    # were two rules that disagreed, and the reader saw both at once.
    from targum.strings import drawn_in

    assert reading_language({"en", "ru"}) == drawn_in({"en", "ru"}) == "ru"
    # The chrome alone falls back where nothing has been written for a language. The
    # meanings do not: they are bought per language rather than written here, and a
    # French reader had French meanings before any of the chrome was French.
    assert reading_language({"fr"}) == "fr" and drawn_in({"fr"}) == "en"


def test_the_cached_half_of_the_prompt_names_no_language_of_its_own() -> None:
    """targum-internal#286, item 3. `SYSTEM` is cached for every reader, so a rule in it
    that names English is a rule about English written for readers who are not being
    written to in English.

    It used to say "How you write English", "its English beside it" and "the English
    rules above". Which language to write in belongs to the ledger, which is the half
    that changes per reader; `SYSTEM` says only *how*.

    The one mention left is the note-answering paragraph, which names the English gloss
    as its example and then says, in the same sentence, "in a conversation held in
    another language, in that language, the same way". The hedge is what carries it, and
    a neutral rewrite would lose the concrete example without gaining anything.
    """
    from targum.chat import prompts

    named = [line.strip() for line in prompts.SYSTEM.splitlines() if "English" in line]
    assert len(named) == 1, named
    assert "with the English under every line" in named[0]
    # And the sentence that hedges it is still there, two lines down.
    assert "in a conversation held in another language, in that language" in prompts.SYSTEM

    assert "How you write to the reader" in prompts.SYSTEM
    assert "How you write English" not in prompts.SYSTEM
    assert "its meaning beside it" in prompts.SYSTEM


# -- the contract is written for the reader's language (targum-internal#286 item 4) ------


def test_the_calques_named_are_the_ones_this_reader_would_be_pulled_into() -> None:
    """The four calques named were English ones, on a contract handed to every reader.
    A Russian reader is pulled two ways, not one — and only one of them was named.

    The English list stays whatever the reader reads: the model's own pull toward
    English does not weaken because the person on the other side is Russian. The
    reader's-language list is the *second* pull, and it exists only for a reader who has
    a second language to be pulled by.
    """
    from targum.chat import hebrew

    russian = " ".join(hebrew.contract("Russian").split())
    english = " ".join(hebrew.contract("English").split())

    # Both pulls are named for a Russian reader.
    assert 'not "אָז נַגִּיד אֶת זֶה יָשִׁיר" for "let\'s say it straight"' in russian
    assert "do not think of a Russian sentence and translate it either" in russian
    assert "«сделать фотографию»" in russian and "לְצַלֵּם" in russian
    assert "«сколько тебе лет»" in russian and "בֶּן כַּמָּה אַתָּה" in russian
    assert "«заниматься спортом»" in russian

    # And an English reader's contract is what it was: no Russian in it anywhere.
    assert "Russian" not in english
    assert "сделать" not in english

    # A language nothing has been written for falls back to the contract as it was,
    # rather than to an empty "and do not think of a … sentence" with nothing after it.
    french = " ".join(hebrew.contract("French").split())
    assert "do not think of a French sentence" not in french
    assert 'not "מַדָּף הַתְחָלָה מְשׁוּתָּף" for "a shared starter shelf". Speak to the' in french


def test_a_reader_who_has_said_their_gender_is_not_hedged_at() -> None:
    """The contract knew one way to learn how to address somebody — the ledger — so a
    Russian woman who wrote «я прочитала» went on being spoken to in forms that refuse to
    choose. Her own sentence had already said, as plainly as the ledger would.

    Never from a name, which is the one source that looks like an answer and is not.
    """
    from targum.chat import hebrew

    russian = " ".join(hebrew.contract("Russian").split())
    assert "«я прочитала» rather than «я прочитал»" in russian
    assert "as plainly as the ledger would" in russian
    assert "Never take it from a name." in russian

    # The hedging forms are still there: they are what to do when nothing has said.
    assert "an infinitive (כְּדַאי לִקְרוֹא)" in russian
    assert "the first person plural (בּוֹאוּ נִקְרָא)" in russian

    # An English reader gets the rule without a Russian example they could not read.
    english = " ".join(hebrew.contract("English").split())
    assert "a gendered form of their own in any language they write in" in english
    assert "прочитала" not in english
