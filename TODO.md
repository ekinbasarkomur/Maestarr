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
