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
  summary: string; // one readable line per item, written by the server
  loop: string | null; // "You've thought about this 3 times", when it keeps coming up
  items: CapturedItem[];
  needs_date: number[]; // ids of tasks and reminders that came back without a due date
};

export type SyncResult = {
  fetched: number;
  added: number;
  changes: { title: string; field: string; old: string | null; new: string | null }[];
};

// GET /context/now, also the context strip at the top of the Retrace screen
export type ContextNow = {
  place: { place: string; at: string } | null;
  due_soon: Entry[];
  recent_captures: { id: number; type: string; title: string; status: string; created_at: string }[];
  // Only on the Retrace screen, when it was opened from a "lost a thought here" notification
  ghost?: { id: number; place: string | null; lost_at: string };
};

// One ranked "Was it...?" guess on the Retrace screen
export type Guess = {
  ref: string; // "item:12" or "assignment:3"
  kind: "item" | "assignment";
  id: number;
  type: string;
  title: string;
  course: string | null;
  due_at: string | null;
  score: number;
  chips: string[];
  question: string;
};

export type RetraceSession = {
  id: number;
  started_at: string;
  context: ContextNow;
  chips: string[];
  guesses: Guess[];
  phrased_by_ai: boolean;
};

export type RetraceEnd = {
  outcome: "recovered" | "ghost" | "gave_up";
  text?: string;
  item_id?: number; // the thought was this item, already on the list
  cue?: string;
  ghost_id?: number;
};

export type RetraceResult = {
  id: number;
  outcome: RetraceEnd["outcome"];
  seconds_taken: number;
  recovered_item_id: number | null;
  capture: CaptureResult | null;
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
    // Our server explains what was wrong in a "detail" field; show that when there is one
    const detail = await response
      .json()
      .then((body: { detail?: unknown }) => (typeof body.detail === "string" ? body.detail : null))
      .catch(() => null);
    throw new ApiError(detail ?? `Server error ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  list: (s: Settings) => request<Entry[]>(s, "/list"),
  capture: (s: Settings, text: string) =>
    request<CaptureResult>(s, "/captures", "POST", { text, source: "text" }),
  completeItem: (s: Settings, id: number) =>
    request(s, `/items/${id}`, "PATCH", { status: "done" }),
  setDue: (s: Settings, id: number, due: { date: string; time?: string } | { text: string }) =>
    request<{ summary: string }>(s, `/items/${id}/due`, "POST", due),
  completeAssignment: (s: Settings, id: number) =>
    request(s, `/assignments/${id}`, "PATCH", { done: true }),
  syncCarmen: (s: Settings) => request<SyncResult>(s, "/sync", "POST"),
  startRetrace: (s: Settings, ghostId?: number) =>
    request<RetraceSession>(s, "/retrace", "POST", ghostId ? { ghost_id: ghostId } : undefined),
  endRetrace: (s: Settings, id: number, end: RetraceEnd) =>
    request<RetraceResult>(s, `/retrace/${id}`, "PATCH", end),
};

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}
