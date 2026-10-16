import { useColorScheme } from "react-native";

const light = {
  background: "#F6F5F2",
  surface: "#FFFFFF",
  text: "#1C1B1A",
  muted: "#6B6862",
  border: "#E3E0DA",
  accent: "#3E5BD8",
  accentText: "#FFFFFF",
  danger: "#B3261E",
  overdue: "#B3261E",
  assignment: "#7A4FD0",
  banner: "#1C1B1A",
  bannerText: "#FFFFFF",
};

const dark: typeof light = {
  background: "#121212",
  surface: "#1E1E1E",
  text: "#EDEBE7",
  muted: "#A19D96",
  border: "#2E2D2B",
  accent: "#8299F2",
  accentText: "#0E1330",
  danger: "#F2B8B5",
  overdue: "#F2B8B5",
  assignment: "#C3A6F5",
  banner: "#EDEBE7",
  bannerText: "#121212",
};

export type Theme = typeof light;

export function useTheme(): Theme {
  return useColorScheme() === "dark" ? dark : light;
}
