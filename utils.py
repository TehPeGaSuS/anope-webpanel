import re


def parse_alist(lines):
    """
    Format: "N: #channel = Level (Description)" or "N: #channel = Level"
    """
    pattern = re.compile(r'^\d+:\s+(!?#\S+)\s+=\s+(\S+)(?:\s+\((.+)\))?$')
    channels = []
    for line in lines:
        m = pattern.match(line)
        if m:
            raw_channel = m.group(1)
            noexpire = raw_channel.startswith("!")
            channels.append({
                "channel":  raw_channel.lstrip("!"),
                "noexpire": noexpire,
                "level":    m.group(2),
                "desc":     m.group(3) or "",
            })
    return channels


def parse_flags_list(lines):
    """
    Format: "N: mask = FLAGS -- added by X at DATE (comment)"
    """
    pattern = re.compile(
        r'^\d+:\s+(\S+)\s+=\s+(\S+)\s+--\s+added by\s+(\S+)\s+at\s+(.+?)(?:\s+\((.+)\))?$'
    )
    entries = []
    for line in lines:
        line = line.replace('\x1b', '').strip()
        m = pattern.match(line)
        if m:
            entries.append({
                "mask":    m.group(1),
                "flags":   m.group(2),
                "addedby": m.group(3),
                "addedat": m.group(4).strip(),
                "comment": m.group(5) or "",
            })
    return entries


def parse_akick_view(lines):
    """
    Format: "N: mask -- added by X on DATE; last used: DATE (reason)"
    Uses AKICK VIEW for full detail including creator and last used.
    """
    pattern = re.compile(
        r'^\d+:\s+(\S+)\s+--\s+added by\s+(\S+)\s+on\s+(.+?);\s+last used:\s+(.+?)(?:\s+\((.+)\))?$'
    )
    entries = []
    for line in lines:
        m = pattern.match(line.strip())
        if m:
            entries.append({
                "mask":     m.group(1),
                "addedby":  m.group(2),
                "addedat":  m.group(3).strip(),
                "lastused": m.group(4).strip(),
                "reason":   m.group(5) or "",
            })
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
    Format: header line, then one fingerprint per line.
    """
    certs = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("Certificate list") or line.startswith("End"):
            continue
        if re.match(r'^[0-9a-fA-F]{16,}$', line):
            certs.append(line)
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
    Format: "N: message" or empty list message.
    """
    pattern = re.compile(r'^\d+:\s+(.+)$')
    entries = []
    for line in lines:
        m = pattern.match(line.strip())
        if m:
            entries.append({"num": len(entries) + 1, "text": m.group(1)})
    return entries


def parse_log_list(lines):
    """
    Format: "N: command on service: method"
    e.g. "1: chanserv/flags on ChanServ: MESSAGE @"
    """
    pattern = re.compile(r'^\d+:\s+(\S+)\s+on\s+(\S+):\s+(\S+)(?:\s+(\S+))?')
    entries = []
    for line in lines:
        line = line.strip().replace('\x1b', '')
        m = pattern.match(line)
        if m:
            entries.append({
                "command": m.group(1),
                "service": m.group(2),
                "method":  m.group(3),
                "status":  m.group(4) or "",
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
        for key in ("letters", "words", "lines", "smileys", "actions"):
            m2 = re.search(rf'{key}:\s*(\d+)', line)
            if m2:
                result[key] = int(m2.group(1))
    return result


def parse_cs_list(lines):
    """
    Format: "#channel (Description)" or "#channel"
    First line is header, last is summary.
    """
    pattern = re.compile(r'^(!?#\S+)(?:\s+\((.+)\))?$')
    channels = []
    for line in lines:
        line = line.strip()
        m = pattern.match(line)
        if m:
            channels.append({
                "channel": m.group(1).lstrip("!"),
                "noexpire": m.group(1).startswith("!"),
                "desc": m.group(2) or "",
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
