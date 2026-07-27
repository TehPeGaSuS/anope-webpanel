# Development Notes

Last updated: 2026-07-27

This is the running technical changelog for anope-webpanel: what got built,
what bugs were found and fixed (with root causes), and the quirks of
Anope's RPC/command layer that shaped the implementation. If you're
extending the panel or debugging something that looks wrong, read this
before re-deriving something already figured out here — several of the
entries below document real, non-obvious bugs (a live-tested vulnerability,
Anope reply-format gotchas, silent Jinja rendering bugs) worth knowing
about before touching related code.

For install/usage docs, see the [README](../README.md).

---

## Session Updates (2026-07-27, cont'd) — Forbid search, top pagination, table-overflow fix

- **Fixed a real layout bug on the FORBID page**: neither `.card` nor
  `.data-table` constrained width or wrapped long content, so a long
  unbroken string in Mask/Creator/Reason (e.g. a long domain, or a
  descriptive reason) could push the table wider than its card and spill
  out past the container instead of wrapping. Fixed with `table-layout:
  fixed` + explicit `<colgroup>` column widths, `word-break: break-word`
  on the three free-text columns, and an `overflow-x: auto` wrapper around
  the table as a fallback for anything that still doesn't fit. Verified
  live with a real long mask (`*@zzzzzzzzzzzzzz-7619.dynv6.net`) and a long
  reason string.
- **Added search/filter to the FORBID page** (`?search=`). Anope's `FORBID
  LIST` takes no mask/pattern argument — confirmed via `HELP FORBID`, only
  a type — so this filters server-side in Python against whatever Anope
  already returned (substring match, case-insensitive, across mask/
  creator/reason) before pagination is applied. Most useful on the EMAIL
  type with the 300-entry disposable-domains list loaded. Verified live:
  a broad term correctly matched across all three fields (including a
  case where "mail" false-positived by matching literally inside the
  file-import Creator path `conf/disposable_emails.txt` — not a bug, just
  a reminder the search is genuinely substring-across-all-fields, not
  mask-only), and a specific domain substring correctly narrowed 300
  entries down to 1.
- **Added a second pagination bar above the table**, not just below it —
  same macro, same params, now also showing a "Page X of Y" label. Applies
  to both USERLIST and FORBID (they share `_pagination.html`). The macro
  now renders a `border-bottom` unconditionally so the top instance reads
  as a divider from the table; harmless at the bottom instance too (reads
  as a divider from empty space before the card's rounded corner).

---

## Session Updates (2026-07-27, cont'd) — Paginated User List, new OperServ FORBID page, HostServ OFFERLIST reason bug

- **OperServ USERLIST paginated.** `routes/operserv.py`'s `userlist()` now slices
  results 100/page instead of dumping the whole (potentially huge) list
  server-side. New reusable `templates/_pagination.html` Jinja macro (a `{%
  macro pagination(endpoint, page, total_pages) %}` that forwards arbitrary
  extra query params via Jinja's `**kwargs`), modeled on the pagination
  block already proven in `templates/chanserv/modes.html`. Verified live by
  temporarily dropping `per_page` to 3 via `sed`, confirming page 1/2 show
  distinct entries and an out-of-range page (99) clamps to the last valid
  page instead of erroring, then reverting to 100.

- **New: OperServ FORBID page** (`routes/operserv.py`: `forbid()` /
  `forbid_add()` / `forbid_del()`, `templates/operserv/forbid.html`). This
  command was entirely missing from the panel despite being core OperServ
  functionality. Notes:
  - `FORBID LIST` requires a type argument (no "all types" mode per `HELP
    FORBID`) — the page has a NICK/CHAN/EMAIL/PASSWORD/REGISTER tab
    selector.
  - New parser `parse_os_forbid_list()` in `utils.py`, verified against
    real live data in **both** layouts from the start (lesson learned from
    the LOGONNEWS incident — see below): FIXED is a straight column table;
    FLEXIBLE is always `"mask on TYPE -- created by CREATOR; expires in
    <Never|date> (reason)"` — note FORBID's flexible phrasing is always
    "expires **in**", even for an absolute/Never expiry, unlike other
    commands that switch between "expires in" (relative) / "expires on"
    (absolute).
  - Entries loaded via Anope's file-based bulk-import (`os_forbid`
    module's `file{}` config block — see below) show the config file path
    as their Creator and **cannot be deleted** via `FORBID DEL` (Anope
    rejects it). The template detects this by checking for `/` in the
    Creator field (real nicks never contain one) and shows a disabled
    "from file" label instead of a Delete button. Verified against the
    live 300-entry EMAIL forbid list (see below) — every row correctly
    shows as non-deletable.
  - Uses the same pagination macro as USERLIST.

- **Loaded a real 300-entry EMAIL forbid list on testnet** to get
  realistic pagination data, using Anope's **built-in file-based FORBID
  bulk import** (`os_forbid` module's `file { type = "email"; file =
  "..."; reason = "..."; }` config block in `operserv.conf`) rather than
  ~300 sequential RPC calls. Source: first 300 domains from
  `disposable-email-domains/disposable-email-domains`'s blocklist,
  transformed to Anope's `*@domain` mask format. One gotcha hit and fixed:
  relative `file =` paths in this config block resolve against **`conf/`**
  (via `Anope::ExpandConfig`), not `data/` — first attempt put the file in
  `data/` and got a live "Unable to read conf/disposable_emails.txt,
  ignoring." log error until moved. Also confirmed a real Anope-side
  constraint: `FORBID LIST` itself caps output at ~300 entries per call
  regardless of how many exist ("End of forbid list - 300/302 entries
  shown") — panel pagination only slices what Anope already returned, it
  can't work around this upstream cap.

- **`parse_hs_offerlist` FLEXIBLE bug found while spot-checking HS OFFER
  after the FORBID work** (not the original "HS OFFER missing on prod"
  report — that one was the earlier FLEXIBLE-audit fix; this is a second,
  narrower bug in the same parser found while re-verifying it live
  end-to-end through the app for the first time). The FLEXIBLE branch was
  swallowing an optional trailing `(reason)` into one opaque "trailer"
  string with no reason extracted, e.g. live output `"1: x / x -- expires
  in 1 day (expiring offer reason)"` rendered as a single blob instead of
  splitting into expiry + reason like the FIXED branch already did.
  Fixed `pattern_flexible` to anchor on the known expiry phrases
  (`does not expire` / `expires in|on ...`) with an optional trailing
  `(reason)` group, matching the FIXED branch's `"expires — reason"`
  output shape so both layouts render identically. Verified live in both
  a no-reason and a with-reason case, plus a FIXED-layout regression
  check (unchanged).

**Process note, reaffirmed**: every parser touched or added this session —
`parse_os_forbid_list` from scratch, `parse_hs_offerlist`'s fix — was
checked against real captured output in **both** FIXED and FLEXIBLE before
being called done, including a full page load through the actual running
app, not just a standalone parser unit test. That's now the bar for any
future parser work, not just an aspiration.

