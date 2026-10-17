# Retrace

Retrace is a personal app for a college student at Ohio State. It does three things:

1. **Captures thoughts fast.** Type into the app or say "Hey Siri, Retrace", and AI sorts the
   thought into a task, reminder, idea, song, note or question, with a due date if you said one.
2. **Keeps Carmen in one list.** Canvas (Carmen) assignments sync every hour and sit next to your
   own captures, grouped into Overdue, Today, This week, Later and No date.
3. **Helps you get back thoughts you lost.** Tap **I lost a thought** and Retrace shows where you
   were, what you were doing, and its best guesses, phrased as "Was it...?" questions.

It runs entirely on free services. The whole setup, step by step, is in [docs/SETUP.md](docs/SETUP.md).

## Features

| Feature | What it does |
| --- | --- |
| Capture | `POST /captures` sends text to Gemini, which splits it into items with a type, due date, course and place. If the AI step fails for any reason, the text is saved as a plain note, so a thought is never lost. |
| Siri | A Shortcut dictates a thought, posts it to the server and shows the summary as a notification. |
| Carmen sync | `POST /sync` (hourly, from cron-job.org) reads your Carmen calendar feed, adds new assignments and logs moved deadlines and renamed assignments. |
| Deadline alerts | When a sync finds moved deadlines, one push notification lists them all (old -> new, Columbus time). |
| Morning brief | `POST /brief` (daily at 7:30 AM) sends what's due in the next 48 hours, how many things are overdue, and up to three open captures that have no date. |
| Context trail | iOS arrival automations post where you are (`POST /contexts`). Each capture remembers the place you were at in the last 2 hours. Places are forgotten after 30 days unless something points at them. |
| Retrace | `POST /retrace` ranks things that might be connected to the lost thought: recent captures, open items and assignments due within a week. You answer Yes / No / Close, filter with type chips, then type the thought ("Got it") or give up ("Still gone"). |
| Ghosts | "Still gone" leaves a ghost for 14 days. When you're back at that place, or it's the same time of day, you get one gentle prompt: "Last Tuesday at Dreese you lost a thought. Anything come back?" |
| Loop detector | When a new capture closely matches 2 or more open items, the reply adds "You've thought about this 3 times". |
| Notification cap | At most 5 notifications a day, plus the morning brief. Every notification sent is logged in the `nudges` table. |

## How it fits together

```mermaid
flowchart LR
    subgraph iPhone
        app["Retrace web app<br/>(Home Screen)"]
        siri["Siri Shortcut<br/>'Hey Siri, Retrace'"]
        auto["Arrival automations<br/>(Shortcuts)"]
        ntfyapp["ntfy app"]
    end

    subgraph Render["Render (free web service, Docker)"]
        server["FastAPI server<br/>server/main.py"]
        web["Exported Expo app<br/>served at /"]
    end

    cron["cron-job.org"]
    carmen["Carmen calendar feed"]
    gemini["Gemini API<br/>(free tier)"]
    neon[("Neon Postgres<br/>(free tier)")]
    ntfy["ntfy.sh"]

    app -- "X-API-Key" --> server
    siri -- "POST /captures" --> server
    auto -- "POST /contexts" --> server
    cron -- "POST /sync hourly<br/>POST /brief 7:30 AM<br/>GET /health every 10 min" --> server
    server --- web
    server -- "download .ics" --> carmen
    server -- "sort captures, word questions,<br/>embeddings" --> gemini
    server -- "SQL" --> neon
    server -- "POST /topic" --> ntfy
    ntfy -- push --> ntfyapp
```

There are no timers inside the server. Free Render services fall asleep when nobody calls them,
so anything scheduled is a route that cron-job.org calls from outside.

## Decisions log

