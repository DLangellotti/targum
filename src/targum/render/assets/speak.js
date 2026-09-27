/* Push-to-talk: one press starts, the next stops, and the clip is handed back.
 *
 * Shared by the two pages that carry the box (`_composer.html.j2`): the conversation
 * page, where the clip becomes the next line, and Learn, where it opens a conversation
 * with that line. What is decided here is only the recording; what the clip is for is
 * the caller's.
 *
 * A browser that cannot record has no Speak button at all — `can` is false and the
 * pages hide it — so nothing on the page says a thing it cannot do.
 */
(function () {
  "use strict";

  /* Words said through the page's `TargumStrings`, looked up when a thing is said: this
     file runs before the page has handed its strings over. Where there are none, the
     English here (targum-internal#184). */
  function t(key, english, fill) {
    var said = window.TargumStrings;
    if (said) return said.t(key, english, fill);
    return english.replace(/\{(\w+)\}/g, function (all, name) {
      return fill && Object.prototype.hasOwnProperty.call(fill, name) ? String(fill[name]) : all;
    });
  }
  function tn(key, count, one, other, fill) {
    var said = window.TargumStrings;
    if (said) return said.tn(key, count, one, other, fill);
    var values = { n: count };
    for (var name in fill || {}) values[name] = fill[name];
    return t(key, count === 1 ? one : other, values);
  }

  var can =
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === "function" &&
    typeof MediaRecorder === "function";

  var recorder = null;
  var recorded = [];

  // `mic` is the button, so it can say which press this is: Speak at rest, Stop while
  // recording, and `aria-pressed` either way. Since 2026-09-10 the word is the label
  // and the glyph is the face: a microphone at rest, a square while recording.
  // `onClip(blob)` is called once the clip is whole; `onFail(message)` when the
  // microphone would not open.
  function say(mic, word, glyph) {
    mic.setAttribute("aria-label", word);
    mic.setAttribute("title", word);
    var use = mic.querySelector(".glyph-use");
    if (use) use.setAttribute("href", "#glyph-" + glyph);
  }

  // `resting` is the word the button wears when it is not recording — "Speak" on the
  // composer, "Record" on Add (targum-internal#254). The glyph is the same either way:
  // a microphone at rest, a square while recording.
  function toggle(mic, onClip, onFail, resting) {
    if (!can) return false;
    var word = resting || t("chat.page.speak", "Speak");
    if (recorder) {
      recorder.stop();
      return true;
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(
      function (stream) {
        recorded = [];
        recorder = new MediaRecorder(stream);
        recorder.ondataavailable = function (event) {
          if (event.data && event.data.size) recorded.push(event.data);
        };
        recorder.onstop = function () {
          stream.getTracks().forEach(function (track) {
            track.stop();
          });
          var clip = new Blob(recorded, { type: recorder.mimeType || "audio/webm" });
          recorder = null;
          mic.setAttribute("aria-pressed", "false");
          say(mic, word, "mic");
          onClip(clip);
        };
        recorder.start();
        mic.setAttribute("aria-pressed", "true");
        say(mic, t("speak.stop", "Stop"), "stop");
      },
      function () {
        onFail(t("speak.no-microphone", "We couldn't open the microphone. Check that your browser allows it."));
      }
    );
    return true;
  }

  window.TargumSpeak = {
    can: can,
    toggle: toggle,
    recording: function () {
      return !!recorder;
    },
  };
})();
