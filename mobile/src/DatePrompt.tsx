import { Ionicons } from "@expo/vector-icons";
import { useState } from "react";
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { api, errorMessage, type Settings } from "./api";
import type { Theme } from "./theme";
import { Card, Chip } from "./ui";

export type DateQuestion = { id: number; title: string };

type Props = {
  theme: Theme;
  settings: Settings;
  question: DateQuestion;
  remaining: number; // how many more questions wait after this one
  // `summary` is the server's readable line for the item once dated; null if skipped
  onAnswered: (summary: string | null) => void;
};

const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

// "YYYY-MM-DD" for a day in the phone's or computer's own time zone
function isoDay(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function daysFromNow(days: number): Date {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date;
}

// The one-tap answers: today, tomorrow, the coming Friday, and next Monday
function quickPicks(): { label: string; date: string }[] {
  const today = new Date().getDay();
  const toFriday = (5 - today + 7) % 7 || 7;
  const toMonday = (1 - today + 7) % 7 || 7;
  const picks = [
    { label: "Today", date: isoDay(daysFromNow(0)) },
    { label: "Tomorrow", date: isoDay(daysFromNow(1)) },
  ];
  if (toFriday > 1) picks.push({ label: today === 5 ? "Next Friday" : "Friday", date: isoDay(daysFromNow(toFriday)) });
  if (toMonday > 1) {
    picks.push({ label: today === 1 ? "Next Monday" : WEEKDAYS[1], date: isoDay(daysFromNow(toMonday)) });
  }
  return picks;
}

export function DatePrompt({ theme, settings, question, remaining, onAnswered }: Props) {
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function answer(due: { date: string } | { text: string }) {
    setSaving(true);
    setError(null);
    try {
      const result = await api.setDue(settings, question.id, due);
      setText("");
      onAnswered(result.summary);
    } catch (e) {
      // e.g. "Couldn't find a date in that" - stay on the question so they can try again
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card theme={theme} style={styles.card}>
      <View style={styles.header}>
        <View style={[styles.badge, { backgroundColor: theme.todaySoft }]}>
          <Ionicons name="calendar-outline" size={18} color={theme.today} />
        </View>
        <View style={styles.headerText}>
          <Text style={[styles.title, { color: theme.text }]}>When is this due?</Text>
          <Text style={[styles.subject, { color: theme.muted }]} numberOfLines={2}>
            {question.title}
            {remaining > 0 ? `  ·  ${remaining} more after this` : ""}
          </Text>
        </View>
        {saving && <ActivityIndicator color={theme.accent} />}
      </View>

      <View style={styles.picks}>
        {quickPicks().map((pick) => (
          <Chip key={pick.label} theme={theme} label={pick.label} onPress={() => answer({ date: pick.date })} />
        ))}
      </View>

      <View style={[styles.inputRow, { borderColor: error ? theme.danger : theme.border, backgroundColor: theme.surfaceMuted }]}>
        <TextInput
          value={text}
          onChangeText={setText}
          placeholder="Or type it: next tuesday 3pm, 10/24, end of month…"
          placeholderTextColor={theme.faint}
          editable={!saving}
          onSubmitEditing={() => text.trim() && answer({ text: text.trim() })}
          style={[styles.input, { color: theme.text }]}
        />
        <Pressable
          accessibilityRole="button"
          onPress={() => answer({ text: text.trim() })}
          disabled={saving || !text.trim()}
          style={[styles.set, { backgroundColor: theme.accent, opacity: text.trim() ? 1 : 0.35 }]}
        >
          <Text style={[styles.setText, { color: theme.accentText }]}>Set</Text>
        </Pressable>
      </View>

      {error && <Text style={[styles.error, { color: theme.danger }]}>{error}</Text>}

      <Pressable accessibilityRole="button" onPress={() => onAnswered(null)} disabled={saving} style={styles.skip}>
        <Text style={[styles.skipText, { color: theme.muted }]}>No due date</Text>
      </Pressable>
    </Card>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 16,
    marginBottom: 4,
    gap: 14,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  badge: {
    width: 38,
    height: 38,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  headerText: {
    flex: 1,
    gap: 2,
  },
  title: {
    fontSize: 16,
    fontWeight: "700",
  },
  subject: {
    fontSize: 14,
  },
  picks: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderRadius: 12,
    paddingLeft: 12,
    paddingRight: 4,
  },
  input: {
    flex: 1,
    fontSize: 15,
    paddingVertical: 10,
    ...(Platform.OS === "web" ? ({ outlineStyle: "none" } as object) : {}),
  },
  set: {
    height: 34,
    paddingHorizontal: 16,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  setText: {
    fontSize: 14,
    fontWeight: "600",
  },
  error: {
    fontSize: 13.5,
    marginTop: -6,
  },
  skip: {
    alignSelf: "flex-start",
    paddingVertical: 2,
  },
  skipText: {
    fontSize: 14,
    textDecorationLine: "underline",
  },
});
