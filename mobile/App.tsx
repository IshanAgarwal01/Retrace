import { Ionicons } from "@expo/vector-icons";
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
import { DatePrompt, type DateQuestion } from "./src/DatePrompt";
import { EntryRow } from "./src/EntryRow";
import { formatDue, groupEntries, typeLabel } from "./src/grouping";
import { RetraceScreen } from "./src/RetraceScreen";
import { SettingsScreen } from "./src/SettingsScreen";
import { useTheme, type Theme } from "./src/theme";
import { Column, IconButton } from "./src/ui";

export default function App() {
  return (
    <SafeAreaProvider>
      <Main />
    </SafeAreaProvider>
  );
}

function describeCapture(result: CaptureResult): string {
  const loop = result.loop ? `\n${result.loop}` : "";
  if (!result.ai_ok) return "Saved as a note (AI sorting was unavailable)" + loop;
  return result.items
    .map((item) => {
      const due = formatDue(item.due_at, item.all_day);
      return [`${typeLabel(item.type)}: ${item.title}`, item.course, due].filter(Boolean).join("  ·  ");
    })
    .join("\n") + loop;
}

// A ghost notification opens the web app at /?ghost=12 to go straight to Retrace
function ghostFromUrl(): number | undefined {
  if (Platform.OS !== "web") return undefined;
  const id = Number(new URLSearchParams(globalThis.location?.search ?? "").get("ghost"));
  if (!id) return undefined;
  // Tidy the address so a reload doesn't reopen it
  globalThis.history?.replaceState(null, "", globalThis.location.pathname);
  return id;
}

