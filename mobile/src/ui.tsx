// Small building blocks shared by every screen
import { Ionicons } from "@expo/vector-icons";
import type { ComponentProps, ReactNode } from "react";
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, View, type ViewStyle } from "react-native";

import { MAX_WIDTH, type Theme } from "./theme";

export type IconName = ComponentProps<typeof Ionicons>["name"];

// A centered column, so the app doesn't stretch across a wide computer screen
export function Column({ children, style }: { children: ReactNode; style?: ViewStyle }) {
  return <View style={[styles.column, style]}>{children}</View>;
}

export function IconButton({
  theme,
  icon,
  label,
  onPress,
  busy = false,
  disabled = false,
}: {
  theme: Theme;
  icon: IconName;
  label: string; // read out by screen readers and shown as a tooltip on the web
  onPress: () => void;
  busy?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      // @ts-expect-error `title` is a web-only prop that gives the button a tooltip
      title={Platform.OS === "web" ? label : undefined}
      onPress={onPress}
      disabled={disabled || busy}
      hitSlop={6}
      style={({ hovered, pressed }) => [
        styles.iconButton,
        { backgroundColor: hovered || pressed ? theme.surfaceMuted : "transparent", opacity: disabled ? 0.4 : 1 },
      ]}
    >
      {busy ? <ActivityIndicator size="small" color={theme.muted} /> : <Ionicons name={icon} size={21} color={theme.muted} />}
    </Pressable>
  );
}

export function Chip({
  theme,
  label,
  icon,
  selected = false,
  onPress,
}: {
  theme: Theme;
  label: string;
  icon?: IconName;
  selected?: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={({ hovered }) => [
        styles.chip,
        {
          backgroundColor: selected ? theme.accent : hovered ? theme.accentSoft : theme.surface,
          borderColor: selected ? theme.accent : theme.border,
        },
      ]}
    >
      {icon && <Ionicons name={icon} size={15} color={selected ? theme.accentText : theme.accent} />}
      <Text style={[styles.chipText, { color: selected ? theme.accentText : theme.text }]}>{label}</Text>
    </Pressable>
  );
}

export function PrimaryButton({
  theme,
  label,
  onPress,
  busy = false,
  disabled = false,
}: {
  theme: Theme;
  label: string;
  onPress: () => void;
  busy?: boolean;
  disabled?: boolean;
}) {
  const off = disabled || busy;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={off}
      style={({ hovered, pressed }) => [
        styles.primary,
        { backgroundColor: theme.accent, opacity: disabled ? 0.45 : pressed ? 0.85 : hovered ? 0.92 : 1 },
      ]}
    >
      {busy ? <ActivityIndicator color={theme.accentText} /> : <Text style={[styles.primaryText, { color: theme.accentText }]}>{label}</Text>}
    </Pressable>
  );
}

export function Card({ theme, children, style }: { theme: Theme; children: ReactNode; style?: ViewStyle }) {
  return (
    <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border, shadowColor: theme.shadow }, style]}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  column: {
    flex: 1,
    width: "100%",
    maxWidth: MAX_WIDTH,
    alignSelf: "center",
  },
  iconButton: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: "center",
    justifyContent: "center",
  },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 13,
    paddingVertical: 7,
  },
  chipText: {
    fontSize: 14,
    fontWeight: "500",
  },
  primary: {
    height: 46,
    paddingHorizontal: 22,
    borderRadius: 23,
    alignItems: "center",
    justifyContent: "center",
  },
  primaryText: {
    fontSize: 15,
    fontWeight: "600",
  },
  card: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 16,
    padding: 16,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 10,
    elevation: 2,
  },
});
