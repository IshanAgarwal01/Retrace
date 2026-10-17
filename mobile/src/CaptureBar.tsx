import { Ionicons } from "@expo/vector-icons";
import { useRef, useState } from "react";
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { Theme } from "./theme";
import { useVoice } from "./useVoice";

type Props = {
  theme: Theme;
  // Resolves true when the capture was saved, so the box can clear
  onSubmit: (text: string) => Promise<boolean>;
};

export function CaptureBar({ theme, onSubmit }: Props) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  // What was already typed when the mic started, so spoken words are added after it
  const typedBefore = useRef("");
  const voice = useVoice((spoken) => setText([typedBefore.current, spoken].filter(Boolean).join(" ")));
  const canSend = text.trim().length > 0 && !sending;

  async function send() {
    if (!canSend) return;
    if (voice.listening) voice.stop();
    setSending(true);
    const saved = await onSubmit(text.trim());
    setSending(false);
    if (saved) setText("");
  }

  function toggleMic() {
    if (!voice.listening) typedBefore.current = text.trim();
    voice.toggle();
  }

  return (
    <View style={styles.wrap}>
      {(voice.listening || voice.error) && (
        <View style={styles.hintRow}>
          {voice.listening && <View style={[styles.dot, { backgroundColor: theme.recording }]} />}
          <Text style={[styles.hint, { color: voice.error ? theme.danger : theme.muted }]}>
            {voice.error ?? "Listening… speak your thought, then tap the mic to stop"}
          </Text>
        </View>
      )}
      <View
        style={[
          styles.bar,
          {
            backgroundColor: theme.surface,
            borderColor: voice.listening ? theme.recording : theme.border,
            shadowColor: theme.shadow,
          },
        ]}
      >
        <TextInput
          value={text}
          onChangeText={setText}
          placeholder={voice.supported ? "Type or speak a thought…" : "Type a thought…"}
          placeholderTextColor={theme.faint}
          multiline
          editable={!sending}
          // On a computer, Enter saves and Shift+Enter starts a new line
          onKeyPress={(event) => {
            const e = event.nativeEvent as unknown as { key: string; shiftKey?: boolean };
            if (Platform.OS === "web" && e.key === "Enter" && !e.shiftKey) {
              (event as unknown as { preventDefault: () => void }).preventDefault();
              send();
            }
          }}
          style={[styles.input, { color: theme.text }]}
        />
        <View style={styles.actions}>
          {voice.supported && (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={voice.listening ? "Stop voice typing" : "Start voice typing"}
              onPress={toggleMic}
              disabled={sending}
              style={({ hovered }) => [
                styles.round,
                {
                  backgroundColor: voice.listening ? theme.recording : hovered ? theme.surfaceMuted : "transparent",
                },
              ]}
            >
              <Ionicons
                name={voice.listening ? "stop" : "mic-outline"}
                size={voice.listening ? 16 : 21}
                color={voice.listening ? "#FFFFFF" : theme.muted}
              />
            </Pressable>
          )}
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Save thought"
            onPress={send}
            disabled={!canSend}
            style={[styles.round, { backgroundColor: theme.accent, opacity: canSend ? 1 : 0.35 }]}
          >
            {sending ? (
              <ActivityIndicator size="small" color={theme.accentText} />
            ) : (
              <Ionicons name="arrow-up" size={20} color={theme.accentText} />
            )}
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 14,
    gap: 6,
  },
  hintRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 6,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  hint: {
    fontSize: 13,
  },
  bar: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 6,
    paddingLeft: 16,
    paddingRight: 6,
    paddingVertical: 6,
    borderWidth: 1.5,
    borderRadius: 26,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 1,
    shadowRadius: 16,
    elevation: 4,
  },
  input: {
    flex: 1,
    minHeight: 40,
    maxHeight: 140,
    fontSize: 16,
    paddingTop: 10,
    paddingBottom: 10,
    // Hide the browser's own focus ring; the rounded border already frames the box
    ...(Platform.OS === "web" ? ({ outlineStyle: "none" } as object) : {}),
  },
  actions: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  round: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
});