function greeting(): string {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

function Main() {
  const theme = useTheme();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [editingSettings, setEditingSettings] = useState(false);
  // null = not on the Retrace screen; otherwise the ghost being chased, if any
  const [retrace, setRetrace] = useState<{ ghostId?: number } | null>(() => {
    const ghostId = ghostFromUrl();
    return ghostId ? { ghostId } : null;
  });
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  // Tasks and reminders that came back without a due date, asked about one at a time
  const [dateQuestions, setDateQuestions] = useState<DateQuestion[]>([]);

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
      setLoaded(true);
    }
  }, [settings]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // The confirmation banner disappears on its own after a few seconds
  useEffect(() => {
    if (!banner) return;
    const timer = setTimeout(() => setBanner(null), 6000);
    return () => clearTimeout(timer);
  }, [banner]);

  const sections = useMemo(() => groupEntries(entries), [entries]);
  const counts = useMemo(() => {
    const count = (title: string) => sections.find((s) => s.title === title)?.data.length ?? 0;
    return { overdue: count("Overdue"), today: count("Today"), week: count("This week") };
  }, [sections]);

  async function capture(text: string): Promise<boolean> {
    if (!settings) return false;
    try {
      const result = await api.capture(settings, text);
      setBanner(describeCapture(result));
      setDateQuestions((waiting) => [
        ...waiting,
        ...result.items
          .filter((item) => result.needs_date?.includes(item.id))
          .map((item) => ({ id: item.id, title: item.title })),
      ]);
      setError(null);
      refresh();
      return true;
    } catch (e) {
      setError(errorMessage(e));
      return false;
    }
  }

  function dateAnswered(summary: string | null) {
    setDateQuestions((waiting) => waiting.slice(1));
    if (summary) {
      setBanner(summary);
      refresh();
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

  if (retrace) {
    return (
      <SafeAreaView style={[styles.screen, { backgroundColor: theme.background }]}>
        <StatusBar style="auto" />
        <RetraceScreen
          theme={theme}
          settings={settings}
          ghostId={retrace.ghostId}
          onDone={(message) => {
            setRetrace(null);
            if (message) setBanner(message);
            refresh();
          }}
        />
      </SafeAreaView>
    );
  }

  const today = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: theme.background }]} edges={["top", "left", "right"]}>
      <StatusBar style="auto" />
      <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <Column>
          <View style={styles.header}>
            <View style={styles.brand}>
              <View style={[styles.logo, { backgroundColor: theme.accent }]}>
                <Ionicons name="sparkles" size={16} color={theme.accentText} />
              </View>
              <View>
                <Text style={[styles.appName, { color: theme.text }]}>Retrace</Text>
                <Text style={[styles.date, { color: theme.muted }]}>
                  {greeting()} · {today}
                </Text>
              </View>
            </View>
            <View style={styles.headerButtons}>
              <IconButton theme={theme} icon="sync" label="Sync Carmen now" onPress={syncCarmen} busy={syncing} />
              <IconButton theme={theme} icon="settings-outline" label="Settings" onPress={() => setEditingSettings(true)} />
            </View>
          </View>

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
            ListHeaderComponent={
              <View style={styles.listHeader}>
                <View style={styles.stats}>
                  <Stat theme={theme} value={counts.overdue} label="overdue" color={theme.overdue} />
                  <Stat theme={theme} value={counts.today} label="due today" color={theme.today} />
                  <Stat theme={theme} value={counts.week} label="this week" color={theme.accent} />
                </View>

                <Pressable
                  accessibilityRole="button"
                  onPress={() => setRetrace({})}
                  style={({ hovered, pressed }) => [
                    styles.lost,
                    {
                      backgroundColor: theme.accentSoft,
                      borderColor: hovered ? theme.accent : "transparent",
                      opacity: pressed ? 0.85 : 1,
                    },
                  ]}
                >
                  <View style={[styles.lostIcon, { backgroundColor: theme.accent }]}>
                    <Ionicons name="bulb-outline" size={20} color={theme.accentText} />
                  </View>
                  <View style={styles.lostText}>
                    <Text style={[styles.lostTitle, { color: theme.text }]}>Lost a thought?</Text>
                    <Text style={[styles.lostSub, { color: theme.muted }]}>
                      Retrace what you were doing to get it back
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={20} color={theme.accent} />
                </Pressable>

                {error && (
                  <Pressable
                    onPress={() => setError(null)}
                    style={[styles.errorBox, { backgroundColor: theme.dangerSoft }]}
                  >
                    <Ionicons name="alert-circle-outline" size={18} color={theme.danger} />
                    <Text style={[styles.errorText, { color: theme.danger }]}>{error}</Text>
                  </Pressable>
                )}
              </View>
            }
            renderSectionHeader={({ section }) => (
              <View style={styles.sectionHeader}>
                <Text
                  style={[styles.sectionTitle, { color: section.title === "Overdue" ? theme.overdue : theme.text }]}
                >
                  {section.title}
                </Text>
                <View style={[styles.countBadge, { backgroundColor: theme.surfaceMuted }]}>
                  <Text style={[styles.countText, { color: theme.muted }]}>{section.data.length}</Text>
                </View>
              </View>
            )}
            renderItem={({ item, section }) => (
              <EntryRow entry={item} section={section.title} theme={theme} onComplete={complete} />
            )}
            ListEmptyComponent={
              !loaded || refreshing ? (
                <ActivityIndicator style={styles.loading} color={theme.accent} />
              ) : (
                <View style={styles.empty}>
                  <Ionicons name="checkmark-done-outline" size={36} color={theme.faint} />
                  <Text style={[styles.emptyTitle, { color: theme.text }]}>All clear</Text>
                  <Text style={[styles.emptyText, { color: theme.muted }]}>
                    Capture a thought below, or sync to pull in Carmen.
                  </Text>
                </View>
              )
            }
          />

          {banner && (
            <Pressable
              onPress={() => setBanner(null)}
              style={[styles.banner, { backgroundColor: theme.banner, shadowColor: theme.shadow }]}
            >
              <Ionicons name="checkmark-circle" size={20} color={theme.success} />
              <Text style={[styles.bannerText, { color: theme.bannerText }]}>{banner}</Text>
              <Ionicons name="close" size={18} color={theme.faint} />
            </Pressable>
          )}

          {dateQuestions.length > 0 && (
            <DatePrompt
              key={dateQuestions[0].id}
              theme={theme}
              settings={settings}
              question={dateQuestions[0]}
              remaining={dateQuestions.length - 1}
              onAnswered={dateAnswered}
            />
          )}

          <SafeAreaView edges={["bottom"]}>
            <CaptureBar theme={theme} onSubmit={capture} />
          </SafeAreaView>
        </Column>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Stat({ theme, value, label, color }: { theme: Theme; value: number; label: string; color: string }) {
  return (
    <View style={[styles.stat, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <Text style={[styles.statValue, { color: value ? color : theme.faint }]}>{value}</Text>
      <Text style={[styles.statLabel, { color: theme.muted }]}>{label}</Text>
    </View>
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
    paddingTop: 14,
    paddingBottom: 10,
  },
  brand: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  logo: {
    width: 36,
    height: 36,
    borderRadius: 11,
    alignItems: "center",
    justifyContent: "center",
  },
  appName: {
    fontSize: 22,
    fontWeight: "800",
    letterSpacing: -0.4,
  },
  date: {
    fontSize: 13,
    marginTop: 1,
  },
  headerButtons: {
    flexDirection: "row",
    gap: 2,
  },
  listContent: {
    paddingBottom: 12,
  },
  listHeader: {
    paddingHorizontal: 16,
    paddingTop: 6,
    gap: 12,
  },
  stats: {
    flexDirection: "row",
    gap: 10,
  },
  stat: {
    flex: 1,
    borderWidth: 1,
    borderRadius: 14,
    paddingVertical: 12,
    paddingHorizontal: 14,
  },
  statValue: {
    fontSize: 24,
    fontWeight: "800",
    letterSpacing: -0.5,
  },
  statLabel: {
    fontSize: 12.5,
    marginTop: 1,
  },
  lost: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    padding: 14,
    borderRadius: 16,
    borderWidth: 1.5,
  },
  lostIcon: {
    width: 40,
    height: 40,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  lostText: {
    flex: 1,
    gap: 2,
  },
  lostTitle: {
    fontSize: 16,
    fontWeight: "700",
  },
  lostSub: {
    fontSize: 13.5,
  },
  errorBox: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    padding: 12,
    borderRadius: 12,
  },
  errorText: {
    flex: 1,
    fontSize: 14,
  },
  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginHorizontal: 20,
    marginTop: 22,
    marginBottom: 10,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: "700",
  },
  countBadge: {
    minWidth: 22,
    paddingHorizontal: 7,
    paddingVertical: 1,
    borderRadius: 999,
    alignItems: "center",
  },
  countText: {
    fontSize: 12,
    fontWeight: "600",
  },
  loading: {
    marginTop: 60,
  },
  empty: {
    alignItems: "center",
    gap: 6,
    marginTop: 50,
    marginHorizontal: 32,
  },
  emptyTitle: {
    fontSize: 17,
    fontWeight: "700",
    marginTop: 4,
  },
  emptyText: {
    textAlign: "center",
    fontSize: 14.5,
    lineHeight: 21,
  },
  banner: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
    marginHorizontal: 16,
    marginBottom: 8,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: 14,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 1,
    shadowRadius: 18,
    elevation: 6,
  },
  bannerText: {
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
  },
});
