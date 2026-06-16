"""History normalization and persistence helpers for lshell."""

import readline


def normalize_history_line(line):
    """Normalize a history line without changing quoted whitespace."""
    line = line.strip()
    if not line:
        return ""

    normalized = []
    quote = None
    escape = False
    pending_space = False

    for char in line:
        if escape:
            if pending_space:
                normalized.append(" ")
                pending_space = False
            normalized.append(char)
            escape = False
            continue

        if quote is None and char.isspace():
            pending_space = bool(normalized)
            continue

        if pending_space:
            normalized.append(" ")
            pending_space = False

        normalized.append(char)

        if char == "\\" and quote != "'":
            escape = True
            continue

        if char in ("'", '"'):
            if quote is None:
                quote = char
            elif quote == char:
                quote = None

    return "".join(normalized).rstrip()


def current_history_entries():
    """Return the current readline history as a list of strings."""
    entries = []
    for index in range(1, readline.get_current_history_length() + 1):
        entry = readline.get_history_item(index)
        if entry:
            entries.append(entry)
    return entries


def _replace_history(entries):
    """Replace readline history with the provided entries."""
    readline.clear_history()
    for entry in entries:
        readline.add_history(entry)


def prepare_latest_history_entry(raw_line):
    """Apply session-safe history policies to the latest readline item."""
    history_length = readline.get_current_history_length()
    if history_length <= 0:
        return

    normalized = normalize_history_line(raw_line)
    latest_index = history_length - 1
    latest_entry = readline.get_history_item(history_length)
    if latest_entry is None:
        return

    if not normalized:
        readline.remove_history_item(latest_index)
        return

    if latest_entry != normalized:
        readline.replace_history_item(latest_index, normalized)

    if history_length > 1 and readline.get_history_item(history_length - 1) == normalized:
        readline.remove_history_item(latest_index)


def entries_for_persisted_history(entries):
    """Return normalized history entries with older duplicates removed."""
    deduplicated = []
    seen = set()
    for entry in reversed(entries):
        normalized = normalize_history_line(entry)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduplicated.append(normalized)
    deduplicated.reverse()
    return deduplicated


def prepare_history_for_write():
    """Rewrite readline history using persisted-history policies."""
    _replace_history(entries_for_persisted_history(current_history_entries()))
