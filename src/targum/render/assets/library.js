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
     is a row you have to read every time. "Bible narrative" rather than "Narrative":
     beside Novels and Stories the bare word said nothing, and what it names is the story
     books of the Bible. */
  var KINDS = [
    ["dialogue", t("library.kind.dialogue", "Scenes")],
    ["story", t("library.kind.story", "Stories")],
    ["article", t("library.kind.article", "News")],
    ["novel", t("library.kind.novel", "Novels")],
    ["essay", t("library.kind.essay", "Essays")],
    ["talk", t("library.kind.talk", "Talks")],
    ["prose", t("library.kind.prose", "Bible narrative")],
    ["poetry", t("library.kind.poetry", "Poetry")],
    ["document", t("library.kind.document", "Documents")],
    ["play", t("library.kind.play", "Plays")],
    ["liturgy", t("library.kind.liturgy", "Prayer")],
  ];

  /* What a text is *about*, called what a person calls it when they say what they feel
     like reading. The catalogue's `Tag` vocabulary runs well past what is filed — the
     arrival draws its doors before the texts are tagged into them, on purpose — so this
     names every value and the page draws only the ones with rows behind them
     (design.md §12, 2026-09-17). An entry missing here is a subject nobody has named yet
     and is simply not offered.

     "Hebrew itself" rather than "Language": on a page about learning Hebrew, a chip
     saying "Language" reads as the language switcher. "News" matches what the kinds
     already call an article. */
  var SUBJECTS = [
    ["tanakh", t("library.subject.tanakh", "Tanakh")],
    ["judaica", t("library.subject.judaica", "Judaica")],
    ["journalism", t("library.subject.journalism", "News")],
    ["sport", t("library.subject.sport", "Sport")],
    ["science", t("library.subject.science", "Science")],
    ["history", t("library.subject.history", "History")],
    ["philosophy", t("library.subject.philosophy", "Philosophy")],
    ["technology", t("library.subject.technology", "Technology")],
    ["language", t("library.subject.language", "Hebrew itself")],
    ["art", t("library.subject.art", "Art")],
    ["business", t("library.subject.business", "Business")],
    ["health", t("library.subject.health", "Health")],
    ["archaeology", t("library.subject.archaeology", "Archaeology")],
    ["food", t("library.subject.food", "Food")],
    ["travel", t("library.subject.travel", "Travel")],
    ["music", t("library.subject.music", "Music")],
    ["politics", t("library.subject.politics", "Politics")],
  ];

  /* How much of a text this reader already knows, in three bands. The measure is the
     share of *this text's* words they have marked as known — a fact about the pair of
     them — and not `difficulty`, which is a fact about the text alone. A reader asking
     "can I read this" is asking the first (design.md §12, 2026-09-17).

     The cutoffs are the reading-comprehension ones: around 95% of running words known is
     comfortable reading, and below about 80% a text stops being learnable by reading and
     becomes a decoding exercise. Held a little lower than the literature's, because a
     marked word here is a word somebody pressed rather than the whole of what they know. */
  var COMFORTABLE = 85;
  var WORKABLE = 65;

  /* The one setting that is on before a reader touches anything. "Now" is the default and
     the page says so in words above the list; the other two widen it. */
  var FITS = [
    ["now", t("library.fit.now", "you can read now")],
    ["stretch", t("library.fit.stretch", "a step up from where you are")],
    ["", t("library.fit.all", "everything")],
  ];

  /* Which Hebrew a text is in, oldest first. Chronological rather than alphabetical, and
     never sorted: the five of them are a ramp a learner climbs, and putting Modern above
     Rabbinic because M precedes R would throw that away. */
  var REGISTERS = [
    ["biblical", t("library.register.biblical", "Biblical")],
    ["rabbinic", t("library.register.rabbinic", "Rabbinic")],
    ["medieval", t("library.register.medieval", "Medieval")],
    ["revival", t("library.register.revival", "Revival")],
    ["modern", t("library.register.modern", "Modern")],
  ];

  /* Where each of them sits in that ramp, for sorting the column. Sorting on the label
     would run Biblical, Medieval, Modern, Rabbinic, Revival — five words in an order
     that means nothing about Hebrew. */
  var REGISTER_ORDER = {};
  REGISTERS.forEach(function (pair, index) {
    REGISTER_ORDER[pair[0]] = index;
  });

  //: Only one direction is worth offering. "Without audio" is not a thing anybody looks
  //: for — the question is always whether there is something to listen to. The same
  //: holds for video: a lecture with its slides and a podcast were one row saying
  //: "audio", and the reader who imported the lecture could not find it again.
  var SPOKEN = [
    ["", t("library.filter.any", "Any")],
    ["yes", t("library.spoken.audio", "With audio")],
    ["video", t("library.spoken.video", "With video")],
  ];

  var LENGTHS = [
    ["", t("library.filter.any", "Any")],
    ["short", t("library.length.short", "Under 20 min")],
    ["hour", t("library.length.hour", "20 min – 2 hr")],
    ["long", t("library.length.long", "Over 2 hr")],
  ];

  // The share of running words a reader would have to look up, in three steps. The
  // numbers behind them are measured off each text: see scripts/measure_difficulty.py.
  // Said in words as well as tiers, because the cutoffs were never stated anywhere:
  // "Beginners cannot understand library listings", said the first alpha reader.
  var LEVELS = [
    ["", t("library.filter.any", "Any")],
    ["easy", t("library.level.easy", "Easier — up to 1 word in 5 hard")],
    ["mid", t("library.level.mid", "Middling — about 1 in 4")],
    ["hard", t("library.level.hard", "Harder — more than 1 in 4")],
  ];

  // The same number as a sentence: 17% is "about 1 word in 6 is hard". "Hard" because
  // it is the reader's own word — the band the count starts at is the one every tapped
  // word calls "hard", and the highlight menu offers "hard and up". Not "new to you":
  // the share is a fact about the text — how much of its vocabulary is rare — and a
  // reader who knows no words looks up all twenty-two of a text that says 0%.
  function inWords(share) {
    if (!share) return "";
    return t("library.hard-share", "about 1 word in {n} is hard", { n: Math.max(2, Math.round(100 / share)) });
  }

  /* One line under the controls that says what the active one means — for the reader
     who cannot yet read a title on the page, the most important sentence on it. Stated,
     never justified. At most two clauses; the first is the one that changes what the
     list is. "—" is explained only while one is on screen. */
  var NOTES = {
    base: t("library.note.base", "Tap a text to read it."),
    kind: {
      dialogue: t("library.note.dialogue", "Scenes — numbered conversations with audio. Start at 1."),
      prose: t("library.note.prose", "Bible narrative — the Bible's story books."),
      talk: t("library.note.talk", "Talks — lectures and explainers, with the video beside them."),
      article: t("library.note.article", "News — the Israeli press, in the week it was written."),
      play: t("library.note.play", "Plays — a speaker, then a line."),
      liturgy: t("library.note.liturgy", "Prayer — the siddur and the service, the same words every day."),
    },
    register: {
      biblical: t("library.note.biblical", "Biblical — the Hebrew of the Bible."),
      rabbinic: t("library.note.rabbinic", "Rabbinic — the Hebrew of the Mishnah, the codes and the prayer book."),
      medieval: t("library.note.medieval", "Medieval — philosophy, in the Hebrew built to carry Arabic argument."),
      revival: t("library.note.revival", "Revival — literary Hebrew from 1850 to 1930, before the language settled."),
      modern: t("library.note.modern", "Modern — Hebrew as it is written today."),
    },
    spoken: t("library.note.spoken", "With audio — a recording, line by line."),
    video: t("library.note.video", "With video — a recording that kept its pictures."),
    sort: {
      difficulty: t("library.note.difficulty", "Hard words — the share of a text's words that are rare in everyday use."),
      known: t("library.note.known", "Words you know — the share of a text's words you have marked as known."),
    },
    unmeasured: t("library.note.unmeasured", "— means we haven't measured it yet."),
  };

  /* Whether the shelf on show is Hebrew's (2026-09-14). "Which Hebrew" — the register, its
     chips, its column and its note — is a question about Hebrew texts, and under another
     language it is not asked: a register picked while reading Hebrew went on filtering a
     Russian shelf down to nothing, under a note about the Hebrew of the Bible. The choice
     is kept for when the reader comes back to Hebrew. */
  var inHebrew = true;

  function noteFor(showing) {
    var clauses = [];
    if (view.kind && NOTES.kind[view.kind]) clauses.push(NOTES.kind[view.kind]);
    if (inHebrew && view.register && NOTES.register[view.register]) {
      clauses.push(NOTES.register[view.register]);
    }
    if (view.spoken === "yes") clauses.push(NOTES.spoken);
    if (view.spoken === "video") clauses.push(NOTES.video);
    if (NOTES.sort[view.sort]) clauses.push(NOTES.sort[view.sort]);
    if (!clauses.length) clauses.push(NOTES.base);
    clauses = clauses.slice(0, 2);
    var dashed = showing.some(function (row) {
      return !measured(row);
    });
    if (dashed) clauses[Math.min(1, clauses.length)] = NOTES.unmeasured;
    return clauses.join(" · ");
  }

  /* Where the line is drawn. Under the controls, as `#picked-note`, every time but one:
     on the first visit of an account that knows no words, when the page has opened on
     the Scenes for them, it goes under the heading and above every control, because
     "Start at 1" has to be read before thirteen chips they do not yet understand. */
  var leading = false;
  function placeNote(text) {
    var note = document.getElementById("picked-note");
    var top = document.getElementById("picked-lead");
    var lead = leading && view.kind === "dialogue" && !!top;
    if (top) {
      top.hidden = !lead;
      top.textContent = lead ? text : "";
    }
    note.hidden = lead;
    note.textContent = lead ? "" : text;
  }

  /* The two halves of the page. The catalogue is everybody's; an upload is yours and
     nobody else can reach it. Tabs rather than a filter: they are not two settings of one
     list, they are two lists, and as a select called "Access" the second one was a thing
     nobody found. */
  // "All texts", not "Library": under a page headed Library a first tab of the same name
  // said nothing (2026-09-14). Sentence case, like every other label on the page.
  var WHERE = [
    ["library", t("library.where.library", "All texts")],
    ["mine", t("library.where.mine", "Your uploads")],
  ];

  // Where the gauge starts and stops. Nothing in Hebrew comes in under a tenth or over
  // two fifths, so a bar drawn from zero would be four identical bars.
  var FLOOR = 12;
  var CEILING = 40;

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
     second is drawn as a dash. */
  function measured(row) {
    return row.difficulty > 0 || !!row.entry;
  }

  function level(row) {
    if (!measured(row)) return "";
    var share = row.difficulty || 0;
    if (share <= 20) return "easy";
    return share <= 28 ? "mid" : "hard";
  }

  function lengthOf(minutes) {
    if (minutes < 20) return "short";
    return minutes <= 120 ? "hour" : "long";
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
    if (band === "easy") return "now";
    return band === "mid" ? "stretch" : "hard";
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

  /* Whether a row is filed under one subject. A list, not a value: a match report is
     journalism and sport at once and belongs under both. */
  function holdsSubject(row, tag) {
    return (row.tags || []).indexOf(tag) >= 0;
  }

  /* "Now" means now; "a step up" means now *and* the step. A band that excluded what the
     reader can already read would be a filter nobody wants: asked for something a little
     harder, they still want the whole of what is open to them above it. */
  function fits(row, want) {
    if (!want) return true;
    var where = fitOf(row);
    if (want === "now") return where === "now";
    return where === "now" || where === "stretch";
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
        drawn: !!(built && built.drawn),
        opened: built ? built.opened || 0 : 0,
      });
    });
    readers.forEach(function (reader) {
      if (reader.entry && mine[reader.entry]) return;
      out.push({
        id: reader.name,
        entry: null,
        title: reader.title,
        english: "",
        author: "",
        language: reader.language,
        kind: reader.kind,
        register: reader.register,
        difficulty: reader.difficulty,
        minutes: reader.minutes,
        spoken: !!reader.spoken,
        video: !!reader.video,
        // A reader's own text is filed under no subject: nothing has read it to say what
        // it is about, and `serve.py` sends an empty list rather than a guess.
        tags: reader.tags || [],
        built: reader,
        opened: reader.opened || 0,
      });
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
      english: group.english,
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
    return !!unfolded[group.id];
  }

  /* --- drawing one ----------------------------------------------------------- */

  function gauge(row) {
    var box = el("span", "gauge");
    if (!measured(row)) {
      box.appendChild(el("span", "col count", "—"));
      return box;
    }
    var share = row.difficulty || 0;
    var track = el("span", "track");
    var fill = el("span", "fill");
    var reach = Math.max(6, Math.min(100, ((share - FLOOR) / (CEILING - FLOOR)) * 100));
    fill.style.inlineSize = reach + "%";
    track.appendChild(fill);
    box.appendChild(track);
    box.appendChild(el("span", "col count", share + "%"));
    var said = inWords(share);
    if (said) box.title = said;
    box.setAttribute(
      "aria-label",
      t("library.hard-words-share", "{share}% hard words", { share: share }) + (said ? ": " + said : "")
    );
    return box;
  }

  /* How much of this text the reader already knows, as a share of its dictionary forms.
     A column rather than only a line in the title cell, because the front door sells the
     shelf as sorted by it and a sort wants a heading to press.

     An em dash where nothing is measured. Never 0%: "not measured" and "you know none of
     this" are different claims, and the second one is the one this number must never make
     about a book nobody has counted. */
  function yours(row) {
    var share = knownOf(row);
    if (typeof share !== "number") return el("span", "col count", "—");
    var shown = Math.round(share * 100);
    var box = el("span", "col count", shown + "%");
    box.setAttribute(
      "aria-label",
      t("library.you-know", "you know {share}% of its words", { share: shown })
    );
    return box;
  }

  function named(list, value) {
    for (var i = 0; i < list.length; i++) if (list[i][0] === value) return list[i][1];
    return "";
  }

  // A title's trailing English part, where a Hebrew title has one: the weekly's level.
  function splitLevel(text) {
    var found = /^(.*[\u0590-\u05FF].*?) · ([A-Za-z][^\u0590-\u05FF]*)$/.exec(String(text || ""));
    return found ? { title: found[1], level: found[2] } : { title: text, level: "" };
  }

  /* One text as a card: the shape the page is browsed in (design.md §12, 2026-09-17).
   *
   * The same facts the row carries, laid out to be scanned rather than compared — the
   * cover first, because a picture is what a browsing eye lands on, then the title in its
   * own face, then one line of facts, then how much of it the reader knows. What the card
   * adds over the row is the media mark, which sits on the cover: "without playing with
   * checkboxes or dropdowns I want to see immediately what media is available" is
   * answered by the layout and not by a control.
   *
   * A built text is a link and an unbuilt one is a button, exactly as in the table: what
   * pressing an unbuilt row does is start spending, and a card must not quietly become a
   * cheaper way to do that.
   */
  function card(row) {
    var item = el("li", "card-item");
    item.setAttribute("data-row", row.id);

    var open = el(row.built ? "a" : "button", "card");
    if (row.built) {
      open.href = keyed("/reader/" + encodeURIComponent(row.built.name) + "/reader/index.html");
    } else {
      open.type = "button";
      open.setAttribute("data-build", row.id);
    }

    var cover = el("span", "card-cover");
    cover.setAttribute("aria-hidden", "true");
    cover.appendChild(
      window.TargumCovers.tile(keyed("/thumb/" + encodeURIComponent(row.id)), {
        title: row.title,
        language: row.language,
        drawn: row.entry ? row.drawn : false,
      })
    );
    // One mark, never two: a video can be listened to as well, and a card saying both
    // says less than one saying "video" does. The word is on the label rather than on
    // the page, so the mark stays a mark.
    if (row.video || row.spoken) {
      var mark = el("span", "card-media");
      mark.appendChild(glyph(row.video ? "video" : "audio"));
      mark.setAttribute(
        "aria-label",
        row.video ? t("library.video", "Video") : t("library.audio", "Audio")
      );
      cover.appendChild(mark);
    }
    open.appendChild(cover);

    var what = el("span", "card-what");
    var number = window.TargumScenes ? window.TargumScenes.numberOf(row.id) : 0;
    if (number) {
      var scene = el("span", "card-scene", t("library.scene", "Scene {n}", { n: number }));
      scene.setAttribute("lang", saidIn);
      what.appendChild(scene);
    } else if (isNew(row)) {
      // "I want to see what was recently added right away" — answered by the card
      // rather than by a sort, so it is true of the page whatever order it is in.
      // In the scene's place, because a numbered scene is never new.
      var fresh = el("span", "card-scene card-new", t("library.new", "New"));
      fresh.setAttribute("lang", saidIn);
      what.appendChild(fresh);
    }
    // Its own direction and its own clip, so a long Hebrew title loses its end and never
    // its start — the edge Hebrew begins at.
    var split = splitLevel(row.title);
    var title = el("bdi", "card-title", split.title);
    title.setAttribute("lang", row.language);
    title.setAttribute("dir", "auto");
    what.appendChild(title);
    // Where the beginner's path is, as the row carries it: "Start here" before anything
    // has been read, "Next" after. A card that dropped this would take the one line on
    // the page that says where to begin.
    if (nextRow && row.id === nextRow.entry) {
      var next = el(
        "span",
        "row-next",
        anyFinished ? t("library.next", "Next") : t("library.start-here", "Start here")
      );
      next.setAttribute("role", "status");
      next.setAttribute("lang", saidIn);
      what.appendChild(next);
    }
    if (row.english) {
      var english = el("span", "card-english", row.english);
      english.setAttribute("lang", row.englishLang || "en");
      english.setAttribute("dir", "ltr");
      what.appendChild(english);
    }

    var meta = [named(KINDS, row.kind), said(row.minutes)];
    if (measured(row)) {
      meta.push(t("library.hard-words-share", "{share}% hard words", { share: row.difficulty || 0 }));
    }
    what.appendChild(el("span", "card-meta", meta.filter(Boolean).join(" · ")));

    // The last line is the reader's own: how much of this text they already know. A text
    // nobody has counted says so in words rather than claiming a nought.
    var share = knownOf(row);
    var mine = el("span", "card-known");
    if (typeof share === "number") {
      var shown = Math.round(share * 100);
      var track = el("span", "card-known-track");
      var fill = el("span");
      fill.style.inlineSize = Math.max(2, Math.min(100, shown)) + "%";
      track.appendChild(fill);
      mine.appendChild(track);
      mine.appendChild(
        el("span", "card-known-say", t("library.you-know", "you know {share}% of its words", { share: shown }))
      );
    } else {
      mine.appendChild(el("span", "card-known-say", t("library.known.none", "New to you")));
    }
    what.appendChild(mine);
    // The cell a build narrates itself in, as the table's row has. Inside the pressed
    // element and not beside it: `build()` finds it with `open.querySelector`, so a
    // state cell hung on the list item is a state cell it throws on.
    what.appendChild(el("span", "row-state"));

    open.appendChild(what);
    item.appendChild(open);
    return item;
  }

  /* A collection, as a card among the cards.
   *
   * It is a shelf rather than a text: no cover of its own, and the press on it opens
   * rather than reads. Drawn here rather than reusing the table's row, which was the
   * first attempt and looked exactly like what it was — a row of grid cells with no grid
   * around them, stacked vertically in the middle of a grid of cards.
   *
   * Its facts are its members' added up, the same ones `fold()` computes: how many texts,
   * how long altogether, and whether any of them can be heard. */
  function groupCard(row) {
    var group = row.group;
    var item = el("li", "card-item");
    item.setAttribute("data-row", row.id);

    var open = el("button", "card card-group" + (isOpen(group) ? " open" : ""));
    open.type = "button";
    open.setAttribute("aria-expanded", isOpen(group) ? "true" : "false");
    open.setAttribute("data-group", group.id);

    var caret = el("span", "card-fold");
    caret.setAttribute("aria-hidden", "true");
    open.appendChild(caret);

    var what = el("span", "card-what");
    var title = el("bdi", "card-title", row.title);
    title.setAttribute("lang", row.language);
    title.setAttribute("dir", "auto");
    what.appendChild(title);
    // Where the beginner's path is while the shelf holding it is shut. Once it is open
    // the chip is on the scene itself; closed, a hundred scenes behind one card would
    // otherwise take the only line on the page that says where to start.
    if (nextRow && !isOpen(group) && group.members.indexOf(nextRow.entry) >= 0) {
      var chip = el(
        "span",
        "row-next",
        anyFinished ? t("library.next", "Next") : t("library.start-here", "Start here")
      );
      chip.setAttribute("role", "status");
      chip.setAttribute("lang", saidIn);
      what.appendChild(chip);
    }
    if (row.english) {
      var english = el("span", "card-english", row.english);
      english.setAttribute("lang", "en");
      english.setAttribute("dir", "ltr");
      what.appendChild(english);
    }
    var meta = [
      tn("library.group-texts", row.rows.length, "{n} text", "{n} texts"),
      said(row.minutes),
    ];
    if (row.video) meta.push(t("library.video", "Video"));
    else if (row.spoken) meta.push(t("library.audio", "Audio"));
    what.appendChild(el("span", "card-meta", meta.filter(Boolean).join(" · ")));
    open.appendChild(what);
    item.appendChild(open);
    return item;
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

  function draw(row, member) {
    if (row.group) return drawGroup(row);
    var item = el("li", member ? "member" : null);
    item.setAttribute("data-row", row.id);

    var open = el(row.built ? "a" : "button", "row-open");
    if (row.built) {
      open.href = keyed("/reader/" + encodeURIComponent(row.built.name) + "/reader/index.html");
    } else {
      open.type = "button";
      open.setAttribute("data-build", row.id);
    }

    open.appendChild(
      window.TargumCovers.tile(keyed("/thumb/" + encodeURIComponent(row.id)), {
        title: row.title,
        language: row.language,
      })
    );

    var what = el("span", "what");
    var title = el("span", "row-title");
    title.setAttribute("lang", row.language);
    // A scene says which it is, outside the Hebrew's own direction, before the title.
    var number = window.TargumScenes ? window.TargumScenes.numberOf(row.id) : 0;
    if (number) {
      var scene = el("span", "row-scene", t("library.scene", "Scene {n}", { n: number }));
      scene.setAttribute("lang", saidIn);
      title.appendChild(scene);
    }
    // Its own direction, and its own clip: an ellipsis on the LTR cell around it cut
    // the *start* of a long Hebrew title, which is the edge Hebrew begins at (2026-09-14).
    // A weekly edition's title carries its level in English at its end ("מבט השבוע · …
    // · Easy · 1,000 words"), and one isolate for both put the English inside the
    // Hebrew's direction; the level is drawn beside the title instead.
    var parts = splitLevel(row.title);
    var bdi = el("bdi", "row-name", parts.title);
    bdi.setAttribute("dir", "auto");
    title.appendChild(bdi);
    if (parts.level) {
      var level = el("span", "row-level", parts.level);
      level.setAttribute("lang", "en");
      title.appendChild(level);
    }
    // The one row to open next: the first scene not yet finished. "Start here" until
    // something has been, "Next" after. Ink, not accent — `.pointed` already spends the
    // page's accent on the row somebody was sent to — and a status, so what is read out
    // is what is seen.
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
    what.appendChild(title);
    // The English under the Hebrew, in ink, with the byline after it: for a reader who
    // cannot yet read the line above, this is the title. Its own element, so the two
    // directions never share a string. An upload has no English and keeps its byline
    // line as it was.
    if (row.english) {
      var english = el("span", "row-english", row.english);
      // The language it is actually in, so a screen reader and the font stack both get
      // it right: this used to be `en` whatever the row said, which was true until a
      // row could say something else (targum-internal#289).
      english.setAttribute("lang", row.englishLang || "en");
      english.setAttribute("dir", "ltr");
      if (row.author) {
        // A byline is often half Hebrew ("Omid Memarian, תרגום Gallia Hoz"): isolated, so
        // its words never trade places with the title's.
        var after = el("span", "row-by-after", " · ");
        var who = el("bdi", null, row.author);
        who.setAttribute("dir", "auto");
        after.appendChild(who);
        english.appendChild(after);
      }
      what.appendChild(english);
    } else if (row.author) {
      var by = el("span", "row-by", row.author);
      by.setAttribute("dir", "auto");
      what.appendChild(by);
    }
    // Personal, where it can be: a text on the shelf is measured against the reader's
    // own words. Absent for one never built, for one built without word-level
    // annotation — "not measured" and "you know none of this" are different claims —
    // and at zero: "you know 0% of its words" is true and unkind, and the line starts
    // once there is something to say (as Learn's does).
    var share = knownOf(row);
    if (typeof share === "number" && share > 0) {
      what.appendChild(
        el(
          "span",
          "row-fit",
          t("library.you-know", "you know {share}% of its words", {
            share: Math.round(share * 100),
          })
        )
      );
    }
    // The one thing on a row that is not a column: a text either can be listened to or
    // cannot, and a column of blanks down the page to say "no audio" would be noise.
    // One word, not two: a video can be listened to as well, and a row saying
    // "audio video" says less than "video" does. No tooltip: what the word means is
    // said in the line under the controls, where a phone can read it.
    if (row.video) what.appendChild(el("span", "row-video", t("library.video", "Video")));
    else if (row.spoken) what.appendChild(el("span", "row-audio", t("library.audio", "Audio")));
    // On a phone the kind, which Hebrew and the hard words leave their columns, and a
    // row that only said a title and a length gave a learner nothing to choose by
    // (2026-09-14). They come back as one line under the title.
    var meta = [named(KINDS, row.kind), named(REGISTERS, row.register)];
    if (measured(row)) {
      meta.push(t("library.hard-words-share", "{share}% hard words", { share: row.difficulty || 0 }));
    }
    if (row.video) meta.push(t("library.video", "Video"));
    else if (row.spoken) meta.push(t("library.audio", "Audio"));
    var metaLine = meta.filter(Boolean).join(" · ");
    if (metaLine) what.appendChild(el("span", "row-meta", metaLine));
    open.appendChild(what);

    open.appendChild(el("span", "col label drop", named(KINDS, row.kind)));
    open.appendChild(el("span", "col label drop", named(REGISTERS, row.register)));
    open.appendChild(el("span", "col count", said(row.minutes)));
    var hard = gauge(row);
    hard.className = "gauge drop";
    open.appendChild(hard);
    var mine = yours(row);
    mine.className = "col count drop";
    open.appendChild(mine);

    /* Where a build narrates itself — and, on a text this reader has finished, the one
       word that says so, in leaf: a real state, not a score, and the only leaf on the
       page. It used to say Public or Private, which the two
       tabs say once at the top now — but it is also what `build()` writes into, and a
       row with nothing to write into threw the moment anybody pressed one. Empty until
       there is something to say, and its column collapses to nothing while it is. */
    var state = el("span", "row-state");
    if (row.built && finishedDocs[row.built.document] && finishedDocs[row.built.document].done) {
      state.className = "row-state finished";
      state.textContent = t("library.finished", "finished");
    }
    open.appendChild(state);

    item.appendChild(open);

    // Only where there is something to draw: a text on the shelf, from the library's own
    // catalogue — a cover is drawn from what the catalogue says a text is — and with no
    // cover yet. And only where this deployment has a key to draw with.
    if (canDraw && row.built && !row.built.shared && row.entry && !row.drawn) {
      var draw = el("button", "draw", t("library.cover.draw", "Draw cover"));
      draw.type = "button";
      draw.setAttribute("data-draw", row.built.name);
      item.appendChild(draw);
    }
    return item;
  }

  /* A collection, as one row on the same grid as every other. Same columns in the same
     places, because a row that lines up with the ones under it is read as one of them —
     and a disclosure where the cover would be, because a collection has no cover and a
     triangle in a column of its own would push every other row out of true. */
  function drawGroup(row) {
    var group = row.group;
    var item = el("li", "group" + (isOpen(group) ? " open" : ""));
    item.setAttribute("data-row", row.id);

    var open = el("button", "row-open row-group");
    open.type = "button";
    open.setAttribute("aria-expanded", isOpen(group) ? "true" : "false");
    open.setAttribute("data-group", group.id);

    var caret = el("span", "row-fold");
    caret.setAttribute("aria-hidden", "true");
    open.appendChild(caret);

    var what = el("span", "what");
    var title = el("span", "row-title");
    title.setAttribute("lang", row.language);
    var name = el("bdi", "row-name", row.title);
    name.setAttribute("dir", "auto");
    title.appendChild(name);
    // Where the beginner's path is, when the shelf holding it is shut. The chip is on
    // the scene itself once this is open; closed, a hundred scenes behind one row would
    // otherwise take the only line on the page that says where to start.
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
    // The English and the count on one line, the way a text carries its English and its
    // byline: what this is, then how much of it there is.
    var under = el("span", "row-english", row.english || "");
    under.setAttribute("lang", "en");
    under.setAttribute("dir", "ltr");
    var count = el(
      "span",
      "row-by-after",
      (row.english ? " · " : "") + tn("library.group-texts", row.rows.length, "{n} text", "{n} texts")
    );
    if (saidIn !== "en") count.setAttribute("lang", saidIn);
    under.appendChild(count);
    what.appendChild(under);
    if (row.video) what.appendChild(el("span", "row-video", t("library.video", "Video")));
    else if (row.spoken) what.appendChild(el("span", "row-audio", t("library.audio", "Audio")));
    // On a phone the kind, which Hebrew and the hard words leave their columns, and a
    // row that only said a title and a length gave a learner nothing to choose by
    // (2026-09-14). They come back as one line under the title.
    var meta = [named(KINDS, row.kind), named(REGISTERS, row.register)];
    if (measured(row)) {
      meta.push(t("library.hard-words-share", "{share}% hard words", { share: row.difficulty || 0 }));
    }
    if (row.video) meta.push(t("library.video", "Video"));
    else if (row.spoken) meta.push(t("library.audio", "Audio"));
    var metaLine = meta.filter(Boolean).join(" · ");
    if (metaLine) what.appendChild(el("span", "row-meta", metaLine));
    open.appendChild(what);

    open.appendChild(el("span", "col label drop", named(KINDS, row.kind)));
    open.appendChild(el("span", "col label drop", named(REGISTERS, row.register)));
    open.appendChild(el("span", "col count", said(row.minutes)));
    var hard = gauge(row);
    hard.className = "gauge drop";
    open.appendChild(hard);
    var groupMine = yours(row);
    groupMine.className = "col count drop";
    open.appendChild(groupMine);
    open.appendChild(el("span", "row-state"));

    item.appendChild(open);
    return item;
  }

  /* --- sorting and sifting ---------------------------------------------------- */

  var SORTS = {
    // By the English where there is one: for the reader this page is sorted for, the
    // Hebrew titles are not yet in an order.
    title: function (row) {
      return row.english || row.title || "";
    },
    kind: function (row) {
      return named(KINDS, row.kind);
    },
    // By age, not by label. See REGISTER_ORDER.
    register: function (row) {
      var place = REGISTER_ORDER[row.register];
      return typeof place === "number" ? place : REGISTERS.length;
    },
    minutes: function (row) {
      return row.minutes || 0;
    },
    difficulty: function (row) {
      return row.difficulty || 0;
    },
    // Most of it known first, which is the way somebody choosing what to read wants it
    // — so this column alone sorts descending by default (`DESCENDING` below). A row
    // with nothing measured sorts as -1 and lands at the far end either way: it is not
    // 0% known, and putting it among the texts that really are would be the one claim
    // this number must never make.
    known: function (row) {
      var share = knownOf(row);
      return typeof share === "number" ? share : -1;
    },
    /* When it arrived: the catalogue's own date for a catalogue row, and the day it was
       built for a text of the reader's own, which is when it arrived *for them*
       (targum-internal#315).

       A row nobody dated sorts last under Newest rather than first. Nine hundred rows
       predate the field and were dated from the file's history where it has one and from
       a floor where it has none (`scripts/backfill_added.py`); a row that fell through
       even that is "we do not know", and "we do not know" must never read as "just
       arrived". Compared as text because `YYYY-MM-DD` sorts correctly as text and a date
       parsed in the browser is a date in the browser's timezone. */
    added: function (row) {
      var when = dateOf(row);
      // Any dated row outranks every undated one, whatever their positions. The offset
      // is well past any day count this century, so the two scales never meet.
      if (when) return 1e6 + daysSince(when);
      /* And among the undated, where it sits in the catalogue file. Nine hundred rows
         predate the field and nothing can date them (`scripts/backfill_added.py`), so
         without this "Newest" would be alphabetical among them, which is no order at
         all. Rows are appended as they are added, so a later position is a later
         arrival — evidence of *order*, never of date, which is why it can never put an
         undated row above a dated one and why no row is ever marked New by it. */
      return row.place || 0;
    },
  };

  /* The day a row arrived, from whichever side knows. A catalogue row carries the
     catalogue's date; a text of the reader's own carries the day they built it, which is
     when it arrived for them and is the more honest answer for a text only they have. */
  function dateOf(row) {
    if (row.entry && row.entry.added) return row.entry.added;
    if (row.built && row.built.built) return dayOf(row.built.built);
    return "";
  }

  function daysSince(day) {
    var then = Date.parse(day + "T00:00:00Z");
    return isNaN(then) ? 0 : Math.round(then / 86400000);
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

  //: Columns a reader means "most first" by. Every other column reads smallest first.
  //: Newest is the whole of what "added" is for, so it never reads oldest first.
  var DESCENDING = { known: true, added: true };

  var COLUMNS = [
    ["", ""],
    ["title", t("library.column.title", "Text")],
    ["kind", t("library.column.kind", "Kind")],
    ["register", t("library.column.register", "Which Hebrew")],
    ["minutes", t("library.column.minutes", "Length")],
    // What the number under it means, said the way somebody choosing a text would ask
    // it. "Looked up" is the measurement's name, not the reader's question — and "New
    // words" was a claim about the reader the number cannot make: it counts words that
    // are rare in the language, not words this reader has not met (2026-09-14).
    ["difficulty", t("library.column.difficulty", "Hard words")],
    // What the reader came to the page to ask. Beside "Hard words" because the two are
    // the same question asked twice — how hard is this in the language, and how hard is
    // it for me — and the second is the one the front door sells.
    ["known", t("library.column.known", "Words you know")],
    // Unlabelled: the column a build narrates itself in, empty the rest of the time.
    ["", ""],
  ];

  // Whether the server can draw at all, answered by the server. A deployment with no
  // image key offers nothing rather than offering and failing.
  var canDraw = false;
  // The reader's own finishes, by content hash, and the scene to open next — set once
  // the server has said what is shared.
  var finishedDocs = stored("targum:docs");
  var nextRow = null;
  var anyFinished = false;

  // Whether this browser has ever drawn the page. A remembered view means the reader has
  // made choices here before, and those win over anything the page would choose for
  // them; only a first visit is the page's to open somewhere.
  var firstVisit = false;
  try {
    firstVisit = localStorage.getItem("targum:library") === null;
  } catch (e) {
    firstVisit = false;
  }

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
    // Since 2026-09-17: what a text is about, how far into reach it has to be, and
    // whether the list is drawn as cards or as the table.
    "subject",
    "fit",
    "shape",
  ];
  var views = stored("targum:library");
  if (
    VIEW_FIELDS.some(function (field) {
      return Object.prototype.hasOwnProperty.call(views, field);
    })
  ) {
    views = { he: views };
  }

  function viewFor(code) {
    var one = views[code];
    if (!one || typeof one !== "object") one = views[code] = {};
    // Easiest first. The default was by access, which sorted the catalogue into public
    // and private — a fact about who may read a text rather than about whether this
    // reader can. Somebody arriving at forty texts in a language they are learning is
    // asking which of them they can read now, and that is what the list answers.
    if (!one.sort) one.sort = "difficulty";
    // The direction the sort itself means, not 1 by default: Newest reads newest first
    // and "Words you know" reads most first, and a view that carried a sort without a
    // direction — a stored one from before either existed — showed them backwards.
    if (!one.dir) one.dir = DESCENDING[one.sort] ? -1 : 1;
    if (!one.kind) one.kind = "";
    if (!one.register) one.register = "";
    if (!one.where) one.where = "library";
    if (!one.subject) one.subject = "";
    // `fit` is deliberately left unset here. What it defaults to depends on whether this
    // reader has marked any words, which is not known until `/readers` answers — see
    // `fitWanted`. Once they choose, the choice is stored and outranks both defaults.
    if (!one.shape) one.shape = "cards";
    return one;
  }

  /* How much of the library to show, resolved rather than stored.
   *
   * The page opens on what the reader can read now: "I want to be able to immediately
   * choose a reading AT MY LEVEL" is answered by the list already being there, not by a
   * control that could be found (design.md §12, 2026-09-17).
   *
   * Except when that would be a near-empty page, which is the thing it must never be.
   * Two readers would get one: somebody who has marked nothing, where the fallback
   * measure is the text's own hard-word share and the page would be making a claim about
   * a stranger; and somebody who has marked a dozen words, where every row honestly
   * reads 2% known and nothing is within reach yet. Neither of them is helped by an
   * empty shelf.
   *
   * So the default is the narrowest band that still leaves a screen's worth, and it
   * widens on its own as a vocabulary grows. No threshold on how many words somebody
   * knows: the question is whether the list it produces is worth showing, and that is
   * the question this asks directly. A reader who picks a band gets it whatever it
   * leaves — including an empty one, which is an answer rather than a greeting. */
  var ENOUGH = 6;
  var autoFit = "";

  function fitWanted(state) {
    var one = state || view;
    if (typeof one.fit === "string") return one.fit;
    return autoFit;
  }

  function defaultFit(everything, code) {
    if (!anyKnown) return "";
    var bands = ["now", "stretch", ""];
    for (var i = 0; i < bands.length; i++) {
      var pretend = {};
      for (var key in view) pretend[key] = view[key];
      // A string, so `fitWanted` answers from it and never comes back here.
      pretend.fit = bands[i];
      var standing = 0;
      for (var j = 0; j < everything.length; j++) {
        if (matches(everything[j], code, pretend)) standing++;
        if (standing >= ENOUGH) return bands[i];
      }
    }
    return "";
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
    if (!inLanguage(row, code)) return false;
    if (state.kind && row.kind !== state.kind) return false;
    if (code === lang.HOME && state.register && row.register !== state.register) return false;
    if (state.length && lengthOf(row.minutes) !== state.length) return false;
    if (state.spoken === "yes" && !row.spoken) return false;
    if (state.spoken === "video" && !row.video) return false;
    if (state.level && level(row) !== state.level) return false;
    // What it is about. A row's tags are a list, so this asks whether the chosen one is
    // among them rather than whether it is the value — a match report is journalism and
    // sport at once, and belongs under both chips.
    if (state.subject && !holdsSubject(row, state.subject)) return false;
    if (!fits(row, fitWanted(state))) return false;
    if (state.where === "mine" && row.entry) return false;
    if (state.where !== "mine" && !row.entry) return false;
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
      if (typeof left === "number") order = left - right;
      else order = String(left).localeCompare(String(right));
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

  /* How many rows each subject would leave standing, asked with the subject filter
     itself lifted — the rule the kinds already follow, so choosing one never removes the
     others from the row it lives in.

     Counted rather than merely seen, because the count goes on the chip. Tanakh and
     Judaica are the two biggest Hebrew subjects; a bare row of subject names tells a
     modern-Hebrew learner this is a religious library, and the numbers tell them what is
     really there (design.md §12, 2026-09-17). */
  /* The kind is lifted with it, because the kind is no longer a peer of the subject —
     it is a refinement under it, and it lives in the fold with the other refinements.
     Left standing it takes the whole row away: the page opens a new reader on the
     Scenes, no scene is filed under any subject, and the one row this page is browsed
     by would vanish on the first visit of every reader who has it. So pressing a
     subject clears the kind (see `subjects`), and these counts are what pressing it
     actually leaves. */
  function unsubjected() {
    var pretend = {};
    for (var key in view) pretend[key] = view[key];
    pretend.subject = "";
    pretend.kind = "";
    return pretend;
  }

  function subjectTally(rows, code) {
    var tally = {};
    var pretend = unsubjected();
    rows.forEach(function (row) {
      if (!matches(row, code, pretend)) return;
      (row.tags || []).forEach(function (tag) {
        tally[tag] = (tally[tag] || 0) + 1;
      });
    });
    return tally;
  }

  /* The subjects, as chips that carry their counts.
   *
   * Drawn from the rows that exist and never from `Tag`, which runs well past what is
   * filed: the arrival draws a door before anything is tagged into it, on purpose, and
   * on this page that same door is a dead end. Hebrew carries eight subjects with
   * anything behind them, not seventeen.
   *
   * "All" leads and is the default. Nearly half the Hebrew shelf carries no subject at
   * all, so a subject can only ever narrow — as the page's one division it would hide
   * them (design.md §12, 2026-09-17). */
  function subjects(host, rows, code, redraw) {
    if (!host) return;
    host.textContent = "";
    // The row and the word over it are one thing: a heading above nothing is a heading
    // that says the page is broken.
    var label = document.getElementById("subject-label");
    var tally = subjectTally(rows, code);
    var offered = SUBJECTS.filter(function (pair) {
      return tally[pair[0]];
    });
    // One subject over a shelf divides nothing; the row is left empty rather than
    // offering "All" and one word, which is the rule `chips()` already applies.
    if (offered.length < 2) {
      host.hidden = true;
      if (label) label.hidden = true;
      return;
    }
    host.hidden = false;
    if (label) label.hidden = false;
    var here = rows.filter(function (row) {
      return matches(row, code, unsubjected());
    }).length;
    var all = [["", t("library.filter.all", "All"), here]].concat(
      offered.map(function (pair) {
        return [pair[0], pair[1], tally[pair[0]]];
      })
    );
    all.forEach(function (one) {
      var chip = el("button", "chip subject");
      chip.type = "button";
      chip.appendChild(document.createTextNode(one[1]));
      // Its own element, so the number can be quieted and given tabular figures without
      // the name inheriting either.
      chip.appendChild(el("span", "chip-n", String(one[2])));
      chip.setAttribute("aria-pressed", view.subject === one[0] ? "true" : "false");
      // The count is part of what the chip says, so a screen reader gets the sentence
      // rather than "News 40" run together.
      chip.setAttribute(
        "aria-label",
        tn("library.subject.count", one[2], "{name}, {n} text", "{name}, {n} texts", { name: one[1] })
      );
      chip.addEventListener("click", function () {
        view.subject = one[0];
        // Picking a subject is going somewhere, not narrowing where you are. The kind is
        // a refinement inside the place you were, and carrying it along is how a reader
        // opened on the Scenes presses "Science" and is shown nothing at all.
        view.kind = "";
        redraw();
      });
      host.appendChild(chip);
    });
  }

  function chips(host, options, field, redraw, shape, seen) {
    host.textContent = "";
    var offered = seen
      ? options.filter(function (pair) {
          return seen[pair[0]];
        })
      : options;
    // Nothing to choose between is not a choice: one kind left, or none, and the row of
    // chips is the word "All" on its own.
    if (seen && offered.length < 2) offered = [];
    var all = offered.length ? [["", t("library.filter.all", "All")]].concat(offered) : [];
    all.forEach(function (pair) {
      var chip = el("button", shape || "chip", pair[1]);
      chip.type = "button";
      chip.setAttribute("aria-pressed", view[field] === pair[0] ? "true" : "false");
      chip.addEventListener("click", function () {
        view[field] = pair[0];
        redraw();
      });
      host.appendChild(chip);
    });
  }

  /* The line above the list, which says how many texts there are and how far the list
     has been narrowed to fit the reader — with the narrowing itself as the control.
     A sentence with one word in it you can press, rather than a filter to be found
     (design.md §12, 2026-09-17).
   *
   * It is a `select` and not a menu of our own: three options, and the platform's own
   * control is reachable by keyboard and by a thumb on every device without any of it
   * being written here. */
  function fitLine(host, count, redraw) {
    if (!host) return;
    host.textContent = "";
    // The number in its own element: ink and tabular, where the sentence around it is
    // the quieter voice the page uses for what it is doing.
    host.appendChild(
      el("span", "count", tn("library.tally.all", count, "{n} text", "{n} texts", { n: count }))
    );
    host.appendChild(document.createTextNode(" · "));
    var lead = el("label", "fit");
    lead.appendChild(
      document.createTextNode(t("library.fit.showing", "showing") + " ")
    );
    var pick = el("select", "fit-pick");
    pick.id = "fit";
    FITS.forEach(function (pair) {
      var option = el("option", null, pair[1]);
      option.value = pair[0];
      if (fitWanted() === pair[0]) option.selected = true;
      pick.appendChild(option);
    });
    pick.onchange = function () {
      view.fit = pick.value;
      redraw();
    };
    pick.setAttribute("aria-label", t("library.fit.how-much", "How much of the library to show"));
    lead.appendChild(pick);
    host.appendChild(lead);
  }

  /* Cards or the table, remembered. The table is the older shape and it is kept rather
     than replaced: the complaint that retired the last card grid was that a card cannot
     be sorted, and it was a fair one — so the sortable thing stays one press away
     (design.md §12, 2026-09-17). */
  var SHAPES = [
    ["cards", t("library.shape.cards", "Cards")],
    ["list", t("library.shape.list", "List")],
  ];

  /* Sorting, for the shape that has no columns to press.
   *
   * The table sorts by its headings and always did; a grid of cards has no headings, so
   * a browse view with no way to reorder itself would be a browse view you can only
   * scroll. These are the three orders somebody browsing actually asks for — what is
   * new, what is easy, what I nearly know — and they write the same `view.sort` the
   * headings do, because they are the same state shown two ways.
   *
   * Only three. "A to Z" is not one of them: the shelf is in Hebrew, a reader who wants
   * one text by name has the search field, and a fourth word here would be a fourth
   * thing to read before choosing. The table keeps every column it had.
   */
  var SORTS_OFFERED = [
    ["added", t("library.sort.added", "Newest")],
    ["difficulty", t("library.sort.difficulty", "Easiest")],
    ["known", t("library.sort.known", "Words you know")],
  ];

  function sorts(host, redraw) {
    if (!host) return;
    host.textContent = "";
    // The table says this with its headings, and one state wearing two controls at once
    // is two things to keep in step and one of them always wrong.
    host.hidden = view.shape === "list";
    if (host.hidden) return;
    SORTS_OFFERED.forEach(function (pair) {
      var press = el("button", "shape", pair[1]);
      press.type = "button";
      press.setAttribute("aria-pressed", view.sort === pair[0] ? "true" : "false");
      press.addEventListener("click", function () {
        view.sort = pair[0];
        view.dir = DESCENDING[pair[0]] ? -1 : 1;
        redraw();
      });
      host.appendChild(press);
    });
  }

  function shapes(host, redraw) {
    if (!host) return;
    host.textContent = "";
    SHAPES.forEach(function (pair) {
      var press = el("button", "shape", pair[1]);
      press.type = "button";
      press.setAttribute("aria-pressed", view.shape === pair[0] ? "true" : "false");
      press.addEventListener("click", function () {
        view.shape = pair[0];
        redraw();
      });
      host.appendChild(press);
    });
  }

  /* The one control that changes which list you are looking at rather than what it is
     narrowed to. Underlined rather than pilled: the page already has pills for the
     language above it and chips for the filters below, and a third row of the same shape
     would be a third thing to tell apart. */
  function tabs(host, options, field, redraw) {
    if (!host) return;
    host.textContent = "";
    options.forEach(function (pair) {
      var tab = el("button", "tab", pair[1]);
      tab.type = "button";
      tab.setAttribute("role", "tab");
      var on = (view[field] || options[0][0]) === pair[0];
      tab.setAttribute("aria-selected", on ? "true" : "false");
      tab.addEventListener("click", function () {
        view[field] = pair[0];
        redraw();
      });
      host.appendChild(tab);
    });
  }

  function choices(select, options, field, redraw) {
    select.textContent = "";
    options.forEach(function (pair) {
      var option = el("option", null, pair[1]);
      option.value = pair[0];
      if ((view[field] || "") === pair[0]) option.selected = true;
      select.appendChild(option);
    });
    select.onchange = function () {
      view[field] = select.value;
      redraw();
    };
  }

  function heading(redraw) {
    var host = document.getElementById("rows-head");
    host.textContent = "";
    COLUMNS.forEach(function (pair) {
      // The register's column says nothing under another language: kept as an empty cell
      // so the row still lines up with the heading.
      if (!pair[0] || (pair[0] === "register" && !inHebrew)) {
        host.appendChild(el("span"));
        return;
      }
      var button = el("button", pair[0] === "kind" || pair[0] === "register" ? "drop" : null);
      button.type = "button";
      // Under the Scenes chip the list is in scene order whatever this column says, so
      // the column says that instead, and cannot be pressed: a heading reading "New
      // words" over a list not in that order would be a lie.
      var scenes = pair[0] === "difficulty" && view.kind === "dialogue";
      button.appendChild(
        document.createTextNode(scenes ? t("library.column.scene-number", "Scene number") : pair[1])
      );
      if (pair[0] === "difficulty" || pair[0] === "known") button.className = "drop";
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
        if (!job.id) throw new Error(t("library.build.could-not-start", "We couldn't start this one."));
        // Said, and then pressed (2026-09-14). The first press used to go straight on to
        // the build, while the conversation and the Add page both say how long a thing
        // takes and wait for the reader's own press before anything is spent. The same
        // here: how long, and a press of its own beside the row.
        return confirmBuild(open, state, job).then(function (yes) {
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

  function confirmBuild(open, state, job) {
    return new Promise(function (resolve) {
      var item = open.parentNode;
      tell(state, waitFor(job));
      var go = el("button", "row-go", t("library.build.start-reading", "Start reading"));
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

  ask("/readers").then(function (data) {
    var readers = data.readers || [];
    var shared = data.shared || [];
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
    canDraw = !!data.covers;
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
    var empty = document.getElementById("picked-empty");
    var tally = document.getElementById("tally");
    var find = document.getElementById("find");
    var clear = document.getElementById("clear");
    var chosen;

    function redraw() {
      remember("targum:library", views);
      // Resolved before anything is filtered, and before the chips are counted, so the
      // whole page agrees about how much of the library it is showing.
      autoFit = defaultFit(everything, chosen);
      // "Which Hebrew" asks nothing of another language (2026-09-13).
      var registerSet = document.getElementById("register-chips");
      if (registerSet && registerSet.parentNode) registerSet.parentNode.hidden = chosen !== lang.HOME;
      // Only the registers actually in front of this reader, the same way the kinds are.
      // Two values could always both be offered; five cannot — a shelf of Hebrew
      // journalism would otherwise carry four chips that find nothing.
      chips(
        document.getElementById("register-chips"),
        REGISTERS,
        "register",
        redraw,
        "segment",
        present(everything, "register", chosen)
      );
      // Only the kinds that are actually in front of this reader. A row of seven chips
      // where three of them find nothing — and one of them is "Documents" — is seven
      // things to read and four dead ends.
      chips(
        document.getElementById("kind-chips"),
        KINDS,
        "kind",
        redraw,
        "chip",
        present(everything, "kind", chosen)
      );
      // What it is about, above the list and always visible: the row a reader browses by
      // (design.md §12, 2026-09-17).
      subjects(document.getElementById("subject-chips"), everything, chosen, redraw);
      sorts(document.getElementById("sorts"), redraw);
      shapes(document.getElementById("shape"), redraw);
      choices(document.getElementById("audio"), SPOKEN, "spoken", redraw);
      choices(document.getElementById("length"), LENGTHS, "length", redraw);
      choices(document.getElementById("difficulty"), LEVELS, "level", redraw);
      tabs(document.getElementById("where"), WHERE, "where", redraw);
      heading(redraw);

      var surviving = everything.filter(function (row) {
        return matches(row, chosen);
      });
      var top = folded(surviving);
      /* A list that is one collection is that collection. Picking the Scenes chip and
         being shown a single row saying "Scenes · 100 texts" is the filter answering a
         question with the question. */
      if (top.length === 1 && top[0].group) top = top[0].rows;
      var showing = sorted(top);
      host.textContent = "";
      cards.textContent = "";
      /* Two shapes over one list. Whichever is on is filled and the other is emptied,
         so nothing is drawn twice and a build narrating itself has exactly one cell to
         write into. A collection folds the same way in both: one row, or one card, over
         its texts, and opening it lays its members out beside it. */
      var browsing = view.shape !== "list";
      host.hidden = browsing;
      cards.hidden = !browsing;
      showing.forEach(function (row) {
        if (browsing) {
          // A collection is a card of its own shape: a shelf rather than a text, with no
          // cover and a press that opens rather than reads.
          cards.appendChild(row.group ? groupCard(row) : card(row));
          if (row.group && isOpen(row.group)) {
            within(row.group, row.rows).forEach(function (member) {
              cards.appendChild(card(member));
            });
          }
          return;
        }
        host.appendChild(draw(row));
        if (row.group && isOpen(row.group)) {
          within(row.group, row.rows).forEach(function (member) {
            host.appendChild(draw(member, true));
          });
        }
      });
      // The table's heading belongs to the table; over a grid of cards it is a row of
      // sort buttons pointing at columns nobody can see.
      var head = document.getElementById("rows-head");
      if (head) head.hidden = browsing;
      placeNote(noteFor(showing));
      pointAt();
      // Counted within the list being looked at, not across both: "2 of 116" under Your
      // Uploads would be counting somebody's two texts against everybody's catalogue.
      var here = everything.filter(function (row) {
        return inLanguage(row, chosen) && (view.where === "mine" ? !row.entry : row.entry);
      });
      empty.hidden = showing.length > 0;
      if (!showing.length) {
        // An empty tab and an empty filter are different things to be told.
        // A language with no catalogue yet says so, and points at what the reader has in
        // it already, if anything (2026-09-14): "Nothing here yet" under Italian hid the
        // two Italian texts one tab away.
        var uploaded = everything.filter(function (row) {
          return inLanguage(row, chosen) && !row.entry;
        }).length;
        empty.textContent = here.length
          ? t("library.empty.no-match", "Nothing here matches that.")
          : view.where === "mine"
            ? t("library.empty.mine", "You haven't added anything yet. Use Add to bring your own.")
            : uploaded
              ? t("library.empty.language-uploads", "No {language} texts in the library yet. You have {n} in Your uploads.", {
                  language: names[chosen] || chosen,
                  n: uploaded,
                })
              : t("library.empty.language", "No {language} texts in the library yet.", {
                  language: names[chosen] || chosen,
                });
      }
      var total = here.length;
      // Texts, not rows. A folded list is thirty-six rows over three hundred and
      // fifty-two texts, and counting the rows would say "36 of 352" — two different
      // things, in one sentence, both of them true.
      var found = surviving.length;
      tally.textContent =
        found === total
          ? tn("library.tally.all", total, "{n} text", "{n} texts")
          : t("library.tally.found", "{found} of {total}", { found: found, total: total });
      // The sentence above the list: how many there are in this language, and how much
      // of it is being shown. The count is every text on this shelf, not the surviving
      // ones — it is the thing the narrowing is measured against.
      fitLine(document.getElementById("said"), total, redraw);
      clear.hidden = !(
        view.find ||
        view.kind ||
        view.register ||
        view.length ||
        view.level ||
        view.subject
      );
    }

    /* Learn suggests something to read and links here with the id in the hash. Finding it
       is the reader's problem otherwise: this catalogue is forty rows and the thing they
       were sent for could be anywhere in it. Marked and scrolled to, never pressed —
       what pressing an unbuilt row does is start spending, and nothing arrives at a page
       with permission to do that. */
    var lifted = false;
    function pointAt() {
      var wanted = decodeURIComponent((location.hash || "").slice(1));
      if (!wanted) return;
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
      if (holding && !unfolded[holding.id] && !lifted) {
        lifted = true;
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
      view.where = target.entry ? "library" : "mine";
      find.value = "";
      // show() redraws, and redraw() comes back through here with the row in the list.
      if (code && code !== chosen) return show(code);
      redraw();
    }

    find.value = view.find || "";
    find.addEventListener("input", function () {
      view.find = find.value.trim();
      redraw();
    });
    clear.addEventListener("click", function () {
      // Not `where`: Clear empties the filters, and which of the two lists you are
      // looking at is not one of them.
      view.find = view.kind = view.register = view.length = view.level = view.subject = "";
      find.value = "";
      redraw();
    });

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
    var codes = lang.order(all, names);
    chosen = lang.current(codes);
    view = viewFor(chosen);
    var betaNote = document.getElementById("beta-note");

    /* Where the page opens for an account that knows nothing. A first visit, no word
       marked in Hebrew and nothing of their own in it: the list opens on the Scenes,
       in order, with the line that says to start at 1 above everything else. Once
       only — from then on the view is remembered and the reader's own choices win. The
       count is the same one Learn opens with, from the same store. */
    if (firstVisit && chosen === lang.HOME && !view.kind) {
      var charts = window.TargumCharts;
      var store = charts ? charts.collect(charts.meaningLanguage(chosen))[chosen] : null;
      var known = charts ? charts.known(store && store.words) : 0;
      var ownHebrew = readers.some(function (reader) {
        return inLanguage(reader, chosen);
      });
      if (!known && !ownHebrew) {
        view.kind = "dialogue";
        leading = true;
      }
    }

    function show(code) {
      chosen = code;
      view = viewFor(code);
      find.value = view.find || "";
      inHebrew = code === lang.HOME;
      lang.set(code);
      lang.switcher(document.getElementById("langs"), codes, names, code, show);
      if (betaNote) {
        betaNote.hidden = !lang.beta(code);
        if (lang.beta(code)) betaNote.textContent = lang.betaNote(code, names);
      }
      // The search names the language the shelf is in.
      var box = document.getElementById("find");
      if (box) {
        box.placeholder = t("library.search", "Search a title, {language} or English", {
          language: names[code] || t("library.search-the-text", "the text"),
        });
      }
      redraw();
    }

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
