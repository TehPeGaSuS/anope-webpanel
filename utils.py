import re

# Anope renders dates in (at least) two real formats, and which one shows
# up depends on the ACCOUNT'S LANGUAGE SETTING, not on layout or Anope
# version — confirmed live against real prod-imported accounts:
#   - blank/default language: C-style ctime, "Mon Jul 27 11:28:43 2026"
#   - language en_US.UTF-8:   "Mon 07 Mar 2016 01:20:00 AM CET" (weekday,
#     day, month, year, 12h time, AM/PM, then a variable timezone
#     abbreviation - CET/CEST/UTC/etc. depending on the account's Location)
# Every disposable test account created this session defaulted to blank
# language, so this second format was never exercised until real
# prod-imported accounts (en_US.UTF-8) surfaced it as "access lists don't
# show up" for FIXED-layout accounts. Both forms must be anchored here
# since trailing description/reason text in FIXED layout isn't wrapped in
# parens, so a generic .+? can't tell where the date ends.
DATE_RE = (
    r'(?:[A-Za-z]{3}\s+[A-Za-z]{3}\s+\d{1,2}\s+\d{1,2}:\d{2}:\d{2}\s+\d{4}'
    r'|[A-Za-z]{3}\s+\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{1,2}:\d{2}:\d{2}\s+[AP]M\s+[A-Za-z]{2,5})'
)


def strip_irc(text):
    """Strip all IRC formatting characters from a string."""
    return re.sub(r'[](?:\d{1,2}(?:,\d{1,2})?)?', '', text)


def as_search_mask(term):
    """
    Anope's LIST-family commands (NickServ/ChanServ/HostServ LIST, OperServ
    CHANLIST) require an explicit glob pattern to do a substring match —
    confirmed live: `LIST clitest` against a channel actually named
    "#clitest" returns 0 matches, `LIST *clitest*` finds it. A bare search
    box term is useless without this. Auto-wraps plain terms in `*...*`;
    anything that already looks deliberate (a glob char, a `//regex/`
    pattern, or a `#X-Y` range) is passed through untouched.
    """
    term = term.strip()
    if not term or term.startswith('#') or term.startswith('/'):
        return term
    if '*' in term or '?' in term:
        return term
    return f"*{term}*"


def as_userlist_mask(term):
    """
    OperServ USERLIST's pattern must be the full `nick!user@host[#realname]`
    shape (confirmed live: bare `USERLIST claudetest` returns 0 users,
    `USERLIST *claudetest*!*@*` finds them) — a different shape than the
    other LIST commands, so it gets its own wrapper. A bare term is treated
    as a nick substring search. Channel targets (`#channel`) and anything
    that already contains mask structure are passed through untouched.
    """
    term = term.strip()
    if not term or term.startswith('#') or '!' in term or '@' in term:
        return term
    if '*' in term or '?' in term:
        return term
    return f"*{term}*!*@*"


def parse_alist(lines):
    """
    Handles all three NickServ layout formats (FLEXIBLE, FIXED, MONOSPACE).

    FLEXIBLE:  "N: #channel = Level (Description)"  -- IRC bold around channel
    FIXED:     tabular "N  #channel  Level  Description" with header row
    MONOSPACE: same as FIXED but lines may be prefixed with monospace char (\x11)

    All IRC formatting characters are stripped before matching.
    """
    # Format A: FLEXIBLE — "N: #channel = Level" or "N: #channel = Level (desc)"
    pattern_a = re.compile(r'^(\d+):\s+(!?#\S+)\s+=\s+(\S+)(?:\s+\((.+)\))?$')
    # Format B: FIXED/MONOSPACE — "N  #channel  Level  Description"
    pattern_b = re.compile(r'^(\d+)\s+(!?#\S+)\s+(\S+)(?:\s+(.+))?$')

    # Header words to skip
    skip = {'number', 'channel', 'access', 'description', 'channels', 'end'}

    channels = []
    for line in lines:
        # Strip IRC formatting: bold (\x02), monospace (\x11), color (\x03), reset (\x0f)
        line = re.sub(r'[\x02\x03\x0f\x11\x16\x1d\x1f]', '', line).strip()
        if not line:
            continue
        # Skip header/footer lines
        first_word = line.split()[0].lower().rstrip(':') if line.split() else ''
        if first_word in skip:
            continue

        # Try FLEXIBLE format first
        m = pattern_a.match(line)
        if m:
            raw_channel = m.group(2)
            channels.append({
                "channel":  raw_channel.lstrip("!"),
                "noexpire": raw_channel.startswith("!"),
                "level":    m.group(3),
                "desc":     m.group(4) or "",
            })
            continue

        # Try FIXED/MONOSPACE format
        m = pattern_b.match(line)
        if m:
            raw_channel = m.group(2)
            channels.append({
                "channel":  raw_channel.lstrip("!"),
                "noexpire": raw_channel.startswith("!"),
                "level":    m.group(3),
                "desc":     m.group(4) or "",
            })
    return channels


def parse_flags_list(lines):
    """
    Parse ChanServ FLAGS LIST output. Handles all three layout formats:
    
    FLEXIBLE:  "N: mask = FLAGS -- added by X at DATE (comment)"
    FIXED:     "N  mask  FLAGS  creator  date  [comment]"
    MONOSPACE: Same as FIXED but with \x11 prefix stripped by IRC formatting removal
    
    All IRC formatting characters (\x02, \x11, \x03, etc.) are stripped first.
    """
    # FLEXIBLE: "1: mask = +oOtv -- added by founder at Mon Jun 30 12:00:00 2026 (comment)"
    pattern_flexible = re.compile(
        r'^\d+:\s+(\S+)\s+=\s+(\S+)\s+--\s+added by\s+(\S+)\s+at\s+(.+?)(?:\s+\((.+)\))?$'
    )
    # FIXED/MONOSPACE: "1  user!*@*  +oOtv  founder  Mon Jun 30 12:00:00 2026  optional description"
    # The date is matched explicitly (DATE_RE) since real output has no delimiter
    # between the date and a trailing description column (confirmed live: description
    # is plain trailing text, not wrapped in parens) — a generic .+? would swallow
    # part of the description into the date field.
    pattern_fixed = re.compile(
        rf'^\d+\s+(\S+)\s+(\S+)\s+(\S+)\s+({DATE_RE})(?:\s+(.+))?$'
    )
    
    # Header/footer words to skip
    skip = {'number', 'mask', 'flags', 'access', 'creator', 'date', 'added', 'by', 'at', 'end'}
    
    entries = []
    for line in lines:
        # Strip ALL IRC formatting chars (bold \x02, monospace \x11, color \x03, reset \x0f, etc.)
        line = re.sub(r'[\x02\x03\x0f\x11\x16\x1d\x1f]', '', line).strip()
        
        if not line:
            continue
        
        # Skip header/footer lines
        first_word = line.split()[0].lower().rstrip(':') if line.split() else ''
        if first_word in skip:
            continue
        
        # Try FLEXIBLE format first
        m = pattern_flexible.match(line)
        if m:
            entries.append({
                "mask":    m.group(1),
                "flags":   m.group(2),
                "addedby": m.group(3),
                "addedat": m.group(4).strip(),
                "comment": m.group(5) or "",
            })
            continue
        
        # Try FIXED/MONOSPACE format
        m = pattern_fixed.match(line)
        if m:
            comment = (m.group(5) or "").strip()
            if comment.startswith("(") and comment.endswith(")"):
                comment = comment[1:-1]
            entries.append({
                "mask":    m.group(1),
                "flags":   m.group(2),
                "addedby": m.group(3),
                "addedat": m.group(4).strip(),
                "comment": comment,
            })
            continue

    return entries


