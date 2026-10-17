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

import { Ionicons } from "@expo/vector-icons";

import { api, errorMessage, type Guess, type RetraceEnd, type RetraceSession, type Settings } from "./api";
import { formatDue } from "./grouping";
import type { Theme } from "./theme";
import { Card, Chip, Column, IconButton, PrimaryButton, type IconName } from "./ui";
import { useVoice } from "./useVoice";

const CHIP_ICONS: Record<string, IconName> = {
  task: "checkbox-outline",
  buy: "cart-outline",
  "tell someone": "chatbubble-outline",
  idea: "bulb-outline",
  song: "musical-notes-outline",
  worry: "cloud-outline",
  "class thing": "school-outline",
};

type Props = {
  theme: Theme;
  settings: Settings;
  // Set when opened from a notification about a thought lost earlier
  ghostId?: number;
  // Called when the screen closes; `message` is shown as a banner on the main list
  onDone: (message: string | null) => void;
};

// What you said about a guess: it was the thought, or it was close
type Mark = "yes" | "close";

export function RetraceScreen({ theme, settings, ghostId, onDone }: Props) {
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
  const typedBefore = useRef("");
  const voice = useVoice((spoken) => setText([typedBefore.current, spoken].filter(Boolean).join(" ")));

  useEffect(() => {
    api
      .startRetrace(settings, ghostId)
      .then(setSession)
      .catch((e) => setError(errorMessage(e)));
  }, [settings, ghostId]);

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
      const result = await api.endRetrace(settings, session.id, { ...end, ghost_id: ghostId });
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
    if (session) {
      api.endRetrace(settings, session.id, { outcome: "gave_up", cue, ghost_id: ghostId }).catch(() => {});
    }
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

  function toggleMic() {
    if (!voice.listening) typedBefore.current = text.trim();
    voice.toggle();
  }

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <Column>
        <View style={styles.header}>
          <IconButton theme={theme} icon="chevron-back" label="Back to your list" onPress={close} />
          <View style={styles.headerText}>
            <Text style={[styles.title, { color: theme.text }]}>Lost a thought?</Text>
            <Text style={[styles.subtitle, { color: theme.muted }]}>Let's retrace what you were doing</Text>
          </View>
        </View>

        {error && <Text style={[styles.error, { color: theme.danger }]}>{error}</Text>}

        {!session && !error && <ActivityIndicator style={styles.loading} color={theme.accent} />}

        {session && context && (
          <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
            <Card theme={theme} style={styles.contextCard}>
              {context.ghost && (
                <ContextLine
                  theme={theme}
                  icon="sparkles"
                  label="The thought you lost"
                  text={[context.ghost.place, formatDue(context.ghost.lost_at, false)].filter(Boolean).join(" · ")}
                />
              )}
              <ContextLine
                theme={theme}
                icon="location-outline"
                label="Where you were"
                text={context.place ? `${context.place.place} · ${formatDue(context.place.at, false)}` : "No place recorded yet"}
              />
              {context.recent_captures.length > 0 && (
                <ContextLine
                  theme={theme}
                  icon="time-outline"
                  label="What you captured lately"
                  text={context.recent_captures.slice(0, 3).map((c) => c.title).join(" · ")}
                />
              )}
              {context.due_soon.length > 0 && (
                <ContextLine
                  theme={theme}
                  icon="calendar-outline"
                  label="Due soon"
                  text={context.due_soon.slice(0, 3).map((e) => e.title).join(" · ")}
                />
              )}
            </Card>

            <Text style={[styles.sectionTitle, { color: theme.text }]}>What kind of thing was it?</Text>
            <View style={styles.chips}>
              {session.chips.map((name) => (
                <Chip
                  key={name}
                  theme={theme}
                  label={name}
                  icon={CHIP_ICONS[name]}
                  selected={chip === name}
                  onPress={() => pickChip(name)}
                />
              ))}
            </View>

            {guesses.length > 0 && <Text style={[styles.sectionTitle, { color: theme.text }]}>Maybe it was…</Text>}
            {guesses.map((guess) => {
              const mark = marks[guess.ref];
              return (
                <Card key={guess.ref} theme={theme} style={mark ? { borderColor: theme.accent, borderWidth: 1.5 } : undefined}>
                  <Text style={[styles.question, { color: theme.text }]}>{guess.question}</Text>
                  <View style={styles.answers}>
                    <AnswerButton theme={theme} label="Yes" icon="checkmark" active={mark === "yes"} onPress={() => markGuess(guess, "yes")} />
                    <AnswerButton
                      theme={theme}
                      label="No"
                      icon="close"
                      onPress={() => setHidden((current) => new Set(current).add(guess.ref))}
                    />
                    <AnswerButton
                      theme={theme}
                      label="Close"
                      icon="ellipsis-horizontal"
                      active={mark === "close"}
                      onPress={() => markGuess(guess, "close")}
                    />
                  </View>
                </Card>
              );
            })}

            <Text style={[styles.sectionTitle, { color: theme.text }]}>Got it?</Text>
            <View
              style={[
                styles.inputBox,
                { borderColor: voice.listening ? theme.recording : theme.border, backgroundColor: theme.surface },
              ]}
            >
              <TextInput
                ref={input}
                value={text}
                onChangeText={setText}
                placeholder={voice.supported ? "Type or say the thought before it slips away again" : "Type the thought before it slips away again"}
                placeholderTextColor={theme.faint}
                multiline
                editable={!saving}
                style={[styles.input, { color: theme.text }]}
              />
              {voice.supported && (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={voice.listening ? "Stop voice typing" : "Start voice typing"}
                  onPress={toggleMic}
                  style={[styles.mic, { backgroundColor: voice.listening ? theme.recording : theme.surfaceMuted }]}
                >
                  <Ionicons name={voice.listening ? "stop" : "mic-outline"} size={voice.listening ? 15 : 19} color={voice.listening ? "#FFFFFF" : theme.muted} />
                </Pressable>
              )}
            </View>
            {voice.error && <Text style={[styles.error, { color: theme.danger }]}>{voice.error}</Text>}

            <PrimaryButton theme={theme} label="Got it" onPress={recover} busy={saving} disabled={!text.trim()} />
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
      </Column>
    </KeyboardAvoidingView>
  );
}

function ContextLine({ theme, icon, label, text }: { theme: Theme; icon: IconName; label: string; text: string }) {
  return (
    <View style={styles.contextLine}>
      <View style={[styles.contextIcon, { backgroundColor: theme.accentSoft }]}>
        <Ionicons name={icon} size={16} color={theme.accent} />
      </View>
      <View style={styles.contextText}>
        <Text style={[styles.cardLabel, { color: theme.muted }]}>{label}</Text>
        <Text style={[styles.cardText, { color: theme.text }]}>{text}</Text>
      </View>
    </View>
  );
}

function AnswerButton({
  theme,
  label,
  icon,
  active = false,
  onPress,
}: {
  theme: Theme;
  label: string;
  icon: IconName;
  active?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ hovered }) => [
        styles.answer,
        {
          borderColor: active ? theme.accent : theme.border,
          backgroundColor: active ? theme.accent : hovered ? theme.surfaceMuted : "transparent",
        },
      ]}
    >
      <Ionicons name={icon} size={15} color={active ? theme.accentText : theme.muted} />
      <Text style={{ color: active ? theme.accentText : theme.text, fontSize: 14, fontWeight: "600" }}>{label}</Text>
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
    gap: 8,
    paddingHorizontal: 12,
    paddingTop: 14,
    paddingBottom: 12,
  },
  headerText: {
    gap: 1,
  },
  title: {
    fontSize: 22,
    fontWeight: "800",
    letterSpacing: -0.4,
  },
  subtitle: {
    fontSize: 13.5,
  },
  loading: {
    marginTop: 60,
  },
  error: {
    fontSize: 14,
    marginHorizontal: 20,
    marginBottom: 4,
  },
  content: {
    paddingHorizontal: 16,
    paddingBottom: 40,
    gap: 10,
  },
  contextCard: {
    gap: 14,
  },
  contextLine: {
    flexDirection: "row",
    gap: 12,
  },
  contextIcon: {
    width: 30,
    height: 30,
    borderRadius: 9,
    alignItems: "center",
    justifyContent: "center",
  },
  contextText: {
    flex: 1,
    gap: 2,
  },
  cardLabel: {
    fontSize: 12,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  cardText: {
    fontSize: 15,
    lineHeight: 21,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: "700",
    marginTop: 14,
    marginHorizontal: 4,
  },
  chips: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  question: {
    fontSize: 16,
    lineHeight: 22,
    fontWeight: "500",
  },
  answers: {
    flexDirection: "row",
    gap: 8,
    marginTop: 12,
  },
  answer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 7,
  },
  inputBox: {
    flexDirection: "row",
    alignItems: "flex-start",
    borderWidth: 1.5,
    borderRadius: 14,
    paddingLeft: 14,
    paddingRight: 8,
    paddingVertical: 8,
  },
  input: {
    flex: 1,
    fontSize: 16,
    minHeight: 80,
    paddingVertical: 6,
    textAlignVertical: "top",
    ...(Platform.OS === "web" ? ({ outlineStyle: "none" } as object) : {}),
  },
  mic: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  stillGone: {
    alignItems: "center",
    padding: 12,
  },
});
