# TODO

Bigger pieces of work that are agreed but not started. Each one becomes a spec
before it is built.

---

## 1. Multiple users and an administrator account

Today Maestarr has exactly one account. Everyone in a household shares it — its
conversations, its taste profile, its Telegram chat and its right to delete things.

### Goal

Several people use one Maestarr, each with their own picks and history, while one
**administrator** owns the stack: connections, settings, and anything destructive.

### Roles

| Role | Can |
| --- | --- |
| **Admin** | Everything: Settings, services, users, API keys, caching, 18+ switch. Approves any action. |
| **User** | Chat, Discover, picks, details; search and **request** titles. Adding/downloading/deleting needs an admin's approval unless the admin allows it for that user. |
| **Viewer** *(optional)* | Browse picks and details only; no chat actions. |

Per-user switches the admin can set: may download without approval, may delete,
may see adult content (only if 18+ is on globally), may use Telegram.

### What becomes per user

- **Conversations** — each user sees only their own (admin can view all for support).
- **Taste profile, feedback and shelves** — built from *their* history: map each
  Maestarr user to a Jellyfin user (and optionally their own Trakt / AniList / Letterboxd);
  impressions, *Not for me* and the cache keys get a `user_id`.
- **Language** — the reply language setting moves from global to per user (global = default).
- **Telegram** — each allowed chat id belongs to one user; pairing (`/start`) links the chat
  to the user who pressed *Connect*.
- **API / MCP tokens** — one or more per user, with the user's permissions.

### Approval routing

- A user's write action creates a **pending request** instead of running: it appears in
  the admin's chat/Home ("Ayşe wants to download Se7en — Approve / Deny") and on the
  admin's Telegram with buttons; the user sees "waiting for approval".
- The admin can approve, deny, or approve-and-always-allow for that user and tool.

### Accounts

- Onboarding creates the first account as **admin** (existing single-user installs are
  migrated: the current user becomes admin, all data stays theirs).
- Settings → **Users**: create, invite (one-time link, since there may be no SMTP),
  reset password, change role, disable, delete (with or without their conversations).
