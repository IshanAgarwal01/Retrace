import { useColorScheme } from "react-native";

const light = {
  background: "#F5F5F9",
  surface: "#FFFFFF",
  surfaceMuted: "#F0F0F6",
  text: "#18181B",
  muted: "#6B6B76",
  faint: "#A1A1AA",
  border: "#E6E6EE",
  accent: "#5046E5",
  accentSoft: "#EEEDFD",
  accentText: "#FFFFFF",
  danger: "#C53030",
  dangerSoft: "#FDECEC",
  overdue: "#C53030",
  today: "#B45309",
  todaySoft: "#FEF3E2",
  success: "#15803D",
  assignment: "#7C3AED",
  banner: "#18181B",
  bannerText: "#FFFFFF",
  shadow: "rgba(24, 24, 40, 0.08)",
  recording: "#E11D48",
};

const dark: typeof light = {
  background: "#0F0F14",
  surface: "#1A1A22",
  surfaceMuted: "#23232D",
  text: "#EDEDF2",
  muted: "#A1A1B0",
  faint: "#6B6B78",
  border: "#2A2A35",
  accent: "#8B85FF",
  accentSoft: "#26244A",
  accentText: "#0F0F14",
  danger: "#F59090",
  dangerSoft: "#3A1C1F",
  overdue: "#F59090",
  today: "#F5B565",
  todaySoft: "#3A2A14",
  success: "#6CD49A",
  assignment: "#B79CFF",
  banner: "#EDEDF2",
  bannerText: "#0F0F14",
  shadow: "rgba(0, 0, 0, 0.4)",
  recording: "#FB7185",
};

export type Theme = typeof light;

export function useTheme(): Theme {
  return useColorScheme() === "dark" ? dark : light;
}

// Each course gets its own steady color, picked from its name
const COURSE_COLORS = ["#2563EB", "#0D9488", "#D97706", "#DB2777", "#7C3AED", "#059669", "#DC2626", "#4F46E5"];

export function courseColor(course: string): string {
  let hash = 0;
  for (const char of course) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return COURSE_COLORS[hash % COURSE_COLORS.length];
}

// The content column never gets wider than this, so it reads well on a big screen
export const MAX_WIDTH = 760;
