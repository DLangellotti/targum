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

  var can =
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === "function" &&
    typeof MediaRecorder === "function";

  var recorder = null;
  var recorded = [];

  // `mic` is the button, so it can say which press this is: "Speak" at rest, "Stop"
  // while recording, and `aria-pressed` either way. `onClip(blob)` is called once the
  // clip is whole; `onFail(message)` when the microphone would not open.
  function toggle(mic, onClip, onFail) {
    if (!can) return false;
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
          mic.textContent = "Speak";
          onClip(clip);
        };
        recorder.start();
        mic.setAttribute("aria-pressed", "true");
        mic.textContent = "Stop";
      },
      function () {
        onFail("The microphone could not be opened.");
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
