# Development Notes

Technical reference for anope-webpanel: architecture, setup requirements,
and the non-obvious Anope behaviors that shaped the implementation. If
you're extending the panel or debugging something that looks wrong, the
[Gotchas](#anope-gotchas--non-obvious-behavior) section below is worth
reading first — several of these cost real debugging time to figure out
and aren't documented anywhere in Anope's own docs.

For install/usage docs, see the [README](../README.md).

---

## Project overview

A modern web control panel for Anope IRC Services 2.1, built as a
replacement for the bundled `webcpanel` module. Designed to be
whitelabel-ready and easy to extend by non-developers (plain HTML
templates, no build tooling).

**Stack:** Flask + Jinja2 + HTMX + TailwindCSS (CDN) + vanilla CSS variables

**Key design decisions:**
- Stateless auth: `anope.checkCredentials` called on every login, result cached in the Flask session.
- The RPC bearer token must be **base64-encoded** before sending (an undocumented Anope quirk — see `jsonrpc.cpp`).
- Channel names are stored **without `#`** in URLs (e.g. `/chanserv/PTirc/access`) — the `chan()` helper in `routes/chanserv.py` adds `#` back before RPC calls, `chanurl()` strips it for `url_for()`.
- All Anope output is parsed via functions in `utils.py` — never trust raw IRC strings directly in templates.
- `strip_irc()` in `utils.py` strips IRC formatting characters before parsing anything.
- Anope's `NS SET LAYOUT` changes the output format of nearly every list command across every service — see the Gotchas section, this is the single biggest source of parsing bugs in this codebase.

---

## File structure

```
anope-panel/
  app.py                   # Flask factory, blueprints, context_processor for network branding
  auth.py                  # login_required decorator, login/logout routes, session caching
  rpc.py                   # RPC client wrapper (base64 token, error handling)
  utils.py                 # All IRC output parsers + strip_irc() + DATE_RE + search-mask helpers
  routes/
    nickserv.py            # NickServ routes
    chanserv.py             # ChanServ routes (also has chan() / chanurl() helpers)
    botserv.py              # BotServ routes (own chan() / chanurl() copies)
    services.py              # MemoServ + HostServ routes
    operserv.py             # OperServ routes
  templates/
    base.html               # Layout: top nav, channel pill bar, sidebar, content
    _flashes.html            # Shared flash-message partial
    _pagination.html         # Reusable pagination macro
    login.html               # Standalone login page (does not extend base.html)
    dashboard.html
    nickserv/                # info, set, cert, alist, ajoin, drop, list, oper/<nick>,
                              # email, password, confirm/reset flows, recover, resend, getemail (oper)
    chanserv/                # index, set, access, access_num, xop, levels, akick,
                              # entrymsg, log, modes, stats, top, gstats, clone, list, drop
    botserv/                 # index (kickers+settings+say/act), badwords, bots (oper)
    memoserv/                # index, read, send, settings, ignore, sendall (oper), staff (oper)
    hostserv/                # index, offerlist, admin, waiting, offer (oper)
    operserv/                # akill, chankill, forbid, ignore, sessions, userlist, chanlist,
                              # oper, stats, seen, news, mode, jupe, noop, danger
  .env.example
  requirements.txt
```

---

## Anope modules required (modules.conf)

```
module { name = "httpd"
  httpd { name = "httpd/main"; ip = "127.0.0.1"; port = 8080; timeout = 30 } }

module { name = "jsonrpc"; server = "httpd/main"
  token { token = "your_token"; methods = "anope.*" } }

module { name = "rpc_user"; pretenduser = yes }
module { name = "rpc_data" }
```

---

## Environment variables (.env)

```
SECRET_KEY=...
FLASK_DEBUG=0
BIND=127.0.0.1
PORT=5000
ANOPE_RPC_URL=http://127.0.0.1:8080/jsonrpc
ANOPE_RPC_TOKEN=your_token_plaintext   # NOT base64 — rpc.py handles encoding
NETWORK_NAME=My IRC Network
NETWORK_URL=https://example.com
NETWORK_LOGO=https://example.com/logo.png   # URL or local path, blank = text fallback
NETWORK_COLOR=#1f6feb                        # Drives --accent CSS variable throughout
PANEL_URL=https://panel.example.com          # Used to build clickable links in confirmation emails
```

---

## Features

### NickServ
Info, Settings (all toggles including HIDE_*/AUTOLOGIN/NEVEROP, layout,
timezone, display nick, danger zone), Certificates (CERT LIST — self-service
ADD is a single click, see Gotchas), Access List, Auto Join, Email change,
Password change, unauthenticated confirm/reset-password flows (clickable
email links), Nick Drop, Nick List + oper-only Nick management (SASET,
SUSPEND/UNSUSPEND, DROP with override), UPDATE, RECOVER/GHOST/RELEASE,
RESEND, GETEMAIL (oper).

### ChanServ
My Channels, Settings, Flags, numeric Access list, xOP (VOP/HOP/AOP/SOP/QOP),
Levels, Akick, Entry Messages, Log settings, live channel Modes page
(topic/mode/kick/ban/invite/sync/enforce/status, paginated user list),
Stats + chanstats (SET CHANSTATS, GSTATS, TOP10/GTOP10), Clone, Channel
List (with search), Drop, BAN (with expiry), DOWN/UP.

### BotServ
Per-channel: assign/unassign, all 10 kickers, channel options, bad words
list, SAY/ACT. Oper: network bot list, add/change/delete bots, mark bot
private.

### MemoServ
Memo list (unread highlighted), read/send/delete, CANCEL, CHECK, Ignore
List, Settings (notify modes, limit), oper SENDALL/STAFF broadcast.

### HostServ
VHost request/activate/deactivate/group, Offer List (browse + take an
offer), oper: All VHosts (list/set/setall/del/delall), Waiting Requests
(activate/reject), Offer List management (add/del/clear).

### OperServ
AKILL, Chankill, Services Ignore List, Sessions + session-limit Exceptions
(parsed tables, threshold control), User List + Channel List
(both paginated, with search — see Gotchas), Forbid (paginated, searchable,
NICK/CHAN/EMAIL/PASSWORD/REGISTER), Services Operators (list/add/del),
Stats, News (LOGONNEWS/OPERNEWS/RANDOMNEWS), Seen, Force Mode, Noop, Jupe,
Danger Zone (Reload/Update/Restart/Shutdown/Quit — the latter three
require typing the network name to confirm, matching Anope's own CLI
behavior).

### UI / UX
Light/dark theme (persisted, FOUC-free), responsive layout (collapsible
sidebar below 860px, scrollable tables/nav), network branding via `.env`,
per-page pagination on every list-style page.

---

## Anope gotchas & non-obvious behavior

These cost real debugging time to figure out and are either undocumented
or documented in a way that's easy to miss. If you're touching a related
route or parser, read the relevant bullet first.

**RPC command failures look like success.** `anope.command` reports
command-level failures (wrong code, access denied, invalid argument) as a
normal successful JSON-RPC `result` — never an `error`. Any code that
chains a follow-up action on a prior call must check the *text* of the
reply, not just the absence of an exception. This bit us once for real:
an early draft of the password-reset flow chained `CONFIRM RESETPASS` →
`SET PASSWORD` trusting "no exception" as "code was valid" — which would
have let anyone reset any account's password with a garbage code. Fixed
with a helper that fails closed unless the expected success phrase is
actually present in the reply.

**`NS SET LAYOUT` changes the output format of almost every list command,
across every service** (NickServ, ChanServ, BotServ, MemoServ, HostServ,
OperServ), between three shapes: `FIXED` (tabular columns), `FLEXIBLE`
(colon/dash-delimited free text, e.g. `"1: mask -- created by X on
DATE"`), and `MONOSPACE` (FIXED + a `\x11` prefix, stripped by
`strip_irc()`). Every parser in `utils.py` must handle FIXED and FLEXIBLE
— the docstring on each parser documents both real formats it was
verified against. When adding or touching a parser, verify against real
captured output in **both** layouts, not just whichever one your test
account happens to be set to — this codebase has shipped the same class
of bug (parser silently returns zero rows, or worse, garbled data) many
times by only checking one.

**Dates render in a second format depending on the account's language
setting, independent of layout.** A blank/default-language account gets
C-style ctime dates (`"Mon Jul 27 11:28:43 2026"`); an `en_US.UTF-8`
account gets a 12-hour/AM-PM form with a variable timezone abbreviation
(`"Mon 07 Mar 2016 01:20:00 AM CET"`). Both are anchored in the shared
`DATE_RE` constant in `utils.py`, used by every FIXED-layout parser —
fixing it there covers all of them at once. Worth remembering since a
FIXED-layout account with a real language set (common for real users,
uncommon for freshly-created test accounts) can silently break date
parsing in a way layout-only testing won't catch.

**Anope's LIST-family commands need explicit glob patterns.** `NickServ
LIST`, `ChanServ LIST`, `HostServ LIST`, `OperServ CHANLIST`, and
`OperServ USERLIST` all require a wildcarded pattern to do a substring
match — a bare typed term matches nothing (confirmed live: `ChanServ LIST
clitest` against a channel literally named `#clitest` returns 0 matches;
`LIST *clitest*` finds it). `USERLIST` is stricter still: its pattern must
be shaped like `nick!user@host[#realname]`, not just wildcarded. The
panel's search boxes route through `as_search_mask()` / `as_userlist_mask()`
in `utils.py`, which auto-wrap a bare term in `*...*` while leaving
deliberate input (existing wildcards, a `//regex/` pattern, or a `#X-Y`
range) untouched.

