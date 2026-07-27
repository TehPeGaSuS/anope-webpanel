# anope-webpanel

A modern, self-hosted web control panel for [Anope IRC Services](https://www.anope.org/) 2.1, built as a full replacement for the bundled `webcpanel` module — using Anope's JSON-RPC interface instead of scraping IRC output through a bot.

Built for network admins and end users alike: users manage their own nick, channels, memos, and vhost from a browser instead of memorizing IRC commands; opers get a full administrative surface for NickServ, ChanServ, BotServ, MemoServ, HostServ, and OperServ — without ever needing to be connected to IRC.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![Flask](https://img.shields.io/badge/flask-3.x-black.svg)

---

## Table of contents

- [Why this exists](#why-this-exists)
- [Screenshots](#screenshots)
- [Features](#features)
- [Requirements](#requirements)
- [Anope configuration](#anope-configuration)
- [Installation](#installation)
- [Configuration reference (`.env`)](#configuration-reference-env)
- [Clickable confirmation emails](#clickable-confirmation-emails)
- [Running in production](#running-in-production)
- [How it works](#how-it-works)
- [Security](#security)
- [Known limitations / roadmap](#known-limitations--roadmap)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## Why this exists

Anope ships with `webcpanel`, a module that renders HTML server-side from inside Anope itself. It works, but it's tightly coupled to Anope's own template engine, hard to theme, and hard to extend without touching C++.

Anope 2.1 also ships a proper **JSON-RPC** interface (`jsonrpc` + `rpc_user` + `rpc_data` + `rpc_message` + `rpc_system` modules) that exposes essentially everything IRC operators and users can do over IRC — including running arbitrary service commands (`anope.command`), reading structured account/channel/user data (`anope.account`, `anope.channel`, `anope.user`), and checking credentials (`anope.checkCredentials`) — as clean HTTP calls.

anope-webpanel is a standalone Flask application that talks to Anope purely over that RPC interface. No IRC bot, no polling, no scraping — every action a user or oper takes in the browser is a single `anope.command` call, and Anope's own permission system (the same one enforced on IRC) decides whether it's allowed. That means the panel doesn't need to reimplement Anope's privilege model at all — it trusts Anope to say no.

## Screenshots

_TODO: add screenshots of the dashboard, NickServ settings, ChanServ modes page, and the dark theme before making the repo public._

## Features

Full coverage of every command Anope exposes by default (no third-party modules required, beyond optional `chanstats` support) — see [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the complete, dated build log.

### NickServ
- Account info, grouped nicks table, ungroup a secondary nick
- Settings: AUTOOP, KEEPMODES, PRIVATE, MSG (PRIVMSG vs NOTICE), NEVEROP, AUTOLOGIN (cert-based), LANGUAGE, GREET, MASTODON, LOCATION, URL, TIMEZONE, LAYOUT (FLEXIBLE/FIXED/MONOSPACE), display nick, protection, HIDE flags (email/mask/status/quit)
- Optional chanstats opt-in (`SET CHANSTATS`)
- Certificates (fingerprint list, add/remove)
- Access list (ALIST)
- Auto-join list (AJOIN)
- Email change with confirmation link
- Password change
- Password reset — public, unauthenticated flow: request by nick+email, click the emailed link, set a new password
- Registration confirmation — public, clickable link (no login required)
- Resend confirmation email (public, for a lost/expired registration email)
- Nick recovery (RECOVER/GHOST/RELEASE)
- Update (force-refresh memos, channel modes, vhost)
- Two-step nick drop
- **Oper**: nick list/search, find accounts by email (GETEMAIL), per-nick admin view (force password, no-expire, suspend/unsuspend with reason+expiry, forced drop)

### ChanServ
- My Channels dashboard with a quick-switch pill bar
- Settings: AUTOOP, KEEPTOPIC, PEACE, PERSIST, PRIVATE, RESTRICTED, SECUREFOUNDER, SECUREOPS, SIGNKICK, TOPICLOCK, NOEXPIRE, description/URL/email, founder/successor transfer, ban type
- Flags-based access (FLAGS) and numeric ACCESS list
- xOP tiers (VOP/HOP/AOP/SOP/QOP) in one page
- Levels editor (per-privilege inline edit)
- AKICK list with creator/last-used tracking
- Entry messages
- Log configuration
- Live channel modes page: topic, mode string, kick/ban/unban/invite, sync, enforce, get channel key, per-user status (op/deop/halfop/voice/protect/owner and their inverses), status lookup, paginated user list (100/page)
- Quick user actions: ban (with optional expiry+reason), unban, down/up (status refresh)
- Channel stats (letters/words/lines/smileys/actions) and top-10 leaderboard, plus network-wide personal stats and leaderboard — requires the optional `chanstats` module + a MySQL backend
- Clone settings to another channel
- Channel search/list with suspended/no-expire filters
- Two-step channel drop
- **Oper**: suspend/unsuspend

### BotServ
- Assign/unassign a bot to a channel
- All ten kickers (badwords, bolds, caps, colors, flood, italics, repeat, reverses, underlines, AMSG) with time-to-ban and per-kicker tuning (caps min/percent, flood lines/seconds, repeat count)
- Channel options: don't-kick-ops, don't-kick-voices, fantasy commands, greet messages, ban expiry
- Bad words list (add/delete/clear, with ANY/SINGLE/START/END matching)
- SAY / ACT (make the bot speak)
- **Oper**: network bot list, add/rename/delete bots, mark a bot private

### MemoServ
- Inbox with unread highlighting, read/delete/delete-all
- Send to a nick or channel
- Cancel your last unread memo
- Check whether your last memo to someone was read
- Ignore list (block memos by nick/host)
- Notification preferences (6 modes) and memo limit
- **Oper**: broadcast a memo to all users, or to all staff

### HostServ
- Request a vhost, view your current one, turn it on/off, sync to grouped nicks
- Browse and claim from the network's vhost offer list
- **Oper**: manage all vhosts (search, set, delete), review/approve/reject pending requests, manage the offer list

### OperServ
- AKILL list, CHANKILL (ban + kick every user on a channel)
- Services ignore list
- Sessions
- Network-wide user/channel search (USERLIST/CHANLIST)
- Services operator management (list, add, remove — opertype picker)
- Stats (users, AKILL count, hash tables, password encryption, uplink, uptime)
- Seen-database maintenance (stats/clear)
- News (logon / oper / random — list, add, delete)
- Force channel/user modes
- Noop (lock out a compromised server's opers)
- Jupe a server
- Danger zone: reload config, force a database save, restart/shutdown/quit — the latter three require typing the network name to confirm, mirroring Anope's own built-in safeguard

### Everything else
- Light/dark theme, persisted, flicker-free on load, including the login page
- Whitelabel branding via `.env` (network name, URL, logo, accent color)
- Every IRC-formatted response is parsed and IRC formatting-escaped before display — nothing raw ever reaches the page
- Handles all three Anope `LAYOUT` output formats (FLEXIBLE/FIXED/MONOSPACE) transparently

## Requirements

- **Anope IRC Services 2.1+**, with these modules enabled: `httpd`, `jsonrpc`, `rpc_user`, `rpc_data`, `rpc_message`, `rpc_system`
- **Python 3.9+**
- An IRCd Anope is already linked to (any IRCd Anope supports — this was built and tested against UnrealIRCd 6, but nothing in the panel talks to the IRCd directly; it only ever talks to Anope's RPC endpoint)
- Optional: MySQL/MariaDB + the `chanstats` module, if you want channel/network activity stats

## Anope configuration

Add to (or verify in) your `modules.conf`:

```
module { name = "httpd"
  httpd { name = "httpd/main"; ip = "127.0.0.1"; port = 8080; timeout = 30 } }

module
{
	name = "jsonrpc"
	server = "httpd/main"

	token
	{
		token = "generate-a-long-random-token-here"
		methods = "~anope.message* anope.*"
	}
}

module { name = "rpc_user"; pretenduser = yes }
module { name = "rpc_data" }
module { name = "rpc_message" }
module { name = "rpc_system" }
```

Notes:
- Bind `httpd` to `127.0.0.1` unless you specifically want the RPC endpoint reachable from outside the box — the panel talks to it over plain HTTP, so put it behind your existing reverse proxy / firewall rules, not the public internet.
- The `token`'s `methods` glob determines which RPC methods that token may call. `anope.*` covers everything the panel uses (`anope.command`, `anope.account`, `anope.channel`, `anope.checkCredentials`, the `anope.list*` calls). The `~anope.message*` exclusion is fine to leave as-is — the panel never calls the raw messaging RPC methods; anything message-like (BotServ SAY/ACT, memos) goes through `anope.command`.
- `pretenduser = yes` on `rpc_user` lets commands execute for an account that isn't currently connected to IRC, which the panel relies on constantly (e.g. checking credentials, reading settings, running commands) — without it, most of the panel simply won't work for offline users.
- We recommend a plain (non-hashed) token for simplicity, generated with something like `openssl rand -hex 32`. If you'd rather hash it, see `token_hash` in Anope's own `modules.conf` documentation — `rpc.py` sends the token base64-encoded either way (an Anope RPC quirk, not a security measure).

## Installation

On newer Ubuntu/Debian, `venv` is split out of the base `python3` package and won't be there by default — install it first or `python3 -m venv` will fail with a "No module named venv" / "ensurepip is not available" error:

```bash
sudo apt install python3-venv python3-pip
```

Then:

```bash
git clone https://github.com/TehPeGaSuS/anope-webpanel.git
cd anope-webpanel

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env — see the Configuration reference below

python3 app.py
```

By default this starts a development server on the host/port set in `.env`. Visit it in a browser and log in with any Anope account's nick and password.

## Configuration reference (`.env`)

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | yes | Flask session signing key. Generate one with `python3 -c "import secrets; print(secrets.token_hex(32))"` — never reuse the example value. |
| `FLASK_DEBUG` | no | `1` to enable Flask's debug reloader/debugger. Never enable in production — the debugger allows arbitrary code execution if reachable. |
| `BIND` | no | Interface to bind to. Default `127.0.0.1`; use `0.0.0.0` only behind a reverse proxy. |
| `PORT` | no | Port for the Flask dev server. Default `5000`. |
| `ANOPE_RPC_URL` | yes | Full URL to Anope's JSON-RPC endpoint, e.g. `http://127.0.0.1:8080/jsonrpc`. |
| `ANOPE_RPC_TOKEN` | yes | The plaintext token from your `jsonrpc` module's `token` block. `rpc.py` base64-encodes it automatically. |
| `PANEL_URL` | no | Public base URL of this panel (no trailing slash). Only used for documentation/consistency — see [Clickable confirmation emails](#clickable-confirmation-emails) below, since Anope's mail templates need the matching value set independently. |
| `NETWORK_NAME` | no | Displayed in the header and page titles. |
| `NETWORK_URL` | no | Your network's main website, linked from the header. |
| `NETWORK_LOGO` | no | URL or local path (`/static/logo.png`) to a logo image. Leave blank for a text fallback. |
| `NETWORK_COLOR` | no | Hex accent color, drives the active-tab underline and primary buttons. Default `#1f6feb`. |

## Clickable confirmation emails

By default, Anope's registration/password-reset/email-change emails just tell the user to run an IRC command (`/msg NickServ CONFIRM ...`). This panel exposes matching web routes so those emails can instead contain a clickable link that lands the user directly on a pre-filled confirmation page — no IRC client, no login required, same pattern as most sites (GitHub, Google, etc.): the link itself is the proof of identity, so the user only supplies what the link couldn't carry (e.g. a new password).

Routes provided:
- `/nickserv/confirm/register/<nick>/<code>` — registration confirmation
- `/nickserv/confirm/email/<nick>/<code>` — email change confirmation
- `/nickserv/reset/<nick>/<code>` — password reset (prompts only for the new password)

To wire these into the actual emails, add a `define` to your Anope config and reference it in the `mail` block:

```
define
{
	name = "panel.host"
	value = "https://your-panel-domain.example"
}
```

Then in `anope.conf`'s `mail` block:

```
registration_message = "Hi,

			You have requested to register the nickname {nick} on {network}.
			Click here to complete registration: ${panel.host}/nickserv/confirm/register/{nick}/{code}
			Or type \" /msg NickServ CONFIRM REGISTER {code} \" on IRC.

			If you don't know why this mail was sent to you, please ignore it silently.

			{network} administrators."

reset_message = "Hi,

		You have requested to have the password for {nick} reset.
		Click here to reset it: ${panel.host}/nickserv/reset/{nick}/{code}
		Or type \" /msg NickServ CONFIRM RESETPASS {nick} {code} \" on IRC, then SET PASSWORD.

		If you don't know why this mail was sent to you, please ignore it silently.

		{network} administrators."

emailchange_message = "Hi,

		You have requested to change your email address from {old_email} to {new_email}.
		Click here to confirm: ${panel.host}/nickserv/confirm/email/{account}/{code}
		Or type \" /msg NickServ CONFIRM EMAIL {code} \" on IRC.

		If you don't know why this mail was sent to you, please ignore it silently.

		{network} administrators."
```

**The `$` is not optional.** Anope has two completely separate substitution mechanisms that both use curly braces: `${name}` (defined by a `define` block, expanded once at config-parse time) and bare `{name}` (Anope's own runtime message tokens — `{nick}`, `{code}`, `{network}`, `{account}`, etc., expanded when the email is actually sent). Using `{panel.host}` without the `$` will load with **no error at all**, but the value silently never gets substituted — it isn't one of the tokens Anope's mail composer recognizes for these messages, so it goes out as dead literal text in every real email. Always verify with a real registration/reset before trusting it.

After editing, reload Anope's config (`/msg OperServ RELOAD`, or the panel's own OperServ → Danger Zone → Reload, if you're already an oper) — this is non-disruptive and doesn't drop connections.

Keep `PANEL_URL` in `.env` and the `panel.host` define in sync by hand whenever the panel's public address changes.

## Running in production

The built-in Flask server (`python3 app.py`) is for development only. For production:

1. Run behind a WSGI server, e.g. [Gunicorn](https://gunicorn.org/):
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 127.0.0.1:5000 'app:create_app()'
   ```
2. Put a reverse proxy (nginx, Caddy, etc.) in front for TLS termination.
3. Set `FLASK_DEBUG=0` (or omit it) and use a real, unique `SECRET_KEY`.
4. Consider a process manager (systemd, supervisor) to keep it running and restart on failure.

### systemd (per-user service, no root required)

Tested on Ubuntu. Rather than a system-wide unit under a dedicated service account, this runs as a **user** systemd service under whichever account owns the checkout — simpler permissions, no `sudo` needed to manage it day-to-day.

One-time setup, as that user:

```bash
loginctl enable-linger "$(whoami)"   # let the service keep running after you log out / on boot
mkdir -p ~/.config/systemd/user
```

`enable-linger` is the important part — without it, systemd kills your user's services the moment your last session ends.

Create `~/.config/systemd/user/anope-panel.service` (adjust the paths to wherever you cloned the repo):

```ini
[Unit]
Description=anope-webpanel
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/anope-webpanel
Environment=PATH=%h/anope-webpanel/.venv/bin
ExecStart=%h/anope-webpanel/.venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 'app:create_app()'
Restart=on-failure

[Install]
WantedBy=default.target
```

(`%h` is systemd's placeholder for the unit owner's home directory — no need to hardcode a username.)

Then enable and start it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now anope-panel.service
```

Manage it the same way as any systemd service, just with `--user` on every command: `systemctl --user status anope-panel`, `journalctl --user -u anope-panel -f`, `systemctl --user restart anope-panel`.

## How it works

- **Authentication** is stateless from Anope's perspective: on login, the panel calls `anope.checkCredentials(nick, password)`, and on success stores the account name (plus a cached oper flag) in a signed Flask session cookie. There's no separate panel-side user database.
- **Every action** is a single call to `anope.command(source, service, command_string)` — literally the same command a user would type on IRC, executed with `source` set to the acting account. Anope resolves permissions exactly as it would for that account on IRC; the panel does not duplicate or second-guess Anope's own privilege model. Coarse `is_oper` checks in the panel exist purely for UX (don't show admin pages to users who obviously can't use them) — the real security boundary is always Anope itself.
- **Parsing**: Anope's RPC layer returns command output as literal IRC-formatted text lines (the same thing that would print to an IRC client), not structured JSON, for anything routed through `anope.command`. `utils.py` contains dedicated parsers for every list/info format the panel displays, each written and verified against real captured output — Anope's output format also varies by the account's `LAYOUT` setting (FLEXIBLE/FIXED/MONOSPACE), which the parsers handle transparently.
- **Channel URLs** never contain a literal `#` (to avoid `%23` noise) — routes take the channel name without it and add it back before any RPC call.

## Security

- Anope's own command-permission system is the real authorization boundary — verified live during development (a non-privileged account attempting an oper-only command gets rejected by Anope itself, not by the panel).
- **No CSRF protection yet.** There are no CSRF tokens on any form. Modern browsers' default `SameSite=Lax` cookie behavior blocks the most naive cross-site attacks, but that's not a substitute for real tokens on a panel with destructive actions (channel/nick drop, AKILL, service restart). Contributions adding `flask-wtf` or equivalent are very welcome.
- Anope reports **command-level failures as normal successful RPC replies**, not JSON-RPC errors (e.g. "wrong confirmation code" comes back as an ordinary `result`, not an `error`). Any code that chains a follow-up action off an RPC call's success must check the actual reply text, not just the absence of an exception — see `_anope_confirmed()` in `routes/nickserv.py` for the pattern, and `docs/DEVELOPMENT.md` for the full story of a near-miss vulnerability this caused during development.
- Report security issues by opening a private security advisory on GitHub rather than a public issue, if the repository has that enabled; otherwise a regular issue is fine for anything that isn't immediately exploitable.

## Known limitations / roadmap

- No CSRF protection (see [Security](#security))
- Channel memos (`MS LIST #channel`) not yet exposed — same underlying commands as personal memos, just channel-scoped
- OperServ Sessions/Exception list still show raw text instead of a parsed table
- Lower-value/higher-risk OperServ admin commands not exposed: CONFIG, MODINFO/MODLIST/MODLOAD/MODRELOAD/MODUNLOAD, LOGSEARCH, DEFCON, FORBID, SNLINE/SQLINE, SVSNICK/SVSJOIN/SVSPART, KICK, KILL
- No automated test suite yet
- Chanstats parsers are verified against Anope's source code but not yet against live populated data — see `docs/DEVELOPMENT.md` for details

See `docs/DEVELOPMENT.md` for the full, dated list.

## Troubleshooting

- **Everything returns "Could not connect to Anope services"**: check `ANOPE_RPC_URL` and that Anope's `httpd` module is actually listening where you think it is (`ss -tlnp | grep <port>` on the Anope host).
- **Login fails for an account you know is correct**: confirm `rpc_user` is loaded with `pretenduser = yes`, and that your token's `methods` glob actually permits `anope.checkCredentials`.
- **Oper pages 403 even for an account with an opertype**: an opertype assigned purely via `OperServ OPER ADD` (as opposed to one configured in `operserv.conf`) defaults to `require_oper = true` in Anope — the connected client also needs real IRCd oper mode (`+o`), not just the services opertype, before Anope will honor OperServ command permissions. This is Anope's behavior, not a panel bug.
- **A command "succeeds" but nothing changed**: see the RPC reply-format note under [Security](#security) — some Anope failures don't raise an error at the transport level.
- For anything else, `docs/DEVELOPMENT.md` documents a long list of specific, previously-hit bugs with root causes — worth a search before assuming something new is broken.

## Contributing

Issues and pull requests welcome. A few ground rules given the codebase's history:

- **Verify against a live Anope instance where possible.** Several bugs in this project's history came from output formats that looked reasonable on paper but didn't match real Anope replies (date formats, column padding, layout-dependent formatting). If you're adding a parser, test it against real captured output, not just the `HELP` text.
- **Check for route/endpoint name collisions** before adding new ones — Flask will crash hard (`AssertionError: View function mapping is overwriting an existing endpoint`) on a duplicate, and it's happened more than once in this project's history.
- **Anope's RPC layer reports failures as normal replies**, not exceptions (see [Security](#security)) — don't assume "no exception" means "it worked" for anything with a real consequence.

## License

[MIT](LICENSE).

## Acknowledgments

- The [Anope](https://www.anope.org/) team, for the services daemon and its JSON-RPC interface this panel is built entirely on top of.
- Inspired by (and built as a replacement for) Anope's bundled `webcpanel` module.
