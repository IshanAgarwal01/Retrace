import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

export type Settings = {
  serverUrl: string;
  apiKey: string;
};

// One row of the merged list from GET /list
export type Entry = {
  kind: "item" | "assignment";
  id: number;
  type: string;
  title: string;
  course: string | null;
  due_at: string | null;
  all_day: boolean;
  place: string | null;
  url: string | null;
};

export type CapturedItem = {
  id: number;
  type: string;
  title: string;
  due_at: string | null;
  all_day: boolean;
  course: string | null;
};

export type CaptureResult = {
  ai_ok: boolean;
  items: CapturedItem[];
};

export type SyncResult = {
  fetched: number;
  added: number;
  changes: { title: string; field: string; old: string | null; new: string | null }[];
};

const SETTINGS_KEY = "retrace-settings";
const TIMEOUT_MS = 30_000; // AI captures can take several seconds

// SecureStore keeps the API key in the iPhone Keychain. It doesn't exist in a
// browser, so the web preview falls back to localStorage.
export async function loadSettings(): Promise<Settings | null> {
  try {
    const raw =
      Platform.OS === "web"
        ? globalThis.localStorage?.getItem(SETTINGS_KEY) ?? null
        : await SecureStore.getItemAsync(SETTINGS_KEY);
    return raw ? (JSON.parse(raw) as Settings) : null;
  } catch {
    return null;
  }
}

export async function saveSettings(settings: Settings): Promise<void> {
  const raw = JSON.stringify(settings);
  if (Platform.OS === "web") {
    globalThis.localStorage?.setItem(SETTINGS_KEY, raw);
  } else {
    await SecureStore.setItemAsync(SETTINGS_KEY, raw);
  }
}

export class ApiError extends Error {}

async function request<T>(
  settings: Settings,
  path: string,
  method: "GET" | "POST" | "PATCH" = "GET",
  body?: unknown,
): Promise<T> {
  const url = settings.serverUrl.trim().replace(/\/+$/, "") + path;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json", "X-API-Key": settings.apiKey.trim() },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch {
    throw new ApiError(`Can't reach the server at ${settings.serverUrl}`);
  } finally {
    clearTimeout(timer);
  }

  if (response.status === 401) {
    throw new ApiError("The server rejected the API key");
  }
  if (!response.ok) {
    throw new ApiError(`Server error ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  list: (s: Settings) => request<Entry[]>(s, "/list"),
  capture: (s: Settings, text: string) =>
    request<CaptureResult>(s, "/captures", "POST", { text, source: "text" }),
  completeItem: (s: Settings, id: number) =>
    request(s, `/items/${id}`, "PATCH", { status: "done" }),
  completeAssignment: (s: Settings, id: number) =>
    request(s, `/assignments/${id}`, "PATCH", { done: true }),
  syncCarmen: (s: Settings) => request<SyncResult>(s, "/sync", "POST"),
};

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}