def parse_akick_view(lines):
    """
    Parse ChanServ AKICK VIEW output. Handles all three layout formats:
    
    FLEXIBLE:  "N: mask -- added by X on DATE; last used: DATE (reason)"
    FIXED:     "N  mask  creator  date_added  date_lastused  [reason]"
    MONOSPACE: Same as FIXED but with \x11 prefix stripped by IRC formatting removal
    
    All IRC formatting characters (\x02, \x11, \x03, etc.) are stripped first.
    """
    # FLEXIBLE with last used: "1: mask -- added by creator on DATE; last used: DATE (reason)"
    pattern_flexible_used = re.compile(
        r'^\d+:\s+(\S+)\s+--\s+added by\s+(\S+)\s+on\s+(.+?);\s+last used:\s+(.+?)(?:\s+\((.+)\))?$'
    )
    # FLEXIBLE never used: "1: mask -- added by creator on DATE; never used (reason)"
    pattern_flexible_never = re.compile(
        r'^\d+:\s+(\S+)\s+--\s+added by\s+(\S+)\s+on\s+(.+?);\s+never used(?:\s+\((.+)\))?$'
    )
    # FIXED/MONOSPACE: "1  mask  creator  date_added  date_lastused|Never  [reason]"
    # Both date columns are matched explicitly (DATE_RE) since two adjacent free-text
    # .+? groups can't be split unambiguously — confirmed live output ("Mon Jul 27
    # 11:28:43 2026  Never      testreason") was parsed wrong by the old pattern:
    # addedat truncated to "Mon", lastused absorbed the rest of the date + reason.
    pattern_fixed_used = re.compile(
        rf'^\d+\s+(\S+)\s+(\S+)\s+({DATE_RE})\s+(Never(?:\s+used)?|{DATE_RE})(?:\s+(.+))?$'
    )
    
    # Header/footer words to skip
    skip = {'number', 'mask', 'creator', 'added', 'by', 'on', 'last', 'used', 'date', 'end'}
    
    entries = []
    for line in lines:
        # Strip ALL IRC formatting chars (bold \x02, monospace \x11, color \x03, reset \x0f, etc.)
        line = re.sub(r'[\x02\x03\x0f\x11\x16\x1d\x1f]', '', line).strip()
        
        if not line:
            continue
        
        # Skip header/footer lines
        first_word = line.split()[0].lower().rstrip(':') if line.split() else ''
        if first_word in skip:
            continue
        
        # Try FLEXIBLE format with last used date
        m = pattern_flexible_used.match(line)
        if m:
            entries.append({
                "mask":     m.group(1),
                "addedby":  m.group(2),
                "addedat":  m.group(3).strip(),
                "lastused": m.group(4).strip(),
                "reason":   m.group(5) or "",
            })
            continue
        
        # Try FLEXIBLE format with never used
        m = pattern_flexible_never.match(line)
        if m:
            entries.append({
                "mask":     m.group(1),
                "addedby":  m.group(2),
                "addedat":  m.group(3).strip(),
                "lastused": "Never used",
                "reason":   m.group(4) or "",
            })
            continue
        
        # Try FIXED/MONOSPACE format
        m = pattern_fixed_used.match(line)
        if m:
            reason = (m.group(5) or "").strip()
            if reason.startswith("(") and reason.endswith(")"):
                reason = reason[1:-1]
            entries.append({
                "mask":     m.group(1),
                "addedby":  m.group(2),
                "addedat":  m.group(3).strip(),
                "lastused": m.group(4).strip(),
                "reason":   reason,
            })
            continue
    
    return entries


def parse_akill_list(lines):
    """
    Format: "N: mask (reason)"
    """
    pattern = re.compile(r'^\d+:\s+(\S+)(?:\s+\((.+)\))?$')
    entries = []
    for line in lines:
        m = pattern.match(line.strip())
        if m:
            entries.append({
                "mask":   m.group(1),
                "reason": m.group(2) or "",
            })
    return entries


def parse_cert_list(lines):
    """
    Parses NickServ CERT LIST / VIEW output. Real format (confirmed live —
    the original regex required the WHOLE line to be pure hex, but real
    output is tabular with Description (LIST) or Creator/Created/
    Description (VIEW) columns trailing the fingerprint, so it never
    matched and always returned zero entries):
      LIST: "Certificate list for PeGaSuS:"
            "Fingerprint                                                       Description"
            "afece0309b03476a80997d605f026789c987816e0d91cbabb1bf68e06c96b8da  "
      VIEW: adds "Creator  Created" columns before Description.
    Only the leading fingerprint is extracted (matches this function's
    existing flat-list-of-strings return shape).
    """
    pattern = re.compile(r'^([0-9a-fA-F]{16,})(?:\s|$)')
    certs = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('certificate', 'fingerprint'):
            continue
        m = pattern.match(line)
        if m:
            certs.append(m.group(1))
    return certs


