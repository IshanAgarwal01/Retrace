import { Ionicons } from "@expo/vector-icons";
import { useState } from "react";
import { Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { api, errorMessage, saveSettings, type Settings } from "./api";
import type { Theme } from "./theme";
import { Card, PrimaryButton } from "./ui";

type Props = {
  theme: Theme;
  initial: Settings | null;
  onSaved: (settings: Settings) => void;
  onCancel?: () => void;
};

export function SettingsScreen({ theme, initial, onSaved, onCancel }: Props) {
  // On the web the app is served by the Retrace server itself, so its own address is the answer
  const defaultUrl = Platform.OS === "web" ? globalThis.location?.origin ?? "" : "";
  const [serverUrl, setServerUrl] = useState(initial?.serverUrl ?? defaultUrl);
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

  const inputStyle = [
    styles.input,
    { color: theme.text, borderColor: theme.border, backgroundColor: theme.surfaceMuted },
  ];

  return (
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      <View style={styles.brand}>
        <View style={[styles.logo, { backgroundColor: theme.accent }]}>
          <Ionicons name="sparkles" size={24} color={theme.accentText} />
        </View>
        <Text style={[styles.appName, { color: theme.text }]}>Retrace</Text>
        <Text style={[styles.tagline, { color: theme.muted }]}>Catch every thought. Get back the ones you lose.</Text>
      </View>

      <Card theme={theme} style={styles.card}>
        <Text style={[styles.heading, { color: theme.text }]}>Connect to your server</Text>
        <Text style={[styles.help, { color: theme.muted }]}>
          The address is usually filled in for you. The API key is RETRACE_API_KEY from your server settings
          (line 2 of server/.env).
        </Text>

        <Text style={[styles.label, { color: theme.muted }]}>Server address</Text>
        <TextInput
          value={serverUrl}
          onChangeText={setServerUrl}
          placeholder="https://retrace-xxxx.onrender.com"
          placeholderTextColor={theme.faint}
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
          placeholderTextColor={theme.faint}
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
          onSubmitEditing={testAndSave}
          style={inputStyle}
        />

        {error && (
          <View style={[styles.errorBox, { backgroundColor: theme.dangerSoft }]}>
            <Ionicons name="alert-circle-outline" size={18} color={theme.danger} />
            <Text style={[styles.errorText, { color: theme.danger }]}>{error}</Text>
          </View>
        )}

        <View style={styles.buttons}>
          <PrimaryButton
            theme={theme}
            label="Test and save"
            onPress={testAndSave}
            busy={testing}
            disabled={!serverUrl.trim() || !apiKey.trim()}
          />
          {onCancel && (
            <Pressable accessibilityRole="button" onPress={onCancel} style={styles.cancel}>
              <Text style={{ color: theme.muted, fontSize: 15 }}>Cancel</Text>
            </Pressable>
          )}
        </View>
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    justifyContent: "center",
    padding: 20,
    width: "100%",
    maxWidth: 480,
    alignSelf: "center",
    gap: 24,
  },
  brand: {
    alignItems: "center",
    gap: 8,
  },
  logo: {
    width: 56,
    height: 56,
    borderRadius: 17,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 4,
  },
  appName: {
    fontSize: 28,
    fontWeight: "800",
    letterSpacing: -0.6,
  },
  tagline: {
    fontSize: 15,
    textAlign: "center",
  },
  card: {
    gap: 8,
    padding: 22,
  },
  heading: {
    fontSize: 18,
    fontWeight: "700",
  },
  help: {
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 6,
  },
  label: {
    fontSize: 13,
    fontWeight: "600",
    marginTop: 8,
  },
  input: {
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
  },
  errorBox: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    padding: 12,
    borderRadius: 12,
    marginTop: 8,
  },
  errorText: {
    flex: 1,
    fontSize: 14,
  },
  buttons: {
    marginTop: 14,
    gap: 4,
  },
  cancel: {
    alignItems: "center",
    padding: 12,
  },
});
