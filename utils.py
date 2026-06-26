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