**`FORBID` gotchas**: `FORBID LIST` requires a type argument (`NICK` /
`CHAN` / `EMAIL` / `PASSWORD` / `REGISTER`) — there's no "list everything"
mode, and no pattern/mask argument either (the panel's Forbid search
filters client-side against what Anope already returned). Anope itself
caps `FORBID LIST` output around 300 entries per call regardless of how
many exist. Entries loaded via `os_forbid`'s file-based bulk import
(`file { type = "email"; file = "..."; }` in `operserv.conf`) show the
config file path as their Creator and **cannot be deleted** via `FORBID
DEL` — the panel detects this by checking for `/` in the Creator field
(real nicks never contain one). That config block's `file =` path
resolves relative to Anope's **`conf/`** directory, not `data/`.

**Self-service `CERT ADD` takes zero arguments.** It grabs the fingerprint
of the *currently connected* TLS client — there's no way to register an
arbitrary typed-in fingerprint for yourself (the two-argument form is
oper-only, for modifying someone else's list). This is deliberate Anope
behavior, not a bug — see
[anope/anope#326](https://github.com/anope/anope/issues/326). The panel's
"Add Certificate" page is a single button, not a text field, and only
works if you're simultaneously connected to IRC over TLS with SASL
EXTERNAL / certfp while using the panel.

**NickServ confirm/reset commands resolve identity from the RPC `source`
parameter, not from command arguments.** `CONFIRM REGISTER <code>` and
`CONFIRM EMAIL <code>` resolve the target account from `source.GetAccount()`
— you must call them with `source=<nick>`, not just embed the nick in the
command string. `RESETPASS` requires **both** `nickname` and `email` (it's
unauthenticated by design, so identity comes from proving you know the
registered email). `CONFIRM RESETPASS` only validates the code — it does
**not** set a new password; that's a separate `SET PASSWORD` call
afterward, which works with `source=<nick>` alone (no live IRC session
required).

**Clickable links in confirmation emails need `${panel.host}`, not
`{panel.host}`.** Anope has two separate substitution mechanisms: a
config-parse-time `define`/`${name}` substitution (triggered only by a
literal `$` before `{`), and a completely different runtime message-token
substitution (`{nick}`/`{code}`/`{account}`, bare braces, resolved when the
email is actually composed). Using the bare-brace form for a `define`
value loads with **no error at all** but silently never substitutes —
the literal text ships in real emails. Set the value once via:
```
define { name = "panel.host"; value = "https://panel.example.com" }
```
...and reference it as `${panel.host}/nickserv/confirm/register/{nick}/{code}`
in the `mail` block templates.

**`require_oper` needs a live `+o`, not just a services opertype.** An
account granted an opertype purely via `OperServ OPER ADD` (as opposed to
one configured in `operserv.conf`) defaults to `require_oper = true`
(`include/opertype.h`) — the *connected IRC client* also needs real ircd
oper mode before Anope will honor OperServ command permissions. A failing
request comes back as a generic `"No such command"` (Anope's RPC layer
doesn't distinguish "doesn't exist" from "access denied"), which reads
like a panel bug but usually isn't — check this first.

**Anope's built-in `Services Administrator` opertype does not include
`operserv/userlist` or `operserv/chanlist`** by default — only `Services
Root` (`*`) does. Worth flagging for admins configuring opertypes who want
non-Root opers to use those two panel pages.

**`OperServ NEWS`/`STATS` details**: there's no generic `NEWS` command —
it's three separate commands (`LOGONNEWS`/`OPERNEWS`/`RANDOMNEWS`), each
with its own `LIST`/`ADD`/`DEL`. `SEEN` (database maintenance for the
`seen` fantasy command) registers on OperServ despite the command living
in `chanserv.conf` — easy to miss when looking for it.

**`ChanServ UNBAN <channel> [nick]` removes bans blocking a specific nick**
(resolved by their current host) — it is not a generic "remove this
arbitrary ban mask" command. A founder-level `CS MODE #chan -b mask` on a
ChanServ-managed ban appears to succeed but is silently reverted; ChanServ
actively re-syncs bans it manages. There's no direct Anope command for
"remove an arbitrary ban mask" at the founder level.

**HostServ `OFFERLIST TAKE`** takes a single argument
(`{vhost|entry-num}`) — no separate ident parameter.

**`OFFERLIST` requires a live IRC connection, even to just browse.**
Anope's `OFFERLIST`/`OFFERLIST TAKE` command (`CommandHSOfferList`) sets
`RequireUser(true)` unconditionally, so it fails with a generic `"No such
command"` for any account that isn't simultaneously connected to IRC —
confirmed live, identical RPC call succeeds when connected and fails
otherwise. The oper-only `OFFER LIST/ADD/DEL/CLEAR` command has no such
requirement. The panel can't work around this (it's not something to
patch around in Anope's source), so it catches the specific error and
shows a clear explanation instead of the raw Anope message.

**`OFFERLIST` and `OFFER LIST` return genuinely different reply shapes**
despite listing the same underlying offers — they're different Anope
command classes (`CommandHSOfferList` vs `CommandHSOffer`). Bare
`OFFERLIST` includes a "your vhost preview" and an expiry phrase per
entry; oper `OFFER LIST` has neither, just entry/template/optional
reason, in both FIXED and FLEXIBLE layout. `parse_hs_offerlist()` has to
try both shapes — don't assume two similarly-named commands share a
format without checking each independently.

**`OperServ SESSION LIST <threshold>` rejects a threshold of 1** with
"Invalid threshold value. It must be a valid integer greater than 1." —
not an error reply, a normal-looking text line (same "failures look like
success" gotcha above), so a naive caller that doesn't check the text
will render that message as if it were session data. The panel defaults
its threshold input to 2.

**Anope oper-privileged commands stay privileged over RPC.**
`anope.command`'s `CommandSource` is built from the real `NickCore` of
the account passed in the RPC call (`rpc_user.cpp`), so Anope's own
permission checks (e.g. `nickserv/suspend`, `operserv/session`) apply
exactly as if that account ran the command from IRC — there's no RPC-side
bypass. A non-oper account can't be granted a privileged action just by
having the panel call it on their behalf; that would need a real,
separately-provisioned service oper account in `opers.conf`.

---

## Known limitations / roadmap

- **HostServ VALIDATE** intentionally not exposed: it requires publishing
  a DNS TXT record and Anope verifying it via live lookup — an
  out-of-band step the panel can't assist with. Users can validate from
  IRC once their TXT record propagates.
- Not yet exposed: `CONFIG`/`MODINFO`/`MODLIST`/`MODLOAD`/`MODRELOAD`/
  `MODUNLOAD`/`LOGSEARCH`/`DEFCON`/`SNLINE`/`SQLINE`/`SVSNICK`/`SVSJOIN`/
  `SVSPART`/`KICK`/`KILL` — lower-value or higher-risk admin commands.
- **MemoServ channel memos** (`MS LIST #channel`) not yet built — would
  want its own view under the channel's ChanServ context.
- No CSRF protection yet — flagged here deliberately, see the README's
  Security section.

---

## Contributing

Anope command syntax should always be pulled from live `HELP <command>`
output (or the relevant `modules/**/*.cpp` source) before writing a route
— several of the gotchas above exist because an earlier assumption about
command syntax or reply format turned out to be wrong. When adding a new
list-style parser, test it against real captured output in both `FIXED`
and `FLEXIBLE` layout before considering it done.
