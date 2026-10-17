import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type TextInputInstance,
} from "react-native";

import { api, errorMessage, type Guess, type RetraceEnd, type RetraceSession, type Settings } from "./api";
import { formatDue } from "./grouping";
import type { Theme } from "./theme";

type Props = {
  theme: Theme;
  settings: Settings;
  // Called when the screen closes; `message` is shown as a banner on the main list
  onDone: (message: string | null) => void;
};

// What you said about a guess: it was the thought, or it was close
type Mark = "yes" | "close";

export function RetraceScreen({ theme, settings, onDone }: Props) {
  const [session, setSession] = useState<RetraceSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chip, setChip] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [marks, setMarks] = useState<Record<string, Mark>>({});
  const [cue, setCue] = useState<string | undefined>(undefined);
  // The guess you said "Yes" to, if any
  const [picked, setPicked] = useState<Guess | null>(null);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const input = useRef<TextInputInstance>(null);

  useEffect(() => {
    api
      .startRetrace(settings)
      .then(setSession)
      .catch((e) => setError(errorMessage(e)));
  }, [settings]);

  // Tapping a type chip moves the guesses of that type to the top. The server already
  // ranked them; sort is stable, so the ranking holds within each group.
  const guesses = useMemo(() => {
    const visible = (session?.guesses ?? []).filter((g) => !hidden.has(g.ref));
    if (!chip) return visible;
    return [...visible].sort((a, b) => Number(b.chips.includes(chip)) - Number(a.chips.includes(chip)));
  }, [session, hidden, chip]);

  async function finish(end: RetraceEnd, message: string) {
    if (!session) return onDone(null);
    setSaving(true);
    try {
      const result = await api.endRetrace(settings, session.id, end);
      if (result.capture) message = `Got it back! ${result.capture.summary}`;
      onDone(message);
    } catch (e) {
      setError(errorMessage(e));
      setSaving(false);
    }
  }

  function recover() {
    // Saying "Yes" to something already on your list and keeping its words means the
    // thought was that item, so don't save it a second time
    if (picked?.kind === "item" && text.trim() === picked.title) {
      finish({ outcome: "recovered", item_id: picked.id, cue }, `Got it back! It's already on your list: ${picked.title}`);
    } else {
      finish({ outcome: "recovered", text: text.trim(), cue }, "Got it back!");
    }
  }

  function close() {
    // Leaving without an answer still counts, so the session isn't left open.
    // Don't wait for it: the screen closes right away either way.
    if (session) api.endRetrace(settings, session.id, { outcome: "gave_up", cue }).catch(() => {});
    onDone(null);
  }

  function markGuess(guess: Guess, mark: Mark) {
    setMarks((current) => ({ ...current, [guess.ref]: mark }));
    setCue(mark === "yes" ? guess.ref : `close:${guess.ref}`);
    // "Yes" fills in the guess so you can fix it up; "Close" leaves the box for your words
    setPicked(mark === "yes" ? guess : null);
    if (mark === "yes") setText(guess.title);
    input.current?.focus();
  }

  function pickChip(name: string) {
    const next = chip === name ? null : name;
    setChip(next);
    // A guess you answered is a better cue than a chip, so don't overwrite it
    if (next && (!cue || cue.startsWith("chip:"))) setCue(`chip:${next}`);
  }

  const context = session?.context;
  const pill = { borderColor: theme.border, backgroundColor: theme.surface };

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: theme.text }]}>Lost a thought?</Text>
        <Pressable accessibilityRole="button" onPress={close} hitSlop={8}>
          <Text style={[styles.headerButton, { color: theme.accent }]}>Back</Text>
        </Pressable>
      </View>

      {error && <Text style={[styles.error, { color: theme.danger }]}>{error}</Text>}

      {!session && !error && <ActivityIndicator style={styles.loading} color={theme.accent} />}

      {session && context && (
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
            <Text style={[styles.cardLabel, { color: theme.muted }]}>Where you were</Text>
            <Text style={[styles.cardText, { color: theme.text }]}>
              {context.place
                ? `${context.place.place} · ${formatDue(context.place.at, false)}`
                : "No place recorded yet"}
            </Text>
            {context.recent_captures.length > 0 && (
              <>
                <Text style={[styles.cardLabel, { color: theme.muted }]}>What you captured lately</Text>
                <Text style={[styles.cardText, { color: theme.text }]}>
                  {context.recent_captures.slice(0, 3).map((c) => c.title).join(" · ")}
                </Text>
              </>
            )}
            {context.due_soon.length > 0 && (
              <>
                <Text style={[styles.cardLabel, { color: theme.muted }]}>Due soon</Text>
                <Text style={[styles.cardText, { color: theme.text }]}>
                  {context.due_soon.slice(0, 3).map((e) => e.title).join(" · ")}
                </Text>
              </>
            )}
          </View>

          <Text style={[styles.sectionTitle, { color: theme.muted }]}>What kind of thing was it?</Text>
          <View style={styles.chips}>
            {session.chips.map((name) => {
              const selected = chip === name;
              return (
                <Pressable
                  key={name}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  onPress={() => pickChip(name)}
                  style={[styles.chip, pill, selected && { backgroundColor: theme.accent, borderColor: theme.accent }]}
                >
                  <Text style={{ color: selected ? theme.accentText : theme.text, fontSize: 14 }}>{name}</Text>
                </Pressable>
              );
            })}
          </View>

          {guesses.length > 0 && (
            <Text style={[styles.sectionTitle, { color: theme.muted }]}>Maybe it was…</Text>
          )}
          {guesses.map((guess) => {
            const mark = marks[guess.ref];
            const highlighted = mark ? { borderColor: theme.accent } : null;
            return (
              <View
                key={guess.ref}
                style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }, highlighted]}
              >
                <Text style={[styles.question, { color: theme.text }]}>{guess.question}</Text>
                <View style={styles.answers}>
                  <AnswerButton theme={theme} label="Yes" active={mark === "yes"} onPress={() => markGuess(guess, "yes")} />
                  <AnswerButton
                    theme={theme}
                    label="No"
                    onPress={() => setHidden((current) => new Set(current).add(guess.ref))}
                  />
                  <AnswerButton
                    theme={theme}
                    label="Close"
                    active={mark === "close"}
                    onPress={() => markGuess(guess, "close")}
                  />
                </View>
              </View>
            );
          })}

          <Text style={[styles.sectionTitle, { color: theme.muted }]}>Got it?</Text>
          <TextInput
            ref={input}
            value={text}
            onChangeText={setText}
            placeholder="Type the thought before it slips away again"
            placeholderTextColor={theme.muted}
            multiline
            editable={!saving}
            style={[styles.input, { color: theme.text, borderColor: theme.border, backgroundColor: theme.surface }]}
          />
          <Pressable
            accessibilityRole="button"
            disabled={saving || !text.trim()}
            onPress={recover}
            style={[styles.button, { backgroundColor: theme.accent, opacity: text.trim() ? 1 : 0.4 }]}
          >
            {saving ? (
              <ActivityIndicator color={theme.accentText} />
            ) : (
              <Text style={[styles.buttonText, { color: theme.accentText }]}>Got it</Text>
            )}
          </Pressable>
          <Pressable
            accessibilityRole="button"
            disabled={saving}
            onPress={() =>
              finish(
                { outcome: "ghost", cue },
                "Still gone. Retrace will check in if you're back here and it might return.",
              )
            }
            style={styles.stillGone}
          >
            <Text style={{ color: theme.muted, fontSize: 15 }}>Still gone</Text>
          </Pressable>
        </ScrollView>
      )}
    </KeyboardAvoidingView>
  );
}

