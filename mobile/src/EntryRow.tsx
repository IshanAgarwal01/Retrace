import { Linking, Pressable, StyleSheet, Text, View } from "react-native";

import type { Entry } from "./api";
import { formatDue, typeLabel } from "./grouping";
import type { Theme } from "./theme";

type Props = {
  entry: Entry;
  overdue: boolean;
  theme: Theme;
  onComplete: (entry: Entry) => void;
};

export function EntryRow({ entry, overdue, theme, onComplete }: Props) {
  const due = formatDue(entry.due_at, entry.all_day);
  const isAssignment = entry.kind === "assignment";
  const details = [typeLabel(entry.type), entry.course, due, entry.place].filter(Boolean).join("  ·  ");

  return (
    <View style={[styles.row, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <Pressable
        accessibilityRole="checkbox"
        accessibilityLabel={`Mark ${entry.title} done`}
        hitSlop={12}
        onPress={() => onComplete(entry)}
        style={[styles.check, { borderColor: isAssignment ? theme.assignment : theme.accent }]}
      />
      <Pressable
        style={styles.body}
        disabled={!entry.url}
        onPress={() => entry.url && Linking.openURL(entry.url)}
      >
        <Text style={[styles.title, { color: theme.text }]}>{entry.title}</Text>
        <Text style={[styles.details, { color: overdue ? theme.overdue : theme.muted }]}>{details}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    paddingVertical: 12,
    paddingHorizontal: 14,
    marginHorizontal: 16,
    marginBottom: 8,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
  },
  check: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
  },
  body: {
    flex: 1,
    gap: 3,
  },
  title: {
    fontSize: 16,
    fontWeight: "500",
  },
  details: {
    fontSize: 13,
  },
});
