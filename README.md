# Daily Brief Bot

An LLM-powered personal assistant that lives in Discord. Tell it what you need in plain language
("meeting tomorrow at 3pm", "todo: finish the report", "what's on next week?") and it updates
Google Calendar / Google Tasks for you. Every morning it posts a briefing that combines today's
calendar, open tasks, and unread Gmail.

Built and run as a 24/7 background service on macOS.

## Features

| You say (natural language) | The bot does |
|---|---|
| A sentence with a time — *"meeting tomorrow at 3pm"* | Creates a Google Calendar event |
| A to-do with no time — *"todo: prepare slides"* | Creates a Google Task |
| A question — *"what do I have next week?"* | Queries the calendar for that date range |
| A delete request — *"cancel the dentist appointment"* | Finds matching events and asks you to confirm by number before deleting |
| *(scheduled, 8:00 daily)* | Morning brief: today's events + tasks + unread mail |
| *(scheduled, Mondays)* | Weekly overview, Monday through Sunday |
| *"matcha stock"* | Live product availability from a Cloudflare-protected shop page (optional monitor) |

## Architecture

```
Discord message
      │
      ▼
bot.py ──► claude_nlp.py ──► Groq LLM (gpt-oss-120b)
  │            returns structured JSON: {intent, title, datetime, query range}
  │
  ├──► google_services.py ──► Google Calendar / Tasks / Gmail APIs (OAuth 2.0)
  ├──► matcha_monitor.py  ──► Playwright headless Chromium ──► BeautifulSoup parser
  └──► message_builder.py ──► formatted Discord replies

scheduler.py (APScheduler) ──► daily / weekly briefs, periodic stock checks
launchd ──► keeps the process alive, restarts on crash
```

| Module | Responsibility |
|---|---|
| `bot.py` | Discord event handling, intent routing, delete-confirmation state, failure alerting |
| `claude_nlp.py` | Prompted LLM call that turns free text into a strict JSON intent |
| `google_services.py` | Calendar / Tasks / Gmail wrappers, credential refresh |
| `scheduler.py` | Cron and interval jobs in the user's local timezone |
| `matcha_monitor.py` | Headless-browser scraper with state diffing to detect restocks |
| `message_builder.py` | All user-facing message formatting |
| `config.py` | Environment-based configuration |

## Engineering notes

- **Structured LLM output.** The model is constrained to a fixed JSON schema with explicit rules for
  relative dates ("this week", "next month"). Malformed output falls back to a safe `other` intent
  instead of crashing.
- **Safe destructive actions.** Deleting an event is a two-step flow: the bot lists candidates and
  waits for a numeric reply (60 s TTL), so an ambiguous keyword can't delete the wrong event.
- **Explicit auth-expiry handling.** A custom `GoogleAuthExpiredError` surfaces "please re-authenticate"
  instead of a vague failure when the OAuth refresh token is revoked.
- **Timezone correctness.** All date math goes through one IANA zone (`zoneinfo`) so daylight-saving
  changes are handled. This fixed a real bug where the event time and the "today" calculation used
  different timezones and drifted by 13 hours.
- **Getting past Cloudflare challenges.** Plain HTTP requests get 403s, so the monitor drives headless
  Chromium and waits for the real DOM to render, with retries. Reusing a persistent browser instance
  instead of launching one per check cut fetch latency from 1.8 s to 0.9 s.
- **Failure alerting with backoff.** If the monitor fails 3 times in a row it alerts once, then only
  every 18 further failures, so a broken monitor is noticed without flooding the channel.
- **Process supervision.** Runs under a macOS `launchd` agent with auto-restart. (The project lives
  outside TCC-protected folders, since background processes are silently denied access there.)

## Tech stack

Python 3.11 · discord.py · Groq API · Google Calendar / Tasks / Gmail APIs · OAuth 2.0 ·
APScheduler · Playwright · BeautifulSoup · launchd

## Setup

```bash
pip install -r requirements.txt
playwright install chromium        # only needed for the stock monitor
cp .env.example .env               # fill in your tokens
```

1. **Google APIs:** In Google Cloud Console, enable the Calendar, Tasks, and Gmail APIs, create an
   OAuth 2.0 *Desktop app* client, and save it as `credentials.json`. Then run
   `python auth_setup.py` once to create `token.json`.
2. **Discord:** Create an application in the Developer Portal, enable the *Message Content* intent,
   invite the bot with `Send Messages` + `Read Message History`, and copy the channel ID.
3. **Run:** `python bot.py`

### Configuration (`.env`)

| Variable | Description |
|---|---|
| `DISCORD_BOT_TOKEN` | Discord bot token |
| `DISCORD_CHANNEL_ID` | Channel the bot reads and posts in |
| `GROQ_API_KEY` | Groq API key for intent parsing |
| `LOCAL_TZ` | IANA timezone, e.g. `America/Chicago` |
| `MORNING_HOUR` / `MORNING_MINUTE` | Time of the daily brief |
| `MATCHA_CHECK_INTERVAL_MINUTES` | Stock check interval; `0` disables the monitor |
| `MATCHA_IDLE_REPORT_HOURS` | Post a "still out of stock" heartbeat after N quiet hours; `0` disables |

> The bot's replies and prompts are in Traditional Chinese, its primary user's language.
