# Setting up Retrace for free

This guide takes you from nothing to Retrace running on your iPhone. Every service here has a
free plan, and none needs a credit card. Plan on about an hour.

You'll collect five values along the way. Keep them in a private note as you go, because Render
asks for all of them in step 5:

| Name | What it is | Where it comes from |
| --- | --- | --- |
| `GEMINI_API_KEY` | Lets the server use Google's AI | Step 1 |
| `DATABASE_URL` | Where your data is stored | Step 2 |
| `CARMEN_FEED_URL` | Your Carmen calendar | Step 3 |
| `RETRACE_API_KEY` | The password for your server | Step 4 |
| `NTFY_TOPIC` | The secret channel for notifications | Step 4 |

> Treat all five like passwords. Never post them, screenshot them or commit them to GitHub.
> The `.env` file is already in `.gitignore` for this reason.

---

## 1. Gemini API key (the AI)

1. Go to **https://aistudio.google.com** and sign in with a Google account.
2. Click **Get API key**, then **Create API key**.
3. Copy the key (it starts with `AIza`). This is `GEMINI_API_KEY`.

The free tier has daily limits. If you hit them, Retrace keeps working without AI: captures are
saved as plain notes and Retrace questions use simple templates.

## 2. Neon database (where your data lives)

1. Go to **https://neon.tech** and sign up (signing in with GitHub is easiest).
2. Create a project. Name it `retrace`.
3. For **Region**, pick **AWS US East 2 (Ohio)**. Render runs in Ohio too, so they're close
   together and the app feels faster.
4. When the project is ready, click **Connect** on the dashboard.
5. Copy the connection string. It looks like
   `postgresql://neondb_owner:...@ep-something.us-east-2.aws.neon.tech/neondb?sslmode=require`.
   This is `DATABASE_URL`.

You don't need to create any tables: the server creates them the first time it starts.

## 3. Carmen calendar feed

1. Open **Carmen** in a browser and click **Calendar** on the left.
2. At the bottom right, click **Calendar Feed**.
3. Copy the link. This is `CARMEN_FEED_URL`.

## 4. Make two secrets

`RETRACE_API_KEY` and `NTFY_TOPIC` are random strings you make up. Long random ones are best,
because anyone who knows them can use your server or read your notifications. On any computer
with Python, run this twice and use one result for each:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 5. Render (runs the server and the app)

1. Go to **https://render.com** and sign up with GitHub. Allow Render to see the **Retrace**
   repository.
2. In the dashboard click **New** -> **Blueprint**.
3. Pick the **Retrace** repository. Render finds `render.yaml` and shows one free web service
   called `retrace`.
4. Render asks for the secret values. Paste them in:
   - `DATABASE_URL`: from step 2
   - `GEMINI_API_KEY`: from step 1
   - `CARMEN_FEED_URL`: from step 3
   - `RETRACE_API_KEY`: from step 4
   - `NTFY_TOPIC`: from step 4
5. Click **Apply**. The first build takes several minutes.
6. When it says **Live**, open the service and copy its address, something like
   `https://retrace-abcd.onrender.com`. That's your **server address**.
7. Check it: open `https://<your address>/health` in a browser. You should see `{"status":"ok"}`.

Every time new code lands on the `main` branch, Render rebuilds automatically. Your data is safe
in Neon, so rebuilds never lose anything.

## 6. cron-job.org (the scheduler)

Free Render services fall asleep after about 15 minutes with no visitors. Retrace has no timers
of its own, so cron-job.org calls it on a schedule instead.

1. Sign up at **https://cron-job.org**.
2. Under **Settings**, set your time zone to **America/New_York**, so 7:30 AM means 7:30 in
   Columbus.
3. Create three cronjobs (**Cronjobs** -> **Create cronjob**):

| Title | URL | Schedule | Advanced tab |
| --- | --- | --- | --- |
| Retrace sync | `https://<your address>/sync` | Every hour | Request method **POST**; add header `X-API-Key` = your `RETRACE_API_KEY` |
| Retrace brief | `https://<your address>/brief` | Every day at **7:30** | Request method **POST**; add header `X-API-Key` = your `RETRACE_API_KEY` |
| Retrace keep-awake | `https://<your address>/health` | Every **10** minutes | Leave as **GET**; no header needed |

