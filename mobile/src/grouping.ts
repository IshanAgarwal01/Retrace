import type { Entry } from "./api";

export type Section = {
  title: string;
  data: Entry[];
};

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfDay(date: Date): number {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy.getTime();
}

// Times arrive from the server in UTC; `new Date(...)` and these comparisons use
// the phone's own time zone, so "Today" means today where you are.
export function groupEntries(entries: Entry[], now: Date = new Date()): Section[] {
  const tomorrow = startOfDay(now) + DAY_MS;
  const weekEnd = startOfDay(now) + 7 * DAY_MS;
  const groups: Record<string, Entry[]> = {
    Overdue: [],
    Today: [],
    "This week": [],
    Later: [],
    "No date": [],
  };

  for (const entry of entries) {
    if (!entry.due_at) {
      groups["No date"].push(entry);
      continue;
    }
    const due = new Date(entry.due_at).getTime();
    if (due < now.getTime()) groups.Overdue.push(entry);
    else if (due < tomorrow) groups.Today.push(entry);
    else if (due < weekEnd) groups["This week"].push(entry);
    else groups.Later.push(entry);
  }

  return Object.entries(groups)
    .filter(([, data]) => data.length > 0)
    .map(([title, data]) => ({ title, data }));
}

export function formatDue(dueAt: string | null, allDay: boolean, now: Date = new Date()): string {
  if (!dueAt) return "";
  const due = new Date(dueAt);
  const daysAway = Math.round((startOfDay(due) - startOfDay(now)) / DAY_MS);

  let day: string;
  if (daysAway === 0) day = "Today";
  else if (daysAway === 1) day = "Tomorrow";
  else if (daysAway > 1 && daysAway < 7) day = due.toLocaleDateString(undefined, { weekday: "long" });
  else day = due.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });

  if (allDay) return day;
  return `${day}, ${due.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
}

const TYPE_LABELS: Record<string, string> = {
  assignment: "Carmen",
  task: "Task",
  reminder: "Reminder",
  idea: "Idea",
  song: "Song",
  note: "Note",
  question: "Question",
};

export function typeLabel(type: string): string {
  return TYPE_LABELS[type] ?? type;
}
