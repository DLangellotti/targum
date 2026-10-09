/* The library: everything there is to read, in one list you can sort and sift.
 *
 * It used to be a grid of cards holding the catalogue, with the reader's own texts on
 * another page entirely. Two shapes for one question — what shall I read — and neither
 * of them answerable in a hurry: a card cannot be sorted, and twenty-six of them are a
 * wall. This is one row per text, and the controls above the list act on all of them as
 * you type.
 *
 * A picked text arrives with a translation somebody published, so opening one is only a
 * matter of fetching two texts and matching them up. Nothing about that is the reader's
 * business, and none of it belongs in what the page says.
 *
 * One language at a time. Someone reading Hebrew should not have to look past a Russian
 * novel to find their own shelf, and the language they pick here is the one their words
 * page opens on.
 */

(function () {
  "use strict";

  /* The page's words in the reader's language, from `strings.js` (targum-internal#184). */
  var words = window.TargumStrings;
  var t = words.t;
  var tn = words.tn;
  // What the page's own words are marked as, so a screen reader says them in their language.
  var saidIn = words.language;

  var key = window.TARGUM_KEY;
  /* Hosted there is no start-up key: the session cookie identifies the reader, and a key
     riding in every URL is a bearer token in browser history, on a shared screen, and in
     a Referer. Local it stays, because there it proves the page came from the terminal
     that started the process. Both cases are this one branch. */
  function keyed(path) {
    if (!key) return path;
    return path + (path.indexOf("?") < 0 ? "?" : "&") + "k=" + encodeURIComponent(key);
  }

  function keyHeaders(extra) {
    var head = extra || {};
    if (key) head["X-Targum-Key"] = key;
    return head;
  }

  var names = window.TARGUM_LANGUAGES || {};
  var catalogue = window.TARGUM_CATALOGUE || [];
  var collections = window.TARGUM_COLLECTIONS || [];
  var lang = window.TargumLang;

  /* What a text is, called what a reader would call it — which is not always what the
     catalogue calls it. "Prose" is the catalogue's word for the narrative books of the
     Tanakh, and beside "Novels" and "Stories", which are also prose, it says nothing to
     anybody. "News" is what an article is.

     Scenes first: the hundred numbered dialogues are where a reader with no words at all
     starts, and the chip that opens that path should be the first one met. After it,
     ordered by how much of the catalogue each one holds, so the next chips a reader
     meets are the ones with fifty texts behind them rather than the ones with two.
     Fixed rather than recomputed: a row of filters that rearranges itself as you use it
     is a row you have to read every time. "Tanakh" for the Bible's story books, and
     "Dialogues" and "Videos" rather than the catalogue's "Scenes" and "Talks": the
     boards' words (design.md §12, "A text is named in everyday words", 2026-10-09). */
  var KINDS = [
    ["dialogue", t("library.kind.dialogue", "Dialogues")],
    ["story", t("library.kind.story", "Stories")],
    ["article", t("library.kind.article", "News")],
    ["novel", t("library.kind.novel", "Novels")],
    ["essay", t("library.kind.essay", "Essays")],
    ["talk", t("library.kind.talk", "Videos")],
    ["prose", t("library.kind.prose", "Tanakh")],
    ["poetry", t("library.kind.poetry", "Poetry")],
    ["document", t("library.kind.document", "Documents")],
    ["play", t("library.kind.play", "Plays")],
    ["liturgy", t("library.kind.liturgy", "Prayer")],
  ];

  /* One text's kind, on its own row or tile: "Dialogue · 3 min", "Video · 9 min". The
     names above are shelves and chips, plural, and on a row they read as the catalogue's
     ids — "Talks · 1 min", "Documents · 5 min" (design review, 2026-10-09). */
  var KIND_ONE = [
    ["dialogue", t("library.kind-one.dialogue", "Dialogue")],
    ["story", t("library.kind-one.story", "Story")],
    ["article", t("library.kind-one.article", "News")],
    ["novel", t("library.kind-one.novel", "Novel")],
    ["essay", t("library.kind-one.essay", "Essay")],
    ["talk", t("library.kind-one.talk", "Video")],
    ["prose", t("library.kind-one.prose", "Tanakh")],
    ["poetry", t("library.kind-one.poetry", "Poetry")],
    ["document", t("library.kind-one.document", "Document")],
    ["play", t("library.kind-one.play", "Play")],
    ["liturgy", t("library.kind-one.liturgy", "Prayer")],
  ];

  /* How much of a text this reader already knows, in three bands. The measure is the
     share of *this text's* words they have marked as known — a fact about the pair of
     them — and not `difficulty`, which is a fact about the text alone. A reader asking
     "can I read this" is asking the first (design.md §12, 2026-09-17).

     The cutoffs are David's, 2026-10-08, and the Library's shelves are drawn by them:
     90% and up is Read it now, 75–90% is A stretch, and under that is Hard for now
     (design.md §12, "The Library is shelved by how much you'd follow"). They were 85 and
     65 while a band was a filter over one list; as the names of shelves they say what a
     reader would find on opening one, and a text read at 80% is not read "now". */
  var COMFORTABLE = 90;
  var WORKABLE = 75;

  /* The three shelves, in the order the page stands them, and the words each is called
     by. One band each: since the shelves (2026-10-09) a band is exactly itself, and See
     all under A stretch is the stretch and not the stretch with everything easier. */
  var BANDS = [
    ["now", t("library.band.now", "Read it now")],
    ["stretch", t("library.band.stretch", "A stretch")],
    ["hard", t("library.band.hard", "Hard for now")],
  ];

  /* The same bands as the sentence above a See all list says them, and "everything". */
  var FITS = [
    ["now", t("library.fit.now", "you can read now")],
    ["stretch", t("library.fit.stretch", "a step up from where you are")],
    ["hard", t("library.fit.hard", "hard for now")],
    ["", t("library.fit.all", "everything")],
  ];

  function bandNamed(id) {
    for (var n = 0; n < BANDS.length; n++) if (BANDS[n][0] === id) return BANDS[n];
    return null;
  }

  /* Whether the shelf on show is Hebrew's (2026-09-14). "Which Hebrew" — the register, its
     chips, its column and its note — is a question about Hebrew texts, and under another
     language it is not asked: a register picked while reading Hebrew went on filtering a
     Russian shelf down to nothing, under a note about the Hebrew of the Bible. The choice
     is kept for when the reader comes back to Hebrew. */
  var inHebrew = true;

  /* The line under the controls. It led the page once, on a first visit that opened on
     the Scenes; the Library opens on its shelves since 2026-10-09, and the next scene is
     the first card of Read it now with its "Start here", so the line is always here. */
  function placeNote(text) {
    var note = document.getElementById("picked-note");
    note.hidden = false;
    note.textContent = text;
  }

  /* --- the Beit Midrash (targum-internal#340, 2026-09-19) ---------------------------
   *
   * A third tab, Hebrew's alone: the texts `catalogue.beit_midrash()` keeps, walked as a
   * tree the way Sefaria's contents is — doors, then the books behind each under their
   * own headings. "Someone who only studies Biblical Hebrew should be able to find what
   * they are looking for right away": the tab, Tanakh, Ruth.
   *
   * **It is not a second room.** There was a Beit Midrash shelf once, with its own
   * addresses, and it was taken out because a reader had to know which room a text was
   * in before they could find it (`catalogue.Tag`). Every row here is also a row under
   * All texts, at the same address, drawn by the same code: this is the one list
   * (design.md §12, "The library folds") asked a different question — not "what is it
   * about" but "where does it stand". A subject only ever narrows (§12, 2026-09-17), and
   * so does a door.
   *
   * Which door a collection stands behind is a fact in the catalogue file
   * (`Collection.door`), and a file that says nothing draws no tab. The names are here
   * because they are the page's own words, like the subjects'.
   *
   * It crosses one line the rest of the library does not: the Aramaic translations of the
   * Tanakh — Onkelos, Jonathan — are Aramaic rows,
   * and they have a door here, named for what they are rather than by the word the
   * brand keeps for itself (David, 2026-09-19 — Sefaria files them under Tanakh,
   * and a Torah student looks for Onkelos beside the Torah). They open as Aramaic
   * readers and their words still go to the Aramaic list (targum-internal#202); their
   * cards say Aramaic. Nowhere else does the Hebrew shelf show another language's rows.
   */
  var DOORS = [
    ["tanakh", "תנ״ך", t("library.door.tanakh", "Tanakh")],
    ["portions", "פרשות השבוע", t("library.door.portions", "The Torah, by portion")],
    ["targum", "תרגום", t("library.door.targum", "Aramaic translations")],
    ["mishnah", "משנה", t("library.door.mishnah", "Mishnah")],
    ["halakhah", "הלכה", t("library.door.halakhah", "Halakhah")],
    ["thought", "מחשבה ומוסר", t("library.door.thought", "Thought and ethics")],
    ["liturgy", "תפילה", t("library.door.liturgy", "Liturgy")],
  ];
  var MIDRASH = ["midrash", t("library.where.midrash", "Jewish texts")];
  //: The language the tree carries besides Hebrew.
  var BESIDE_HEBREW = "arc";

  function doorNamed(id) {
    for (var n = 0; n < DOORS.length; n++) if (DOORS[n][0] === id) return DOORS[n];
    return null;
  }

  function ask(path, body) {
    return fetch(keyed(path), {
      method: body ? "POST" : "GET",
      headers: keyHeaders({ "Content-Type": "application/json" }),
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (response) {
      return response.json();
    });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function base(code) {
    return (code || "").split("-")[0].toLowerCase();
  }

  function stored(name) {
    try {
      return JSON.parse(localStorage.getItem(name) || "{}");
    } catch (e) {
      return {};
    }
  }

  function remember(name, value) {
    try {
      localStorage.setItem(name, JSON.stringify(value));
    } catch (e) {}
  }

  Array.prototype.forEach.call(document.querySelectorAll(".site-nav a"), function (link) {
    link.href = keyed(link.getAttribute("href"));
  });

  /* --- what the list holds --------------------------------------------------- */

  /* Whether a row's share means anything. Zero is a measurement on a catalogue text — a
     twenty-word scene with no uncommon word in it — and "not measured" on an upload
     built without word-level annotation. The two are different claims, and only the
     second is drawn as a dash. The longest scene is 67 words. */
  var MEASURED_ZERO = 200;

  function measured(row) {
    if (row.difficulty > 0) return true;
    // A zero is believable only on a text short enough to have no uncommon word in it.
    // Forty-seven catalogue rows — Rashi, the Aramaic targumim, a novel — carry 0 because
    // nobody measured them, and read "0% hard words" at the top of Easiest (2026-09-27).
    return !!row.entry && (row.entry.words || 0) <= MEASURED_ZERO;
  }

  function level(row) {
    if (!measured(row)) return "";
    var share = row.difficulty || 0;
    if (share <= 20) return "easy";
    return share <= 28 ? "mid" : "hard";
  }

  /* Whether a row is within reach, and how far. Two answers to one question, because the
     page has to give an honest one to a reader who has marked nothing yet.

     With words marked, the measure is the reader's own: how much of this text they know.
     With none — a first visit, or somebody who reads without pressing — every row would
     answer 0% and "what you can read now" would be empty, which is the worst possible
     first page. There the page falls back to the text's own hard-word share, which is
     what it filtered on before any of this (design.md §12, 2026-09-17). */
  var anyKnown = false;

  function fitOf(row) {
    if (anyKnown) {
      var share = knownOf(row);
      // `knownOf` answers in the unit the column prints it from — a fraction, not a
      // percentage. Nothing measured is not a claim about the reader, so it sits in the
      // middle rather than being hidden, the same way an unmeasured difficulty does.
      if (typeof share !== "number") return "stretch";
      var percent = share * 100;
      if (percent >= COMFORTABLE) return "now";
      return percent >= WORKABLE ? "stretch" : "hard";
    }
    // Nothing marked: the text's own difficulty stands in. Unmeasured is not "hard" —
    // it is not a claim at all — so it sits in the middle rather than being hidden.
    if (!measured(row)) return "stretch";
    var band = level(row);
    /* And where the reader said on arrival how much Hebrew they have, that moves what
       "now" means until their own marked words can (targum-internal#306, 2026-09-19;
       `charts.seed`). The ladder in thirds: a beginner reads the easy shelf now, as
       before; from bet plus the middle shelf is within reach as well; from dalet all of
       it is. Coarse on purpose — it is a seed, and `anyKnown` retires it. */
    var reach = seedReach();
    if (reach === 2) return "now";
    if (band === "easy") return "now";
    if (band === "mid") return reach === 1 ? "now" : "stretch";
    return reach === 1 ? "stretch" : "hard";
  }

  //: 0, 1 or 2: how far up the shelf the rung a reader named reaches. 0 where they named
  //: none, or where something about them has been measured since.
  var seeded = "";

  function seedReach() {
    var ladder = window.TargumCharts;
    // Asked over the ulpan ladder, so it says nothing about another language's shelf.
    if (!seeded || !ladder || !inHebrew) return 0;
    var at = ladder.seedFraction(seeded);
    if (at >= 5 / 7) return 2;
    return at >= 3 / 7 ? 1 : 0;
  }

  /* How lately a text has to have arrived to be worth marking. A fortnight, which is
     about how long somebody goes between looking at a library — long enough that a
     reader who visits every other week never misses one, short enough that the mark
     still means something when a dozen rows arrive at once.

     Not a badge and not a count. §6 forbids gamification, and this is not a reward for
     anything: it is the shelf answering "what is new", which is what was asked for. */
  var LATELY_DAYS = 14;

  function isNew(row) {
    var when = dateOf(row);
    if (!when) return false;
    var day = 24 * 60 * 60 * 1000;
    var then = Date.parse(when + "T00:00:00Z");
    if (isNaN(then)) return false;
    var since = (Date.now() - then) / day;
    // Never a future date: a row dated tomorrow by a bad clock or a bad hand is a row
    // that would sit marked New for ever.
    return since >= -1 && since <= LATELY_DAYS;
  }

  /* The day a row arrived, from whichever side knows. A catalogue row carries the
     catalogue's date; a text of the reader's own carries the day they built it, which is
     when it arrived for them and is the more honest answer for a text only they have. */
  function dateOf(row) {
    if (row.entry && row.entry.added) return row.entry.added;
    if (row.built && row.built.built) return dayOf(row.built.built);
    return "";
  }

  /* A day from the seconds a built reader records, in the reader's own timezone, which
     is the one they would name the day by. */
  function dayOf(seconds) {
    try {
      var when = new Date(seconds * 1000);
      var month = String(when.getMonth() + 1);
      var day = String(when.getDate());
      return (
        when.getFullYear() +
        "-" +
        (month.length < 2 ? "0" + month : month) +
        "-" +
        (day.length < 2 ? "0" + day : day)
      );
    } catch (e) {
      return "";
    }
  }

  /* A band is exactly itself (2026-10-09). It used to be that "a step up" meant now *and*
     the step, when the band was the one setting over one list; now each band is a shelf,
     and See all under a shelf is that shelf's texts and no others. */
  function fits(row, want) {
    if (!want) return true;
    return fitOf(row) === want;
  }

  function said(minutes) {
    if (minutes < 60) return t("library.minutes", "{n} min", { n: minutes });
    var hours = Math.round(minutes / 60);
    return t("library.hours", "{n} hr", { n: hours });
  }

  // One row per text, from two places. A catalogue entry the reader has already built
  // is one row and not two: the catalogue is where it came from, the shelf is where it
  // is now, and the row says both.
  // How much of each catalogue text the reader knows, for the rows they have not built
  // (targum-internal#293). Filled from `/readers`; empty on a box with no index, which
  // leaves every unbuilt row saying what it said before, which is nothing.
  var catalogueKnown = {};

  // What a row's "you know" is, whichever side it came from. A built copy's own
  // measurement wins: that is the text this reader actually has, annotation and all.
  function knownOf(row) {
    // A collection knows what its texts know, the middle of them: a mean is dragged by
    // the one hard thing in it.
    if (row.rows) {
      var shares = row.rows
        .map(knownOf)
        .filter(function (share) {
          return typeof share === "number";
        })
        .sort(function (a, b) {
          return a - b;
        });
      return shares.length ? shares[Math.floor(shares.length / 2)] : null;
    }
    if (row.built && typeof row.built.known === "number") return row.built.known;
    var measured = row.entry && catalogueKnown[row.entry.id];
    return measured && typeof measured.known === "number" ? measured.known : null;
  }

  //: The language this page is being read in. `TargumStrings` carries it already; the
  //: page says `en` when it has no catalogue of its own, which is the right fallback.
  var uiLanguage = (words && words.language) || "en";

  /* The title a reader who cannot read the Hebrew can read, in their own language where
     the catalogue has one (targum-internal#289).

     The front door sells in Russian and the shelf behind it was entirely English, which
     is the whole of the complaint. English is the fallback and never wrong, only
     foreign. */
  function namedIn(entry) {
    return (entry && entry.named && entry.named[uiLanguage]) || "";
  }

  function titleIn(entry) {
    return namedIn(entry) || (entry && entry.english) || "";
  }

  function blurbIn(entry) {
    return (entry && entry.blurbs && entry.blurbs[uiLanguage]) || (entry && entry.blurb) || "";
  }

  // The reader's texts that are not in the catalogue, which `rows()` leaves out.
  var yoursAlone = [];
  // What `/jobs` said was building, last time it was asked.
  var buildingNow = [];

  function rows(readers, shared) {
    var mine = {};
    var out = [];
    // The shared texts first, then the reader's own over them: a text on both is one
    // row, and it is theirs. A shared row opens like any built text and offers nothing
    // else — nothing on it can be bought, drawn or trashed, which `within()` on the
    // server already refuses. Before this the page read only the reader's own, so a
    // seeded scene showed as an unbuilt button and pressing it built a personal copy.
    (shared || []).forEach(function (reader) {
      if (reader.entry) mine[reader.entry] = reader;
    });
    readers.forEach(function (reader) {
      if (reader.entry) mine[reader.entry] = reader;
    });
    catalogue.forEach(function (entry, place) {
      var built = mine[entry.id];
      out.push({
        id: entry.id,
        entry: entry,
        // Where it sits in the catalogue file, which is the only evidence of arrival
        // order the nine hundred undated rows have. See `SORTS.added`.
        place: place + 1,
        title: entry.title,
        english: titleIn(entry),
        englishLang: namedIn(entry) ? uiLanguage : "en",
        author: entry.author,
        language: entry.language,
        // Every language it can be read in: Daniel's Hebrew and Aramaic, a Torah book's
        // Hebrew and the Onkelos beside it (2026-09-14).
        languages: entry.languages || [entry.language],
        kind: entry.kind,
        register: entry.register,
        difficulty: entry.difficulty,
        minutes: entry.minutes,
        spoken: !!entry.spoken,
        video: !!entry.video,
        // What it is about (targum-internal#314). The server has sent these since the
        // arrival began asking in subjects; nothing on this page read them until now.
        tags: entry.tags || [],
        built: built || null,
        // Where it opens without being built: a portion's reader, which the box keeps
        // for everybody (targum-internal#410). "" for every other text.
        opens: portionsAt[entry.id] || "",
        drawn: !!(built && built.drawn),
        opened: built ? built.opened || 0 : 0,
      });
    });
    // Only the catalogue. A reader's own texts, and what is building, are rows on Your
    // targums (design.md §12, 2026-09-25); a catalogue text they built is the row above,
    // marked as theirs. The rest are kept only to be counted, for a language whose
    // catalogue is empty (see the empty line in `redraw`).
    var listed = {};
    catalogue.forEach(function (entry) {
      listed[entry.id] = true;
    });
    yoursAlone = readers.filter(function (reader) {
      return !(reader.entry && listed[reader.entry]);
    });
    return out;
  }

  /* --- collections ------------------------------------------------------------
   *
   * One row per text was the right shape for forty texts. It stops being it somewhere
   * around a hundred: the Mishneh Torah is thirteen rows of `הלכות …`, Berdichevsky is
   * thirty-nine stories, and a reader asking what to read cannot see past either. So a
   * collection collapses to one row and opens where it stands — the list stays one list,
   * which is the whole reason this page is a list.
   *
   * Nothing is grouped that the filters have not left standing: a collection is built
   * out of the rows that survived, so opening one never shows a text the reader has
   * filtered away, and one that has nothing left is not drawn at all.
   */

  /* Which collection each text is in, by id. Built once. */
  var GROUP_OF = {};
  collections.forEach(function (group) {
    (group.members || []).forEach(function (id) {
      GROUP_OF[id] = group;
    });
  });

  /* Where a text sits inside its own collection, so an ordered one keeps its order. */
  var PLACE_IN = {};
  collections.forEach(function (group) {
    (group.members || []).forEach(function (id, index) {
      PLACE_IN[id] = index;
    });
  });

  /* Which door of the Beit Midrash a text stands behind: its collection's, or its own
     where it is in none. "" for everything that is not in the tree. */
  function doorOf(row) {
    if (!row.entry) return "";
    var group = GROUP_OF[row.id];
    var said = group ? group.door : row.entry.door;
    return said && doorNamed(said) ? said : "";
  }

  /* The middle value, which is the honest single number for a set of texts: a mean is
     dragged by the one hard thing in it, and Berdichevsky's thirty-nine range from 13 to
     20. Zero where nothing in the collection has been measured — the row then says "—"
     exactly as an unmeasured text does. */
  function middle(numbers) {
    var real = numbers.filter(function (n) {
      return n > 0;
    });
    if (!real.length) return 0;
    real.sort(function (a, b) {
      return a - b;
    });
    return real[Math.floor(real.length / 2)];
  }

  /* What every row of a set agrees on, or "" where they do not. The Torah is all
     Biblical and says so; a collection of an author's essays and novels has no one kind
     and leaves the column empty rather than picking one of them. */
  function shared(rows, field) {
    var first = rows.length ? rows[0][field] : "";
    for (var i = 1; i < rows.length; i++) if (rows[i][field] !== first) return "";
    return first;
  }

  /* One collection, as a row. Its columns are its members' columns added up, which is
     what makes it sortable and filterable beside them rather than pinned somewhere. */
  function fold(group, rows) {
    return {
      id: "group:" + group.id,
      group: group,
      rows: rows,
      entry: null,
      title: group.title,
      // The group's own name in the reader's language, by the same helpers a row uses —
      // they only want something with `named` and `english`, and a collection has both
      // since targum-internal#289. A shelf that read "Тора" over rows whose group was
      // still called "Torah" was the complaint.
      english: titleIn(group),
      englishLang: namedIn(group) ? uiLanguage : "en",
      author: "",
      language: rows[0].language,
      kind: shared(rows, "kind"),
      register: shared(rows, "register"),
      difficulty: middle(
        rows.map(function (row) {
          return row.difficulty || 0;
        })
      ),
      minutes: rows.reduce(function (total, row) {
        return total + (row.minutes || 0);
      }, 0),
      spoken: rows.some(function (row) {
        return row.spoken;
      }),
      video: rows.some(function (row) {
        return row.video;
      }),
      // Every subject its texts are about, not only the ones they agree on. The Mishneh
      // Torah is one row over thirteen sections; asking for Judaica must find it, and
      // `shared()` — which is right for the kind and the register — would drop a subject
      // that only some of its members carry.
      tags: rows.reduce(function (all, row) {
        (row.tags || []).forEach(function (tag) {
          if (all.indexOf(tag) < 0) all.push(tag);
        });
        return all;
      }, []),
      built: null,
      opened: 0,
    };
  }

  /* The surviving rows, with each collection's members folded into one. In the
     collections' own order, so a shelf does not jump about as the sort changes — the
     fold is a fact about the catalogue and the sort is a question about the list. */
  function folded(showing) {
    var mine = {};
    var loose = [];
    showing.forEach(function (row) {
      var group = GROUP_OF[row.id];
      if (!group) {
        loose.push(row);
        return;
      }
      (mine[group.id] = mine[group.id] || []).push(row);
    });
    var out = loose;
    collections.forEach(function (group) {
      var kept = mine[group.id];
      if (!kept) return;
      // One survivor is not a collection: folding it would hide a single text behind a
      // click and say "1 text" where the text's own name would do.
      if (kept.length < 2) {
        out = out.concat(kept);
        return;
      }
      out.push(fold(group, kept));
    });
    return out;
  }

  /* Which collections are open. Remembered, because a reader who opened the Mishneh
     Torah to look through it has not finished looking. Not `opened`, which the reader's
     own open-counts already are, and which shadows this inside the callback all of it
     runs in. */
  var unfolded = stored("targum:opened-groups");

  function isOpen(group) {
    // A search opens everything it found. A reader who types "teshuvah" and is shown
    // one closed row saying "Mishneh Torah" has been told the search failed.
    if (view.find) return true;
    // Behind a door of the Beit Midrash every shelf stands open: the Tanakh is its books
    // under Torah, Prophets and Writings, and a student looking for Ruth should not have
    // to guess which of three shut rows it is in.
    if (view.where === "midrash" && view.door) return true;
    return !!unfolded[group.id];
  }

  /* --- drawing one ----------------------------------------------------------- */

  function named(list, value) {
    for (var i = 0; i < list.length; i++) if (list[i][0] === value) return list[i][1];
    return "";
  }

  // A title's trailing English part, where a Hebrew title has one: the weekly's level.
  function splitLevel(text) {
    var found = /^(.*[֐-׿].*?) · ([A-Za-z][^֐-׿]*)$/.exec(String(text || ""));
    return found ? { title: found[1], level: found[2] } : { title: text, level: "" };
  }

  /* Where pressing a row goes, or "" where pressing it offers a build. A portion opens
     its reader, which is built once for the box: nothing to build and nothing to spend
     (targum-internal#410). A text the reader has, theirs or the shared shelf's, opens
     that copy. */
  function readerFor(row) {
    if (row.opens) return row.opens;
    if (row.built) return "/reader/" + encodeURIComponent(row.built.name) + "/reader/index.html";
    return "";
  }

  /* A text's picture, the way home draws one (design.md §12, "Every text has a picture",
     2026-10-08): `/thumb/<id>?drawn=1` answers with its own picture where it has one and
     the server's letter on the colour of its kind where it has none, so the library draws
     no letter of its own any more. */
  function pictureOf(row, className) {
    return window.TargumCovers.picture(
      { entry: row.id, title: row.title, language: row.language, kind: row.kind, register: row.register },
      { keyed: keyed, className: className }
    );
  }

  /* The two marks a cover can carry. §7: a 16 box, a 1.4 stroke, round caps, and no
     fill — the same drawing rules the nav's glyphs follow. */
  function glyph(which) {
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    var paths =
      which === "video"
        ? ["M2.6 4.4h6.2a1.4 1.4 0 0 1 1.4 1.4v4.4a1.4 1.4 0 0 1-1.4 1.4H2.6a1.4 1.4 0 0 1-1.4-1.4V5.8a1.4 1.4 0 0 1 1.4-1.4z", "m10.2 8.2 4.2-2.4v4.8l-4.2-2.4z"]
        : ["M8 2.6v10.8", "M5 5.4v5.2", "M2.4 7.2v1.6", "M11 4.8v6.4", "M13.6 7.2v1.6"];
    paths.forEach(function (d) {
      var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      svg.appendChild(path);
    });
    return svg;
  }

  /* How long a text is, the way the boards count it (SeeAllDesk): in words, "1,129
     words", because a reader chooses a text by how much there is to read. A recording is
     its time ("9 min", board SubFromLibrary): its words are what was said, not what
     there is to sit through. */
  function wordsOf(row) {
    if (row.rows) {
      return row.rows.reduce(function (total, one) {
        return total + wordsOf(one);
      }, 0);
    }
    return (row.entry && row.entry.words) || 0;
  }

  function lengthSaid(row) {
    var words = wordsOf(row);
    if (row.video || row.kind === "talk" || !words) return row.minutes ? said(row.minutes) : "";
    var shown;
    try {
      shown = words.toLocaleString(saidIn);
    } catch (e) {
      shown = String(words);
    }
    return tn("library.see.words", words, "{n} word", "{n} words", { n: shown });
  }

  /* The length's cell. On a phone the kind goes in front of it, "Dialogue · 21 words",
     where the line under the title is not drawn (board SeeAllPhone). */
  function lengthCell(row) {
    var cell = el("span", "col see-length");
    var kind = row.group ? "" : named(KIND_ONE, row.kind);
    if (kind) cell.appendChild(el("span", "see-length-kind", kind + " · "));
    cell.appendChild(el("span", "see-length-said", lengthSaid(row)));
    return cell;
  }

  /* How much of it the reader knows, at the row's end: "95% known" over a bar, in leaf
     where it is read now (board SeeAllDesk). Rounded down, as the shelves round: a row
     under A stretch never says 90%. Unmeasured says so, and never claims a nought. */
  function knownCell(row) {
    var share = knownOf(row);
    var cell = el("span", "see-known");
    if (typeof share !== "number") {
      cell.className = "see-known unmeasured";
      cell.appendChild(el("span", "see-known-say", t("library.known.unmeasured", "Not measured yet")));
      return cell;
    }
    var shown = Math.floor(share * 100);
    if (fitOf(row) === "now") cell.className = "see-known near";
    cell.appendChild(el("span", "see-known-say", t("library.known-share", "{share}% known", { share: shown })));
    cell.setAttribute("aria-label", t("library.you-know", "you know {share}% of its words", { share: shown }));
    var meter = el("span", "meter");
    meter.setAttribute("aria-hidden", "true");
    var fill = el("span");
    if (fill.style.setProperty) fill.style.setProperty("--done", String(Math.max(0.02, Math.min(1, share))));
    meter.appendChild(fill);
    cell.appendChild(meter);
    return cell;
  }

  //: Whether somebody is signed in, which Subscribe needs: `/readers` says.
  var signedIn = false;

  /* What a row can be subscribed to, where the catalogue can name it (design.md §12, "A
     subscription is the account's", 2026-10-09: "Subscribing happens … on a Library row"):
     a portion is the weekly portion, and a text from a channel the catalogue names is
     that channel. Null for everything else, which is most rows. */
  function subscribable(row) {
    if (row.group) {
      if (row.group.channel) return ["channel", row.group.channel];
      if (row.group.door === "portions") return ["series", "parasha"];
      return null;
    }
    if (row.opens) return ["series", "parasha"];
    var group = GROUP_OF[row.id];
    if (group && group.channel) return ["channel", group.channel];
    return null;
  }

  /* The row's Subscribe, from the hook a series page uses (`subscribe.js`): one press for
     a series, and for a channel the confirm page, where the cap is chosen. Beside the
     row's own press rather than inside it, since a press cannot hold a press. */
  function subscribeCell(row, member) {
    var hook = window.TargumSubscribe;
    var what = signedIn && hook && hook.button ? subscribable(row) : null;
    if (!what) return null;
    // Once a list, not once a row: a collection's texts are under its own row's
    // Subscribe, and the portions' door has its one in the trail above them.
    if (member && !row.group) return null;
    if (view.where === "midrash" && view.door === "portions" && what[0] === "series") return null;
    return subscribePress(what, row);
  }

  function subscribePress(what, row) {
    var hook = window.TargumSubscribe;
    var cell = el("span", "row-sub");
    var press = hook.button(what[0], what[1], {
      subscribe: t("library.subscribe", "Subscribe"),
      subscribed: t("library.subscribed", "Subscribed"),
    });
    press.className = (press.className ? press.className + " " : "") + "btn ghost outline small";
    press.setAttribute(
      "title",
      t("library.subscribe-to", "Subscribe to {name}", {
        name: what[0] === "series" ? t("library.door.portion", "Weekly portion") : (row && (row.author || row.english || row.title)) || "",
      })
    );
    cell.appendChild(press);
    return cell;
  }

  /* One text as a row of See all (board SeeAllDesk; design.md §12, "The Library stands on the
   * ground", 2026-10-09): its picture, its title with the English beside it, what
   * it is and whose, one line of what it is about, how long, and how much of it the
   * reader knows. A built text is a link and an unbuilt one is a button: what pressing
   * an unbuilt row does is start spending, after a press of its own (`confirmBuild`).
   */
  function draw(row, member) {
    if (row.group) return drawGroup(row);
    var item = el("li", "row see-row" + (member ? " member" : ""));
    item.setAttribute("data-row", row.id);

    var reading = readerFor(row);
    var open = el(reading ? "a" : "button", "row-open");
    if (reading) {
      open.href = keyed(reading);
    } else {
      open.type = "button";
      open.setAttribute("data-build", row.id);
    }

    var picture = el("span", "see-pic");
    var tile = pictureOf(row, "thumb");
    if (tile.setAttribute) tile.setAttribute("aria-hidden", "true");
    picture.appendChild(tile);
    // One mark, never two: a video can be listened to as well. Said, since it is drawn.
    if (row.video || row.spoken) {
      var media = el("span", "card-media");
      media.setAttribute("role", "img");
      media.setAttribute("aria-label", row.video ? t("library.video", "Video") : t("library.audio", "Audio"));
      media.appendChild(glyph(row.video ? "video" : "audio"));
      picture.appendChild(media);
    }
    open.appendChild(picture);

    var what = el("span", "what");
    var title = el("span", "row-title");
    title.setAttribute("lang", row.language);
    // No scene number before the title: "Scene 218" is the catalogue's id, and the row's
    // kind already says it is a dialogue (design review, 2026-10-09). Its own direction,
    // and its own clip, so a long Hebrew title loses its end and never its start.
    var parts = splitLevel(row.title);
    var bdi = el("bdi", "row-name", parts.title);
    bdi.setAttribute("dir", "auto");
    title.appendChild(bdi);
    if (parts.level) {
      var level = el("span", "row-level", parts.level);
      level.setAttribute("lang", "en");
      title.appendChild(level);
    }
    // The one row to open next: the first scene not yet finished.
    if (nextRow && row.id === nextRow.entry) {
      var chip = el(
        "span",
        "row-next",
        anyFinished ? t("library.next", "Next") : t("library.start-here", "Start here")
      );
      chip.setAttribute("role", "status");
      chip.setAttribute("lang", saidIn);
      title.appendChild(chip);
    }
    // Arrived lately (targum-internal#315): a tag, not a badge to clear.
    if (isNew(row) && !(window.TargumScenes && window.TargumScenes.numberOf(row.id))) {
      var fresh = el("span", "tag is-new row-new", t("library.new", "New"));
      fresh.setAttribute("lang", saidIn);
      title.appendChild(fresh);
    }
    what.appendChild(title);
    // The English beside the Hebrew, on one line where there is room (board SeeAllDesk):
    // for a reader who cannot yet read the line before it, this is the title.
    if (row.english) {
      var english = el("span", "row-english", row.english);
      english.setAttribute("lang", row.englishLang || "en");
      english.setAttribute("dir", "ltr");
      what.appendChild(english);
    }
    // What it is and whose: "Dialogue · targum", "Novel · אברהם מאפו, 1853".
    // Spans rather than bare text, so the row can be searched by its attributes.
    var meta = el("span", "row-meta");
    meta.appendChild(el("span", null, named(KIND_ONE, row.kind)));
    if (row.author) {
      meta.appendChild(el("span", null, named(KIND_ONE, row.kind) ? " · " : ""));
      var who = el("bdi", "row-by", row.author);
      who.setAttribute("dir", "auto");
      meta.appendChild(who);
    }
    what.appendChild(meta);
    /* What the text is, in the catalogue's own sentence, in the reader's language where
       the catalogue has one (design.md §12, "See all says what each text is"). One line
       at a desk, two on a phone. */
    var blurb = blurbIn(row.entry);
    if (blurb) {
      var about = el("span", "row-blurb", blurb);
      about.setAttribute("lang", row.entry.blurbs && row.entry.blurbs[uiLanguage] ? uiLanguage : "en");
      what.appendChild(about);
    }
    open.appendChild(what);

    open.appendChild(lengthCell(row));
    open.appendChild(knownCell(row));

    /* Where a build narrates itself — and, on a text this reader has finished, the one
       word that says so, in leaf. Empty until there is something to say; `build()`
       writes into it, so every row has one. */
    var state = el("span", "row-state");
    if (row.built && finishedDocs[row.built.document] && finishedDocs[row.built.document].done) {
      state.className = "row-state finished";
      state.textContent = t("library.finished", "finished");
    }
    open.appendChild(state);
    item.appendChild(open);

    var sub = subscribeCell(row, member);
    if (sub) item.appendChild(sub);

    // Only where there is something to draw: a text on the shelf, from the catalogue,
    // with no cover yet, and only where this deployment has a key to draw with.
    if (canDraw && row.built && !row.built.shared && row.entry && !row.drawn) {
      var drawing = el("button", "draw btn ghost outline small", t("library.cover.draw", "Draw cover"));
      drawing.type = "button";
      drawing.setAttribute("data-draw", row.built.name);
      item.appendChild(drawing);
    }
    return item;
  }

  /* A collection, as one row among the rows: a caret where the picture would be, its
     name and English, how many texts, and its members' length and known share added up.
     Pressed, it opens where it stands. */
  function drawGroup(row) {
    var group = row.group;
    var item = el("li", "row see-row group" + (isOpen(group) ? " open" : ""));
    item.setAttribute("data-row", row.id);

    var open = el("button", "row-open row-group");
    open.type = "button";
    open.setAttribute("aria-expanded", isOpen(group) ? "true" : "false");
    open.setAttribute("data-group", group.id);

    var caret = el("span", "see-pic row-fold");
    caret.setAttribute("aria-hidden", "true");
    open.appendChild(caret);

    var what = el("span", "what");
    var title = el("span", "row-title");
    title.setAttribute("lang", row.language);
    var name = el("bdi", "row-name", row.title);
    name.setAttribute("dir", "auto");
    title.appendChild(name);
    if (nextRow && !isOpen(group) && group.members.indexOf(nextRow.entry) >= 0) {
      var chip = el(
        "span",
        "row-next",
        anyFinished ? t("library.next", "Next") : t("library.start-here", "Start here")
      );
      chip.setAttribute("role", "status");
      chip.setAttribute("lang", saidIn);
      title.appendChild(chip);
    }
    what.appendChild(title);
    if (row.english) {
      var english = el("span", "row-english", row.english);
      english.setAttribute("lang", row.englishLang || "en");
      english.setAttribute("dir", "ltr");
      what.appendChild(english);
    }
    var count = tn("library.group-texts", row.rows.length, "{n} text", "{n} texts");
    var kind = named(KIND_ONE, row.kind);
    var meta = el("span", "row-meta", kind ? kind + " · " + count : count);
    if (saidIn !== "en") meta.setAttribute("lang", saidIn);
    what.appendChild(meta);
    var blurb = blurbIn(group);
    if (blurb) {
      var about = el("span", "row-blurb", blurb);
      about.setAttribute("lang", group.blurbs && group.blurbs[uiLanguage] ? uiLanguage : "en");
      what.appendChild(about);
    }
    open.appendChild(what);
    open.appendChild(lengthCell(row));
    open.appendChild(knownCell(row));
    open.appendChild(el("span", "row-state"));
    item.appendChild(open);
    var sub = subscribeCell(row);
    if (sub) item.appendChild(sub);
    return item;
  }

  /* --- sorting and sifting ---------------------------------------------------- */

  /* The orders See all is read in, one for each column head that can be pressed (board
     SeeAllDesk: Text · Length · % known). */
  var SORTS = {
    // By the English where there is one: for the reader this page is sorted for, the
    // Hebrew titles are not yet in an order.
    title: function (row) {
      return row.english || row.title || "";
    },
    minutes: function (row) {
      return row.minutes || 0;
    },
    // Most of it known first, which is the way somebody choosing what to read wants it.
    // A row with nothing measured is not 0% known: it goes after every row that was,
    // whichever way the column reads (see `sorted`).
    known: function (row) {
      var share = knownOf(row);
      return typeof share === "number" ? share : null;
    },
  };

  //: Columns a reader means "most first" by. Every other column reads smallest first.
  var DESCENDING = { known: true };

  /* The heads over the rows (board SeeAllDesk): the picture's column, then Text, Length
     and % known, and the cell a build narrates itself in. The Kind, Which Hebrew and Level
     columns went with the filters that were their questions (design.md §12, "See all is
     a table, a page at a time", 2026-10-09): a row says its kind under its title. */
  var COLUMNS = [
    ["", ""],
    ["title", t("library.column.title", "Text")],
    ["minutes", t("library.column.minutes", "Length")],
    ["known", t("library.column.known-share", "% known")],
    ["", ""],
  ];

  /* What the foot of the list says the order is: "% known, high to low". */
  //: Whether the list on show is one work read front to back, which keeps its order.
  var inItsOrder = false;

  function orderSaid() {
    if (inItsOrder || (view.kind === "dialogue" && window.TargumScenes)) {
      return t("library.order.in-order", "in order");
    }
    if (view.sort === "title") {
      return view.dir > 0 ? t("library.order.title-up", "title, A to Z") : t("library.order.title-down", "title, Z to A");
    }
    if (view.sort === "minutes") {
      return view.dir > 0
        ? t("library.order.length-up", "shortest first")
        : t("library.order.length-down", "longest first");
    }
    // Before anything is marked, "known" is the texts' own words standing in.
    if (!anyKnown) return view.dir < 0 ? t("library.order.easiest", "easiest first") : t("library.order.hardest", "hardest first");
    return view.dir < 0
      ? t("library.order.known-down", "% known, high to low")
      : t("library.order.known-up", "% known, low to high");
  }

  // Whether the server can draw at all, answered by the server. A deployment with no
  // image key offers nothing rather than offering and failing.
  var canDraw = false;
  // The reader's own finishes, by content hash, and the scene to open next — set once
  // the server has said what is shared.
  var finishedDocs = stored("targum:docs");
  var nextRow = null;
  var anyFinished = false;

  // One view per language (2026-09-14). A filter set on the Hebrew shelf is a question
  // about Hebrew texts: carried to French it hid the shelf behind a choice made
  // somewhere else, and "Poetry, under ten minutes" set for one language is not what
  // the reader asked of the next. A store from before this is one flat view, and it was
  // Hebrew's.
  var VIEW_FIELDS = [
    "sort",
    "dir",
    "kind",
    "register",
    "level",
    "length",
    "spoken",
    "where",
    "find",
    "subject",
    "fit",
    "shape",
    "door",
  ];
  var views = stored("targum:library");
  if (
    VIEW_FIELDS.some(function (field) {
      return Object.prototype.hasOwnProperty.call(views, field);
    })
  ) {
    views = { he: views };
  }

  //: The kinds a door may name that are more than one of the catalogue's: Books is the
  //: novels and the stories (board Library, "Browse by kind").
  var KIND_SETS = { books: ["novel", "story"] };

  function viewFor(code) {
    var one = views[code];
    if (!one || typeof one !== "object") one = views[code] = {};
    /* Most of it known first (board SeeAllDesk: "% known ↓"), which before anything is
       marked is easiest first: `sorted` breaks a tie on the texts' own words. A sort from
       before 2026-10-09 — Level, Kind, Which Hebrew, Newest — has no column to undo it
       any more, so it is read as this one. */
    if (!SORTS[one.sort]) {
      one.sort = "known";
      one.dir = -1;
    }
    if (one.dir !== 1 && one.dir !== -1) one.dir = DESCENDING[one.sort] ? -1 : 1;
    if (!one.kind) one.kind = "";
    if (one.kind && !named(KINDS, one.kind) && !KIND_SETS[one.kind]) one.kind = "";
    // "mine" was the Your uploads tab until 2026-09-25; a view stored on it is on All texts.
    if (!one.where || one.where === "mine") one.where = "library";
    if (!one.door) one.door = "";
    // The Library's box is the one search now (design.md §12, "One search, everywhere",
    // 2026-10-09): it opens over the page rather than narrowing it, so a search stored
    // from before must not go on narrowing the shelf with nothing on the page saying so.
    one.find = "";
    /* The filters that are no longer on the page (design.md §12, "The Library stands on the
       ground", 2026-10-09): the subjects, which Hebrew, the media, the length
       and the level. Kept, they would go on narrowing the list with nothing on it saying
       so, so a view that carried one lets it go. */
    one.subject = one.register = one.spoken = one.length = one.level = "";
    // `fit` is left unset: See all is under the band its shelf was, or none.
    return one;
  }

  /* How much of the library a See all list shows: the band it was opened from, or
     everything. No longer resolved for the reader (2026-09-17's narrowest band that left a
     screen's worth): the Library opens on its shelves now, one per band, and a band with
     nothing on it is a shelf that is not drawn rather than a list that is empty. */
  function fitWanted(state) {
    var one = state || view;
    return typeof one.fit === "string" ? one.fit : "";
  }

  /* The doors, as cards on the grid the texts use: the Hebrew name in the reading face,
     the page's own word under it, and how many texts stand behind it — "each chip
     carries its count" (design.md §12), so a door says what is there before it is
     opened. Only doors with something behind them, in the catalogue's order. */
  function doors(host, showing, redraw) {
    var behind = {};
    showing.forEach(function (row) {
      var door = doorOf(row);
      if (door) behind[door] = (behind[door] || 0) + 1;
    });
    DOORS.forEach(function (door) {
      if (!behind[door[0]]) return;
      var press = el("button", "door-card");
      press.type = "button";
      press.setAttribute("data-door", door[0]);
      var name = el("bdi", "door-name", door[1]);
      name.setAttribute("lang", "he");
      press.appendChild(name);
      press.appendChild(el("span", "door-english", door[2]));
      press.appendChild(
        el("span", "door-holds", tn("library.tally.all", behind[door[0]], "{n} text", "{n} texts"))
      );
      press.addEventListener("click", function () {
        view.door = door[0];
        redraw();
      });
      // The host is the cards' list, so a door is an item of it like any card.
      var item = el("li", "door-item");
      item.appendChild(press);
      host.appendChild(item);
    });
  }

  /* Where you are, in words, above the list: "Beit Midrash › Tanakh". The first is the
     way back to the doors. Drawn only inside one — at the doors the tab already says
     where you are, and a trail of one step is a label. */
  function crumbs(host, tree, redraw) {
    if (!host) return;
    host.textContent = "";
    var door = tree && view.door ? doorNamed(view.door) : null;
    host.hidden = !door;
    if (!door) return;
    var back = el("button", "crumb", MIDRASH[1]);
    back.type = "button";
    back.addEventListener("click", function () {
      view.door = "";
      view.find = "";
      var find = document.getElementById("find");
      if (find) find.value = "";
      redraw();
    });
    host.appendChild(back);
    host.appendChild(el("span", "crumb-step", "›"));
    var here = el("span", "crumb crumb-here");
    var name = el("bdi", null, door[1]);
    name.setAttribute("lang", "he");
    here.appendChild(name);
    here.appendChild(document.createTextNode(" · " + door[2]));
    here.setAttribute("aria-current", "page");
    host.appendChild(here);
    // The weekly portion is a series: its door says Subscribe once, here.
    if (door[0] === "portions" && signedIn && window.TargumSubscribe) {
      host.appendChild(subscribePress(["series", "parasha"], null));
    }
    // The Tanakh door leads on to the whole of it, one square a chapter (#144).
    if (door[0] === "tanakh") {
      var map = el("a", "crumb crumb-map", t("library.door.tanakh-map", "Every chapter on one map"));
      map.href = keyed("/tanakh-map");
      host.appendChild(map);
    }
  }

  /* The tree has an address — `#bm`, `#bm/tanakh` — the first view of this page that
     does, so a link can land somebody on the Writings' door. Written with
     `replaceState`: walking the tree is not a history of pages. A row's own hash
     (`#ruth`, `#build:ruth`) is left alone; `pointAt` reads those. */
  var TREE_HASH = "bm";

  function address(tree) {
    if (!window.history || !history.replaceState) return;
    var now = decodeURIComponent((location.hash || "").slice(1));
    var mine = now === TREE_HASH || now.indexOf(TREE_HASH + "/") === 0;
    if (!tree) {
      if (mine) history.replaceState(null, "", location.pathname + location.search);
      return;
    }
    if (now && !mine && seeAddressed() === null) return;
    var want = "#" + TREE_HASH + (view.door ? "/" + view.door : "");
    if (location.hash !== want) history.replaceState(null, "", location.pathname + location.search + want);
  }

  //: The door a tree address names, "" for the doors themselves, null for any other hash.
  function addressed() {
    var now = decodeURIComponent((location.hash || "").slice(1));
    if (now === TREE_HASH) return "";
    if (now.indexOf(TREE_HASH + "/") !== 0) return null;
    var door = now.slice(TREE_HASH.length + 1);
    return doorNamed(door) ? door : "";
  }


  /* --- the shelves (design.md §12, "The Library is shelved by how much you'd follow",
   * 2026-10-09) ------------------------------------------------------------------------
   *
   * The Library opens on its shelves, not on a list: one row of texts a band — what the
   * reader can read now, what is a stretch, what is hard for now — each with a See all
   * that is the one list, narrowed to that band, with every filter it always had. "I want
   * to be able to immediately choose a reading AT MY LEVEL" (2026-09-17) is answered by
   * the first shelf rather than by a band the list opened on, and a reader who has
   * marked almost nothing is shown the texts nearest them under Hard for now rather than
   * a narrowed list that had to widen itself to be worth showing.
   *
   * The measure is the one the list's band already used (`fitOf`): the share of a text's
   * words this reader knows, and the text's own hard-word share until they have marked
   * any. targum's own playlists (`swipe` collections) stand as a shelf of their own.
   *
   * The shelves are the landing. `#see` is the list, `#see/<band>` the list under one
   * band, and any other address (a text somebody was sent to, `#bm` for the Beit
   * Midrash) opens what it always opened.
   */
  var SEE = "see";
  //: How many texts a shelf stands before its See all: one row of five, as the board
  //: draws it (a phone shows the first two, in its two columns).
  var SHELF_MOST = 5;
  //: How many rows See all draws before its Show more (board SeeAllDesk).
  var PAGE = 50;
  var page = PAGE;
  //: Whether the list is up rather than the shelves.
  var seeAll = false;
  //: targum's own playlists, as the catalogue file lists them; only the ones with
  //: something built on the shared shelf are offered (`Library.targum_sets`).
  var sets = window.TARGUM_SETS || [];

  //: The band a See all address names, "" for the whole list, null for any other hash.
  function seeAddressed() {
    var now = decodeURIComponent((location.hash || "").slice(1));
    if (now === SEE) return "";
    if (now.indexOf(SEE + "/") !== 0) return null;
    var band = now.slice(SEE.length + 1);
    return bandNamed(band) ? band : "";
  }

  /* The kind a See all address names — `#see/kind/story` — or null. A touchstone on Your
     Progress opens its shelf this way (design.md §12, "Your Progress is a story in three
     parts", 2026-10-09): the whole list, every band, narrowed to that kind of text. */
  function kindAddressed() {
    var now = decodeURIComponent((location.hash || "").slice(1));
    var lead = SEE + "/kind/";
    if (now.indexOf(lead) !== 0) return null;
    var kind = now.slice(lead.length);
    for (var n = 0; n < KINDS.length; n++) if (KINDS[n][0] === kind) return kind;
    return KIND_SETS[kind] ? kind : null;
  }

  /* A step the Back button can undo: from the shelves into a list is going somewhere. */
  function mark(hash) {
    var bare = location.pathname + location.search;
    if (window.history && history.pushState) history.pushState(null, "", bare + (hash ? "#" + hash : ""));
    else location.hash = hash ? "#" + hash : "";
  }

  /* Nearest first: the most of it known, and before anything is marked the fewest hard
     words. A text nobody measured goes after every one somebody did. */
  function nearest(a, b) {
    if (anyKnown) {
      var left = knownOf(a);
      var right = knownOf(b);
      left = typeof left === "number" ? left : -1;
      right = typeof right === "number" ? right : -1;
      if (left !== right) return right - left;
    }
    var hardLeft = measured(a) ? a.difficulty || 0 : 1000;
    var hardRight = measured(b) ? b.difficulty || 0 : 1000;
    if (hardLeft !== hardRight) return hardLeft - hardRight;
    return String(a.title).localeCompare(String(b.title));
  }

  /* One band's shelf: its texts nearest first, one from each collection — a hundred
     scenes or thirty-nine of an author's stories are one place to start, and a shelf of
     them is a shelf of one thing — and the next scene first wherever it falls. */
  function shelfOf(pool, band) {
    var inBand = pool.filter(function (row) {
      return fitOf(row) === band;
    });
    inBand.sort(nearest);
    if (nextRow) {
      for (var n = 0; n < inBand.length; n++) {
        if (inBand[n].id === nextRow.entry) {
          inBand.unshift(inBand.splice(n, 1)[0]);
          break;
        }
      }
    }
    var taken = {};
    var out = [];
    for (var i = 0; i < inBand.length && out.length < SHELF_MOST; i++) {
      // The scenes are one sequence however the file folds them.
      var scene = window.TargumScenes && window.TargumScenes.numberOf(inBand[i].id);
      var group = scene ? { id: "scenes" } : GROUP_OF[inBand[i].id];
      if (group) {
        if (taken[group.id]) continue;
        taken[group.id] = true;
      }
      out.push(inBand[i]);
    }
    return { rows: out, count: inBand.length };
  }

  /* One text on a shelf: its picture, what it is and how long, its title in its own face,
     and how much of it the reader knows. Pressed, it does what a card does: a text the
     reader has opens, and one they have not offers its build and waits for the press. */
  function shelfCard(row, band) {
    var item = el("li", "band-item");
    item.setAttribute("data-row", row.id);
    var reading = readerFor(row);
    var open = el(reading ? "a" : "button", "band-card");
    if (reading) {
      open.href = keyed(reading);
    } else {
      open.type = "button";
      open.setAttribute("data-build", row.id);
    }
    var cover = el("span", "band-cover");
    cover.setAttribute("aria-hidden", "true");
    cover.appendChild(pictureOf(row, "thumb band-thumb"));
    if (row.video || row.spoken) {
      var media = el("span", "card-media");
      media.appendChild(glyph(row.video ? "video" : "audio"));
      cover.appendChild(media);
    }
    open.appendChild(cover);
    // The kind and the length, as every tile says them, a dialogue's too: never its
    // scene number (design.md §12, "A text is named in everyday words", 2026-10-09).
    var kind = [named(KIND_ONE, row.kind), row.minutes ? said(row.minutes) : ""].filter(Boolean).join(" · ");
    var what = el("span", "band-kind", kind);
    what.setAttribute("lang", saidIn);
    open.appendChild(what);
    var title = el("bdi", "band-title", splitLevel(row.title).title);
    title.setAttribute("lang", row.language);
    title.setAttribute("dir", "auto");
    open.appendChild(title);
    if (nextRow && row.id === nextRow.entry) {
      var next = el(
        "span",
        "row-next",
        anyFinished ? t("library.next", "Next") : t("library.start-here", "Start here")
      );
      next.setAttribute("role", "status");
      next.setAttribute("lang", saidIn);
      open.appendChild(next);
    }
    // How much of it the reader knows, always (board Library: "[93%] known"); a text
    // nobody has measured says so rather than claiming a nought.
    var share = knownOf(row);
    open.appendChild(
      typeof share === "number"
        ? el(
            "span",
            "band-known" + (band === "now" ? " near" : ""),
            // Rounded down, as the Tanakh map rounds: a card on A stretch never says 90%.
            t("library.known-share", "{share}% known", { share: Math.floor(share * 100) })
          )
        : el("span", "band-known unmeasured", t("library.known.unmeasured", "Not measured yet"))
    );
    open.appendChild(el("span", "row-state"));
    item.appendChild(open);
    return item;
  }

  /* The sets on the shared shelf in this language, each with its members that are built
     there, in the file's order. A member not built is left out, as the playlists tab
     leaves it out: opening a set spends nothing. */
  function setsHere(shared, code) {
    var built = {};
    (shared || []).forEach(function (reader) {
      if (reader.entry) built[reader.entry] = true;
    });
    var out = [];
    sets.forEach(function (group) {
      var members = (group.members || []).filter(function (id) {
        var entry = catalogued(id);
        return built[id] && entry && inLanguage(entry, code);
      });
      if (members.length) out.push({ group: group, members: members });
    });
    return out;
  }

  /* One of targum's playlists: the first four of it as one picture, as its card on Your
     targums draws it, its name in the reader's language, and how many texts. */
  function setCard(one) {
    var item = el("li", "band-item");
    item.setAttribute("data-set", one.group.id);
    var open = el("button", "band-card band-set");
    open.type = "button";
    open.setAttribute("data-set", one.group.id);
    var mosaic = el("span", "band-cover band-mosaic");
    mosaic.setAttribute("aria-hidden", "true");
    one.members.slice(0, 4).forEach(function (id) {
      var entry = catalogued(id) || {};
      mosaic.appendChild(pictureOf({ id: id, title: entry.title, language: entry.language }, "thumb"));
    });
    open.appendChild(mosaic);
    var count = el("span", "band-kind", tn("library.group-texts", one.members.length, "{n} text", "{n} texts"));
    count.setAttribute("lang", saidIn);
    open.appendChild(count);
    var name = el("bdi", "band-title band-set-name", titleIn(one.group) || one.group.title);
    name.setAttribute("dir", "auto");
    if (titleIn(one.group)) name.setAttribute("lang", namedIn(one.group) ? uiLanguage : "en");
    open.appendChild(name);
    open.appendChild(el("span", "row-state"));
    item.appendChild(open);
    return item;
  }

  /* Opening a set copies it into the reader's playlists, or finds the copy they have, and
     goes to its first text — what Open does on Your targums' Playlists tab. */
  function openSet(button, id) {
    var state = button.querySelector(".row-state");
    button.disabled = true;
    ask("/playlists/targum/" + encodeURIComponent(id), {})
      .then(function (answer) {
        if (answer && answer.signedIn === false) {
          window.location.href = keyed("/account/signin");
          return;
        }
        if (!answer || answer.error) throw new Error("refused");
        var first = (answer.items || []).filter(function (one) {
          return one.open;
        })[0];
        if (!first) {
          window.location.href = keyed("/playlists/" + answer.id);
          return;
        }
        var path = first.open;
        window.location.href = keyed(
          path + (path.indexOf("?") < 0 ? "?" : "&") + "list=" + answer.id + "&at=" + first.position
        );
      })
      .catch(function () {
        tell(state, t("library.set.failed", "We couldn't open that playlist. Try again."));
        button.disabled = false;
      });
  }

  function shelf(id, name, note, cards, onSee) {
    var section = el("section", "band");
    section.setAttribute("data-band", id);
    section.setAttribute("aria-labelledby", "band-" + id);
    var head = el("div", "band-head");
    var heading = el("h2", "section-title band-name", name);
    heading.id = "band-" + id;
    head.appendChild(heading);
    if (onSee) {
      var all = el("a", "band-all", t("library.see-all", "See all"));
      all.href = "#" + SEE + "/" + id;
      all.setAttribute("aria-label", t("library.see-all-named", "See all: {name}", { name: name }));
      all.addEventListener("click", function (event) {
        if (event && event.preventDefault) event.preventDefault();
        onSee(id);
      });
      head.appendChild(all);
    }
    section.appendChild(head);
    if (note) section.appendChild(el("p", "band-note", note));
    var list = el("ul", "band-cards");
    cards.forEach(function (card) {
      list.appendChild(card);
    });
    section.appendChild(list);
    return section;
  }

  var BAND_NOTES = {
    now: t("library.band.now-note", "You know 90% or more of their words."),
    stretch: t("library.band.stretch-note", "You know 75–90% of their words: a word to look up every line or two."),
    hard: t("library.band.hard-note", "You know less than 75% of their words. The nearest come first."),
  };

  /* The shelves, in order: Read it now, A stretch, targum's playlists, Hard for now. A
     band with nothing in it is not drawn. Answers how many shelves stand. */
  function drawShelves(host, pool, shared, code, onSee) {
    host.textContent = "";
    var drawn = [];
    BANDS.forEach(function (band) {
      var found = shelfOf(pool, band[0]);
      if (found.rows.length) {
        drawn.push(
          shelf(
            band[0],
            band[1],
            anyKnown ? BAND_NOTES[band[0]] : "",
            found.rows.map(function (row) {
              return shelfCard(row, band[0]);
            }),
            onSee
          )
        );
      }
      if (band[0] === "stretch") {
        var offered = setsHere(shared, code);
        if (offered.length) {
          drawn.push(
            shelf(
              "sets",
              t("library.band.sets", "Playlists from targum"),
              t("library.band.sets-note", "Short texts to swipe through, one after another."),
              offered.map(setCard),
              null
            )
          );
        }
      }
    });
    // Before anything is marked the bands are the texts' own hard words, and the page
    // says so once rather than under every shelf.
    if (drawn.length && !anyKnown) {
      host.appendChild(
        el(
          "p",
          "note shelves-note",
          t("library.shelves.unmarked", "Until you mark words you know, these go by how common each text's words are.")
        )
      );
    }
    drawn.forEach(function (section) {
      host.appendChild(section);
    });
    return drawn.length;
  }

  var view = viewFor(lang.HOME);

  /* Whether one row survives the filters. `using` lets a caller ask the question against
     a different set of them — see `present()`, which asks it with one filter lifted. */
  // Every language a row is written in. Daniel is Hebrew with Aramaic chapters and is on
  // both shelves (2026-09-13); a row from before `languages` existed has its one.
  function inLanguage(row, code) {
    var all = row.languages && row.languages.length ? row.languages : [row.language];
    for (var n = 0; n < all.length; n++) if (base(all[n]) === code) return true;
    return false;
  }

  function matches(row, code, using) {
    var state = using || view;
    var tree = state.where === "midrash";
    // The one place the Hebrew shelf shows rows of another language: the Aramaic door.
    if (!inLanguage(row, code) && !(tree && code === lang.HOME && inLanguage(row, BESIDE_HEBREW))) {
      return false;
    }
    if (state.kind) {
      var kinds = KIND_SETS[state.kind] || [state.kind];
      if (kinds.indexOf(row.kind) < 0) return false;
    }
    /* The band is for choosing from the catalogue. It is not for the Beit Midrash: a tree that hid the Writings from a beginner because
       they are hard would be a tree with branches missing, and the reader came to see
       where things stand. Each row still says how much of it they know. */
    if (!tree && !fits(row, fitWanted(state))) return false;
    if (!row.entry) return false;
    if (tree) {
      var behind = doorOf(row);
      if (!behind) return false;
      // A search looks behind every door; otherwise one door at a time.
      if (state.door && !state.find && behind !== state.door) return false;
    }
    if (state.find) {
      // The blurb and the name the text is filed under are in this on purpose. A reader
      // typing "herzl" into a library of Hebrew titles otherwise finds nothing: the
      // titles and the bylines are both in Hebrew, and the only Latin a text carries is
      // the sentence describing it and its own id.
      // The collection a text is in, too: a reader typing "mishneh torah" is looking for
      // its thirteen sections, and not one of them has those words anywhere in it.
      var holds = GROUP_OF[row.id];
      var hay = [
        row.title,
        row.english,
        row.author,
        // Both blurbs: a Russian reader searching a Russian word should find the row,
        // and one searching the English it was drafted from should still find it too.
        row.entry ? row.entry.blurb : "",
        row.entry ? blurbIn(row.entry) : "",
        row.id,
        holds ? holds.title + " " + holds.english : "",
      ]
        .join(" ")
        .toLowerCase();
      if (hay.indexOf(state.find.toLowerCase()) < 0) return false;
    }
    return true;
  }

  /* The rows inside one open collection. An ordered collection — a work read front to
     back — keeps its own order whatever column the page is sorted on, for the reason the
     scenes already do: Deuteronomy above Genesis because it measures easier is not a
     Torah. An author's shelf has no such order, and takes the reader's. */
  function within(group, rows) {
    if (!group.ordered) return sorted(rows);
    return rows.slice().sort(function (a, b) {
      return (PLACE_IN[a.id] || 0) - (PLACE_IN[b.id] || 0);
    });
  }

  function sorted(list) {
    // A numbered sequence has one order. Under the Scenes chip the list is scene 1, 2,
    // 3… whatever column was last sorted on — their measured shares are noise at twenty
    // words — and the heading says so (see `heading()`).
    if (view.kind === "dialogue" && window.TargumScenes) return window.TargumScenes.ordered(list);
    var pick = SORTS[view.sort] || SORTS.title;
    return list.slice().sort(function (a, b) {
      var left = pick(a);
      var right = pick(b);
      var order;
      if ((left === null) !== (right === null)) return left === null ? 1 : -1;
      if (typeof left === "number") order = left - right;
      else if (left !== null) order = String(left).localeCompare(String(right));
      else order = 0;
      /* Known ties — and before anything is marked every row ties at nothing measured —
         are broken by the texts' own words, fewer hard ones counting as more known, so
         "% known, high to low" is easiest first until the reader's words can say. */
      if (!order && view.sort === "known") {
        var hardA = measured(a) ? a.difficulty || 0 : 1000;
        var hardB = measured(b) ? b.difficulty || 0 : 1000;
        if (hardA !== hardB) {
          // Unmeasured goes last whichever way the column reads.
          if (hardA === 1000 || hardB === 1000) return hardA === 1000 ? 1 : -1;
          order = hardB - hardA;
        }
      }
      // A tie falls back to the title, so the list never shuffles under a reader who
      // sorted by something half of it shares.
      if (!order) order = String(a.title).localeCompare(String(b.title));
      return order * view.dir;
    });
  }

  /* --- the controls ----------------------------------------------------------- */

  /* Which values of one field the rest of the filters leave standing.
   *
   * Computed against everything except the field being drawn, so choosing a kind never
   * removes the other kinds from the row it lives in — that would be a filter that eats
   * itself. */
  function present(rows, field, code) {
    var seen = {};
    rows.forEach(function (row) {
      var pretend = {};
      for (var key in view) pretend[key] = view[key];
      pretend[field] = "";
      if (matches(row, code, pretend)) seen[row[field]] = true;
    });
    return seen;
  }

  /* --- the menus (board SeeAllDesk: "Kind: All ▾", "Level: Any ▾", "Language: Hebrew ▾")
   *
   * A pill that says what it is set to, and under it a short list to choose from. Not a
   * native `select` (design.md §12, "The Library stands on the ground"): the desk's
   * controls are one layer, and the platform's list came up in the system's face and
   * colours beside everything else drawn in the desk's. A button and a list of
   * `menuitemradio`, as the language menu in the bar is; Escape and a press anywhere else
   * close it, and the arrows walk it.
   */
  var openMenu = null;

  function closeMenu(focusBack) {
    if (!openMenu) return;
    var was = openMenu;
    openMenu = null;
    was.list.hidden = true;
    was.press.setAttribute("aria-expanded", "false");
    if (focusBack && was.press.focus) was.press.focus();
  }

  function menu(id, label, options, current, onPick) {
    var box = el("div", "see-menu");
    box.setAttribute("data-menu", id);
    var press = el("button", "see-menu-press");
    press.type = "button";
    press.id = "menu-" + id;
    press.setAttribute("aria-haspopup", "menu");
    press.setAttribute("aria-expanded", "false");
    press.appendChild(el("span", "see-menu-label", label + ":"));
    press.appendChild(document.createTextNode(" "));
    press.appendChild(el("span", "see-menu-value", named(options, current) || (options[0] || ["", ""])[1]));
    box.appendChild(press);
    var list = el("div", "see-menu-list");
    list.setAttribute("role", "menu");
    list.setAttribute("aria-label", label);
    list.hidden = true;
    var items = [];
    options.forEach(function (pair) {
      var item = el("button", "see-menu-item", pair[1]);
      item.type = "button";
      item.setAttribute("role", "menuitemradio");
      item.setAttribute("aria-checked", pair[0] === current ? "true" : "false");
      item.setAttribute("data-value", pair[0]);
      item.addEventListener("click", function () {
        closeMenu(true);
        if (pair[0] !== current) onPick(pair[0]);
      });
      items.push(item);
      list.appendChild(item);
    });
    list.addEventListener("keydown", function (event) {
      var at = items.indexOf(event.target);
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        var next = items[(at + (event.key === "ArrowDown" ? 1 : items.length - 1)) % items.length];
        if (next && next.focus) next.focus();
      } else if (event.key === "Escape") {
        event.preventDefault();
        closeMenu(true);
      } else if (event.key === "Tab") {
        closeMenu(false);
      }
    });
    box.appendChild(list);
    press.addEventListener("click", function () {
      var was = openMenu && openMenu.press === press;
      closeMenu(false);
      if (was) return;
      openMenu = { press: press, list: list };
      list.hidden = false;
      press.setAttribute("aria-expanded", "true");
      var on = items.filter(function (item) {
        return item.getAttribute("aria-checked") === "true";
      })[0] || items[0];
      if (on && on.focus) on.focus();
    });
    return box;
  }

  if (document.addEventListener) {
    document.addEventListener("click", function (event) {
      if (!openMenu) return;
      var inside = event.target && event.target.closest ? event.target.closest(".see-menu") : null;
      if (!inside || !inside.contains(openMenu.press)) closeMenu(false);
    });
    document.addEventListener("keydown", function (event) {
      if (openMenu && event.key === "Escape") closeMenu(true);
    });
  }

  /* The levels, as the Level menu says them: the three shelves, and any. */
  var LEVEL_MENU = [["", t("library.filter.any", "Any")]].concat(BANDS);

  /* Kind, Level and Language, beside the search on See all. Kind offers the kinds in
     front of this reader, as the chips did; Level is the band, the shelf the list was
     opened from; Language is the one the bar's menu also sets. */
  function drawMenus(host, everything, code, codes, redraw, pickLanguage) {
    if (!host) return;
    host.textContent = "";
    var seen = present(everything, "kind", code);
    var kinds = [["", t("library.filter.all", "All")]].concat(
      KINDS.filter(function (pair) {
        return seen[pair[0]] || view.kind === pair[0];
      })
    );
    if (KIND_SETS[view.kind]) kinds.push([view.kind, t("library.kind.books", "Books")]);
    host.appendChild(
      menu("kind", t("library.menu.kind", "Kind"), kinds, view.kind || "", function (value) {
        view.kind = value;
        page = PAGE;
        redraw();
      })
    );
    host.appendChild(
      menu("level", t("library.menu.level", "Level"), LEVEL_MENU, fitWanted(), function (value) {
        view.fit = value;
        page = PAGE;
        mark(SEE + (value ? "/" + value : ""));
        redraw();
      })
    );
    var languages = (codes || [code]).map(function (one) {
      return [one, names[one] || one];
    });
    host.appendChild(
      menu("language", t("library.menu.language", "Language"), languages, code, function (value) {
        page = PAGE;
        pickLanguage(value);
      })
    );
  }

  function heading(redraw) {
    var host = document.getElementById("rows-head");
    host.textContent = "";
    COLUMNS.forEach(function (pair, at) {
      // The picture's column has no head; the build's cell at the end takes no column.
      if (!pair[0]) {
        if (!at) host.appendChild(el("span", "see-head-pic"));
        return;
      }
      var button = el("button", "see-head-" + pair[0]);
      button.type = "button";
      // Under the Dialogues the list is in scene order whatever this column says, so the
      // column says that instead, and cannot be pressed.
      var scenes = pair[0] === "known" && view.kind === "dialogue";
      button.appendChild(
        document.createTextNode(scenes ? t("library.column.in-order", "In order") : pair[1])
      );
      if (scenes) {
        button.disabled = true;
        button.setAttribute("aria-disabled", "true");
      } else if (view.sort === pair[0]) {
        button.setAttribute("aria-sort", view.dir > 0 ? "ascending" : "descending");
        button.appendChild(el("span", "arrow", view.dir > 0 ? " ↑" : " ↓"));
      }
      button.addEventListener("click", function () {
        if (scenes) return;
        if (view.sort === pair[0]) view.dir = -view.dir;
        else {
          view.sort = pair[0];
          view.dir = DESCENDING[pair[0]] ? -1 : 1;
        }
        page = PAGE;
        redraw();
      });
      host.appendChild(button);
    });
  }

  /* --- building one ----------------------------------------------------------- */

  // The pipeline narrates itself in its own words. This is the reader's.
  var PLAIN = {
    // Keyed by the pipeline's own English, which is what arrives; said in the reader's.
    "Finding each word's dictionary form…": t("library.build.words", "We're reading the words…"),
    "Adding vowel points…": t("library.build.points", "We're adding vowel points…"),
    "Building the reader…": t("library.build.page", "We're setting the page…"),
  };

  function say(message) {
    if (!message) return "";
    if (PLAIN[message]) return PLAIN[message];
    if (message.indexOf("Matching") === 0) return t("library.build.lining-up", "We're lining it up…");
    if (message.indexOf("Looking up") === 0) return t("library.build.looking-up", "We're looking up the words…");
    return t("library.build.almost", "Almost there…");
  }

  // A build's sentence in the row (2026-09-14). The state's own column is a word wide and
  // clips, which is right for "finished" and cut a failure down to "We lost that buil…";
  // a sentence takes a line of its own under the title, whole.
  function tell(state, text) {
    state.textContent = text;
    state.classList.toggle("said", !!text);
  }

  function watch(id, state, open) {
    return new Promise(function (resolve) {
      var timer = setInterval(function () {
        ask("/job/" + id).then(function (job) {
          // A failure or a refusal ends the watch, and the row can be pressed again: the
          // sentence usually says to start it again.
          var problem = job.error || (job.stage === "blocked" && job.blocked);
          if (problem) {
            clearInterval(timer);
            tell(state, problem);
            open.disabled = false;
            resolve();
            return;
          }
          tell(state, say(job.message) || t("library.build.almost", "Almost there…"));
          if (job.stage === "done") {
            clearInterval(timer);
            window.location.href = keyed("/reader/" + job.reader.split("/").map(encodeURIComponent).join("/"));
            resolve();
          }
        });
      }, 700);
    });
  }

  function build(open, entry) {
    var state = open.querySelector(".row-state");
    open.disabled = true;
    tell(state, t("library.build.getting-ready", "We're getting it ready…"));
    ask("/prepare", {
      source: entry.source,
      // The language this reader reads into, not English by assumption. They read in
      // two; a button that always bought one of them would be a button that reads their
      // mind wrong half the time. Clamped to what the account is offered, so a
      // remembered choice that no longer stands asks for English rather than a refusal.
      to: window.TargumSync ? window.TargumSync.into(lang.into()) : lang.into() || "en",
      from: entry.language,
      words: true,
      gloss: false,
      // Every published translation this text has. The reader switches between them.
      translations: entry.translations.map(function (t) {
        return t.source;
      }),
    })
      .then(function (job) {
        if (job.error) throw new Error(job.error);
        if (job.blocked) throw new Error(job.blocked);
        // A price with no build in it — the server pointing at a catalogue row instead —
        // is not something to press Build on: an empty id came back as a lost build.
        if (!job.id) throw new Error(t("library.build.could-not-start", "We couldn't start this one. Try again."));
        // Said, and then pressed (2026-09-14). The first press used to go straight on to
        // the build, while the conversation and the Add page both say how long a thing
        // takes and wait for the reader's own press before anything is spent. The same
        // here: how long, and a press of its own beside the row.
        return confirmBuild(open, state, job, entry).then(function (yes) {
          if (!yes) {
            tell(state, "");
            open.disabled = false;
            return;
          }
          tell(state, t("library.build.lining-up", "We're lining it up…"));
          return ask("/build", { id: job.id }).then(function (started) {
            if (started.error) throw new Error(started.error);
            if (started.stage === "blocked") throw new Error(started.blocked);
            return watch(job.id, state, open);
          });
        });
      })
      .catch(function (problem) {
        tell(state, String(problem.message || problem));
        open.disabled = false;
      });
  }

  // How long it will take, in the reader's minutes, and the press that starts it.
  function waitFor(job) {
    if (!job.estimate) return t("library.wait.moment", "Ready in a moment.");
    var mins = Math.max(1, Math.round((job.total || job.segments || 0) / 25));
    var chapter = job.chapters > 1;
    if (mins <= 1) {
      return chapter
        ? t("library.wait.chapter-minute", "Your first chapter will be ready in about a minute.")
        : t("library.wait.minute", "Ready in about a minute.");
    }
    if (mins <= 4) {
      return chapter
        ? t("library.wait.chapter-couple", "Your first chapter will be ready in a couple of minutes.")
        : t("library.wait.couple", "Ready in a couple of minutes.");
    }
    return chapter
      ? t("library.wait.chapter-minutes", "Your first chapter will be ready in about {n} minutes.", { n: mins })
      : t("library.wait.minutes", "Ready in about {n} minutes.", { n: mins });
  }

  function confirmBuild(open, state, job, entry) {
    return new Promise(function (resolve) {
      var item = open.parentNode;
      tell(state, waitFor(job));
      // The verb follows the medium (targum-internal#337): the row knows what it carries.
      var starting = entry && entry.video
        ? t("library.build.start-watching", "Start watching")
        : entry && entry.kind === "talk"
          ? t("library.build.start-listening", "Start listening")
          : t("library.build.start-reading", "Start reading");
      var go = el("button", "row-go", starting);
      go.type = "button";
      var not = el("button", "row-not", t("library.build.not-now", "Not now"));
      not.type = "button";
      function done(answer) {
        if (go.parentNode) go.parentNode.removeChild(go);
        if (not.parentNode) not.parentNode.removeChild(not);
        resolve(answer);
      }
      go.onclick = function () {
        done(true);
      };
      not.onclick = function () {
        done(false);
      };
      item.appendChild(go);
      item.appendChild(not);
      if (go.focus) go.focus();
    });
  }

  function drawCovers(button, name) {
    button.disabled = true;
    button.textContent = t("library.cover.drawing", "Drawing…");
    ask("/cover", { name: name, chapters: true })
      .then(function (job) {
        if (job.error) throw new Error(job.error);
        if (!job.id) {
          button.textContent = t("library.cover.drawn", "Drawn");
          return;
        }
        return new Promise(function (resolve) {
          var timer = setInterval(function () {
            ask("/job/" + job.id).then(function (state) {
              if (state.error) {
                clearInterval(timer);
                button.textContent = state.error;
                resolve();
                return;
              }
              // Counted rather than guessed at: a book with thirty-five chapters worth
              // drawing takes minutes, and a button that only says "Drawing…" for that
              // long is indistinguishable from one that has died.
              if (state.total > 1) {
                button.textContent = t("library.cover.progress", "{done} of {total}", {
                  done: state.done,
                  total: state.total,
                });
              }
              if (state.stage === "done") {
                clearInterval(timer);
                resolve();
              }
            });
          }, 900);
        });
      })
      .then(function () {
        // Drawn now, so the row shows it. The tiles ask for the image again from
        // scratch, which is the only way past a browser that has cached the 404.
        location.reload();
      })
      .catch(function (problem) {
        button.textContent = String(problem.message || problem);
        button.disabled = false;
      });
  }

  /* --- putting it together ----------------------------------------------------- */

  function kept() {
    var found = [];
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var name = localStorage.key(i) || "";
        if (name.indexOf("targum:vocab:") === 0) {
          found.push({ language: name.slice("targum:vocab:".length) });
        }
      }
    } catch (e) {}
    return found;
  }

  /* --- the Weekly portion shelf (targum-internal#411) ---------------------------------
   *
   * The fifty-four portions are catalogue rows, behind the Beit Midrash's door and in
   * their collection, and that is where somebody looking for Vayera finds it. What that
   * cannot answer is the question a reader of the portion asks every week: which one is
   * it this Shabbat? So a shelf of its own, above the list: this week's first, then the
   * year onward from it, round to where it began.
   *
   * Every card opens the portion's reader, which the box builds once for everybody: a
   * card here never builds and never spends (#410). `/portions` says which is read this
   * week on both calendars, and the reader's own — `TargumFollow.schedule()`, the
   * diaspora's until they say — picks. The switch is drawn only in a week the two
   * calendars read different portions, as `/parasha` draws it.
   */

  //: The shared shelf, as `/readers` last answered it.
  var sharedNow = [];
  //: Each portion's reader by its catalogue id, filled from `/portions`.
  var portionsAt = {};
  //: What `/portions` said, kept so the shelf can be drawn again for the other calendar.
  var portionShelf = null;

  /* Kept by `follow.js`, which rides in the bar on every page, so Learn and the bell
     ask for the week's portion by the same calendar. The fallback is the same key, for a
     page that has the shelf without the bar. */
  var SCHEDULE = "targum:schedule";
  function scheduleKept() {
    var follow = window.TargumFollow;
    if (follow && follow.schedule) return follow.schedule();
    try {
      return localStorage.getItem(SCHEDULE) === "israel" ? "israel" : "diaspora";
    } catch (e) {
      return "diaspora";
    }
  }
  function keepSchedule(which) {
    var follow = window.TargumFollow;
    if (follow && follow.setSchedule) return follow.setSchedule(which);
    try {
      localStorage.setItem(SCHEDULE, which);
    } catch (e) {}
  }

  /* The cards in the order the shelf shows them: this week's reading, then the cycle
     onward from it and round. A doubled week stands first as one card; its halves keep
     their places at the end of the year, where they come round again. */
  function portionOrder(answer, schedule) {
    var all = (answer && answer.portions) || [];
    var week = (answer && answer.week) || {};
    var cycle = all.filter(function (one) {
      return one.listed;
    });
    var slug = week[schedule] || week.diaspora || week.israel || "";
    var first = null;
    all.forEach(function (one) {
      if (one.slug === slug) first = one;
    });
    if (!first) return cycle;
    var last = first.numbers && first.numbers.length ? first.numbers[first.numbers.length - 1] : 0;
    var start = 0;
    for (var i = 0; i < cycle.length; i++) {
      if (cycle[i].numbers && cycle[i].numbers[0] > last) {
        start = i;
        break;
      }
    }
    var onward = last ? cycle.slice(start).concat(cycle.slice(0, start)) : cycle;
    return [first].concat(
      onward.filter(function (one) {
        return one.slug !== first.slug;
      })
    );
  }

  function catalogued(id) {
    for (var i = 0; i < catalogue.length; i++) if (catalogue[i].id === id) return catalogue[i];
    return null;
  }

  // "10 Oct", in the page's language. Noon, so no timezone moves the Shabbat to Friday.
  function shabbatSaid(iso) {
    var at = new Date(iso + "T12:00:00");
    if (isNaN(at.getTime())) return "";
    try {
      return at.toLocaleDateString(saidIn, { day: "numeric", month: "short" });
    } catch (e) {
      return iso;
    }
  }

  function portionCard(one, thisWeek, shabbat) {
    var item = el("li", "portion-item" + (thisWeek ? " this-week" : ""));
    item.setAttribute("data-portion", one.slug);
    var open = el("a", "portion-card");
    open.href = keyed(one.href);
    if (thisWeek) {
      var when = el(
        "span",
        "portion-when",
        shabbat
          ? t("library.portions.this-shabbat-on", "This Shabbat · {date}", { date: shabbatSaid(shabbat) })
          : t("library.portions.this-shabbat", "This Shabbat")
      );
      when.setAttribute("lang", saidIn);
      open.appendChild(when);
    }
    var name = el("bdi", "portion-name", one.hebrew);
    name.setAttribute("lang", "he");
    name.setAttribute("dir", "rtl");
    open.appendChild(name);
    var entry = catalogued(one.id);
    var english = el("span", "portion-english", titleIn(entry) || one.name);
    english.setAttribute("lang", entry && namedIn(entry) ? uiLanguage : "en");
    english.setAttribute("dir", "ltr");
    open.appendChild(english);
    // The verses: the whole of the blurb on this week's card, which has the room; the
    // range alone on the rest.
    var span = el("span", "portion-span", (thisWeek && blurbIn(entry)) || one.summary || "");
    span.setAttribute("lang", thisWeek && entry && blurbIn(entry) ? uiLanguage : "en");
    open.appendChild(span);
    item.appendChild(open);
    return item;
  }

  function drawPortions() {
    var section = document.getElementById("portions");
    var list = document.getElementById("portion-cards");
    if (!section || !list) return;
    var schedule = scheduleKept();
    var ordered = portionOrder(portionShelf, schedule);
    list.textContent = "";
    if (!ordered.length) {
      section.hidden = true;
      return;
    }
    var week = (portionShelf && portionShelf.week) || {};
    var current = week[schedule] || week.diaspora || week.israel || "";
    ordered.forEach(function (one, place) {
      list.appendChild(portionCard(one, place === 0 && one.slug === current, portionShelf.shabbat));
    });
    // Both calendars, only in a week they part company.
    var pick = document.getElementById("portion-schedule");
    if (pick) {
      pick.textContent = "";
      var apart = !!(week.diaspora && week.israel && week.diaspora !== week.israel);
      pick.hidden = !apart;
      if (apart) {
        [
          ["diaspora", t("library.portions.diaspora", "Diaspora")],
          ["israel", t("library.portions.israel", "Israel")],
        ].forEach(function (pair) {
          var press = el("button", "segment", pair[1]);
          press.type = "button";
          press.setAttribute("aria-pressed", schedule === pair[0] ? "true" : "false");
          press.addEventListener("click", function () {
            keepSchedule(pair[0]);
            drawPortions();
          });
          pick.appendChild(press);
        });
      }
    }
  }

  /* The shelf is Hebrew's: under another language it is not this page's. And it stands
     among the shelves, not over a See all list, which is one list. */
  function placePortions(code, shelving) {
    var section = document.getElementById("portions");
    if (!section) return;
    var any = !!(portionShelf && portionShelf.portions && portionShelf.portions.length);
    section.hidden = !any || code !== lang.HOME || shelving === false;
  }

  /* The shelf and what is building, asked for together (design.md §12, 2026-09-17).
     `/jobs` is what the bell polls; the library reads the same answer, so the two can
     never disagree about what is happening. A build is no longer a row here (2026-09-25:
     it is on Your targums), but a catalogue text being built somewhere else still turns
     into a built row here when it finishes, which is what `follow()` watches for. */
  Promise.all([
    ask("/readers"),
    ask("/jobs").catch(function () { return {}; }),
    ask("/portions").catch(function () { return {}; }),
  ]).then(function (both) {
    var data = both[0] || {};
    buildingNow = (both[1] && both[1].jobs) || [];
    portionShelf = both[2] && both[2].portions ? both[2] : null;
    portionsAt = {};
    ((portionShelf && portionShelf.portions) || []).forEach(function (one) {
      if (one.id && one.href) portionsAt[one.id] = one.href;
    });
    drawPortions();
    var readers = data.readers || [];
    var shared = data.shared || [];
    // What is on the shared shelf, for which of targum's playlists can be opened here.
    sharedNow = shared;
    catalogueKnown = data.catalogue || {};
    /* Whether this reader has marked anything at all, which decides what "at my level"
       is a measure of. With words marked it is the share of a text this reader knows;
       with none, every row would answer 0% and the page would open on an empty list —
       so the text's own difficulty stands in instead (see `fitOf`). */
    anyKnown = Object.keys(catalogueKnown).some(function (id) {
      var one = catalogueKnown[id];
      return one && typeof one.known === "number" && one.known > 0;
    });
    if (!anyKnown) {
      anyKnown = (readers || []).concat(shared || []).some(function (reader) {
        return typeof reader.known === "number" && reader.known > 0;
      });
    }
    // The rung they named on arrival, while it is all the page has to go on. `charts.seed`
    // answers "" once their marked words reach a rung of their own.
    seeded = "";
    if (!anyKnown && window.TargumCharts) {
      var ledger = window.TargumCharts.collect(window.TargumCharts.meaningLanguage(lang.HOME))[lang.HOME];
      seeded = window.TargumCharts.seed(ledger && ledger.words, lang.HOME);
    }
    canDraw = !!data.covers;
    signedIn = !!data.signedIn;
    var opened = stored("targum:opened");
    readers.concat(shared).forEach(function (reader) {
      reader.opened = opened[reader.document] || 0;
    });
    if (window.TargumScenes) {
      nextRow = window.TargumScenes.next(shared, finishedDocs);
      anyFinished = shared.some(function (reader) {
        return window.TargumScenes.numberOf(reader.entry) > 0 && window.TargumScenes.finished(reader, finishedDocs);
      });
    }

    var everything = rows(readers, shared);
    var host = document.getElementById("catalogue");
    var cards = document.getElementById("cards");
    var picked = document.getElementById("picked");
    var empty = document.getElementById("picked-empty");
    var tally = document.getElementById("tally");
    var more = document.getElementById("see-more");
    var find = document.getElementById("find");
    var chosen;
    // Every language this reader has, for the Language menu; set below, before the first draw.
    var codes = [];

    /* What an empty page says. An empty list and an empty filter are different things to
       be told. A language with no catalogue yet says so, and points at what the reader
       has in it already, if anything (2026-09-14): "Nothing here yet" under Italian hid
       the two Italian texts the reader had brought. They are on Your targums since
       2026-09-25, so that is where it points. */
    function emptySaid(here) {
      var uploaded = yoursAlone.filter(function (reader) {
        return inLanguage(reader, chosen);
      }).length;
      return here
        ? t("library.empty.no-match", "Nothing here matches that. Try another search or fewer filters.")
        : uploaded
          ? tn(
              "library.empty.language-yours",
              uploaded,
              "No {language} texts in the library yet. You have {n} in Your targums.",
              "No {language} texts in the library yet. You have {n} in Your targums.",
              { language: names[chosen] || chosen }
            )
          : t("library.empty.language", "No {language} texts in the library yet.", {
              language: names[chosen] || chosen,
            });
    }

    /* See all: the one list, under the band its shelf is, a page at a time. */
    function seeBand(band) {
      view.fit = band || "";
      view.find = "";
      find.value = "";
      view.where = "library";
      seeAll = true;
      page = PAGE;
      mark(SEE + (band ? "/" + band : ""));
      redraw();
      if (window.scrollTo) window.scrollTo(0, 0);
    }

    /* And back to the shelves, which is the Library. */
    function toShelves() {
      seeAll = false;
      view.find = "";
      find.value = "";
      view.where = "library";
      view.door = "";
      mark("");
      redraw();
    }

    /* The kind doors (board Library, "Browse by kind"): the Tanakh's map, then News,
       Video, Books, the Weekly portion, the Mishnah and the rest of the Jewish texts. Each
       is an address the page already answers — `#see/kind/<kind>`, `#bm/<door>` — so a
       door is a link, and only a door with something behind it in this language is
       drawn. */
    function drawDoors(doorsHost, code) {
      if (!doorsHost) return;
      doorsHost.textContent = "";
      var here = everything.filter(function (row) {
        return inLanguage(row, code) && row.entry;
      });
      function holds(test) {
        return here.some(test);
      }
      function behind(door) {
        return everything.some(function (row) {
          return doorOf(row) === door;
        });
      }
      var hebrew = code === lang.HOME;
      var offered = [];
      if (hebrew) offered.push(["tanakh", keyed("/tanakh-map"), t("library.door.tanakh", "Tanakh"), "תנ״ך"]);
      [
        ["article", t("library.door.news", "News")],
        ["talk", t("library.door.video", "Video")],
        ["books", t("library.door.books", "Books")],
      ].forEach(function (pair) {
        var kinds = KIND_SETS[pair[0]] || [pair[0]];
        var found = holds(function (row) {
          return kinds.indexOf(row.kind) >= 0;
        });
        if (found) offered.push([pair[0], "#" + SEE + "/kind/" + pair[0], pair[1], ""]);
      });
      if (hebrew && behind("portions")) {
        offered.push(["portions", "#" + TREE_HASH + "/portions", t("library.door.portion", "Weekly portion"), ""]);
      }
      if (hebrew && behind("mishnah")) {
        offered.push(["mishnah", "#" + TREE_HASH + "/mishnah", t("library.door.mishnah", "Mishnah"), ""]);
      }
      if (hebrew && everything.some(function (row) { return !!doorOf(row); })) {
        offered.push(["midrash", "#" + TREE_HASH, MIDRASH[1], ""]);
      }
      doorsHost.hidden = !offered.length;
      if (!offered.length) return;
      var label = el("span", "lib-doors-label", t("library.doors-label", "Browse by kind:"));
      doorsHost.appendChild(label);
      var list = el("div", "lib-doors-row");
      offered.forEach(function (one) {
        var door = el("a", "lib-door");
        door.href = one[1];
        door.setAttribute("data-door", one[0]);
        if (one[3]) {
          var name = el("bdi", "lib-door-hebrew", one[3]);
          name.setAttribute("lang", "he");
          door.appendChild(name);
        }
        door.appendChild(el("span", "lib-door-name", one[2]));
        // A door within the page goes there now, and the Back button comes back.
        if (one[1].charAt(0) === "#") {
          door.addEventListener("click", function (event) {
            if (event && event.preventDefault) event.preventDefault();
            mark(one[1].slice(1));
            moved();
            if (window.scrollTo) window.scrollTo(0, 0);
          });
        }
        list.appendChild(door);
      });
      doorsHost.appendChild(list);
    }

    /* See all's head: "All Hebrew texts 720", or the band it was opened from with what
       the band means ("A stretch [75–90%] known", board SubFromLibrary). */
    var BAND_RANGES = {
      now: t("library.band.now-range", "90% known and up"),
      stretch: t("library.band.stretch-range", "75–90% known"),
      hard: t("library.band.hard-range", "under 75% known"),
    };
    function seeTitle(titleHost, count) {
      if (!titleHost) return;
      titleHost.textContent = "";
      var band = bandNamed(fitWanted());
      var kind = view.kind ? named(KINDS, view.kind) || (KIND_SETS[view.kind] ? t("library.kind.books", "Books") : "") : "";
      var name = band
        ? band[1]
        : kind
          ? t("library.see.title-kind", "{kind} in {language}", { kind: kind, language: names[chosen] || chosen })
          : t("library.see.title-all", "All {language} texts", { language: names[chosen] || chosen });
      titleHost.appendChild(el("span", "see-title-name", name));
      titleHost.appendChild(
        el("span", "see-title-count", band && anyKnown ? BAND_RANGES[band[0]] + " · " + count : String(count))
      );
    }

    /* Where a row the address names falls in the list, so the page reaches it. */
    function placeOf(showing, wanted) {
      for (var n = 0; n < showing.length; n++) {
        if (showing[n].id === wanted) return n;
        if (showing[n].rows) {
          for (var m = 0; m < showing[n].rows.length; m++) if (showing[n].rows[m].id === wanted) return n;
        }
      }
      return -1;
    }

    function redraw() {
      remember("targum:library", views);
      closeMenu(false);
      /* The Jewish texts are Hebrew's, and are drawn only where the catalogue says which
         door anything stands behind: a door onto an empty tree is a dead end. Under
         another language, or a file with no doors, a view left in it goes back to the
         Library. */
      var treed =
        chosen === lang.HOME &&
        everything.some(function (row) {
          return !!doorOf(row);
        });
      if (view.where === "midrash" && !treed) view.where = "library";
      var tree = view.where === "midrash";
      if (!tree) view.door = "";
      // At the doors themselves there is no list yet.
      var atDoors = tree && !view.door && !view.find;
      crumbs(document.getElementById("crumbs"), tree, redraw);
      address(tree);

      /* The shelves, where the page lands (design.md §12, 2026-10-09). See all is the
         list under a band; the Jewish texts are their doors, then a door's list. */
      var shelving = !tree && !seeAll;
      var seeing = !tree && seeAll;
      if (document.body && document.body.classList) {
        document.body.classList.toggle("is-seeing", seeing);
      }
      var back = document.getElementById("see-back");
      if (back) back.hidden = shelving;
      var titleHost = document.getElementById("see-title");
      if (titleHost) titleHost.hidden = !seeing;
      var menus = document.getElementById("see-menus");
      if (menus) {
        menus.hidden = !seeing;
        if (seeing) drawMenus(menus, everything, chosen, codes, redraw, show);
        else menus.textContent = "";
      }
      var doorsHost = document.getElementById("lib-doors");
      if (doorsHost) {
        if (shelving) drawDoors(doorsHost, chosen);
        else doorsHost.hidden = true;
      }
      var note = document.getElementById("picked-note");
      if (note) note.hidden = !atDoors;
      placePortions(chosen, shelving);
      var shelvesHost = document.getElementById("shelves");
      if (shelvesHost) shelvesHost.hidden = !shelving;
      cards.hidden = !atDoors;
      host.textContent = "";
      cards.textContent = "";
      more.hidden = true;
      var head = document.getElementById("rows-head");

      if (shelving) {
        var unbanded = {};
        for (var field in view) unbanded[field] = view[field];
        unbanded.fit = "";
        unbanded.find = "";
        unbanded.kind = "";
        var pool = everything.filter(function (row) {
          return matches(row, chosen, unbanded);
        });
        var standing = shelvesHost ? drawShelves(shelvesHost, pool, sharedNow, chosen, seeBand) : 0;
        // Nothing to shelve is said in the list's card, which is otherwise down.
        picked.hidden = standing > 0;
        empty.hidden = standing > 0;
        if (head) head.hidden = true;
        tally.textContent = "";
        if (!standing) {
          empty.textContent = emptySaid(
            everything.filter(function (row) {
              return inLanguage(row, chosen) && row.entry;
            }).length
          );
        }
        return;
      }

      var surviving = everything.filter(function (row) {
        return matches(row, chosen);
      });
      if (atDoors) {
        picked.hidden = true;
        doors(cards, surviving, redraw);
        placeNote(t("library.note.doors", "Pick a section. Every text here is also under All texts."));
        return;
      }
      picked.hidden = false;
      var top = folded(surviving);
      /* A list that is one collection is that collection. */
      // And an ordered one — the portions, the Torah — keeps its own order.
      var showing;
      inItsOrder = top.length === 1 && !!top[0].group && !!top[0].group.ordered;
      if (top.length === 1 && top[0].group) showing = within(top[0].group, top[0].rows);
      else showing = sorted(top);
      if (seeing) seeTitle(titleHost, surviving.length);

      /* A page at a time (board SeeAllDesk: "13 of 720 · Show more"): fifty rows, and
         Show more for the next fifty. A row the address names is always on the page. */
      var wanted = decodeURIComponent((location.hash || "").slice(1)).replace(/^build:/, "");
      var at = wanted ? placeOf(showing, wanted) : -1;
      if (at >= page) page = Math.ceil((at + 1) / PAGE) * PAGE;
      var shown = showing.slice(0, page);
      shown.forEach(function (row) {
        host.appendChild(draw(row));
        if (row.group && isOpen(row.group)) {
          within(row.group, row.rows).forEach(function (member) {
            host.appendChild(draw(member, true));
          });
        }
      });
      heading(redraw);
      var subs = host.children.some
        ? host.children.some(function (item) {
            return item.querySelector && !!item.querySelector(".row-sub");
          })
        : !!host.querySelector(".row-sub");
      if (picked.classList) picked.classList.toggle("has-subs", subs);
      if (subs && head) head.appendChild(el("span", "see-head-sub", t("library.column.subscribe", "Subscribe")));
      if (head) head.hidden = !showing.length;
      pointAt();
      empty.hidden = showing.length > 0;
      if (!showing.length) {
        var here = everything.filter(function (row) {
          // Behind a door, counted against that door.
          if (tree) return doorOf(row) && (!view.door || view.find || doorOf(row) === view.door);
          return inLanguage(row, chosen) && row.entry;
        });
        empty.textContent = emptySaid(here.length);
      }
      more.hidden = shown.length >= showing.length;
      // Texts, not rows: a collection is one row over many, and "13 of 720" counts texts.
      var textsShown = shown.reduce(function (total, row) {
        return total + (row.rows ? row.rows.length : 1);
      }, 0);
      tally.textContent = !showing.length
        ? ""
        : shown.length < showing.length
          ? t("library.tally.page", "{shown} of {total} · {order}", {
              shown: textsShown,
              total: surviving.length,
              order: orderSaid(),
            })
          : tn("library.tally.all", surviving.length, "{n} text", "{n} texts") + " · " + orderSaid();
    }

    more.addEventListener("click", function () {
      page += PAGE;
      redraw();
    });

    /* Learn suggests something to read and links here with the id in the hash. Finding it
       is the reader's problem otherwise: this catalogue is forty rows and the thing they
       were sent for could be anywhere in it. Marked and scrolled to, never pressed —
       what pressing an unbuilt row does is start spending, and nothing arrives at a page
       with permission to do that. */
    /* Two flags, not one. `lifted` used to do both jobs — "I have opened a collection"
       and "I have lifted the filters" — and opening a collection therefore spent the one
       chance to lift them: a reader sent to a text inside a shut shelf that a filter also
       hid had the shelf opened, the second pass find nothing, and `if (lifted) return`
       give up before it ever looked at the filters. Found on the running page following
       `/open/ruth`, which opens Ketuvim and then needs the band lifted as well
       (targum-internal#313). Each does its own job once. */
    var unfolded_once = false;
    var lifted = false;
    function pointAt() {
      var wanted = decodeURIComponent((location.hash || "").slice(1));
      if (!wanted || addressed() !== null) return;
      /* `#build:<id>` is what `/open/<id>` sends when this reader has not built the text
         yet (targum-internal#313). It means the same as a bare id — find that row and
         show it — and adds one thing: the row's own offer is put up, so the reader lands
         one press from reading rather than on a marked line with nothing to press.

         The press itself is still theirs. The offer states the price and waits; nothing
         here starts a build, because an address is not consent. */
      var offering = wanted.indexOf("build:") === 0;
      if (offering) wanted = wanted.slice("build:".length);
      /* Inside a collection that is shut. Opening it is a smaller thing to do to the
         reader's page than lifting every filter they set, so it is tried first — and
         only once, for the reason `lifted` exists. */
      var holding = GROUP_OF[wanted];
      if (holding && !unfolded[holding.id] && !unfolded_once) {
        unfolded_once = true;
        unfolded[holding.id] = true;
        remember("targum:opened-groups", unfolded);
        redraw();
        return;
      }
      // Whichever host is drawn. The rows live in the table or in the grid, never both,
      // and looking only in the table meant a reader sent to a text while browsing was
      // silently sent nowhere.
      var mark = '[data-row="' + wanted.replace(/"/g, "") + '"]';
      var row = host.querySelector(mark) || (cards && cards.querySelector(mark));
      if (row) {
        row.classList.add("pointed");
        if (row.scrollIntoView) row.scrollIntoView({ block: "center" });
        /* Sent here to build it: put the press under their hand. Focused, not pressed —
           and not quoted either. The quote costs nothing today, but a page that asks the
           server for a price because of what was in an address is a page one source type
           away from spending on a link somebody followed. The reader arrives on the row,
           on the button, one key or one tap from reading. */
        if (offering) {
          var press = row.querySelector("[data-build]");
          if (press && press.focus) press.focus({ preventScroll: true });
        }
        return;
      }
      /* Not drawn. The filters, the tab and the language are all remembered between
         visits, so somebody sent here by Learn could arrive at a list that hides the one
         text they came for, land at the top of it, and have nothing to tell them why.
         Being sent is a stronger claim than a filter set on some earlier visit: lift them
         and draw again. Once — `lifted` is what stops an id that is genuinely not in this
         catalogue from doing it on every redraw. */
      if (lifted) return;
      var target = null;
      for (var i = 0; i < everything.length; i++) {
        if (everything[i].id === wanted) {
          target = everything[i];
          break;
        }
      }
      if (!target) return;
      lifted = true;
      var code = base(target.language);
      // The filters lifted are the ones on the shelf the text is on.
      if (code && code !== chosen) view = viewFor(code);
      view.find = view.kind = view.register = view.length = view.level = view.subject = "";
      // And how far the list was narrowed to fit them. Being sent to a text is a
      // stronger claim than any setting made earlier, and the one text somebody was sent
      // for is exactly the one a "what you can read now" list is entitled to hide.
      view.fit = "";
      view.where = "library";
      find.value = "";
      // show() redraws, and redraw() comes back through here with the row in the list.
      if (code && code !== chosen) return show(code);
      redraw();
    }

    /* While anything is building, ask again (design.md §12, 2026-09-17).
     *
     * Only while: a shelf with nothing on the way polls nothing, the same rule the bell
     * follows, and for the same reason — a page left open overnight should not be a page
     * asking a question every three seconds until morning. When a build finishes,
     * `/readers` has the text it became, so both are asked for again and a catalogue
     * row it came from is marked as built in the same draw.
     */
    var following = null;
    function follow() {
      var going = buildingNow.some(function (job) {
        return job.stage !== "done" && !job.error;
      });
      if (!going) {
        if (following) clearInterval(following);
        following = null;
        return;
      }
      if (following) return;
      following = setInterval(function () {
        var nothing = function () {
          return {};
        };
        Promise.all([ask("/jobs").catch(nothing), ask("/readers").catch(nothing)]).then(
          function (both) {
            buildingNow = (both[0] && both[0].jobs) || [];
            if (both[1] && both[1].readers) {
              everything = rows(both[1].readers, both[1].shared || []);
              sharedNow = both[1].shared || [];
            }
            redraw();
            follow();
          }
        );
      }, 3000);
    }
    follow();

    /* The box is the one search, opened already held to the Library (design.md §12,
       "One search, everywhere", 2026-10-09). It narrowed this list in place until then,
       by title alone and in one spelling; the search folds spelling, reads a
       transliteration and finds words too. What was typed before it opened goes with it. */
    find.value = "";
    function search(event) {
      var palette = window.TargumPalette;
      if (!palette || !palette.show) return;
      if (event && event.preventDefault) event.preventDefault();
      var typed = find.value;
      find.value = "";
      if (find.blur) find.blur();
      palette.show(true, { scope: "library", q: typed });
    }
    find.addEventListener("focus", search);
    find.addEventListener("click", search);
    find.addEventListener("input", search);

    /* One handler over both shapes. A card and a row carry the same three things that
       can be pressed — draw a cover, fold a collection, start a build — so the listener
       is written once and hung on each host, rather than the cards growing a second
       copy that would drift from this one. */
    function pressed(event) {
      var drawing = event.target.closest ? event.target.closest("[data-draw]") : null;
      if (drawing) return drawCovers(drawing, drawing.getAttribute("data-draw"));
      var folding = event.target.closest ? event.target.closest("[data-group]") : null;
      if (folding) {
        var which = folding.getAttribute("data-group");
        unfolded[which] = !unfolded[which];
        remember("targum:opened-groups", unfolded);
        redraw();
        return;
      }
      var button = event.target.closest ? event.target.closest("[data-build]") : null;
      if (!button) return;
      for (var i = 0; i < everything.length; i++) {
        if (everything[i].id === button.getAttribute("data-build") && everything[i].entry) {
          build(button, everything[i].entry);
          return;
        }
      }
    }

    host.addEventListener("click", pressed);
    if (cards) cards.addEventListener("click", pressed);
    /* The shelves press the same way a card does, and one of targum's playlists opens. */
    var shelvesHost = document.getElementById("shelves");
    if (shelvesHost) {
      shelvesHost.addEventListener("click", function (event) {
        var set = event.target.closest ? event.target.closest("button[data-set]") : null;
        if (set) return openSet(set, set.getAttribute("data-set"));
        pressed(event);
      });
    }
    var backLink = document.getElementById("see-back-link");
    if (backLink) {
      backLink.addEventListener("click", function (event) {
        if (event && event.preventDefault) event.preventDefault();
        toShelves();
      });
    }

    // Hebrew is always on offer, whether or not anything is on the shelf in it.
    //
    // The languages after it are the reader's own: what they have built, and what they
    // have kept words in. The catalogue deliberately does not add to this list. It
    // holds one Russian novel, and letting it in put Russian in front of every visitor
    // who had never touched it — which is the opposite of what this switcher is for.
    var all = [lang.HOME];
    readers.concat(kept()).forEach(function (thing) {
      var codes = thing.languages && thing.languages.length ? thing.languages : [thing.language];
      codes.forEach(function (one) {
        var code = base(one);
        if (code && all.indexOf(code) < 0) all.push(code);
      });
    });
    codes = lang.order(all, names);
    chosen = lang.current(codes);
    view = viewFor(chosen);
    var betaNote = document.getElementById("beta-note");

    function show(code) {
      chosen = code;
      view = viewFor(code);
      page = PAGE;
      /* Where the page stands: the shelves where the address names nothing, the list under
         `#see` and wherever a text was named, the tree under `#bm`. Landing on the
         shelves leaves a search behind, and the Beit Midrash too: the Library opens on
         its shelves every time, and each of the others has its address. */
      var see = seeAddressed();
      var named = decodeURIComponent((location.hash || "").slice(1));
      var kindNamed = kindAddressed();
      if (see !== null) {
        seeAll = true;
        if (see) view.fit = see;
        if (kindNamed) {
          view.fit = "";
          view.kind = kindNamed;
          view.where = "library";
        }
      } else if (!named) {
        seeAll = false;
        view.find = "";
        view.where = "library";
      } else if (addressed() === null) {
        seeAll = true;
      }
      find.value = view.find || "";
      inHebrew = code === lang.HOME;
      // An address into the tree opens the tree, where the shelf showing is Hebrew's.
      var into = addressed();
      if (into !== null && inHebrew) {
        view.where = "midrash";
        view.door = into;
      }
      lang.set(code);
      lang.switcher(document.getElementById("langs"), codes, names, code, show);
      if (betaNote) {
        betaNote.hidden = !lang.beta(code);
        if (lang.beta(code)) betaNote.textContent = lang.betaNote(code, names);
      }
      redraw();
    }

    // A link followed, or the address edited, while the page is open.
    function moved() {
      page = PAGE;
      var see = seeAddressed();
      if (see !== null) {
        seeAll = true;
        if (see) view.fit = see;
        var kindNamed = kindAddressed();
        if (kindNamed) {
          view.fit = "";
          view.kind = kindNamed;
        }
        view.where = "library";
        return redraw();
      }
      if (!location.hash || location.hash === "#") {
        if (!seeAll && view.where === "library") return;
        seeAll = false;
        view.find = "";
        find.value = "";
        view.where = "library";
        return redraw();
      }
      var into = addressed();
      if (into === null || chosen !== lang.HOME) return;
      view.where = "midrash";
      view.door = into;
      redraw();
    }
    window.addEventListener("hashchange", moved);
    // A step made with `pushState` comes back as a pop, without a hash change.
    window.addEventListener("popstate", moved);

    show(chosen);

    // The shelf is ordered by when each text was last opened, and that is one of the
    // things the account keeps. Signing in on a second machine should therefore reorder
    // the list to match where the reader actually is in their reading.
    //
    // And which languages the switcher offers is the account's answer too, which it
    // gave after the switcher was drawn: asked again here whether or not any words came
    // with it, or a reader who ticked Yiddish on another machine saw Hebrew alone here
    // until a reload.
    if (window.TargumSync) {
      window.TargumSync.onChange(function (changed) {
        var before = codes.join();
        codes = lang.order(all, names);
        var switched = codes.join() !== before;
        if (switched && codes.indexOf(chosen) < 0) chosen = lang.current(codes);
        if (changed) {
          var seen = stored("targum:opened");
          everything.forEach(function (row) {
            if (row.built) row.opened = seen[row.built.document] || 0;
          });
        }
        if (switched) show(chosen);
        else if (changed) redraw();
      });
      window.TargumSync.start();
    }
  })
    // Nothing to list, because nothing could be asked. The catalogue is still drawn from
    // what the page was built with; what fails here is only which of it you already have.
    .catch(function () {});
})();