def _parse_fixed_table_by_header(header_line, data_lines):
    """
    Generic ListFormatter FIXED-layout parser: slices each data line using
    the *character offsets* of the header's column names, rather than
    guessing a per-field regex. Handles columns whose values legitimately
    contain spaces (e.g. an "Expires" column showing "expires in 7 days"),
    which a plain `\\S+` per-field regex can't represent. Returns a list of
    dicts keyed by lowercased header name.
    """
    cols = [(m.start(), m.group().lower()) for m in re.finditer(r'\S+', header_line)]
    starts = [c[0] for c in cols]
    rows = []
    for line in data_lines:
        row = {}
        for i, (start, name) in enumerate(cols):
            end = starts[i + 1] if i + 1 < len(starts) else None
            row[name] = (line[start:end] if end else line[start:]).strip()
        rows.append(row)
    return rows


def parse_xline_view(lines):
    """
    Parses OperServ AKILL VIEW / SNLINE VIEW / SQLINE VIEW output — these
    three commands share the exact same reply shape (all built on the same
    XLine list machinery, `os_akill.cpp`/`os_sxline.cpp`), confirmed live
    against real production SQLINE data (17 real entries) plus disposable
    SNLINE test entries. The `[ID]` field is only present when
    `operserv:akillids` is enabled (true on this network) — kept optional
    here so this still works on installs where it's off.
      FLEXIBLE (confirmed live):
        "1: [I0MXEDTISB] *puta* -- created by James on Tue Aug 13 16:22:04 2024; does not expire ([James] Nick not allowed)"
      FIXED (confirmed live):
        "Number  Mask           Creator  Created                   Expires            ID          Reason"
        "1       *snlinetest2*  PeGaSuS  Mon Jul 27 22:47:28 2026  expires in 7 days  15Z0YM4J7O  [PeGaSuS] short reason"
    """
    pattern_flexible = re.compile(
        r'^\d+:\s+(?:\[(\S+)\]\s+)?(\S+)\s+--\s+created by\s+(\S+)\s+on\s+(.+?);\s+'
        r'(does not expire|expires (?:in|on) .+?)(?:\s+\((.+)\))?$'
    )
    entries = []
    header_idx = None
    for i, raw in enumerate(lines):
        line = strip_irc(raw).strip()
        if line.lower().startswith('number') and 'mask' in line.lower():
            header_idx = i
            break
        m = pattern_flexible.match(line)
        if m:
            entries.append({
                "id":        m.group(1) or "",
                "mask":      m.group(2),
                "createdby": m.group(3),
                "createdat": m.group(4).strip(),
                "expiry":    m.group(5).strip(),
                "reason":    (m.group(6) or "").strip(),
            })
    if header_idx is not None:
        header = strip_irc(lines[header_idx]).strip()
        data_lines = [strip_irc(l).strip() for l in lines[header_idx + 1:]]
        data_lines = [l for l in data_lines if l and not l.lower().startswith('end of')]
        for row in _parse_fixed_table_by_header(header, data_lines):
            entries.append({
                "id":        row.get("id", ""),
                "mask":      row.get("mask", ""),
                "createdby": row.get("creator", ""),
                "createdat": row.get("created", ""),
                "expiry":    row.get("expires", ""),
                "reason":    row.get("reason", ""),
            })
    return entries


def parse_akill_view(lines):
    return parse_xline_view(lines)


def parse_cs_info(lines):
    """
    Parse ChanServ INFO output into a dict.
    Format: "Key: Value" lines.
    Options line is parsed into a set of lowercase option names.
    """
    info = {}
    for line in lines:
        line = line.strip()
        if ':' not in line:
            continue
        key, _, value = line.partition(': ')
        key = key.strip().lower().replace(' ', '_')
        info[key] = value.strip()

    # Parse options into a set for easy template checks
    if 'options' in info:
        info['option_set'] = {
            o.strip().lower().replace(' ', '_')
            for o in info['options'].split(',')
        }
    else:
        info['option_set'] = set()

    return info