---

## Session Updates (2026-07-27, cont'd) — LOGONNEWS "missing" on production → discovered the whole earlier parser audit was FIXED-only, 14 more fixes

A production report ("LOGONNEWS list shows nothing") turned into the most
important finding of the day. First troubleshooting step ruled out the
panel entirely: the user's live IRC session had lost `+o` after a
reconnect (same `require_oper` behavior documented earlier), confirmed via
`Access denied for user PeGaSuS ... with command LOGONNEWS/STATS/...` in
Anope's log — re-`/OPER`ing fixed it, nothing to do in code.

**Then the user mentioned they run `NS SET LAYOUT FLEXIBLE` on production.**
Every single parser fixed in the two audit passes above — the "9 more
broken list parsers" pass AND the brand-new commands built earlier today
(BotServ, OperServ USERLIST/CHANLIST/IGNORE/News) — had been verified
*exclusively* against FIXED-layout output, because every test account used
this session defaulted to Fixed layout. Nobody had checked FLEXIBLE at
all. Switching a test account to `NS SET LAYOUT FLEXIBLE` and re-running
the exact same commands found **14 more parsers broken or silently wrong
under FLEXIBLE**, several of which are parsers that were JUST rewritten
earlier the same day — the FLEXIBLE branch wasn't missing by oversight in
old code, it was actively *removed* by treating "the format I can see
right now" as "the format," instead of "a format."

