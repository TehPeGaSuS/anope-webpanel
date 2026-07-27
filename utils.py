import re

# Anope's C-style ctime date format, e.g. "Mon Jul 27 11:28:43 2026".
# Used to anchor FIXED/MONOSPACE column parsing instead of ambiguous .+? matching,
# since trailing description/reason text in those layouts isn't wrapped in parens.
DATE_RE = r'[A-Za-z]{3}\s+[A-Za-z]{3}\s+\d{1,2}\s+\d{1,2}:\d{2}:\d{2}\s+\d{4}'


def strip_irc(text):
    """Strip all IRC formatting characters from a string."""
    return re.sub(r'[](?:\d{1,2}(?:,\d{1,2})?)?', '', text)


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


def parse_akill_view(lines):
    """
    Format: "N: [ID] mask -- created by X on DATE; expires/does not expire (reason)"
    """
    pattern = re.compile(
        r'^\d+:\s+\[\S+\]\s+(\S+)\s+--\s+created by\s+(\S+)\s+on\s+(.+?);\s+(.+?)(?:\s+\((.+)\))?$'
    )
    entries = []
    for line in lines:
        m = pattern.match(line.strip())
        if m:
            entries.append({
                "mask":      m.group(1),
                "createdby": m.group(2),
                "createdat": m.group(3).strip(),
                "expiry":    m.group(4).strip(),
                "reason":    m.group(5) or "",
            })
    return entries


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
    Parses ChanServ ENTRYMSG LIST output. Real format (confirmed live —
    this docstring's original assumed "N: message" format doesn't match;
    it's a tabular list like badwords/news, and returned zero entries
    against real output):
      "Entry message list for #clitest:"
      "Number  Creator      Created                   Message"
      "1       claudetest3  Mon Jul 27 17:35:30 2026  welcome test message"
      "End of entry message list."
    """
    pattern = re.compile(rf'^(\d+)\s+(\S+)\s+({DATE_RE})\s+(.+)$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('entry', 'number', 'end'):
            continue
        m = pattern.match(line)
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
    Parses ChanServ LOG LIST output. Real format (confirmed live — the
    originally assumed "N: command on service: method" never matched,
    always returned zero entries):
      "Log list for #clitest:"
      "Number  Service   Command  Method"
      "1       ChanServ  FLAGS    MESSAGE"
      "2       ChanServ  ACCESS   NOTICE +"

    Important: the displayed "Command" is a short uppercase name (FLAGS),
    but re-submitting LOG to ADD/DEL requires the full lowercase
    "service/command" form (chanserv/flags) — confirmed live: `LOG #chan
    FLAGS MESSAGE` fails ("FLAGS is not a valid command"), only `LOG #chan
    chanserv/flags MESSAGE` works. `command` here is reconstructed into
    that working form so a delete button fed straight from this parser's
    output actually functions.
    """
    pattern = re.compile(r'^(\d+)\s+(\S+)\s+(\S+)\s+(.+)$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('log', 'number'):
            continue
        m = pattern.match(line)
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
    Parses ChanServ LEVELS LIST output. Real format (confirmed live —
    no "=" at all, this docstring's original assumed format was wrong
    for this Anope version and returned zero entries against real output):
      "Access level settings for channel #clitest:"
      "Name           Level"
      "ACCESS_CHANGE  10"
      "KICK           -1"              (LEVELS SET KICK -1 → nobody, incl. founder)
      "TOPIC          (disabled)"       (LEVELS DIS/DISABLE)
      "ASSIGN         (founder only)"
    """
    pattern = re.compile(r'^(\S+)\s+(.+)$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('access', 'name'):
            continue
        m = pattern.match(line)
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
    Parses NickServ AJOIN LIST output. Real format (confirmed live — the
    originally assumed "N: #channel [key]" never matched, always returned
    zero entries):
      "claudetest3's auto join list:"
      "Number  Channel   Key"
      "1       #clitest  "
    """
    pattern = re.compile(r'^(\d+)\s+(\S+)(?:\s+(\S+))?$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word == 'number':
            continue
        m = pattern.match(line)
        if m:
            entries.append({"channel": m.group(2), "key": m.group(3) or ""})
    return entries


def parse_ns_list(lines):
    """
    Parses NickServ LIST output. Real format (confirmed live — no email is
    shown at all, the originally assumed "nick (email)" format never
    matched, always returned zero entries):
      "List of entries matching *:"
      "Nick         Account      Status"
      "claudetest3  claudetest3  "
      "claudetest4  claudetest4  Unconfirmed"
      "End of list - 6/6 matches shown."
    """
    pattern = re.compile(r'^(\S+)\s+(\S+)(?:\s+(.+))?$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('list', 'end', 'nick'):
            continue
        m = pattern.match(line)
        if m:
            entries.append({
                "nick":    m.group(1),
                "account": m.group(2),
                "status":  (m.group(3) or "").strip(),
            })
    return entries


def parse_hs_list(lines):
    """
    Parses HostServ LIST / WAITING output. Real format (confirmed live —
    the previously assumed "N: nick = vhost -- created by X at Y" format
    (documented as "verified" on 2026-06-30) does not match this Anope
    build's actual output at all and returns zero entries; real output is
    tabular, and WAITING lacks the Creator column LIST has (pending
    requests don't have an approver yet):
      LIST:    "Number  Nick  VHost  Creator  Created"
               "1       claudetest3  test.clitest.example.org  PeGaSuS  Mon Jul 27 17:43:08 2026"
      WAITING: "Number  Nick  VHost  Created"
               "1       claudetest3  test.clitest.example.org  Mon Jul 27 17:43:08 2026"
    """
    pattern_with_creator = re.compile(rf'^(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+({DATE_RE})$')
    pattern_no_creator = re.compile(rf'^(\d+)\s+(\S+)\s+(\S+)\s+({DATE_RE})$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('number', 'displayed', 'no'):
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
    Parses HostServ OFFERLIST / OFFER LIST output. Real format (confirmed
    live — the previously assumed "N: template / preview -- trailer"
    format, documented as "confirmed against live output," does not match
    this Anope build's actual output at all and returned zero entries;
    also, contrary to the old note, Reason IS populated here when set):
      "Current host offer list:"
      "Number  Offered vhost               Your vhost                    Expires          Reason"
      "1       users.ptirc.org.{account}   users.ptirc.org.claudetest3   does not expire"
      "2       users2.ptirc.org.{account}  users2.ptirc.org.claudetest3  does not expire  30d special reason text here"
      "End of host offer list."
    Expires is anchored on its known phrases (like OperServ's ignore list)
    since it's followed by an unlabeled free-text Reason column.
    """
    pattern = re.compile(
        r'^(\d+)\s+(\S+)\s+(\S+)\s+(does not expire|expires (?:in|on) \S.*?)(?:\s{2,}(.+))?$'
    )
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('current', 'number', 'end', 'no', 'host'):
            continue
        m = pattern.match(line)
        if m:
            expires = m.group(4).strip()
            reason = (m.group(5) or "").strip()
            entries.append({
                "num":     m.group(1),
                "offered": m.group(2),
                "yours":   m.group(3),
                "trailer": f"{expires} — {reason}" if reason else expires,
            })
    return entries


def parse_os_userlist(lines):
    """
    Parses OperServ USERLIST output.
    Real format (confirmed live):
      "Users list:"
      "Name         Mask                         Realname"
      "claudetest3  claudetest@Clk-2DDF2811      claudetest3 Test"
      "End of users list. 9 users shown."
    Realname is free text (may contain spaces) so it's captured as the remainder.
    """
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ("name", "users") or line.startswith("End of users list"):
            continue
        m = re.match(r'^(\S+)\s+(\S+)\s+(.+)$', line)
        if m:
            entries.append({
                "name":     m.group(1),
                "mask":     m.group(2),
                "realname": m.group(3).strip(),
            })
    return entries


def parse_os_chanlist(lines):
    """
    Parses OperServ CHANLIST output.
    Real format (confirmed live):
      "Channel list:"
      "Name       Users  Modes  Topic"
      "#clitest   2      nPrt   "
      "End of channel list. 3 channels shown."
    Topic may be empty; Modes is a single token (no spaces).
    """
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ("name", "channel") or line.startswith("End of channel list"):
            continue
        m = re.match(r'^(\S+)\s+(\d+)\s+(\S+)(?:\s+(.+))?$', line)
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
    Parses OperServ LOGONNEWS/OPERNEWS/RANDOMNEWS LIST output.
    Real format (confirmed live):
      "Oper news items:"
      "Number  Creator  Created                   Text"
      "1       PeGaSuS  Mon Jul 27 11:47:16 2026  Welcome opers, please read the MOTD."
      "End of news list."
    """
    pattern = re.compile(rf'^(\d+)\s+(\S+)\s+({DATE_RE})\s+(.+)$')
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ("number",) or line.endswith("news items:") or line.startswith("End of news list") \
           or "no logon news" in line.lower() or "no oper news" in line.lower() or "no random news" in line.lower():
            continue
        m = pattern.match(line)
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
    Parses OperServ IGNORE LIST output.
    Real format (confirmed live):
      "Services ignore list:"
      "Mask              Creator  Reason          Expires"
      "*!*@spammer.test  PeGaSuS  testing ignore  expires in 1 hour"
    Reason is free text; Expires is anchored on its known prefixes since both
    trailing columns are free text and can't otherwise be split reliably.
    """
    pattern = re.compile(
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
        m = pattern.match(line)
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
    Parses BotServ BOTLIST output.
    Real format (confirmed live):
      "Bot list:"
      "Nick      Mask                         Real name"
      "TestBot   testbot@bots.ptirc.org       Test Bot"
      "7 bots available."
    Real name is free text (may contain spaces), captured as the remainder.
    """
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('nick', 'bot') or re.match(r'^\d+\s+bots?\s+available', line, re.I):
            continue
        m = re.match(r'^(\S+)\s+(\S+)\s+(.+)$', line)
        if m:
            entries.append({
                "nick":     m.group(1),
                "mask":     m.group(2),
                "realname": m.group(3).strip(),
            })
    return entries


def parse_bs_badwords(lines):
    """
    Parses BotServ BADWORDS LIST output.
    Real format (confirmed live):
      "Bad words list for #clitest:"
      "Number  Word  Type"
      "1       smeg  ANY"
      "2       heck  SINGLE"
      "End of bad words list."
    """
    entries = []
    for line in lines:
        line = strip_irc(line).strip()
        if not line:
            continue
        first_word = line.split()[0].lower()
        if first_word in ('number', 'bad', 'end'):
            continue
        m = re.match(r'^(\d+)\s+(\S+)\s+(\S+)$', line)
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