function AnswerButton({
  theme,
  label,
  active = false,
  onPress,
}: {
  theme: Theme;
  label: string;
  active?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={[
        styles.answer,
        { borderColor: active ? theme.accent : theme.border, backgroundColor: active ? theme.accent : "transparent" },
      ]}
    >
      <Text style={{ color: active ? theme.accentText : theme.text, fontSize: 14, fontWeight: "500" }}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 12,
  },
  title: {
    fontSize: 28,
    fontWeight: "700",
  },
  headerButton: {
    fontSize: 16,
    fontWeight: "500",
  },
  loading: {
    marginTop: 60,
  },
  error: {
    fontSize: 14,
    marginHorizontal: 20,
    marginBottom: 8,
  },
  content: {
    paddingHorizontal: 16,
    paddingBottom: 40,
    gap: 10,
  },
  card: {
    borderWidth: 1,
    borderRadius: 12,
    padding: 14,
    gap: 4,
  },
  cardLabel: {
    fontSize: 12,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginTop: 4,
  },
  cardText: {
    fontSize: 15,
    lineHeight: 21,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.6,
    marginTop: 12,
    marginHorizontal: 4,
  },
  chips: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  chip: {
    borderWidth: 1,
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  question: {
    fontSize: 16,
    lineHeight: 22,
  },
  answers: {
    flexDirection: "row",
    gap: 8,
    marginTop: 8,
  },
  answer: {
    borderWidth: 1,
    borderRadius: 16,
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  input: {
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 16,
    minHeight: 80,
    textAlignVertical: "top",
  },
  button: {
    height: 48,
    borderRadius: 24,
    alignItems: "center",
    justifyContent: "center",
  },
  buttonText: {
    fontSize: 16,
    fontWeight: "600",
  },
  stillGone: {
    alignItems: "center",
    padding: 12,
  },
});