**The pattern that keeps costing us**: several of the "new" FIXED formats
documented today turned out to be genuinely new relative to an *old*
docstring that already described the FLEXIBLE shape correctly (from an
even earlier session) — e.g. `parse_hs_list`, `parse_hs_offerlist`,
`parse_ajoin_list`. Those old docstrings weren't wrong, they were just
*incomplete* (FIXED-only accounts hadn't been tested against them yet).
Today's "fix" replaced the FLEXIBLE pattern with the FIXED one instead of
adding FIXED alongside FLEXIBLE — turning a stale-but-half-correct parser
into a fresh-but-still-half-correct one. **Every fix in this entry adds a
branch; none of them replace one.**

Fixed (all in `utils.py`, all verified against real live output in both
layouts, plus a live confirmation `os_oper_list`/`bs_info`/`cert_list`
are *already* layout-agnostic by construction and needed no change):

- `parse_os_news_list` — FLEXIBLE: `"N: text -- created by X on DATE"` vs
  FIXED's tabular columns. **This is the one that triggered the whole
  audit.**
- `parse_os_userlist` / `parse_bs_botlist` — FLEXIBLE: `"name (mask)
  [realname]"`. Previously **silently wrong**, not just empty: the
  FIXED-only 3-token regex still matched FLEXIBLE's shape by accident,
  leaving literal parens/brackets in the captured fields.
- `parse_os_chanlist` — FLEXIBLE: `"#chan -- N user(s); +modes (topic)"`
  vs FIXED's tabular columns.
- `parse_os_ignore_list` — FLEXIBLE: `"mask -- created by X; expires...
  (reason)"`. Also **silently wrong** before the fix (matched by
  accident, produced garbled `creator`/`reason`/`expires` values).
- `parse_bs_badwords` — FLEXIBLE: `"N: word -- type: TYPE"` vs FIXED's
  tabular columns.
- `parse_levels_list` — FLEXIBLE uses `"PRIVILEGE = level"` (with `=`,
  the format an *even earlier* fix had assumed and removed); FIXED has no
  `=` at all. Needed both, not either.
- `parse_entrymsg_list` — FLEXIBLE: `"N: message -- created by X at
  DATE"` vs FIXED's tabular columns.
- `parse_log_list` — FLEXIBLE: `"N: COMMAND on Service: METHOD"` (also
  close to an older assumption) vs FIXED's tabular columns. Same
  short-vs-full command-name resubmission quirk applies to both branches.
- `parse_ns_list` — FLEXIBLE: `"nick (account: X)"` /
  `"nick -- Status (account: X)"` vs FIXED's tabular columns.
- `parse_ajoin_list` — FLEXIBLE: `"N: #channel"` (the original
  pre-existing assumption, dropped instead of kept) vs FIXED's tabular
  columns.
- `parse_hs_list` (LIST/WAITING) — FLEXIBLE: `"N: nick = vhost --
  created by X at DATE"` (again, the original pre-existing assumption,
  dropped instead of kept) vs FIXED's tabular columns.
- `parse_hs_offerlist` — FLEXIBLE: `"N: offered / yours -- trailer"`
  (again, the original pre-existing assumption) vs FIXED's tabular
  columns.

**Already layout-agnostic, verified, no change needed**: `parse_cs_list`
(already had both branches from the earlier pass), `parse_os_oper_list`
(genuinely uses a fixed non-ListFormatter table regardless of layout —
confirmed live, identical output both ways), `parse_bs_info` /
`parse_cs_info` / `parse_ns_info` (key:value line splitting doesn't care
about column alignment), `parse_cert_list` (generic leading-hex-run
extraction naturally matches both shapes).

**Process note for next time**: don't trust "verified against real
output" without checking which layout the test account used. From now on,
any new or touched parser should be tested against **both** FIXED and
FLEXIBLE before being called done — a second disposable test account (or
just `NS SET LAYOUT FLEXIBLE` on the existing one, then set it back) costs
almost nothing and would have caught all fourteen of these in the same
session they were written, instead of via a separate production bug
report.

---

## Session Updates (2026-07-27, cont'd) — CERT LIST parser fixed + Add Certificate UI was fundamentally wrong

The one parser flagged as "not independently verified" in the previous
entry — `parse_cert_list` — got resolved once the user connected to IRC
over TLS with a real client certificate and ran `/msg NickServ CERT ADD`
directly, producing real data to test against.

**`parse_cert_list` was broken**, same shape of bug as everything else
this session: the regex required the *entire* line to be pure hex, but
real `CERT LIST`/`CERT VIEW` output is tabular (`Fingerprint [Creator
Created] Description` columns trail the fingerprint), so it always
returned zero entries. Fixed to extract just the leading hex run.

**Bigger find: the "Add certificate" feature's whole UI shape was wrong**,
not just the parser. Per `HELP CERT` and confirmed by reading
`modules/nickserv/ns_cert.cpp` directly: self-service `CERT ADD` takes
**zero arguments** and adds whatever fingerprint the *current live
connection* is presenting — there is no way to register an arbitrary
typed-in fingerprint for yourself (the two-arg form is oper-only, for
modifying *someone else's* list). The panel's form let a user type a
fingerprint into a text box and always called `CERT ADD <typed-value>`,
which — confirmed live — fails every time with `"You are not using a
client certificate."` regardless of what's typed, because Anope isn't
reading the input at all in that failure path; it's checking the live
connection, which the web request (correctly) doesn't have one of. This
is a known, deliberate Anope behavior, not a bug in Anope —
see [anope/anope#326](https://github.com/anope/anope/issues/326).

Fixed by replacing the text field with a plain "Add my current
certificate" button that calls bare `CERT ADD`, with a note that this only
works if the account is *simultaneously* connected to IRC over TLS with
that certificate at the moment the button is clicked (e.g. an IRC client
with SASL EXTERNAL / certfp already connected, using the panel in a
browser at the same time). Confirmed live this actually works end-to-end:
`rpc_user`'s `pretenduser` correctly resolves the RPC call's `source` to
that real live connection (not a synthetic pretend-user) when one exists,
so `CERT ADD` picks up its genuine fingerprint — verified by calling it via
RPC while the test connection was live and getting back "Fingerprint ...
already present" with the *correct* real fingerprint, not a generic error.

---

## Session Updates (2026-07-27, cont'd) — Full parser audit: 9 more broken list parsers found and fixed

Prompted by a "did you check the other layouts too?" — the FLAGS/AKICK fix
earlier only got tested because a user complaint pointed at them directly.
A systematic sweep of every other list-style parser against real live
output (same Fixed-layout test account) turned up **nine more parsers that
were silently broken**, several of them previously marked "✅ done" or
"confirmed against real output" in this very document from an earlier
session — that documentation was wrong, and nothing caught it until this
sweep actually re-ran them against fresh live data instead of trusting the
prior claim. Lesson: "confirmed against live output" is a claim about one
past moment, not a standing guarantee — Anope version differences alone are
enough to silently invalidate it, and there's no test suite to catch a
regression. If you touch any of these parsers again, re-verify against
real captured output, don't just read this file and assume it's still true.

Found and fixed (all in `utils.py`, all verified against real live output
before/after):

- **`parse_access_list`** (ChanServ numeric ACCESS LIST) — only handled
  `N: mask = LEVEL`; real output is tabular `Number Level Mask
  Description` with **Level and Mask in reversed column order** vs the
  flexible form. Returned zero entries.
- **`parse_xop_list`** (ChanServ VOP/HOP/AOP/SOP/QOP LIST) — same story,
  only handled `N: mask`; real output is tabular `Number Mask
  Description`. Returned zero entries.
- **`parse_levels_list`** (ChanServ LEVELS LIST) — assumed `PRIVILEGE =
  level`; real output has **no `=` sign at all** (`ACCESS_CHANGE  10`,
  `TOPIC  (disabled)`, `ASSIGN  (founder only)`). Returned zero entries —
  the Levels page has never shown anything on this Anope version.
- **`parse_entrymsg_list`** (ChanServ ENTRYMSG LIST) — assumed `N:
  message`; real output is tabular `Number Creator Created Message`.
  Returned zero entries.
- **`parse_log_list`** (ChanServ LOG) — assumed `N: command on service:
  method`; real output is tabular `Number Service Command Method[
  status]`. Returned zero entries. Also: the displayed `Command` column is
  a short uppercase name (`FLAGS`) but re-submitting to add/remove a log
  entry requires the full lowercase `service/command` form
  (`chanserv/flags`) — confirmed live, `LOG #chan FLAGS MESSAGE` fails
  ("FLAGS is not a valid command"). The parser now reconstructs the
  working form so a delete button fed from parsed data actually functions
  — this would otherwise have been a second, harder-to-notice bug
  layered on top of the first (page looks fine, delete silently fails).
- **`parse_cs_list`** (ChanServ channel search) — matched `#channel
  (Description)` OR bare `#channel`, but real output has **no parens** —
  it's tabular free text. Any channel with an actual description set was
  **silently dropped from the results entirely** (the line matched
  neither alternative), while undescribed channels happened to still work
  — the kind of bug that looks fine in casual testing because the common
  case (no description) passes.
- **`parse_ns_list`** (NickServ LIST, oper) — assumed `nick (email)`; real
  output never shows email at all (privacy) — it's tabular `Nick Account
  Status`. Returned zero entries. Template updated to show Account/Status
  instead of the never-actually-available Email column.
- **`parse_ajoin_list`** (NickServ AJOIN LIST) — assumed `N: #channel
  [key]`; real output is tabular `Number Channel Key`. Returned zero
  entries.
- **`parse_hs_list`** (HostServ LIST / WAITING) — despite being marked
  "verified against real RPC output (2026-06-30)" in this doc, the
  assumed `N: nick = vhost -- created by X at Y` format does not match
  this Anope build's actual output at all: real output is tabular, and
  **WAITING lacks the Creator column that LIST has** (pending requests
  don't have an approver yet) — the two commands needed different
  patterns. Returned zero entries for both.
- **`parse_hs_offerlist`** (HostServ OFFERLIST) — same story, also marked
  "confirmed against live output" previously. Real format is tabular
  `Number Offered-vhost Your-vhost Expires Reason`, and — contradicting
  the old note that claimed reason is never echoed back — **Reason is
  populated** when set. Anchored on Expires' known phrases (`does not
  expire` / `expires in ...` / `expires on ...`) to split it from the
  unlabeled free-text Reason column that follows, same technique used
  for OperServ's ignore list.

Also cleaned up incidental cruft found while in there: `parse_ns_info`,
`parse_ajoin_list`, and `parse_ns_list` were each **defined twice** in
`utils.py` (the second definition silently shadowing the first, which was
dead code) — removed the dead copies.

**Update**: `parse_cert_list` (NickServ CERT LIST) — flagged above as
unverified since it needs a real TLS client-certificate connection to
produce live data. Resolved in the next entry below once the user
connected one — also broken, and it surfaced a bigger UI-shape bug in the
Add Certificate flow. See "CERT LIST parser fixed + Add Certificate UI was
fundamentally wrong" above.

---

## Session Updates (2026-07-27, cont'd) — Confirm/reset flows fixed, critical vuln closed, base.html bug fixed

While wiring up clickable email-confirmation links (register/email/resetpass),
found the existing NickServ confirm/reset routes were fundamentally broken,
not just missing a keyword — and introduced (then fixed, before it ever
shipped) a real vulnerability while rebuilding them. Detail matters here,
future sessions should read this in full before touching these routes.

**Anope source (`modules/nickserv/ns_register.cpp`, `ns_email.cpp`,
`ns_resetpass.cpp`) reveals the actual mechanics**:
- `CONFIRM REGISTER <code>` and `CONFIRM EMAIL <code>` resolve the target
  account from `source.GetAccount()->na` — i.e. from the RPC **source**
  parameter, not from any nick argument in the command string. The old routes
  called `CONFIRM {code}` with `source=None`, which can't identify an account
  at all (confirmed live: fails outright). Fix: routes now take
  `/nickserv/confirm/register/<nick>/<code>` and
  `/nickserv/confirm/email/<nick>/<code>`, calling
  `rpc("anope.command", nick, "NickServ", "CONFIRM REGISTER/EMAIL <code>")` —
  `source=nick` is what lets Anope resolve `source.nc` correctly. This works
  via RPC even with no live IRC connection, since `rpc_user.cpp`'s
  `AnopeCommandRPCEvent::Run` always sets `source.nc` from the resolved
  `NickAlias`, independent of whether a live `User` was found.
- `RESETPASS` requires **two** arguments, `nickname email` (both must match)
  — it's unauthenticated by design, so identity comes from proving you know
  the registered email, not from a logged-in source. The old route sent zero
  arguments. Fixed: `/nickserv/reset` now collects both fields.
- `CONFIRM RESETPASS [nickname] code` only **validates the code** and (only
  if a *live* IRC user session exists, which RPC never has one for this flow)
  identifies them — it does **not** accept or set a new password. The actual
  password change requires a separate `SET PASSWORD <new>` call afterward.
  `CommandNSSetPassword` uses `source.nc` directly (no live-user requirement,
  no extra permission), so `SET PASSWORD` with `source=nick` alone works —
  confirmed live end-to-end via `checkCredentials` before/after.

**Critical vulnerability found and fixed before ever shipping**: Anope
reports command-level failures (wrong code, expired request, etc.) as a
normal successful JSON-RPC `result` — **not** an `error` — so `rpc.py`'s
`AnopeError` never fires on them (confirmed live: a wrong reset code comes
back as `{"result": ["...is incorrect."]}`, HTTP 200, no `error` field). The
first draft of `reset_confirm()` chained `CONFIRM RESETPASS` →
`SET PASSWORD` unconditionally, trusting "no exception raised" as "the code
was valid." It wasn't: `SET PASSWORD` doesn't care whether a prior confirm
succeeded, so **anyone could have hit `/nickserv/reset/<any-nick>/<garbage>`
and overwritten that account's password with no valid code at all.** Caught
by testing the failure path, not just the success path — proved with a live
checkCredentials check that a wrong-code attempt left the real password
untouched. Fixed with `_anope_confirmed(result, marker)`, which fails closed:
only proceeds if the expected success phrase is actually present in the
reply text. **This is a real architectural trap in this codebase**: any RPC
call whose result feeds a decision (not just a display) must check the reply
text, not just catch `AnopeError` — a business-logic failure looks identical
to success at the exception level. Worth a broader audit if time allows;
scoped fix here covers only the confirm/reset chain since that's the one
with a destructive consequence.

**Separate, older bug found and fixed**: `base.html` only rendered
`{% block content %}` inside `{% if session.get("account") %}` — an
`{% else %}` branch existed but referenced a `content_unauthed` block that
*zero* templates ever defined. Result: every unauthenticated page built on
`base.html` (`reset.html`, `reset_confirm.html`) rendered as a nearly blank
page — title bar and scripts only, no form, no content, nothing — for the
exact audience that needs them (logged-out users who forgot their password).
`login.html` was unaffected only because it's a fully standalone page that
doesn't extend `base.html` at all. Fixed by restructuring so `{% block
content %}` is defined exactly once (Jinja rejects the same block name
defined twice in one file, even across dead if/else branches) with the
sidebar-flex wrapper split into a flanking opening/closing `{% if
session.get("account") %}` pair around a single shared `<main>`. Flash-message
rendering was extracted to `templates/_flashes.html` and included in both
paths (it was previously *also* only inside the logged-in branch, so reset
pages couldn't even show error flashes before this fix).

All of the above verified against the live Anope instance with real
disposable test accounts (`claudetest5`/`6`/`7`, real registration codes
captured from IRC notices — Anope echoes the REGISTER code in-band but not
the RESETPASS/email-change codes, which are email-only and this sandbox has
no working MTA, so those two specifically were verified via wrong-code
rejection + the isolated `SET PASSWORD`-via-`source=nick` mechanism rather
than a full real-code round trip).

**Clickable email links wired up**, using Anope's `define` block
(`src/config.cpp:975` `ReplaceVars` — documented right at the top of
`anope.conf` too, easy to miss) rather than a hardcoded literal:

```
define
{
	name = "panel.host"
	value = "http://127.0.0.1:12347"
}
```

...referenced in the `mail` block's `registration_message`, `reset_message`,
and `emailchange_message` as `${panel.host}/nickserv/confirm/register/{nick}/{code}`
(etc). **The `$` is not optional** — `define` substitution only fires on
`${name}` (config-parse time, in `ReplaceVars`); bare `{name}` is reserved
for Anope's *separate*, later, runtime message-token substitution
(`{nick}`/`{code}`/`{account}`/`{network}`, done by `Anope::Template()` when
the email is actually composed). Get this wrong — as the first draft of this
change did, using bare `{panel.host}` — and the config loads with **no
error at all** (`OperServ RELOAD` reports success either way), but the value
silently never gets substituted: Anope::Template() doesn't recognize
"panel.host" as one of its tokens for these messages, so `{panel.host}`
would go out as dead, literal text in every real confirmation email. Only
caught by re-reading `ReplaceVars`'s trigger condition (`*it != '$'`) and
checking the delimiter Anope's own docs actually specify — a live reload
alone can't catch this class of mistake, since a silently-ignored token
looks identical to a successful reload from the RPC response text.

Since this project is headed to GitHub and isn't publicly deployed yet, the
`panel.host` define's value is the local dev address (`http://127.0.0.1:12347`)
— **update it and `PANEL_URL` in `.env` together** the moment a real domain
exists, then `OperServ RELOAD` (verified live, non-disruptive, does not drop
connections) to pick up the change. Each email keeps the original `/msg
NickServ CONFIRM ...` IRC instructions alongside the new link as a fallback.

---

## Session Updates (2026-07-27) — Live verification, OperServ expansion

Audited and expanded the panel against a real running Anope 2.1 + UnrealIRCd
6.2.7 instance (not just code review) — registered a disposable IRC
account/channel over raw sockets to exercise the real login flow and every
route end-to-end.

**Critical config bug fixed**: `.env` pointed at a stale RPC endpoint
(`127.0.0.1:12345` with a token that matched nothing) while Anope's httpd was
actually on `127.0.0.1:8080`. The panel could not have worked at all before
this — worth double-checking on every fresh deploy, since a wrong
`ANOPE_RPC_URL`/`ANOPE_RPC_TOKEN` fails silently as "Could not connect to
Anope services" rather than an obvious startup error.

**Two more FIXED-layout parsing bugs found and fixed (`utils.py`)**, this
time by running the parsers against real captured output instead of
hand-written fixtures:
- `parse_flags_list`: the FIXED-format regex used a generic `.+?` to consume
  the date column. When a description was present, part of it bled into the
  `addedat` field (real bug, e.g. `addedat` became `"Mon Jul 27 11:29:57
  2026  this"` instead of just the date).
- `parse_akick_view`: same root cause but worse — two adjacent free-text
  `.+?` groups (added-date, last-used) are fundamentally ambiguous without an
  anchor. Confirmed live: `addedat` was truncated to just `"Mon"` and
  `lastused` absorbed the rest of the date plus the reason.
- Fix: added `DATE_RE`, an explicit regex for Anope's ctime-style date format
  (`"Mon Jul 27 11:28:43 2026"`), and anchor on it instead of greedy/non-greedy
  guessing. Both re-verified against live RPC output for the empty- and
  populated-description/reason cases.

**OperServ expanded from AKILL/Sessions/News to full coverage**:
- Fixed News page: it called `OperServ NEWS LIST`, which **does not exist**
  as a command (confirmed live: `{"error":{"message":"No such command"}}`) —
  the page was always broken. Real commands are three separate ones
  (`LOGONNEWS`/`OPERNEWS`/`RANDOMNEWS`, each with its own `LIST`/`ADD`/`DEL`).
  Added a `parse_os_news_list` parser and rebuilt the page with add/delete
  forms for all three.
- New: Stats, User List, Channel List, Services Operators (list/add/del),
  Services Ignore List (list/add/del), Chankill, Jupe, Force Mode
  (channel MODE + user UMODE), Noop, and a Danger Zone (Reload, Update,
  Restart, Shutdown, Quit).
- Every new command's exact syntax was pulled from live `OperServ HELP
  <cmd>` output before writing the route, and every list-style command
  (`USERLIST`, `CHANLIST`, `OPER LIST`, `IGNORE LIST`) was parsed against
  real captured output, not assumed from docs.
- **Live-tested caveat**: Chankill, Jupe, Noop SET, and the Danger Zone
  actions were *not* executed live (they AKILL real users, jupiter a real
  server, kill real opers, or stop/restart the actual running services process
  respectively) — only their syntax (verified against `HELP`) and page
  rendering were confirmed. Test carefully before relying on them.
- **Anope behavior worth knowing**: an account granted an opertype purely
  via `OperServ OPER ADD` (as opposed to one configured in `operserv.conf`)
  defaults to `require_oper = true` (`include/opertype.h`), meaning the
  *connected client* also needs real IRCd oper mode (`+o`) — not just the
  services opertype — before Anope will honor OperServ command permissions.
  Confirmed live: a fresh `OPER ADD`'d account got `"No such command"`
  (Anope's generic RPC error for any `Command::Run` failure, including
  permission failures — it does not distinguish "doesn't exist" from
  "access denied" at the RPC layer) until `OperServ UMODE <nick> +o` was
  applied. If opers report OperServ pages failing through the panel, check
  this before assuming a panel bug.
- Also confirmed live: Anope's built-in **Services Administrator** opertype
  does not include `operserv/userlist` or `operserv/chanlist` by default —
  only `Services Root` (`*`) does. Something to flag for admins configuring
  opertypes if they want non-Root opers to use those two pages.

---

## Session Updates (2026-06-30) — Bug Fixes & Layout Support

**Fixed 10 critical dark mode styling bugs** (reported by TECO):
- Replaced hardcoded Tailwind dark-mode classes with CSS variables in 10 templates
- Forms were rendering dark even when light mode was selected

**Fixed critical LAYOUT format issue** — THE ROOT CAUSE of "No access entries":
- NickServ `SET LAYOUT` setting affects ChanServ FLAGS/AKICK output format
- Previously only supported FLEXIBLE format: `"1: mask = flags -- added by X at DATE"`
- Now supports all three LAYOUT modes: FLEXIBLE, FIXED, and MONOSPACE
- FIXED/MONOSPACE output is tabular: `"1  mask  flags  creator  date"`
- MONOSPACE adds \x11 prefix which is now properly stripped
- Parsers updated: `parse_flags_list()` and `parse_akick_view()` now handle all three formats like `parse_alist()` does

**Fixed 1 parsing bug in `utils.py`**:
- `parse_akick_view()` now properly strips IRC formatting codes before matching

**Files modified**: 12 total
- 10 templates: styling fixes
- 2 utilities: `utils.py` (parse_flags_list + parse_akick_view for LAYOUT support)
- 2 routes: `routes/chanserv.py` (debug logging)

See `BUG_FIXES_REPORT.md` for detailed technical analysis.

---

## Project overview

A modern web control panel for Anope IRC Services 2.1, built as a replacement
for the bundled `webcpanel` module. Designed to be whitelabel-ready and easy
to extend by non-developers (plain HTML templates, no build tooling).

**Stack:** Flask + Jinja2 + HTMX + TailwindCSS (CDN) + vanilla CSS variables

**Key design decisions:**
- Stateless auth: `anope.checkCredentials` called on every login, result cached in Flask session
- Bearer token must be **base64-encoded** before sending (undocumented Anope quirk, found in `jsonrpc.cpp`)
- Channel names are stored **without `#`** in URLs (e.g. `/chanserv/PTirc/access`) — `chan()` helper in `routes/chanserv.py` adds `#` back before RPC calls, `chanurl()` strips it for `url_for()`
- All Anope output is parsed via functions in `utils.py` — never trust raw IRC strings in templates
- `strip_irc()` in `utils.py` strips all IRC formatting chars before parsing
- Anope's `NS SET LAYOUT` affects output format — `parse_alist()` handles all three: FLEXIBLE (`N: #channel = Level`), FIXED (tabular), MONOSPACE (tabular + `\x11` prefix)
- CS SET syntax is `SET OPTION #channel value` (not `SET #channel OPTION value`)
- `is_oper` and `chanserv_channels` are cached in Flask session at login

---

## File structure

```
anope-panel/
  app.py                   # Flask factory, blueprints, context_processor for network branding
  auth.py                  # login_required decorator, login/logout routes, session caching
  rpc.py                   # RPC client wrapper (base64 token, error handling)
  utils.py                 # All IRC output parsers + strip_irc() + DATE_RE
  routes/
    nickserv.py            # NickServ routes
    chanserv.py            # ChanServ routes (also has chan() / chanurl() helpers)
    botserv.py             # BotServ routes (own chan() / chanurl() copies)
    services.py            # MemoServ + HostServ routes
    operserv.py            # OperServ routes
  templates/
    base.html              # Layout: top nav tabs, channel pill bar (ChanServ+BotServ), sidebar, content
    _flashes.html           # Shared flash-message partial (included from both the logged-in and logged-out layout branches)
    login.html             # Standalone login page (does not extend base.html)
    dashboard.html
    nickserv/              # info, set, cert, alist, ajoin, drop, list, oper/<nick>,
                           # email, password, confirm, confirm_register (link), confirm_email_link,
                           # reset, reset_confirm, recover, resend, getemail (oper)
    chanserv/              # index, set, access, access_num, xop, levels, akick,
                           # entrymsg, log, modes, stats, top, gstats, clone, list, drop
    botserv/               # index (kickers+settings+say/act), badwords, bots (oper)
    memoserv/              # index, read, send, settings, ignore, sendall (oper), staff (oper)
    hostserv/              # index, offerlist, admin, waiting, offer (oper)
    operserv/              # akill, chankill, ignore, sessions, userlist, chanlist, oper,
                           # stats, seen, news, mode, jupe, noop, danger
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
```

---

## Completed features

**NickServ gap-filling (2026-07-27)**: added SET AUTOLOGIN (extension-based
toggle, like HIDE_*, not in the Options: line — verified live), SET NEVEROP
(Options: line toggle, slug `never_op`), SET LANGUAGE/GREET/MASTODON/
LOCATION/URL (generic free-text `ns_set_text` route, one handler for all
five since they share `SET OPTION value` syntax), UPDATE (refresh memos/
modes/vhost), RECOVER (aliases GHOST/RELEASE — same underlying command,
one form covers all three), RESEND (unauthenticated, for a lost/expired
registration email — linked from the login page), GETEMAIL (oper, parsed
against real `"Email matched: nick (email) to email."` output). GLIST
intentionally not built — fully redundant with the existing structured
grouped-nicks display (`anope.account`'s `nicks` field) and the oper nick
view, same reasoning as the earlier GROUP removal.

### NickServ ✅
- Info (account details, grouped nicks table — see Ungroup note below, timestamps)
- Settings (AUTOOP/KEEPMODES/PRIVATE/MSG toggles, HIDE options, layout, timezone, display nick, protect, danger zone)
- Certificates (CERT LIST/ADD/DEL via `anope.command`)
- Access List (ALIST add/del)
- Auto Join (AJOIN LIST/ADD/DEL)
- ~~Group~~ removed (2026-06-30): `GROUP nick password` only makes sense run from IRC under the unregistered nick being grouped — can't meaningfully be done from a web session. Route, sidebar link, and template deleted.
- Ungroup button (fixed 2026-06-30): route existed but was never linked anywhere. Added a per-nick Ungroup button to the Grouped Nicks table on NS Info — shown for every grouped nick except the display nick (can't ungroup your own display nick; that's effectively a drop/rename situation Anope handles separately).
- Email change
- Password change
- Confirm email (authenticated + unauthenticated link)
- Password reset (request + confirm link)
- Nick Drop (two-step, requires password)
- Nick List (oper-only, sidebar hidden for non-opers)
- Oper Nick view (oper-only, `/nickserv/oper/<nick>`): account info, grouped nicks, SASET PASSWORD, SASET NOEXPIRE, SUSPEND/UNSUSPEND (with optional expiry+reason), DROP with OVERRIDE; accessible from Nick List "Manage" buttons and sidebar prompt

**ChanServ gap-filling (2026-07-27)**: added DOWN/UP (status refresh/removal,
self or a target nick) to the Modes page's User actions card. BAN turned out
to already exist (`routes/chanserv.py`, not previously listed in this doc) —
enhanced it with the `+expiry` param it was missing (real syntax: `BAN
channel [+expiry] {nick|mask} [reason]`).
**Quirk worth knowing**: `UNBAN channel [nick]` removes bans preventing a
*specific nick* from joining (resolved by their current host) — it is not a
generic "remove this arbitrary ban mask" command, and there's no such
command at the founder level. Confirmed live: a plain founder-level `CS
MODE #chan -b mask` on a ChanServ-added ban appears to succeed (reply says
"Mode -b ... set") but is silently reverted — ChanServ actively re-syncs/
protects bans it manages. Only `UNBAN <nick-that-matches>`, letting the ban
expire, or an oper's `OperServ MODE` (not sync-protected) actually removes
one. Not a panel bug, just how Anope's ban tracking works — if you need a
"remove arbitrary ban mask" founder-facing feature, there isn't a direct
Anope command for it; don't build one assuming `CS MODE -b` works, it won't
stick.

**Chanstats support added (2026-07-27)**, once MySQL was wired up live:
`SET CHANSTATS` toggle (channel-level, on the Stats page; nick-level, on
Nick Settings — both read back correctly via `option_set`, confirmed the
extension is only visible in `NS INFO`/`CS INFO` for self/oper views per
`chanstats.cpp`'s `OnChanInfo`/`OnNickInfo` `show_all`/`show_hidden` gates),
Global Stats (`GSTATS`, network-wide personal stats), and Top 10
(`TOP10`/`GTOP10` — chose to always show 10 rather than separately expose
`TOP`/`GTOP`'s top-3 variant, since 10 is a superset view). `parse_stats`
extended for GSTATS's "Network stats for NICK:" header variant (no
channel); new `parse_cs_top` parser for the ranked list format.
**Caveat**: reply formats for `TOP`/`GSTATS`/etc. were taken directly from
`modules/chanserv/cs_fantasy_top.cpp` / `cs_fantasy_stats.cpp` source, NOT
verified against live populated data — the MySQL backend was connected
during this session but `STATS`/`TOP10` kept returning empty even after
generating real chat activity from an identified, chanstats-enabled account
on a chanstats-enabled channel, with no SQL errors in Anope's log. Likely
the chanstats schema (tables/stored procedures, e.g.
`chanstats21_chanstats_proc_update`) hasn't been imported yet — that's
usually a separate one-time SQL script from the connection grants. Re-verify
parsers against real output once that's sorted.

### ChanServ ✅ (complete)
- My Channels (ALIST-driven, pill bar in header for quick switching)
- Settings (CS SET toggles: AUTOOP/KEEPTOPIC/PEACE/PERSIST/PRIVATE/RESTRICTED/SECUREFOUNDER/SECUREOPS/SIGNKICK/TOPICLOCK/NOEXPIRE; text fields: desc/url/email; dropdowns: founder/successor/bantype; oper: suspend/unsuspend)
- Flags (FLAGS LIST * ALL — add/del with self-remove bug fixed vs webcpanel)
- Access (numeric ACCESS LIST * ALL — add/del)
- xOP (VOP/HOP/AOP/SOP/QOP — all five in one page, add/del)
- Levels (LEVELS LIST/SET/RESET/RESET ALL — inline edit per privilege)
- Akick (AKICK VIEW — add/del, shows creator + last used)
- Entry Messages (ENTRYMSG LIST/ADD/DEL/CLEAR)
- Log settings (LOG LIST/ADD/DEL)
- Modes (live channel state, topic set/clear, mode set, kick/ban/invite/unban, sync, enforce, getkey, status lookup, per-user OP/DEOP/HALFOP/DEHALFOP/VOICE/DEVOICE/PROTECT/DEPROTECT/OWNER/DEOWNER — paginated at 100 users/page)
- Stats (STATS — lines/words/letters/smileys/actions)
- Clone (CLONE with scope selector)
- Channel List (CS LIST with pattern search, SUSPENDED/NOEXPIRE filters for opers)
- Drop (two-step auto-code extraction)

**MemoServ gap-filling (2026-07-27)**: added CANCEL (cancel last unread memo
to a nick/channel), CHECK (whether your last memo to a nick was read),
Ignore List (list/add/del — simple format, unlike most Anope lists there's
no entry numbering, `IGNORE DEL` takes the raw nick/host text back), an INFO
summary on the memo list page, Settings (SET NOTIFY with all six modes, SET
LIMIT), and oper SENDALL/STAFF (broadcast memos).

### MemoServ ✅
- Memo list (parsed, unread highlighted, sender + date columns)
- Read memo
- Send memo (nick or channel)
- Delete memo / Delete all

### HostServ ✅
- VHost request form (REQUEST), current vhost display, read from `anope.account` nick vhost data
- ON / OFF — activate/deactivate assigned vhost
- GROUP — sync vhost to all grouped nicks
- Offer List (user-facing): browse OFFERLIST table, TAKE an offer by entry number (no ident param — confirmed `OFFERLIST TAKE {vhost|entry-num}` is single-arg)
- Oper — All VHosts (LIST with pattern filter, manual SET/SETALL forms, per-row DEL/DELALL). Requires `hostserv/set` (SET/ACTIVATE/REJECT) and `hostserv/del` (DEL/DELALL) in opertype.
- Oper — Waiting Requests (WAITING table, per-row Activate/Reject with optional reason)
- Oper — Offer List management (OFFER ADD with expiry+reason, OFFER DEL per entry, OFFER CLEAR with confirm). Requires `hostserv/offer` in opertype.
- `parse_hs_list` / `parse_hs_offerlist` — the 2026-06-30 "verified against real RPC output" note below turned out to no longer hold; both were found broken again and re-fixed on 2026-07-27 against this Anope build's actual output — see the top of this document for the current fix.

### BotServ ✅ (new, full — was 0% coverage before 2026-07-27)
- Per-channel: assign/unassign, all 10 kickers (BADWORDS/BOLDS/CAPS/COLORS/
  FLOOD/ITALICS/REPEAT/REVERSES/UNDERLINES/AMSG) with ttb + kicker-specific
  extra params (caps min/percent, flood lines/secs, repeat num), channel
  options (DONTKICKOPS/DONTKICKVOICES/FANTASY/GREET/BANEXPIRE), bad words
  list (add/del/clear, with SINGLE/START/END word-matching type), SAY/ACT
  quick actions. All parsed against real live `INFO`/`BADWORDS LIST` output
  (`parse_bs_info`, `parse_bs_badwords` in `utils.py`).
- Oper: network bot list (`BOTLIST`, parsed via `parse_bs_botlist`), add/
  change/delete bots, mark a bot private (`SET PRIVATE`).
- Wired into the ChanServ per-channel sidebar ("Bot" link) and the channel
  pill bar (extended from `chanserv`-only to `chanserv`/`botserv`).
- `SETNOBOT` (make a channel unassignable, oper-only) intentionally not
  exposed as its own page — it's a rare, config-adjacent toggle; Anope's own
  permission check still protects the underlying command either way.

### OperServ ✅ (full)
- AKILL list (AKILL VIEW — add/del, shows creator/date/expiry)
- Chankill (AKILL + enforce every user on a channel)
- Services Ignore List (IGNORE LIST/ADD/DEL, parsed)
- Sessions (raw output)
- User List / Channel List (USERLIST/CHANLIST, parsed, pattern search)
- Services Operators (OPER LIST/ADD/DEL, parsed; opertype dropdown from OPER INFO)
- Stats (STATS with AKILL/HASH/PASSWORD/UPLINK/UPTIME/ALL sub-views)
- News (LOGONNEWS/OPERNEWS/RANDOMNEWS — list/add/del, parsed; previously broken, see Session Updates above)
- Seen (SEEN STATS/CLEAR — database maintenance for the `seen` fantasy command; registers on OperServ despite living in `chanserv.conf`, easy to miss)
- Force Mode (channel MODE and user UMODE)
- Noop (SET/REVOKE)
- Jupe
- Danger Zone: Reload, Update, Restart, Shutdown, Quit — the latter three require typing the network name to confirm, same as Anope's own `QUIT`/`SHUTDOWN`/`RESTART` syntax (`os_shutdown.cpp` checks it server-side too)

### Dashboard ✅
- Online users, channel count, registered accounts (from rpc_data)
- Quick links, oper shortcut

### UI / UX ✅
- Light/dark theme toggle (CSS variables, `data-theme` on `<html>`, FOUC-free)
- Theme persisted in `localStorage`, works on login page too
- Network branding via `.env` (NETWORK_NAME, NETWORK_URL, NETWORK_LOGO, NETWORK_COLOR)
- NETWORK_COLOR drives `--accent` CSS variable throughout
- Sidebar shows channel context (channel name + per-channel sub-pages)
- Channel pill bar (sticky, above sidebar+content, active pill highlighted)
- Pagination on modes user list (50/page)
- IRC escape stripping on all parsed output

---

## Known quirks / gotchas

- **Duplicate routes**: When appending routes across sessions, always check for duplicates with `grep -n "def route_name" routes/file.py` before running. The app will crash with `AssertionError: View function mapping is overwriting` if duplicates exist.
- **Truncated stub bug (fixed 2026-06-29)**: `routes/nickserv.py` had a dead duplicate `# ── SET options` stub at EOF (lines 382–386) — bare decorators `@bp.route("/set")` + `@login_required` with no function body, causing `SyntaxError: invalid syntax`. Removed. The real `/set` routes were already present at lines 185–271.
- **CS SET option_set keys**: Come from Anope's `AddOption()` calls in each cs_set module. Slugs = string lowercased, spaces→underscores. Full verified mapping:
  - `AUTOOP` → `"No auto-op"` slug `no_auto-op` — **inverted**: slug present means AUTOOP is OFF
  - `KEEPMODES` → `"Keep modes"` slug `keep_modes`
  - `KEEPTOPIC` → `"Topic retention"` slug `topic_retention`
  - `CHANSTATS` → `"Chanstats"` slug `chanstats` (third-party module, optional)
  - `PEACE` → `"Peace"` slug `peace`
  - `PERSIST` → `"Persistent"` slug `persistent`
  - `PRIVATE` → `"Private"` slug `private`
  - `RESTRICTED` → `"Restricted access"` slug `restricted_access` (not `restricted`)
  - `SECURE` → **removed from UI (2026-06-30)**: not a real cs_set command in Anope 2.1 — only `SECUREFOUNDER`/`SECUREOPS` exist (`grep AddOption` in cs_set.cpp confirms no bare `secure` toggle). Was previously shown as `?` placeholder; now removed entirely.
  - `SECUREFOUNDER` → `"Secure founder"` slug `secure_founder`
  - `SECUREOPS` → `"Secure ops"` slug `secure_ops`
  - `SIGNKICK` → `"Signed kicks"` slug `signed_kicks`
  - `TOPICLOCK` → `"Topic lock"` slug `topic_lock`
  - `NOEXPIRE` → `"No expiry"` slug `no_expiry`
- **NS SET option_set keys**: Same pattern from NS INFO "Options:" line, lowercased, spaces→underscores. Verified mapping:
  - `AUTOOP` → `"Auto op"` slug `auto_op`
  - `KEEPMODES` → `"Keep modes"` slug `keep_modes`
  - `PRIVATE` → `"Private"` slug `private`
  - `SECURE` → **removed from UI (2026-06-30)**: no `nickserv/set/secure` module exists in Anope 2.1. Was previously shown as `?` placeholder; now removed entirely.
  - `MSG` → `"Message mode"` slug `message_mode` (not `message` — this was a bug, now fixed)
- **HIDE option detection (fixed)**: HIDE flags (`HIDE_EMAIL`/`HIDE_MASK`/`HIDE_STATUS`/`HIDE_QUIT`) are `SerializableExtensibleItem<bool>` extensions on the NickCore, NOT part of the NS INFO "Options:" line — they never appear in `option_set` no matter what. Fixed by having `ns_set()` also call `anope.account` and passing `account` to the template; the Hide settings section now reads `account.extensions.get('HIDE_EMAIL')` etc.
- **HIDE USERMASK toggle bug (fixed)**: `SET HIDE` syntax is `SET HIDE {EMAIL|STATUS|MASK|QUIT} {ON|OFF}` — the command keyword is `MASK`, not `USERMASK`. The template was using "USERMASK" as both the display label AND the value posted to `ns_set_hide`, so the button sent `SET HIDE USERMASK ON` which Anope silently rejects (invalid argument), leaving the toggle stuck OFF forever. Fixed by splitting the tuple into `(display_label, command_keyword, extension_key, description)` — UI still shows "HIDE USERMASK" but the form posts `MASK` as the command argument.
- **channel URL encoding**: `#` in URLs → `%23`. Fixed by storing channel without `#` in URL segment. `chan(channel)` adds `#` back, `chanurl(channel)` strips it. All `rpc("anope.channel", ...)` calls must use `chan(channel)`.
- **Anope layout formats**: FLEXIBLE/FIXED/MONOSPACE affect output. `parse_alist()` handles all three. Other parsers use `strip_irc()` but may need layout-awareness if users report parsing failures.
- **`anope.channel` requires live channel**: Returns error if channel is empty (no users). Modes page handles this gracefully.
- **MemoServ**: `anope.command` with `MS LIST` returns raw IRC lines — always parse with `parse_memo_list()`.

---

## What's left to build

As of 2026-07-27 the panel covers every real Anope command across NickServ,
ChanServ, BotServ, MemoServ, HostServ, and OperServ that's enabled in this
network's config (`SAREGISTER` doesn't exist — confirmed absent from the
actual Anope source tree, it was a stale assumption from an earlier
session's notes). What's left is genuinely the long tail:

### NickServ
- ~~SUSPEND / UNSUSPEND~~ ✅ ~~GETEMAIL~~ ✅ done — see Session Updates

### MemoServ
- Channel memos (`MS LIST #channel` / `MS READ #channel N`) — same
  underlying commands as personal memos, just channel-scoped and gated by
  channel access; not yet built, would want its own view under the
  channel's ChanServ context rather than bolted onto the personal memo list
- ~~IGNORE list / SET NOTIFY / SET LIMIT~~ ✅ done — see Session Updates

### HostServ
- VALIDATE intentionally **not exposed**: requires the user to publish a DNS TXT record for a domain they claim to own, then Anope verifies it via live DNS lookup. That's an out-of-band step (editing DNS at a registrar) the panel can't do anything to assist with beyond "go run VALIDATE once your TXT record propagates" — not worth a dedicated page; users can request via the panel and validate from IRC.
- `parse_hs_list` (fixed 2026-06-30): the WAITING command can produce an *empty* creator field — confirmed real output `"1: galegovski = galegovki.com -- created by  at Sat Jun 27 18:06:45 2026"` (double space, "by  at"). Original regex required `\S+` for creator and silently failed to match the whole line, so WAITING always showed empty even with real pending requests. Fixed to `\S*` (zero-or-more).
- `parse_hs_offerlist` (rewritten 2026-06-30): real `OFFERLIST`/`OFFER LIST` output is NOT a column table — it's `"N: offered-template / your-preview -- trailer"`, e.g. `"1: users.PTirc.{account} / users.PTirc.James -- does not expire (default)"`. There's no separate reason field echoed back (OFFER ADD's reason arg isn't shown in list output). Parser and both offerlist.html/offer.html templates updated to match: fields are `num`, `offered`, `yours`, `trailer`.
- `OFFERLIST TAKE` (fixed 2026-06-30): syntax is `OFFERLIST TAKE {vhost|entry-num}` — single argument, no separate ident parameter. The earlier panel build had a bogus extra `ident` form field that would have appended garbage to the command and broken every TAKE. Removed.

### ChanServ
- ~~BAN (missing +expiry) / DOWN / UP~~ ✅ done — see Session Updates
- ~~Chanstats: SET CHANSTATS / GSTATS / TOP / TOP10 / GTOP / GTOP10~~ ✅ done, but **not yet verified against live populated data** — see the chanstats caveat above

### BotServ
- ~~entire service~~ ✅ done — see Session Updates (was 0% coverage before 2026-07-27)
- `SETNOBOT` intentionally not exposed as its own page (rare, config-adjacent)

### OperServ
- ~~CHANKILL / IGNORE list / JUPE / MODE / NOOP / OPER list / RELOAD / UPDATE / QUIT / SHUTDOWN / STATS / USERLIST / CHANLIST / SEEN~~ ✅ done — see Session Updates
- ~~FORBID~~ ✅ done — see Session Updates
- SNO (snomask management) — not implemented; this is IRCd-level umode +s <flags>, not an Anope OperServ command, so it doesn't belong on this page. Would need a separate UnrealIRCd-facing feature if wanted.
- Sessions / EXCEPTION list still shows raw output only — not parsed into a table
- CONFIG / MODINFO / MODLIST / MODLOAD / MODRELOAD / MODUNLOAD / LOGSEARCH / DEFCON / SNLINE / SQLINE / SVSNICK / SVSJOIN / SVSPART / KICK / KILL — lower-value or higher-risk admin commands not yet exposed

### General
- README.md for Anope devs pitch (install instructions, modules.conf snippet, screenshots)
- Git repo cleanup (remove debug artifacts, add .gitignore)
- Consider a `GET /api/account` endpoint so JS can poll for unread memo count in nav
- NickServ SUSPEND/UNSUSPEND (oper)
- OperServ: make Sessions and News pages parse structured output instead of raw lines
- Error pages (404/500) with proper styling instead of plain text

---

## Pitching to Anope devs — checklist
- [ ] README.md written
- [ ] Clean git history
- [ ] Screenshot tour
- [ ] Note about `NS SET LAYOUT FLEXIBLE` recommendation
- [ ] Note about required modules.conf config
- [ ] Whitelabel demo (different NETWORK_COLOR/LOGO)
