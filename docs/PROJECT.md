# Event Assistant — Montreal activity recommender

Product vision. Technical decisions — stack, data model, request flows,
repo layout — live in `docs/ARCHITECTURE.md`.

## Problem

Finding things to do in Montreal for a specific date (or date range) means
trawling multiple event-listing sites by hand. This project builds a
website with a chatbot that recommends activities for a selected city
(Montreal for now, extensible later) and date range, learns the user's
preferences over the course of conversation, and keeps its activity
database fresh via a nightly AI-agent scraper — with an admin panel to
configure which cities and sources feed it.

This is a personal/portfolio project: optimize for simplicity, low
running cost, and fast iteration over scale or multi-tenant robustness.

## Goals / Non-goals

**Goals**

- Chat-driven activity recommendations for a selected city + date range.
- Chatbot infers and saves user preferences during conversation, without
  interrupting the flow to ask for confirmation each time.
- User can view/edit/remove saved preferences both via a settings page and
  conversationally.
- Nightly agentic scraper keeps the activity database current, without
  hardcoded per-site scraping logic.
- Admin panel to configure cities, sources, trigger/monitor scrapes, and
  correct activity data.
- Works with zero required signup; login (Google OAuth) is optional and
  only needed to sync preferences across devices.
- Zero/near-zero recurring cost: chat runs on the user's own local LLM,
  scraping cost is capped and deliberately kept small.

**Non-goals (v1)**

- Payments or monetization.
- Multiple admins or a roles/permissions system.
- Multiple simultaneously-live cities (data model supports it; only
  Montreal is seeded).
- Admin UI for managing the tag taxonomy (fixed seed list for v1).
- A review/approval queue for scraped activities before they go live.
- Activity images.
- Native mobile app (responsive web only).
- Scrape-failure alerting/notifications (visible in admin, not pushed).
- Auto-broadening search when no activities match (just report no match).

## Product experience

### Browsing and recommendations

The user picks a city (dropdown, Montreal only for now) and a date range
(range picker), then chats. The screen is a split view: a chat sidebar
alongside a live-updating grid of activity cards. Matching activities
appear as cards in the grid, so the grid always reflects the latest
filter/recommendation state — and remains browsable on its own, without
needing the chat to be working.

### Preferences

As the conversation goes on, the assistant picks up durable likes and
dislikes and saves them silently — no confirmation step, just a passing
acknowledgement in its reply. The user stays in control of what was
inferred:

- A settings page lists every saved preference, with add/remove controls.
- The same preferences are editable conversationally (e.g. "forget that I
  like nightlife").

Signup is never required. Logging in with Google is optional and buys one
thing: preferences that follow the user across devices. Preferences
gathered before login are carried over onto the account.

### Admin capabilities

A single admin can configure and correct what feeds the site: manage the
cities offered, manage the sources scraped for each city (including
pausing one), review scrape history per source and trigger a run on
demand, and edit activity records directly to fix bad data.

## Behaviour in edge cases

- **Assistant offline** (the local LLM is unreachable): the chat panel
  says so clearly, and browsing/filtering the activity grid keeps working.
- **A nightly scrape doesn't run** (e.g. the scraper machine was off):
  it shows up as a gap in the run history, and the admin can trigger a
  manual run once it's back. No alerts are pushed for v1.
- **No activities match the filters or date range**: a plain "no
  activities found" message in both chat and grid — the search is not
  automatically broadened.
- **Anonymous preferences are lost** (cookies cleared, different browser):
  an accepted tradeoff for v1, mitigated by optional login.

## Out of scope

- Payments/monetization.
- Multi-admin roles/permissions.
- Additional live cities beyond Montreal (data model supports it, not
  seeded).
- Admin UI for tag-taxonomy management.
- Scraped-activity approval queue.
- Activity images.
- Native mobile app.
- Scraper-failure push notifications/alerting.