- Sessions: list and revoke a user's sessions; optional login with Jellyfin credentials
  (Jellyfin's `/Users/AuthenticateByName`) so household members reuse the password they
  already have.

### Data and code

- `users.role`, `users.jellyfin_user`, per-user settings table; `user_id` on
  `conversations`, `impressions`, `cache` keys, `sessions`, API tokens.
- `require_user` → `require_role(...)`; every tool gets the caller's user in its
  context and checks permissions before acting.
- Audit log: who did what, when, approved by whom (shown to admins).

### Open questions

- Should picks also learn from the *household* (shared shelf "for everyone tonight")?
- Per-user quality profiles / root folders (e.g. kids' library), or keep those global?

---

## 2. Every capability as MCP tools — Maestarr without an AI key

Maestarr already serves its agent's tools over MCP (`/mcp`, streamable HTTP, and
`maestarr serve-mcp` over stdio). Someone without an AI provider key — or who
prefers their own agent (Claude Desktop, Claude Code, Cursor, n8n, a local
model) — should be able to use **everything** Maestarr can do through MCP, with
Maestarr itself never calling an LLM.

### What is missing today

- **Parity**: several features exist only in the web UI's REST API and have no tool:
  the home shelves and picks for tonight, *Not for me* / feedback, title details
  (trailer, cast, ratings), cache status and *Refresh now*, adult picks for Discover,
  more-results paging is there but release *grab by number* is not, settings reads.
- **No-AI mode**: onboarding and the chat assume an AI provider. Without one, the UI
  should say "Chat is off — connect an MCP client" and show the ready-made config; the
  judge already falls back to its rules verdict, which must be documented as the
  default in that mode.
- **Auth and scopes**: there is one API token with full rights. It needs per-user
  tokens (see #1) and scopes: `read` (search, picks, library, queue), `write` (add,
  search-and-grab, monitoring), `delete` (files, torrents, remove from library), `admin`.
- **Approvals over MCP**: write tools run as soon as the client calls them (the client
  is trusted to have asked its user). Offer an alternative for clients that do not ask:
  a token setting "require approval in Maestarr" that turns the call into a pending
  request approved in the web UI/Telegram, using MCP *elicitation* where the client
  supports it.

### Deliverables

- One tool per capability, generated from the same `maestarr.ops` functions the UI uses,
  with clear descriptions and examples; `read-only` / `destructive` hints set correctly.
- MCP **resources** for things an agent wants to read without a call: library summary,
  current queue, taste profile, today's shelves.
- MCP **prompts** for common flows: "recommend for tonight", "find and judge the best
  release of …", "free up space".
- Settings → API & MCP: create tokens with scopes, copy-paste configs for Claude
  Desktop / Claude Code / Cursor / generic HTTP, and a "test connection" page.
- Docs: a "Use Maestarr from your own agent" page with examples, and a list of every tool.
- Tests: each tool callable over MCP with no AI configured; scopes enforced; approvals
  routed when the token requires them.

### Open questions

- Rate limits per token?
- Should the Telegram bot also work without an AI key (button-driven menus only)?

---

## 3. A learning recommender (machine learning), no AI key needed

The recommender is already deterministic — picks are scored without any LLM —
but its weights are fixed by hand (keywords 0.45, genres 0.25, people 0.20 …) and
it only reacts to feedback through simple boosts. With the signals Maestarr now
collects it can **learn** each user's taste, entirely locally, so installs
without an AI provider get picks that improve with use.

### Signals already there (labels)

- **Positive**: watched (with rating, rewatches), favourite (Jellyfin/AniList), requested
  (Seerr), added to Sonarr/Radarr, opened / searched / downloaded from a suggestion.
- **Negative**: *Not for me*; shown repeatedly without a reaction (implicit skip, the
  same impressions table the spacing uses); added but never watched for months (weak).

### Approach (in order of effort)

1. **Learned weights** — a small logistic-regression / gradient-boosted model (scikit-learn,
   or plain numpy) over the features the scorer already computes: keyword, genre, people,
   language, decade overlaps, TMDB rating and votes, popularity, runtime, age, "because
   you watched" origin, in-library. Trained per user on the labels above; falls back to
   today's hand weights until there are ~50 labelled impressions.
2. **Content embeddings** — represent each title by its keywords, genres, people and
   overview (TF-IDF, or a small local sentence-embedding model such as all-MiniLM ~90 MB if
   memory allows); taste = weighted mean of liked items minus disliked; candidates ranked
   by cosine similarity. Gives "similar in feel" beyond exact tag overlap.
3. **Item-to-item collaborative signal** — single-user installs have no "people like you",
   but public data can stand in: TMDB's own recommendations/similar lists (already used as
   candidates) and, optionally, a precomputed item-item matrix from an open dataset
   (e.g. MovieLens) shipped as a small file, mapped by TMDB id.
4. **Exploration** — keep a share of each shelf (e.g. 15 %) for titles the model is
   unsure about (bandit-style), so taste can widen instead of narrowing to Batman.

### Product

- Settings → Discovery → *Recommendation engine*: **Rules** (today) / **Learned** (default
  once enough data) / **Learned + AI explanations** (when an AI key exists, the LLM only
  writes the "why", never ranks).
- Training runs with the cache refresh (daily, in the background), takes seconds, and
  stores the model in the data directory; *Reset what Maestarr learned* button.
- "Why this pick" stays readable: the top contributing features become the reason text
  ("themes you watch: heist, twist ending · with Christopher Nolan").
- Metrics on the settings page: how often picks get opened/searched vs dismissed, before
  and after learning.

### Constraints

- Must fit the 8 GB home server: no GPU, model files under ~100 MB, training under a minute.
- Works per user (see #1) and for adult scenes separately (StashDB tags/performers/studios
  as features), never mixing the two.
- No data leaves the server.

---

## 4. Jellyfin plugin

Bring Maestarr into the place people actually watch: Jellyfin's own web and TV
apps. (Research from 2026-10-14: Jellyfin server plugins are official .NET
plugins; extra pages and UI injection go through the community plugins
*Plugin Pages*, *File Transformation* and *Home Screen Sections*, which this
stack already runs.)