4. On each job, click **Test run** (or wait for it to run) and check that the result is **200 OK**.
   A **401** means the `X-API-Key` header is missing or has a typo.

The keep-awake job means the app opens quickly instead of taking about a minute to wake up.
Render's free plan includes enough hours a month for one service to run all the time.

## 7. ntfy (notifications)

1. On your iPhone, install **ntfy** from the App Store and open it. Allow notifications.
2. Tap **+** to subscribe to a topic.
3. Paste your `NTFY_TOPIC` exactly. Leave the server as **ntfy.sh**. Tap **Subscribe**.
4. Test it: on cron-job.org, run the **Retrace brief** job. A "Good morning" notification should
   arrive within a few seconds.

Retrace sends at most 5 notifications a day, plus the morning brief.

## 8. Put the app on your Home Screen

1. On the iPhone, open **Safari** and go to your server address.
2. Tap the **Share** button, then **Add to Home Screen**, then **Add**.
3. Open **Retrace** from the Home Screen. The server address is filled in for you; paste your
   `RETRACE_API_KEY` and tap **Test and save**.

> Tapping a "you lost a thought" notification opens Retrace in Safari, not the Home Screen app.
> iOS keeps their storage separate, so the first time that happens, enter your API key in Safari
> too.

## 9. "Hey Siri, Retrace"

This Shortcut lets you capture a thought by voice without opening anything.

1. Open the **Shortcuts** app and tap **+** to make a new shortcut. Name it **Retrace** (Siri
   uses this name).
2. Add these actions in order:
   1. **Dictate Text**.
   2. **Get Contents of URL**. Set the URL to `https://<your address>/captures`, then tap the
      arrow to show more options:
      - **Method**: `POST`
      - **Headers**: add `X-API-Key` with your `RETRACE_API_KEY` as the value
      - **Request Body**: `JSON`, with two fields:
        - `text` (Text) = the **Dictated Text** variable (tap and pick it from the list)
        - `source` (Text) = `voice`
   3. **Get Dictionary Value**: get the **Value** for key `summary` in **Contents of URL**.
   4. **Show Notification**: set its text to **Dictionary Value**.
3. Try it: say **"Hey Siri, Retrace"**, then your thought. A notification shows how it was
   sorted, for example `Task: Finish 2321 homework (CSE 2321), due Fri Oct 23`.

## 10. Arrival automations (the context trail)

These tell Retrace where you are, so captures remember their place and Retrace can say "you
were at Dreese". Make one for each place that matters: Dreese, Thompson Library, your dorm, the
RPAC.

1. In **Shortcuts**, open the **Automation** tab and tap **+** (or **New Automation**).
2. Choose **Arrive**, pick the location (search for "Dreese Laboratories"), and set it to
   **Run Immediately**. Turn off **Notify When Run** if you'd rather not see it.
3. Tap **Next**, then **New Blank Automation**, and add **Get Contents of URL**:
   - URL: `https://<your address>/contexts`
   - **Method**: `POST`
   - **Headers**: `X-API-Key` = your `RETRACE_API_KEY`
   - **Request Body**: `JSON`, with one field: `place` (Text) = `Dreese` (the place's name)
4. Tap **Done**. Repeat for your other places, changing the `place` name each time.

Use the same spelling every time for the same place: Retrace matches places by name.

---

## If something goes wrong

| Symptom | Likely fix |
| --- | --- |
| The app says "The server rejected the API key" | Copy `RETRACE_API_KEY` again from Render -> retrace -> **Environment**, with no spaces. |
| The app says "Can't reach the server" | The server may be waking up: wait a minute and pull down to refresh. Check that the keep-awake job is running. |
| Captures are always saved as "Note" | `GEMINI_API_KEY` is missing or wrong, or today's free quota is used up. Check the Render **Logs**. |
| No notifications | The topic in the ntfy app must match `NTFY_TOPIC` exactly. Run the brief job and look for `Could not send notification` in the Render **Logs**. |
| Sync shows 401 on cron-job.org | The `X-API-Key` header is missing on that job, or the method isn't POST. |
