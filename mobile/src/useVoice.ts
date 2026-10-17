// Voice typing with the speech recognition built into Chrome, Edge and Safari.
// It's free and needs nothing from our server. The browser sends the audio to its own
// speech service (Google's, in Chrome) to turn it into text.
import { useEffect, useRef, useState } from "react";
import { Platform } from "react-native";

// The Web Speech API isn't in TypeScript's standard types, so describe the parts we use
type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

function recognitionClass(): (new () => Recognition) | null {
  if (Platform.OS !== "web") return null;
  const w = globalThis as unknown as Record<string, unknown>;
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as (new () => Recognition) | null;
}

const ERRORS: Record<string, string> = {
  "not-allowed": "Microphone access is blocked. Allow it in your browser's address bar, then try again.",
  "service-not-allowed": "Microphone access is blocked. Allow it in your browser's address bar, then try again.",
  "no-speech": "Didn't hear anything. Tap the mic and try again.",
  "audio-capture": "No microphone found.",
  network: "Voice typing needs an internet connection.",
};

/**
 * `onText` gets the words heard so far in this recording (it updates as you speak),
 * so the caller can show them live in a text box.
 */
export function useVoice(onText: (spoken: string) => void) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognition = useRef<Recognition | null>(null);
  const onTextRef = useRef(onText);
  onTextRef.current = onText;

  const supported = recognitionClass() !== null;

  useEffect(() => () => recognition.current?.stop(), []);

  function start() {
    const Klass = recognitionClass();
    if (!Klass) return;
    setError(null);
    const r = new Klass();
    r.lang = "en-US";
    r.continuous = true; // keep listening through short pauses
    r.interimResults = true; // show words as they're recognized
    r.onresult = (event) => {
      let spoken = "";
      for (let i = 0; i < event.results.length; i++) spoken += event.results[i][0].transcript;
      onTextRef.current(spoken.trim());
    };
    r.onerror = (event) => {
      if (event.error !== "aborted") setError(ERRORS[event.error] ?? "Voice typing stopped unexpectedly.");
    };
    r.onend = () => setListening(false);
    recognition.current = r;
    r.start();
    setListening(true);
  }

  function stop() {
    recognition.current?.stop();
    setListening(false);
  }

  return { supported, listening, error, start, stop, toggle: () => (listening ? stop() : start()) };
}
