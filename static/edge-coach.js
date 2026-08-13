/* Simple spoken edging coach — hands-free timed cues. */

const EdgeCoach = (() => {
  let timer = null;
  let running = false;
  let onTick = null;
  let cycle = 0;

  const DEFAULT_SCRIPT = [
    { say: "Get ready. Hands where I want them.", waitMs: 4000 },
    { say: "Edge. Slow. Don't you dare cum.", waitMs: 25000 },
    { say: "Stop. Hands off. Breathe.", waitMs: 12000 },
    { say: "Again. Build it. Right to the edge.", waitMs: 28000 },
    { say: "Stop. Good boy. Stay denied.", waitMs: 15000 },
    { say: "One more. Messy and desperate. Edge.", waitMs: 30000 },
    { say: "Hands off. Locked and denied. Session pause.", waitMs: 5000 },
  ];

  function stop() {
    running = false;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    onTick?.({ running: false, cycle, line: "Stopped." });
  }

  async function run(script = DEFAULT_SCRIPT) {
    stop();
    running = true;
    cycle += 1;
    const myCycle = cycle;

    for (const step of script) {
      if (!running || myCycle !== cycle) return;
      onTick?.({ running: true, cycle, line: step.say });
      await window.Voice.speak(step.say, { interrupt: true });
      if (!running || myCycle !== cycle) return;
      await new Promise((resolve) => {
        timer = setTimeout(resolve, step.waitMs);
      });
    }
    running = false;
    onTick?.({ running: false, cycle, line: "Edging set complete." });
    await window.Voice.speak("Edging set complete. Stay denied.", { interrupt: true });
  }

  function setHandler(fn) {
    onTick = fn;
  }

  return { run, stop, setHandler, isRunning: () => running, DEFAULT_SCRIPT };
})();

window.EdgeCoach = EdgeCoach;
