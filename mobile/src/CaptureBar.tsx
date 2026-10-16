import { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import type { Theme } from "./theme";

type Props = {
  theme: Theme;
  // Resolves true when the capture was saved, so the box can clear
  onSubmit: (text: string) => Promise<boolean>;
};

export function CaptureBar({ theme, onSubmit }: Props) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const canSend = text.trim().length > 0 && !sending;

  async function send() {
    if (!canSend) return;
    setSending(true);
    const saved = await onSubmit(text.trim());
    setSending(false);
    if (saved) setText("");
  }

  return (
    <View style={[styles.bar, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <TextInput
        value={text}
        onChangeText={setText}
        placeholder="What's on your mind?"
        placeholderTextColor={theme.muted}
        multiline
        editable={!sending}
        style={[styles.input, { color: theme.text }]}
      />
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Save thought"
        onPress={send}
        disabled={!canSend}
        style={[styles.send, { backgroundColor: theme.accent, opacity: canSend ? 1 : 0.4 }]}
      >
        {sending ? (
          <ActivityIndicator color={theme.accentText} />
        ) : (
          <Text style={[styles.sendText, { color: theme.accentText }]}>Save</Text>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 10,
    padding: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  input: {
    flex: 1,
    minHeight: 40,
    maxHeight: 120,
    fontSize: 16,
    paddingHorizontal: 8,
    paddingTop: 10,
    paddingBottom: 10,
  },
  send: {
    height: 40,
    minWidth: 64,
    paddingHorizontal: 16,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  sendText: {
    fontSize: 15,
    fontWeight: "600",
  },
});