### Features

- **Maestarr shelves on Jellyfin's home screen** — "Picks for tonight", "Because you
  watched …", "Waiting in your library" as sections through the *Home Screen Sections*
  plugin. Titles already in the library play directly; others show "Get it" (which asks
  Maestarr to add and judge, with the usual approval).
- **"Ask Maestarr" page** — the chat inside Jellyfin's web UI via *Plugin Pages*, signed in
  as the matching Maestarr user, so no separate login.
- **Buttons on item pages** (via *File Transformation*): on a movie/series/episode —
  *Find a better release*, *Subtitles?*, *More like this*; on a missing episode —
  *Find and download*; on a watched item — *Delete and free space* (approval required).
- **Instant watch signals** — the plugin tells Maestarr when something is played,
  finished, rated or favourited (Jellyfin's session/user-data events), so the taste profile
  updates right away instead of polling Jellyfin's slow history query.
- **"Maestarr picks" collections** — optional real Jellyfin collections/playlists that the
  plugin keeps in sync with the user's shelves (this replaces the roadmap item for
  Jellyfin; Emby/Plex stay separate).
- **User mapping** — each Jellyfin user maps to a Maestarr user (see #1); their history,
  picks and permissions follow them across Jellyfin clients.

### Ideas from Jellyfin Helper (a chosen subset, plus our own)

[Jellyfin Helper](https://github.com/JellyPlugins/jellyfin-helper) (GPL-3.0, Jellyfin 12.2+)
is a multi-tab admin plugin with cleanup, library statistics and recommendations. Take
**some** of its features, not all, and add our own. Candidates (to pick from when the
spec is written):

- **Library analysis** — codec / resolution / HDR / container breakdowns; a library
  explorer combining resolution, codec, bitrate, language and watched-by filters down to
  the files; per-library disk usage; a growth timeline; largest folders and recent changes.
  Maestarr could answer these in chat too ("which 4K titles have no Turkish subtitles?").
- **Health checks** — videos missing subtitles, artwork or NFO; orphaned metadata folders.
- **Safe cleanup** — dry run by default and a timestamped trash with auto-purge instead
  of deleting: orphaned trickplay folders, empty folders, orphaned subtitles, broken
  `.strm`/symlinks, Seerr requests whose media is gone.
- **Arr comparison** — items only in Radarr/Sonarr, only in Jellyfin, or in both.
- **User activity** — per-user / per-item plays, completion, favourites, genre mix
  (feeds the taste profile and #1's per-user picks).
- **Discovery surfaces** — sync picks to native Jellyfin playlists; a Discover custom tab
  that excludes everything already in the library or in Radarr/Sonarr; parental limits
  for restricted (child) profiles.
- **Operations** — backup/restore of the plugin state with secrets encrypted at rest, a
  plugin-only log viewer, an unsaved-changes guard on settings.

Not wanted from it: a second, separate recommender (Maestarr's engine stays the one
brain, see #3) and its own Trakt plumbing (Maestarr already connects to Trakt).

Our own additions: *to be added by the user.*

### Shape

- A C# plugin (`Jellyfin.Plugin.Maestarr`) targeting the Jellyfin ABI of each supported
  release (12.x now; plugins are built per Jellyfin version, so CI builds one per target).
- Configuration page in Jellyfin's dashboard: Maestarr URL + API token (scoped, see #2),
  which features to turn on, per-user enablement.
- Talks to Maestarr only over its HTTP API/MCP; Maestarr remains the brain, the plugin
  is UI and events.
- Distributed through a plugin repository manifest (a JSON URL users add in
  Dashboard → Plugins → Repositories), published from GitHub releases.

### Open questions

- TV clients (Android TV, webOS, Swiftfin) do not run injected web UI: shelves via Home
  Screen Sections and collections reach them, buttons and chat do not. Good enough?
- Hard dependency on the three community plugins, or degrade gracefully when one is
  missing (e.g. collections only)?
