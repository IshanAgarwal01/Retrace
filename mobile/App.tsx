import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SectionList,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { api, errorMessage, loadSettings, type CaptureResult, type Entry, type Settings } from "./src/api";
import { CaptureBar } from "./src/CaptureBar";
import { EntryRow } from "./src/EntryRow";
import { formatDue, groupEntries, typeLabel } from "./src/grouping";
import { RetraceScreen } from "./src/RetraceScreen";
import { SettingsScreen } from "./src/SettingsScreen";
import { useTheme } from "./src/theme";

export default function App() {
  return (
    <SafeAreaProvider>
      <Main />
    </SafeAreaProvider>
  );
}

function describeCapture(result: CaptureResult): string {
  if (!result.ai_ok) return "Saved as a note (AI sorting was unavailable)";
  return result.items
    .map((item) => {
      const due = formatDue(item.due_at, item.all_day);
      return [`${typeLabel(item.type)}: ${item.title}`, item.course, due].filter(Boolean).join("  ·  ");
    })
    .join("\n");
}

function Main() {
  const theme = useTheme();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [editingSettings, setEditingSettings] = useState(false);
  const [retracing, setRetracing] = useState(false);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  useEffect(() => {
    loadSettings().then((saved) => {
      setSettings(saved);
      setSettingsLoaded(true);
    });
  }, []);

  const refresh = useCallback(async () => {
    if (!settings) return;
    setRefreshing(true);
    try {
      setEntries(await api.list(settings));
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setRefreshing(false);
    }
  }, [settings]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // The confirmation banner disappears on its own after a few seconds
  useEffect(() => {
    if (!banner) return;
    const timer = setTimeout(() => setBanner(null), 5000);
    return () => clearTimeout(timer);
  }, [banner]);

  const sections = useMemo(() => groupEntries(entries), [entries]);

  async function capture(text: string): Promise<boolean> {
    if (!settings) return false;
    try {
      const result = await api.capture(settings, text);
      setBanner(describeCapture(result));
      setError(null);
      refresh();
      return true;
    } catch (e) {
      setError(errorMessage(e));
      return false;
    }
  }

  async function complete(entry: Entry) {
    if (!settings) return;
    // Remove it right away so the tap feels instant; put it back if the server says no
    setEntries((current) => current.filter((e) => !(e.kind === entry.kind && e.id === entry.id)));
    try {
      if (entry.kind === "item") await api.completeItem(settings, entry.id);
      else await api.completeAssignment(settings, entry.id);
    } catch (e) {
      setError(errorMessage(e));
      refresh();
    }
  }

  async function syncCarmen() {
    if (!settings) return;
    setSyncing(true);
    try {
      const result = await api.syncCarmen(settings);
      const moved = result.changes.length;
      setBanner(
        `Carmen synced: ${result.added} new` + (moved ? `, ${moved} deadline change${moved === 1 ? "" : "s"}` : ""),
      );
      refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSyncing(false);
    }
  }

  if (!settingsLoaded) {
    return (
      <View style={[styles.center, { backgroundColor: theme.background }]}>
        <ActivityIndicator color={theme.accent} />
      </View>
    );
  }

  if (!settings || editingSettings) {
    return (
      <SafeAreaView style={[styles.screen, { backgroundColor: theme.background }]}>
        <StatusBar style="auto" />
        <SettingsScreen
          theme={theme}
          initial={settings}
          onSaved={(saved) => {
            setSettings(saved);
            setEditingSettings(false);
          }}
          onCancel={settings ? () => setEditingSettings(false) : undefined}
        />
      </SafeAreaView>
    );
  }

  if (retracing) {
    return (
      <SafeAreaView style={[styles.screen, { backgroundColor: theme.background }]}>
        <StatusBar style="auto" />
        <RetraceScreen
          theme={theme}
          settings={settings}
          onDone={(message) => {
            setRetracing(false);
            if (message) setBanner(message);
            refresh();
          }}
        />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: theme.background }]} edges={["top", "left", "right"]}>
      <StatusBar style="auto" />
      <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View style={styles.header}>
          <Text style={[styles.appName, { color: theme.text }]}>Retrace</Text>
          <View style={styles.headerButtons}>
            <Pressable accessibilityRole="button" onPress={syncCarmen} disabled={syncing} hitSlop={8}>
              <Text style={[styles.headerButton, { color: theme.accent }]}>{syncing ? "Syncing…" : "Sync"}</Text>
            </Pressable>
            <Pressable accessibilityRole="button" onPress={() => setEditingSettings(true)} hitSlop={8}>
              <Text style={[styles.headerButton, { color: theme.accent }]}>Settings</Text>
            </Pressable>
          </View>
        </View>
        <Pressable
          accessibilityRole="button"
          onPress={() => setRetracing(true)}
          style={[styles.lostButton, { borderColor: theme.accent }]}
        >
          <Text style={[styles.lostButtonText, { color: theme.accent }]}>I lost a thought</Text>
        </Pressable>

        {error && (
          <Pressable onPress={() => setError(null)} style={styles.errorBox}>
            <Text style={[styles.errorText, { color: theme.danger }]}>{error}</Text>
          </Pressable>
        )}

        <SectionList
          sections={sections}
          keyExtractor={(entry) => `${entry.kind}-${entry.id}`}
          refreshing={refreshing}
          onRefresh={refresh}
          stickySectionHeadersEnabled={false}
          // Draw every row up front. By default only the first ~10 render until you
          // scroll, and a short list on a tall screen can't scroll, so the rest never
          // appeared. A few hundred rows is cheap to draw at once.
          initialNumToRender={500}
          contentContainerStyle={styles.listContent}
          renderSectionHeader={({ section }) => (
            <Text
              style={[
                styles.sectionTitle,
                { color: section.title === "Overdue" ? theme.overdue : theme.muted },
              ]}
            >
              {section.title}
            </Text>
          )}
          renderItem={({ item, section }) => (
            <EntryRow entry={item} overdue={section.title === "Overdue"} theme={theme} onComplete={complete} />
          )}
          ListEmptyComponent={
            refreshing ? undefined : (
              <Text style={[styles.empty, { color: theme.muted }]}>
                Nothing here yet. Type a thought below, or tap Sync to pull in Carmen.
              </Text>
            )
          }
        />

        {banner && (
          <Pressable onPress={() => setBanner(null)} style={[styles.banner, { backgroundColor: theme.banner }]}>
            <Text style={[styles.bannerText, { color: theme.bannerText }]}>{banner}</Text>
          </Pressable>
        )}

        <SafeAreaView edges={["bottom"]} style={{ backgroundColor: theme.surface }}>
          <CaptureBar theme={theme} onSubmit={capture} />
        </SafeAreaView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 12,
  },
  appName: {
    fontSize: 28,
    fontWeight: "700",
  },
  headerButtons: {
    flexDirection: "row",
    gap: 18,
  },
  headerButton: {
    fontSize: 16,
    fontWeight: "500",
  },
  lostButton: {
    marginHorizontal: 16,
    marginBottom: 4,
    height: 40,
    borderWidth: 1.5,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  lostButtonText: {
    fontSize: 15,
    fontWeight: "600",
  },
  errorBox: {
    marginHorizontal: 16,
    marginBottom: 8,
  },
  errorText: {
    fontSize: 14,
  },
  listContent: {
    paddingBottom: 16,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.6,
    marginHorizontal: 20,
    marginTop: 16,
    marginBottom: 8,
  },
  empty: {
    textAlign: "center",
    marginTop: 60,
    marginHorizontal: 32,
    fontSize: 15,
    lineHeight: 22,
  },
  banner: {
    marginHorizontal: 16,
    marginBottom: 10,
    padding: 14,
    borderRadius: 12,
  },
  bannerText: {
    fontSize: 14,
    lineHeight: 20,
  },
});