| Choice | Why |
| --- | --- |
| **FastAPI** (Python) | Short, readable route functions; request bodies are checked automatically with Pydantic. |
| **Gemini API, free tier** | Free with no credit card. Structured output with a hand-written JSON schema means the reply always has the shape we expect, and Pydantic checks it a second time. |
| **AI is optional everywhere** | Captures fall back to a note, Retrace questions fall back to templates, and the loop detector falls back to word overlap. The app keeps working with no key or no quota left. |
| **Retrace ranking in plain code, not AI** | The scoring in `server/retrace.py` (recency 3, due soon 2, same place 2, same hour 1) is predictable, testable and free. Gemini only rewords the top guesses. |
| **Embeddings stored once per item** | The free tier limits requests per minute, so each capture embeds only its own items (one small call) and saves the result. Comparing is plain math on stored numbers. |
| **Neon Postgres** | Free and permanent. Render's free disk is wiped on every deploy, so data must live outside the container. |
| **SQLite on a laptop and in tests** | Nothing to install. `server/db.py` hides the difference: `?` placeholders, rows as dicts, `INSERT ... RETURNING id` work on both. |
| **Render, one Docker service** | Free web service that builds from `render.yaml`. One container serves both the API and the app, so there's only one address and no cross-site setup. |
| **cron-job.org** | Free scheduler that can send POST requests with headers, which is what `/sync` and `/brief` need. |
| **ntfy.sh** | Free push notifications with an iPhone app, sent with one HTTP POST: no Apple developer account. |
| **Expo app exported to the web** | One TypeScript codebase. Added to the Home Screen it looks like a native app, with no App Store or developer fee. |
| **One API key, no accounts** | It's one person's app. Every route except `/health` requires the `X-API-Key` header. |
| **Times stored as UTC text** | One unambiguous format in both databases. The phone groups by its own time zone; notifications show Columbus time. |
| **Places from Shortcuts instead of GPS** | A web app can't track location in the background. Arrival automations are free, built into iOS, and only record places you chose. |

Left out on purpose: Spotify and Shazam, effort learning, an insights dashboard, a weekly
review, gap and place nudges, Android, and accounts beyond the single API key.

## Run it on your laptop

You need Python 3.12 or newer and Node 24.

```bash
# 1. The server
cd server
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then fill in the values (see docs/SETUP.md)
fastapi dev main.py                # http://localhost:8000, API docs at /docs
```

Without `DATABASE_URL` the server uses a local SQLite file (`server/retrace.db`). Without
`GEMINI_API_KEY` captures are saved as plain notes. Without `NTFY_TOPIC` no notifications are
sent (they're logged instead).

```bash
# 2. The app, in a second terminal
cd mobile
npm ci
npx expo start --web               # opens in the browser; enter http://localhost:8000 and your key
```

To serve the app from the server itself, the way Render does, run `npx expo export --platform web`
in `mobile/`. The server then serves `mobile/dist` at `http://localhost:8000/`.

## Tests

```bash
cd server
python -m pytest                   # uses a temporary SQLite database
```

To run the same tests on Postgres, point `TEST_DATABASE_URL` at an **empty, throwaway** database.
Every test wipes its tables.

```bash
TEST_DATABASE_URL=postgresql://user:pass@localhost/retrace_test python -m pytest
```

The tests never call Gemini or ntfy: those calls are replaced with fakes.

For the app:

```bash
cd mobile
npx tsc --noEmit                   # type check
npx expo export --platform web     # proves the web build works
```

## API

Every route except `/health` needs the header `X-API-Key: <RETRACE_API_KEY>`.

| Route | Purpose |
| --- | --- |
| `GET /health` | Is the server up? (used by Render and cron-job.org) |
| `POST /captures` `{text, source}` | Save a thought. `source` is `text`, `voice` or `share`. |
| `GET /list` | Open captures and live Carmen assignments, merged |
| `GET /items?status=open` / `PATCH /items/{id}` `{status}` | Your captures; mark done or archived |
| `GET /assignments` / `PATCH /assignments/{id}` `{done}` | Carmen assignments |
| `POST /sync` | Pull Carmen, notify about moved deadlines, forget old places |
| `GET /changes` | Every deadline or title change Carmen ever made |
| `POST /brief` | Send the morning brief |
| `POST /contexts` `{place}` | "I'm here now" from an arrival automation; may prompt a ghost |
| `GET /context/now` | Last place, what's due in 24 hours, 5 newest captures |
| `POST /retrace` `{ghost_id?}` | Start a lost-thought session |
| `PATCH /retrace/{id}` `{outcome, text?, item_id?, cue?, ghost_id?}` | End it: `recovered`, `ghost` or `gave_up` |

## Project layout

```
server/
  main.py       routes
  capture.py    Gemini capture parsing
  carmen.py     Carmen feed download and parsing
  sync.py       saves assignments and logs changes
  notify.py     ntfy notifications, daily cap, Columbus time formatting
  brief.py      the morning brief
  queries.py    reads shared by several routes
  retrace.py    Retrace ranking and question wording
  ghosts.py     lost-thought ghosts and their prompts
  loops.py      the loop detector
  db.py         Postgres/SQLite connection and schema
  tests/        pytest tests
mobile/
  App.tsx       main screen
  src/          capture bar, list rows, settings, Retrace screen, API calls
Dockerfile      builds the app, then the server that serves it
render.yaml     Render Blueprint
docs/SETUP.md   free hosting setup, step by step
```
