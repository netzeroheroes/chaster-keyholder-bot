/* Browser voice helpers — Web Speech API (best in Chrome/Edge). */

const Voice = (() => {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let listening = false;
  let shouldLoop = false;
  let onResult = null;
  let onListeningChange = null;

  function supported() {
    return {
      stt: Boolean(SpeechRecognition),
      tts: "speechSynthesis" in window,
    };
  }

  function preferFemaleVoice() {
    const voices = speechSynthesis.getVoices();
    const prefer = voices.find((v) =>
      /female|zira|susan|samantha|victoria|karen|moira|fiona|google uk english female/i.test(
        `${v.name} ${v.voiceURI}`
      )
    );
    return prefer || voices.find((v) => v.lang.startsWith("en")) || voices[0] || null;
  }

  function speak(text, { interrupt = true } = {}) {
    if (!("speechSynthesis" in window) || !text) return Promise.resolve();
    const clean = String(text)
      .replace(/— Sent to group —[\s\S]*$/i, "")
      .replace(/\[\[\[.*?\]\]\]/g, "")
      .trim();
    if (!clean) return Promise.resolve();

    if (interrupt) speechSynthesis.cancel();

    return new Promise((resolve) => {
      const utter = new SpeechSynthesisUtterance(clean);
      utter.rate = 0.96;
      utter.pitch = 1.05;
      const voice = preferFemaleVoice();
      if (voice) utter.voice = voice;
      utter.onend = () => resolve();
      utter.onerror = () => resolve();
      speechSynthesis.speak(utter);
    });
  }

  function stopSpeaking() {
    if ("speechSynthesis" in window) speechSynthesis.cancel();
  }

  function _ensureRecognition() {
    if (!SpeechRecognition) return null;
    if (recognition) return recognition;
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onstart = () => {
      listening = true;
      onListeningChange?.(true);
    };
    recognition.onend = () => {
      listening = false;
      onListeningChange?.(false);
      if (shouldLoop) {
        setTimeout(() => startListening({ loop: true }), 250);
      }
    };
    recognition.onerror = (e) => {
      listening = false;
      onListeningChange?.(false);
      if (e.error === "not-allowed") {
        shouldLoop = false;
      }
    };
    recognition.onresult = (event) => {
      let interim = "";
      let finalText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const piece = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += piece;
        else interim += piece;
      }
      if (finalText.trim()) {
        onResult?.(finalText.trim(), { final: true });
      } else if (interim.trim()) {
        onResult?.(interim.trim(), { final: false });
      }
    };
    return recognition;
  }

  function startListening({ loop = false } = {}) {
    const rec = _ensureRecognition();
    if (!rec) return false;
    shouldLoop = loop;
    try {
      rec.start();
      return true;
    } catch {
      // already started
      return listening;
    }
  }

  function stopListening() {
    shouldLoop = false;
    try {
      recognition?.stop();
    } catch {
      /* ignore */
    }
  }

  function setHandlers({ result, listeningChange } = {}) {
    onResult = result || null;
    onListeningChange = listeningChange || null;
  }

  // Warm voices list (Chrome loads async)
  if ("speechSynthesis" in window) {
    speechSynthesis.onvoiceschanged = () => preferFemaleVoice();
  }

  return {
    supported,
    speak,
    stopSpeaking,
    startListening,
    stopListening,
    setHandlers,
    isListening: () => listening,
  };
})();

window.Voice = Voice;