def parse_entrymsg_list(lines):
    """
    Parses ChanServ ENTRYMSG LIST output. Layout-sensitive like every
    other Anope list command using ListFormatter — FLEXIBLE returned zero
    entries until caught by an explicit flexible-layout audit.
      FIXED (confirmed live):
        "Entry message list for #clitest:"
        "Number  Creator      Created                   Message"
        "1       claudetest3  Mon Jul 27 17:35:30 2026  welcome test message"
        "End of entry message list."
      FLEXIBLE (confirmed live):
        "Entry message list for #clitest:"
        "1: welcome test message -- created by claudetest3 at Mon Jul 27 17:35:30 2026"
        "End of entry message list."
    """
    pattern_flexible = re.compile(rf'^(\d+):\s+(.+?)\s+--\s+created by\s+(\S+)\s+at\s+({DATE_RE})$')
    pattern_fixed = re.compile(rf'^(\d+)\s+(\S+)\s+({DATE_RE})\s+(.+)$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower().rstrip(':')
        if first_word in ('entry', 'number', 'end'):
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({
                "num":     m.group(1),
                "creator": m.group(3),
                "created": m.group(4).strip(),
                "text":    m.group(2).strip(),
            })
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({
                "num":     m.group(1),
                "creator": m.group(2),
                "created": m.group(3).strip(),
                "text":    m.group(4).strip(),
            })
    return entries


def parse_log_list(lines):
    """
    Parses ChanServ LOG LIST output. Layout-sensitive like every other
    Anope list command using ListFormatter — the FIXED format below was
    the only one live-verified when this was first fixed; FLEXIBLE
    returned zero entries until caught by an explicit flexible-layout
    audit.
      FIXED (confirmed live):
        "Log list for #clitest:"
        "Number  Service   Command  Method"
        "1       ChanServ  FLAGS    MESSAGE"
        "2       ChanServ  ACCESS   NOTICE +"
      FLEXIBLE (confirmed live):
        "Log list for #clitest:"
        "1: FLAGS on ChanServ: MESSAGE"
        "2: ACCESS on ChanServ: NOTICE +"

    Important: the displayed "Command" is a short uppercase name (FLAGS),
    but re-submitting LOG to ADD/DEL requires the full lowercase
    "service/command" form (chanserv/flags) — confirmed live: `LOG #chan
    FLAGS MESSAGE` fails ("FLAGS is not a valid command"), only `LOG #chan
    chanserv/flags MESSAGE` works. `command` here is reconstructed into
    that working form so a delete button fed straight from this parser's
    output actually functions.
    """
    pattern_flexible = re.compile(r'^(\d+):\s+(\S+)\s+on\s+(\S+):\s+(.+)$')
    pattern_fixed = re.compile(r'^(\d+)\s+(\S+)\s+(\S+)\s+(.+)$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower().rstrip(':')
        if first_word in ('log', 'number'):
            continue
        m = pattern_flexible.match(line)
        if m:
            short_command, service = m.group(2), m.group(3)
            method_status = m.group(4).strip().split(None, 1)
            entries.append({
                "command": f"{service.lower()}/{short_command.lower()}",
                "service": service,
                "method":  method_status[0],
                "status":  method_status[1] if len(method_status) > 1 else "",
            })
            continue
        m = pattern_fixed.match(line)
        if m:
            service = m.group(2)
            short_command = m.group(3)
            method_status = m.group(4).strip().split(None, 1)
            entries.append({
                "command": f"{service.lower()}/{short_command.lower()}",
                "service": service,
                "method":  method_status[0],
                "status":  method_status[1] if len(method_status) > 1 else "",
            })
    return entries


def parse_drop_code(lines):
    """
    Extract the drop confirmation code from:
    "Please confirm that you want to drop #channel with /CS DROP #channel CODE"
    Strips IRC escape chars first.
    """
    for line in lines:
        line = line.replace('\x1b', ' ').strip()
        parts = line.split()
        if parts:
            return parts[-1]
    return None


def parse_getkey(lines):
    """Format: "Key for channel #X is KEY." """
    for line in lines:
        m = re.match(r'^Key for channel \S+ is (.+)\.$', line.strip())
        if m:
            return m.group(1)
    return None


def parse_status(lines):
    """
    Format:
      "Access for NICK on #CHAN:"
      "NICK matches access entry MASK, which has privilege LEVEL."
    or "NICK has no access on #CHAN."
    """
    result = {"nick": None, "channel": None, "privilege": None, "entry": None, "lines": lines}
    for line in lines:
        line = line.strip()
        m = re.match(r'^Access for (\S+) on (\S+):$', line)
        if m:
            result["nick"] = m.group(1)
            result["channel"] = m.group(2)
        m2 = re.match(r'^(\S+) matches access entry (\S+), which has privilege (\S+)\.$', line)
        if m2:
            result["entry"] = m2.group(2)
            result["privilege"] = m2.group(3).rstrip('.')
        if 'has no access' in line:
            result["privilege"] = "none"
    return result


def parse_stats(lines):
    """
    Format:
      "Channel stats for NICK on #CHAN:"
      "letters: N, words: N, lines: N, smileys: N, actions: N"
    """
    result = {}
    for line in lines:
        line = line.strip()
        m = re.match(r'^Channel stats for (\S+) on (\S+):$', line)
        if m:
            result["nick"] = m.group(1)
            result["channel"] = m.group(2)
        # GSTATS variant: "Network stats for NICK:" (no channel)
        m0 = re.match(r'^Network stats for (\S+):$', line)
        if m0:
            result["nick"] = m0.group(1)
            result["channel"] = None
        for key in ("letters", "words", "lines", "smileys", "actions"):
            m2 = re.search(rf'{key}:\s*(\d+)', line)
            if m2:
                result[key] = int(m2.group(1))
    return result


def parse_cs_list(lines):
    """
    Parses ChanServ LIST output. Real format (confirmed live — the
    originally assumed "#channel (Description)" silently DROPPED any
    channel with a real description, since real output has no parens at
    all — a tabular "Name  Description" with free trailing text):
      "List of entries matching *:"
      "Name      Description"
      "#clitest  Test channel description"
      "#opers    "
      "End of list - 2/2 matches shown."
    """
    pattern = re.compile(r'^(!?#\S+)(?:\s+(.+))?$')
    channels = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('list', 'name', 'end'):
            continue
        m = pattern.match(line)
        if m:
            desc = (m.group(2) or "").strip()
            if desc.startswith("(") and desc.endswith(")"):
                desc = desc[1:-1]
            channels.append({
                "channel": m.group(1).lstrip("!"),
                "noexpire": m.group(1).startswith("!"),
                "desc": desc,
            })
    return channels


def parse_clone_result(lines):
    """Returns list of result lines, skipping empty ones."""
    return [l.strip() for l in lines if l.strip()]


def parse_memo_list(lines):
    """
    Format: "* N: sent by SENDER at DATE" (unread) or "  N: sent by SENDER at DATE" (read)
    First line is header, last is footer.
    """
    pattern = re.compile(r'^(\*\s+|\s+)?(\d+):\s+sent by\s+(\S+)\s+at\s+(.+)$')
    memos = []
    for line in lines:
        line = line.replace('\x02', '').strip()  # strip IRC bold
        m = pattern.match(line)
        if m:
            memos.append({
                "num":    int(m.group(2)),
                "unread": m.group(1) is not None and '*' in m.group(1),
                "sender": m.group(3),
                "date":   m.group(4).strip(),
            })
    return memos


def parse_access_list(lines):
    """
    Parses ChanServ numeric ACCESS LIST output. Handles both layouts —
    originally FLEXIBLE-only, confirmed broken (returned nothing) against
    real FIXED-layout output:
      "Access list for #opers:"
      "Number  Level  Mask                  Description"
      "1       10     *!*@test.example.com  "
      "End of access list"
    Note FIXED column order is Level then Mask — the reverse of FLEXIBLE's
    "mask = LEVEL".

    FLEXIBLE: "N: mask = LEVEL"  e.g. "1: LunarBNC = HOP"
    """
    pattern_flexible = re.compile(r'^\d+:\s+(\S+)\s+=\s+(\S+)$')
    pattern_fixed = re.compile(r'^\d+\s+(\S+)\s+(\S+)(?:\s+.+)?$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({"mask": m.group(1), "level": m.group(2)})
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({"mask": m.group(2), "level": m.group(1)})
    return entries


def parse_xop_list(lines):
    """
    Parses ChanServ xOP (VOP/HOP/AOP/SOP/QOP) LIST output. Handles both
    layouts — originally FLEXIBLE-only, confirmed broken against real
    FIXED-layout output:
      "AOP list for #clitest"
      "Number  Mask                     Description"
      "1       *!*@aoptest.example.com  "

    FLEXIBLE: "N: mask"  e.g. "3: TECO"
    """
    pattern_flexible = re.compile(r'^\d+:\s+(\S+)$')
    pattern_fixed = re.compile(r'^\d+\s+(\S+)(?:\s+.+)?$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({"mask": m.group(1)})
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({"mask": m.group(1)})
    return entries


def parse_levels_list(lines):
    """
    Parses ChanServ LEVELS LIST output. Layout-sensitive — FLEXIBLE uses
    "=" (confirmed live), FIXED does not (also confirmed live, and this
    docstring previously assumed FIXED's no-"=" shape was the ONLY shape,
    which silently left a literal "= " in the level value for FLEXIBLE
    accounts until caught by an explicit flexible-layout audit):
      FIXED:    "Access level settings for channel #clitest:"
                "Name           Level"
                "ACCESS_CHANGE  10"
                "KICK           -1"              (nobody, incl. founder)
                "TOPIC          (disabled)"       (LEVELS DIS/DISABLE)
                "ASSIGN         (founder only)"
      FLEXIBLE: "Access level settings for channel #clitest:"
                "ACCESS_CHANGE = 10"
                "ASSIGN = (founder only)"
    """
    pattern_flexible = re.compile(r'^(\S+)\s+=\s+(.+)$')
    pattern_fixed = re.compile(r'^(\S+)\s+(.+)$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('access', 'name'):
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({"privilege": m.group(1), "level": m.group(2).strip()})
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({"privilege": m.group(1), "level": m.group(2).strip()})
    return entries


def parse_ns_info(lines):
    """
    Parse NS INFO output into a dict.
    Options line parsed into a set of lowercase slugs.
    """
    info = {}
    for line in lines:
        line = strip_irc(line).strip()
        if ':' not in line:
            continue
        key, _, value = line.partition(': ')
        key = key.strip().lower().replace(' ', '_')
        info[key] = value.strip()
    if 'options' in info:
        info['option_set'] = {
            o.strip().lower().replace(' ', '_')
            for o in info['options'].split(',')
        }
    else:
        info['option_set'] = set()
    return info


def parse_ajoin_list(lines):
    """
    Parses NickServ AJOIN LIST output. Layout-sensitive — FLEXIBLE
    (confirmed live) turned out to be the originally-assumed "N:
    #channel [key]" shape after all, it just wasn't being tried anymore
    once this was "fixed" to FIXED-only earlier the same day, so FLEXIBLE
    silently went back to returning zero entries.
      FIXED (confirmed live):
        "claudetest3's auto join list:"
        "Number  Channel   Key"
        "1       #clitest  "
      FLEXIBLE (confirmed live):
        "claudetest3's auto join list:"
        "1: #clitest"
    """
    pattern_flexible = re.compile(r'^(\d+):\s+(\S+)(?:\s+(\S+))?$')
    pattern_fixed = re.compile(r'^(\d+)\s+(\S+)(?:\s+(\S+))?$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower().rstrip(':')
        if first_word == 'number':
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({"channel": m.group(2), "key": m.group(3) or ""})
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({"channel": m.group(2), "key": m.group(3) or ""})
    return entries


def parse_ns_list(lines):
    """
    Parses NickServ LIST output. Layout-sensitive — no email is shown at
    all in either layout (privacy), but the shape differs completely, and
    only FIXED was tested when this was first fixed.
      FIXED (confirmed live):
        "List of entries matching *:"
        "Nick         Account      Status"
        "claudetest3  claudetest3  "
        "claudetest4  claudetest4  Unconfirmed"
        "End of list - 6/6 matches shown."
      FLEXIBLE (confirmed live):
        "List of entries matching *:"
        "claudetest3 (account: claudetest3)"
        "claudetest4 -- Unconfirmed (account: claudetest4)"
        "End of list - 6/6 matches shown."
    """
    pattern_flexible = re.compile(r'^(\S+)(?:\s+--\s+(.+?))?\s+\(account:\s+(\S+)\)$')
    pattern_fixed = re.compile(r'^(\S+)\s+(\S+)(?:\s+(.+))?$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('list', 'end', 'nick'):
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({
                "nick":    m.group(1),
                "account": m.group(3),
                "status":  (m.group(2) or "").strip(),
            })
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({
                "nick":    m.group(1),
                "account": m.group(2),
                "status":  (m.group(3) or "").strip(),
            })
    return entries


def parse_hs_list(lines):
    """
    Parses HostServ LIST / WAITING output. Layout-sensitive — turns out
    the ORIGINAL "N: nick = vhost -- created by X at Y" assumption (from
    an even earlier session, docstring said "verified" on 2026-06-30) was
    actually FLEXIBLE's real shape all along; it got dropped entirely
    rather than kept alongside FIXED when this was "fixed" earlier the
    same day using only a FIXED-layout account. Lesson: add a branch,
    don't replace one.
      FIXED (confirmed live):
        LIST:    "Number  Nick  VHost  Creator  Created"
                 "1       claudetest3  test.clitest.example.org  PeGaSuS  Mon Jul 27 17:43:08 2026"
        WAITING: "Number  Nick  VHost  Created"
                 "1       claudetest3  test.clitest.example.org  Mon Jul 27 17:43:08 2026"
      FLEXIBLE (confirmed live for LIST; WAITING presumed to drop the
        creator the same way FIXED's WAITING does — creator group uses
        \\S* to allow for that, per the 2026-06-30 note this carries
        forward from):
        LIST: "1: claudetest3 = flextest.clitest.example.org -- created by PeGaSuS at Mon Jul 27 19:17:59 2026"
    """
    pattern_flexible = re.compile(
        rf'^(\d+):\s+(\S+)\s+=\s+(\S+)\s+--\s+created by\s*(\S*)\s+at\s+({DATE_RE})$'
    )
    pattern_with_creator = re.compile(rf'^(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+({DATE_RE})$')
    pattern_no_creator = re.compile(rf'^(\d+)\s+(\S+)\s+(\S+)\s+({DATE_RE})$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower().rstrip(':')
        if first_word in ('number', 'displayed', 'no'):
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({
                "num":       m.group(1),
                "nick":      m.group(2),
                "vhost":     m.group(3),
                "createdby": m.group(4),
                "createdat": m.group(5).strip(),
            })
            continue
        m = pattern_with_creator.match(line)
        if m:
            entries.append({
                "num":       m.group(1),
                "nick":      m.group(2),
                "vhost":     m.group(3),
                "createdby": m.group(4),
                "createdat": m.group(5).strip(),
            })
            continue
        m = pattern_no_creator.match(line)
        if m:
            entries.append({
                "num":       m.group(1),
                "nick":      m.group(2),
                "vhost":     m.group(3),
                "createdby": "",
                "createdat": m.group(4).strip(),
            })
    return entries


def parse_hs_offerlist(lines):
    """
    Parses BOTH `HostServ OFFERLIST` (bare, user-facing) AND
    `HostServ OFFER LIST` (oper subcommand) output — these looked
    interchangeable from a docstring that only ever tested data from the
    bare command, but they're genuinely different Anope command classes
    (CommandHSOfferList vs CommandHSOffer) with different reply shapes,
    confirmed live: OFFER LIST has no "your vhost preview" or "expires"
    data at all, just entry/template/reason. The panel calls OFFERLIST
    for regular users and OFFER LIST for opers (see routes/services.py),
    so both shapes have to work or the oper view silently renders empty.
      OFFERLIST FIXED (confirmed live):
        "Number  Offered vhost               Your vhost                    Expires          Reason"
        "1       users.ptirc.org.{account}   users.ptirc.org.claudetest3   does not expire"
        "2       users2.ptirc.org.{account}  users2.ptirc.org.claudetest3  does not expire  30d special reason text here"
      OFFERLIST FLEXIBLE (confirmed live):
        "1: users/{account} / users/claudetest3 -- does not expire"
        "2: test2.x / test2.x -- expires in 1 day (expiring offer reason)"
      OFFER LIST FIXED (confirmed live):
        "Number  VHost                  Reason"
        "1       users.PTirc.{account}  default"
        "2       users/PTirc/{account}  "
      OFFER LIST FLEXIBLE (confirmed live):
        "1: users.PTirc.{account} (default)"
        "2: users/PTirc/{account}"
    Expires is anchored on its known phrases (like OperServ's ignore list)
    since it's followed by an unlabeled free-text Reason column in FIXED.
    "yours" is None for OFFER LIST entries (no such data exists) — the
    template shows a placeholder for that case.
    """
    pattern_flexible_full = re.compile(
        r'^(\d+):\s+(\S+)\s+/\s+(\S+)\s+--\s+(does not expire|expires (?:in|on) .+?)(?:\s+\((.+)\))?$'
    )
    pattern_fixed_full = re.compile(
        r'^(\d+)\s+(\S+)\s+(\S+)\s+(does not expire|expires (?:in|on) \S.*?)(?:\s{2,}(.+))?$'
    )
    pattern_flexible_simple = re.compile(r'^(\d+):\s+(\S+)(?:\s+\((.+)\))?$')
    pattern_fixed_simple = re.compile(r'^(\d+)\s+(\S+)\s*(.*)$')

    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower().rstrip(':')
        if first_word in ('current', 'number', 'end', 'no', 'host'):
            continue

        m = pattern_flexible_full.match(line)
        if m:
            expires = m.group(4).strip()
            reason = (m.group(5) or "").strip()
            entries.append({
                "num":     m.group(1),
                "offered": m.group(2),
                "yours":   m.group(3),
                "trailer": f"{expires} — {reason}" if reason else expires,
            })
            continue

        m = pattern_fixed_full.match(line)
        if m:
            expires = m.group(4).strip()
            reason = (m.group(5) or "").strip()
            entries.append({
                "num":     m.group(1),
                "offered": m.group(2),
                "yours":   m.group(3),
                "trailer": f"{expires} — {reason}" if reason else expires,
            })
            continue

        m = pattern_flexible_simple.match(line)
        if m:
            entries.append({
                "num":     m.group(1),
                "offered": m.group(2),
                "yours":   None,
                "trailer": (m.group(3) or "").strip(),
            })
            continue

        m = pattern_fixed_simple.match(line)
        if m:
            entries.append({
                "num":     m.group(1),
                "offered": m.group(2),
                "yours":   None,
                "trailer": m.group(3).strip(),
            })
    return entries


def parse_os_userlist(lines):
    """
    Parses OperServ USERLIST output. Layout-sensitive like every other
    Anope list command using ListFormatter — the FIXED format below was
    the only one tested when this was first written, and the FLEXIBLE
    branch was silently WRONG (matched the generic 3-token regex but left
    literal parens/brackets in the captured fields) until caught by an
    explicit flexible-layout audit.
      FIXED (confirmed live):
        "Users list:"
        "Name         Mask                         Realname"
        "claudetest3  claudetest@Clk-2DDF2811      claudetest3 Test"
        "End of users list. 9 users shown."
      FLEXIBLE (confirmed live):
        "Users list:"
        "BotServ (services@services.ptirc.org) [Bot Service]"
        "End of users list. 10 users shown."
    """
    pattern_flexible = re.compile(r'^(\S+)\s+\((\S+)\)\s+\[(.+)\]$')
    pattern_fixed = re.compile(r'^(\S+)\s+(\S+)\s+(.+)$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ("name", "users") or line.startswith("End of users list"):
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({"name": m.group(1), "mask": m.group(2), "realname": m.group(3).strip()})
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({
                "name":     m.group(1),
                "mask":     m.group(2),
                "realname": m.group(3).strip(),
            })
    return entries


def parse_os_chanlist(lines):
    """
    Parses OperServ CHANLIST output. Layout-sensitive like every other
    Anope list command using ListFormatter — FLEXIBLE returned zero
    entries until caught by an explicit flexible-layout audit (the FIXED
    format was the only one tested when this was first written).
      FIXED (confirmed live):
        "Channel list:"
        "Name       Users  Modes  Topic"
        "#clitest   2      nPrt   "
        "End of channel list. 3 channels shown."
      FLEXIBLE (confirmed live):
        "Channel list:"
        "#clitest -- 2 user(s); +nPrt (Test topic for flexible check)"
        "#opers -- 2 user(s); +nPrt"
        "End of channel list. 2 channels shown."
    Topic may be empty; Modes has a leading "+" in FLEXIBLE but not FIXED —
    normalized to bare (no "+") in both, since the template adds its own.
    """
    pattern_flexible = re.compile(r'^(\S+)\s+--\s+(\d+)\s+user\(s\);\s+\+(\S+)(?:\s+\((.+)\))?$')
    pattern_fixed = re.compile(r'^(\S+)\s+(\d+)\s+(\S+)(?:\s+(.+))?$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ("name", "channel") or line.startswith("End of channel list"):
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({
                "channel": m.group(1),
                "users":   int(m.group(2)),
                "modes":   m.group(3),
                "topic":   (m.group(4) or "").strip(),
            })
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({
                "channel": m.group(1),
                "users":   int(m.group(2)),
                "modes":   m.group(3),
                "topic":   (m.group(4) or "").strip(),
            })
    return entries


def parse_os_oper_list(lines):
    """
    Parses OperServ OPER LIST output.
    Real format (confirmed live):
      "Name     Type"
      "PeGaSuS  Services Root"
      "   This oper is configured in the configuration file."
      "   PeGaSuS is online using this oper block."
    Indented lines are notes attached to the preceding oper entry.
    """
    entries = []
    for raw in lines:
        if not raw.strip():
            continue
        stripped = strip_irc(raw)
        if stripped.startswith((" ", "\t")):
            if entries:
                entries[-1]["notes"].append(stripped.strip())
            continue
        line = stripped.strip()
        if line.lower().startswith("name"):
            continue
        # Column padding is dynamic (name width varies), so only a single space
        # separates columns for long names (e.g. "claudetest3 Helper") — match on
        # any whitespace run, not a fixed minimum.
        m = re.match(r'^(\S+)\s+(.+)$', line)
        if m:
            entries.append({"name": m.group(1), "type": m.group(2).strip(), "notes": []})
    return entries


def parse_os_news_list(lines):
    """
    Parses OperServ LOGONNEWS/OPERNEWS/RANDOMNEWS LIST output. Like every
    other Anope list command using ListFormatter, this is ALSO
    layout-sensitive (NS SET LAYOUT) — this was missed all session because
    only FIXED-layout accounts were used for testing, and only caught when
    a real FLEXIBLE-layout production account reported LOGONNEWS
    "not appearing":
      FIXED (confirmed live):
        "Oper news items:"
        "Number  Creator  Created                   Text"
        "1       PeGaSuS  Mon Jul 27 11:47:16 2026  Welcome opers, please read the MOTD."
        "End of news list."
      FLEXIBLE (confirmed live):
        "Logon news items:"
        "1: Welcome to PTirc! -- created by PeGaSuS on Mon Jul 27 19:02:10 2026"
        "End of news list."
    """
    pattern_fixed = re.compile(rf'^(\d+)\s+(\S+)\s+({DATE_RE})\s+(.+)$')
    pattern_flexible = re.compile(rf'^(\d+):\s+(.+?)\s+--\s+created by\s+(\S+)\s+on\s+({DATE_RE})$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower().rstrip(':')
        if first_word in ("number",) or line.endswith("news items:") or line.startswith("End of news list") \
           or "no logon news" in line.lower() or "no oper news" in line.lower() or "no random news" in line.lower():
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({
                "num":     m.group(1),
                "creator": m.group(3),
                "created": m.group(4).strip(),
                "text":    m.group(2).strip(),
            })
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({
                "num":     m.group(1),
                "creator": m.group(2),
                "created": m.group(3).strip(),
                "text":    m.group(4).strip(),
            })
    return entries


def parse_os_ignore_list(lines):
    """
    Parses OperServ IGNORE LIST output. Layout-sensitive like every other
    Anope list command using ListFormatter — FLEXIBLE silently matched the
    FIXED-only regex and produced garbled wrong data (not even a clean
    failure) until caught by an explicit flexible-layout audit.
      FIXED (confirmed live):
        "Services ignore list:"
        "Mask              Creator  Reason          Expires"
        "*!*@spammer.test  PeGaSuS  testing ignore  expires in 1 hour"
      FLEXIBLE (confirmed live):
        "Services ignore list:"
        "*!*@ignoretest.example.com -- created by claudetest3; expires in 59 minutes, 59 seconds (testreason)"
    Reason/Expires are anchored on Expires' known prefixes since they're
    free text with no other reliable delimiter.
    """
    pattern_flexible = re.compile(
        r'^(\S+)\s+--\s+created by\s+(\S+);\s+(does not expire|expires (?:in|on) .+?)(?:\s+\((.+)\))?$'
    )
    pattern_fixed = re.compile(
        r'^(\S+)\s+(\S+)\s+(.+?)\s+(expires in .+|expires on .+|does not expire)$'
    )
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        if line.startswith("Services ignore list") or line.lower().startswith("mask") \
           or line.startswith("Ignore list is empty"):
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({
                "mask":    m.group(1),
                "creator": m.group(2),
                "reason":  (m.group(4) or "").strip(),
                "expires": m.group(3).strip(),
            })
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({
                "mask":    m.group(1),
                "creator": m.group(2),
                "reason":  m.group(3).strip(),
                "expires": m.group(4).strip(),
            })
    return entries


def parse_bs_info(lines):
    """
    Parse BotServ INFO (channel or bot variant) output into a dict.
    Format: "Key: Value" lines, e.g. "Bad words kicker:  Enabled (3 kick(s) to ban)".
    Options line (channel variant only) parsed into a set like parse_cs_info.
    """
    info = {}
    for line in lines:
        line = strip_irc(line).strip()
        if ':' not in line:
            continue
        key, _, value = line.partition(':')
        key = key.strip().lower().replace(' ', '_')
        info[key] = value.strip()
    if info.get('options') and info['options'].lower() != 'none':
        info['option_set'] = {o.strip().lower() for o in info['options'].split(',')}
    else:
        info['option_set'] = set()
    return info


def parse_bs_botlist(lines):
    """
    Parses BotServ BOTLIST output. Layout-sensitive like every other Anope
    list command using ListFormatter — FLEXIBLE silently matched the
    FIXED-only regex and left literal parens/brackets in the captured
    fields until caught by an explicit flexible-layout audit.
      FIXED (confirmed live):
        "Bot list:"
        "Nick      Mask                         Real name"
        "TestBot   testbot@bots.ptirc.org       Test Bot"
        "7 bots available."
      FLEXIBLE (confirmed live):
        "Bot list:"
        "TestBot (testbot@bots.ptirc.org) [Test Bot]"
        "8 bots available."
    """
    pattern_flexible = re.compile(r'^(\S+)\s+\((\S+)\)\s+\[(.+)\]$')
    pattern_fixed = re.compile(r'^(\S+)\s+(\S+)\s+(.+)$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('nick', 'bot') or re.match(r'^\d+\s+bots?\s+available', line, re.I):
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({"nick": m.group(1), "mask": m.group(2), "realname": m.group(3).strip()})
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({
                "nick":     m.group(1),
                "mask":     m.group(2),
                "realname": m.group(3).strip(),
            })
    return entries


def parse_bs_badwords(lines):
    """
    Parses BotServ BADWORDS LIST output. Layout-sensitive like every other
    Anope list command using ListFormatter — FLEXIBLE returned zero
    entries until caught by an explicit flexible-layout audit.
      FIXED (confirmed live):
        "Bad words list for #clitest:"
        "Number  Word  Type"
        "1       smeg  ANY"
        "End of bad words list."
      FLEXIBLE (confirmed live):
        "Bad words list for #clitest:"
        "1: smeg -- type: ANY"
        "End of bad words list."
    """
    pattern_flexible = re.compile(r'^(\d+):\s+(\S+)\s+--\s+type:\s+(\S+)$')
    pattern_fixed = re.compile(r'^(\d+)\s+(\S+)\s+(\S+)$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower().rstrip(':')
        if first_word in ('number', 'bad', 'end'):
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({"num": m.group(1), "word": m.group(2), "type": m.group(3)})
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({"num": m.group(1), "word": m.group(2), "type": m.group(3)})
    return entries


def parse_cs_top(lines):
    """
    Parses ChanServ TOP/TOP10/GTOP/GTOP10 output.
    Format (from modules/chanserv/cs_fantasy_top.cpp, not yet live-verified —
    this Anope instance's chanstats MySQL backend was still being wired up
    when this was written; verify against real output before trusting blindly):
      "Top 10 of #channel"
      " 1 nick             letters: 120, words: 30, lines: 5, smileys: 2, actions: 0"
    """
    pattern = re.compile(
        r'^\s*(\d+)\s+(\S+)\s+letters:\s*(\d+),\s*words:\s*(\d+),\s*lines:\s*(\d+),\s*smileys:\s*(\d+),\s*actions:\s*(\d+)\s*$'
    )
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        m = pattern.match(line)
        if m:
            entries.append({
                "rank":    int(m.group(1)),
                "nick":    m.group(2),
                "letters": int(m.group(3)),
                "words":   int(m.group(4)),
                "lines":   int(m.group(5)),
                "smileys": int(m.group(6)),
                "actions": int(m.group(7)),
            })
    return entries


def parse_os_forbid_list(lines):
    """
    Parses OperServ FORBID LIST output. Layout-sensitive like every other
    Anope list command using ListFormatter — both branches verified live
    from the start (lesson learned from the LOGONNEWS incident).
      FIXED (confirmed live):
        "Forbid list:"
        "Mask      Type  Creator  Expires                   Reason"
        "badnick*  NICK  PeGaSuS  Wed Aug 26 19:35:11 2026  test reason here"
        "#badchan  CHAN  PeGaSuS  Never                      permanent test"
        "End of forbid list."
      FLEXIBLE (confirmed live):
        "Forbid list:"
        "badnick* on NICK -- created by PeGaSuS; expires in Wed Aug 26 19:35:11 2026 (test reason here)"
        "#badchan on CHAN -- created by PeGaSuS; expires in Never (permanent test)"
        "End of forbid list."
    Note FORBID's flexible phrasing is always "expires in ..." (even for an
    absolute date), unlike other commands that switch between "expires in"
    (relative) and "expires on" (absolute) — anchored on that literal
    phrase rather than reusing the "in|on" alternation used elsewhere.
    """
    pattern_flexible = re.compile(
        rf'^(\S+)\s+on\s+(\S+)\s+--\s+created by\s+(\S+);\s+expires in\s+(Never|{DATE_RE})(?:\s+\((.+)\))?$'
    )
    pattern_fixed = re.compile(
        rf'^(\S+)\s+(\S+)\s+(\S+)\s+(Never|{DATE_RE})\s+(.+)$'
    )
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('forbid', 'mask', 'end'):
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({
                "mask":    m.group(1),
                "type":    m.group(2),
                "creator": m.group(3),
                "expires": m.group(4).strip(),
                "reason":  (m.group(5) or "").strip(),
            })
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({
                "mask":    m.group(1),
                "type":    m.group(2),
                "creator": m.group(3),
                "expires": m.group(4).strip(),
                "reason":  m.group(5).strip(),
            })
    return entries


def parse_os_session_list(lines):
    """
    Parses OperServ SESSION LIST output. Layout-sensitive like every other
    Anope list command using ListFormatter — both branches verified live
    against real connections on testnet.
      FLEXIBLE (confirmed live):
        "Hosts with at least 2 sessions:"
        "127.0.0.1: 2 sessions"
      FIXED (confirmed live):
        "Hosts with at least 2 sessions:"
        "Session  Host"
        "2        127.0.0.1"
    """
    pattern_flexible = re.compile(r'^(\S+):\s+(\d+)\s+sessions$')
    pattern_fixed = re.compile(r'^(\d+)\s+(\S+)$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('hosts', 'session', 'invalid', 'no'):
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({"host": m.group(1), "count": m.group(2)})
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({"host": m.group(2), "count": m.group(1)})
    return entries


def parse_os_exception_list(lines):
    """
    Parses OperServ EXCEPTION LIST output. Layout-sensitive like every other
    Anope list command using ListFormatter — both branches verified live
    against a real test exception added on testnet.
      FLEXIBLE (confirmed live):
        "Current Session Limit Exception list:"
        "1: *.example.com -- 5 sessions (test session exception reason)"
      FIXED (confirmed live):
        "Current Session Limit Exception list:"
        "Number  Limit  Mask           Reason"
        "1       5      *.example.com  test session exception reason"
    """
    pattern_flexible = re.compile(r'^(\d+):\s+(\S+)\s+--\s+(\d+)\s+sessions\s+\((.+)\)$')
    pattern_fixed = re.compile(r'^(\d+)\s+(\d+)\s+(\S+)\s+(.+)$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('current', 'number', 'the', 'no'):
            continue
        m = pattern_flexible.match(line)
        if m:
            entries.append({
                "num": m.group(1), "mask": m.group(2),
                "limit": m.group(3), "reason": m.group(4).strip(),
            })
            continue
        m = pattern_fixed.match(line)
        if m:
            entries.append({
                "num": m.group(1), "limit": m.group(2),
                "mask": m.group(3), "reason": m.group(4).strip(),
            })
    return entries
