import { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { api, errorMessage, saveSettings, type Settings } from "./api";
import type { Theme } from "./theme";

type Props = {
  theme: Theme;
  initial: Settings | null;
  onSaved: (settings: Settings) => void;
  onCancel?: () => void;
};

export function SettingsScreen({ theme, initial, onSaved, onCancel }: Props) {
  const [serverUrl, setServerUrl] = useState(initial?.serverUrl ?? "");
  const [apiKey, setApiKey] = useState(initial?.apiKey ?? "");
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function testAndSave() {
    const candidate = { serverUrl: serverUrl.trim(), apiKey: apiKey.trim() };
    setTesting(true);
    setError(null);
    try {
      await api.list(candidate); // proves both the address and the key work
      await saveSettings(candidate);
      onSaved(candidate);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setTesting(false);
    }
  }

  const inputStyle = [styles.input, { color: theme.text, borderColor: theme.border, backgroundColor: theme.surface }];

  return (
    <View style={styles.container}>
      <Text style={[styles.heading, { color: theme.text }]}>Connect to your server</Text>
      <Text style={[styles.help, { color: theme.muted }]}>
        Server address is where your Retrace server runs, for example http://192.168.1.20:8000.
        The API key is RETRACE_API_KEY from server/.env.
      </Text>

      <Text style={[styles.label, { color: theme.muted }]}>Server address</Text>
      <TextInput
        value={serverUrl}
        onChangeText={setServerUrl}
        placeholder="http://192.168.1.20:8000"
        placeholderTextColor={theme.muted}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        style={inputStyle}
      />

      <Text style={[styles.label, { color: theme.muted }]}>API key</Text>
      <TextInput
        value={apiKey}
        onChangeText={setApiKey}
        placeholder="RETRACE_API_KEY"
        placeholderTextColor={theme.muted}
        autoCapitalize="none"
        autoCorrect={false}
        secureTextEntry
        style={inputStyle}
      />

      {error && <Text style={[styles.error, { color: theme.danger }]}>{error}</Text>}

      <Pressable
        accessibilityRole="button"
        onPress={testAndSave}
        disabled={testing || !serverUrl.trim() || !apiKey.trim()}
        style={[styles.button, { backgroundColor: theme.accent }]}
      >
        {testing ? (
          <ActivityIndicator color={theme.accentText} />
        ) : (
          <Text style={[styles.buttonText, { color: theme.accentText }]}>Test and save</Text>
        )}
      </Pressable>

      {onCancel && (
        <Pressable accessibilityRole="button" onPress={onCancel} style={styles.cancel}>
          <Text style={{ color: theme.muted, fontSize: 15 }}>Cancel</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    gap: 8,
  },
  heading: {
    fontSize: 24,
    fontWeight: "700",
    marginTop: 12,
  },
  help: {
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 12,
  },
  label: {
    fontSize: 13,
    fontWeight: "600",
    marginTop: 8,
  },
  input: {
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 16,
  },
  error: {
    fontSize: 14,
    marginTop: 8,
  },
  button: {
    marginTop: 16,
    height: 48,
    borderRadius: 24,
    alignItems: "center",
    justifyContent: "center",
  },
  buttonText: {
    fontSize: 16,
    fontWeight: "600",
  },
  cancel: {
    alignItems: "center",
    padding: 12,
  },
});
