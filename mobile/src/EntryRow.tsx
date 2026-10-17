import { Ionicons } from "@expo/vector-icons";
import { useState } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

import type { Entry } from "./api";
import { formatDue, typeLabel } from "./grouping";
import { courseColor, type Theme } from "./theme";
import type { IconName } from "./ui";

type Props = {
  entry: Entry;
  section: string; // "Overdue", "Today", ... decides the due-date color
  theme: Theme;
  onComplete: (entry: Entry) => void;
};

const TYPE_ICONS: Record<string, IconName> = {
  assignment: "school-outline",
  task: "checkbox-outline",
  reminder: "alarm-outline",
  idea: "bulb-outline",
  song: "musical-notes-outline",
  note: "document-text-outline",
  question: "help-circle-outline",
};

export function EntryRow({ entry, section, theme, onComplete }: Props) {
  const [checking, setChecking] = useState(false);
  const due = formatDue(entry.due_at, entry.all_day);
  const dueColor = section === "Overdue" ? theme.overdue : section === "Today" ? theme.today : theme.muted;

  function check() {
    // Show the tick for a moment before the row disappears, so it feels done
    setChecking(true);
    setTimeout(() => onComplete(entry), 250);
  }

  return (
    <Pressable
      disabled={!entry.url}
      onPress={() => entry.url && Linking.openURL(entry.url)}
      style={({ hovered }) => [
        styles.row,
        {
          backgroundColor: theme.surface,
          borderColor: hovered && entry.url ? theme.accent : theme.border,
          opacity: checking ? 0.5 : 1,
        },
      ]}
    >
      <Pressable
        accessibilityRole="checkbox"
        accessibilityState={{ checked: checking }}
        accessibilityLabel={`Mark ${entry.title} done`}
        hitSlop={10}
        onPress={check}
        style={({ hovered }) => [
          styles.check,
          {
            borderColor: checking || hovered ? theme.success : theme.faint,
            backgroundColor: checking ? theme.success : "transparent",
          },
        ]}
      >
        {checking && <Ionicons name="checkmark" size={14} color="#FFFFFF" />}
      </Pressable>

      <View style={styles.body}>
        <Text
          style={[styles.title, { color: theme.text, textDecorationLine: checking ? "line-through" : "none" }]}
          numberOfLines={2}
        >
          {entry.title}
        </Text>
        <View style={styles.meta}>
          <View style={styles.metaItem}>
            <Ionicons name={TYPE_ICONS[entry.type] ?? "ellipse-outline"} size={13} color={theme.muted} />
            <Text style={[styles.metaText, { color: theme.muted }]}>{typeLabel(entry.type)}</Text>
          </View>
          {entry.course && (
            <View style={[styles.course, { backgroundColor: courseColor(entry.course) + "1F" }]}>
              <View style={[styles.courseDot, { backgroundColor: courseColor(entry.course) }]} />
              <Text style={[styles.courseText, { color: courseColor(entry.course) }]}>{entry.course}</Text>
            </View>
          )}
          {entry.place && (
            <View style={styles.metaItem}>
              <Ionicons name="location-outline" size={13} color={theme.muted} />
              <Text style={[styles.metaText, { color: theme.muted }]}>{entry.place}</Text>
            </View>
          )}
        </View>
      </View>

      {due ? (
        <View style={styles.due}>
          <Ionicons name="time-outline" size={13} color={dueColor} />
          <Text style={[styles.dueText, { color: dueColor }]}>{due}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    paddingVertical: 13,
    paddingHorizontal: 16,
    marginHorizontal: 16,
    marginBottom: 8,
    borderRadius: 14,
    borderWidth: 1,
  },
  check: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    alignItems: "center",
    justifyContent: "center",
  },
  body: {
    flex: 1,
    gap: 5,
  },
  title: {
    fontSize: 15.5,
    fontWeight: "500",
    lineHeight: 21,
  },
  meta: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 10,
  },
  metaItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  metaText: {
    fontSize: 12.5,
  },
  course: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 999,
  },
  courseDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  courseText: {
    fontSize: 12,
    fontWeight: "600",
  },
  due: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    maxWidth: 150,
  },
  dueText: {
    fontSize: 12.5,
    fontWeight: "500",
    textAlign: "right",
  },
});
