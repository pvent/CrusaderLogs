import re
from datetime import datetime

INPUT_PATH = "WoWCombatLog.txt"
OUTPUT_PATH = "WoWCombatLog_Cleaned.txt"
INACTIVITY_TIMEOUT_SECONDS = 300
INSTANCE_ID = 0

# ... keep TBC_BOSSES dict exactly as before ...

GUID_RE = re.compile(r'^(Player|Creature|Pet|Vehicle|Object)-[\w-]+$')
HEADER_RE = re.compile(r'^(\d+/\d+ \d{2}:\d{2}:\d{2}\.\d{3})\s+(\S+)')

# Events whose SOURCE/DEST we trust for unit extraction (all combat events share layout)
UNIT_EVENT_PREFIXES = (
    "SWING_", "SPELL_", "RANGE_", "DAMAGE_SHIELD", "DAMAGE_SPLIT",
    "ENVIRONMENTAL_", "PARTY_KILL", "UNIT_DIED", "UNIT_DESTROYED",
    "SPELL_CAST", "SPELL_PERIODIC", "SPELL_AURA", "SPELL_ENERGIZE",
    "SPELL_DRAIN", "HEALTH_", "POWER_",
)


def parse_timestamp(ts_str, year=2026):
    try:
        return datetime.strptime(f"{year} {ts_str}", "%Y %m/%d %H:%M:%S.%f")
    except ValueError:
        return None


def split_payload(rest):
    fields, buf, in_q = [], "", False
    for ch in rest:
        if ch == '"':
            in_q = not in_q
            buf += ch
        elif ch == ',' and not in_q:
            fields.append(buf.strip().strip('"'))
            buf = ""
        else:
            buf += ch
    fields.append(buf.strip().strip('"'))
    return fields


def extract_units(fields):
    """Return [(guid, name)] for source & dest when they are GUID-bearing units."""
    units = []
    for base in (0, 4):
        if len(fields) > base + 1:
            guid, name = fields[base], fields[base + 1]
            if GUID_RE.match(guid):
                units.append((guid, name))
    return units


def process(input_path, output_path):
    with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    print(f"Read {len(lines)} lines")

    out_lines, enc, buf = [], None, []
    last_dt, last_ts = None, None
    alive_players = set()
    stats = {"start": 0, "kill": 0, "wipe": 0, "kept": 0}

    def flush(success, ts_str):
        nonlocal enc, buf, alive_players
        out_lines.extend(buf)
        out_lines.append(
            f'{ts_str}  ENCOUNTER_END,{enc["id"]},"{enc["name"]}",'
            f'{enc["difficulty"]},{enc["group_size"]},{success}\n')
        print(f"  END  : {enc['name']} ({'KILL' if success else 'WIPE'}) @ {ts_str}")
        enc, buf, alive_players = None, [], set()
        stats["kill" if success else "wipe"] += 1

    for raw in lines:
        line = raw.rstrip('\n\r')
        m = HEADER_RE.match(line)
        if not m:
            continue
        ts_str, event = m.group(1), m.group(2)
        t = parse_timestamp(ts_str)

        if event in ("ENCOUNTER_START", "ENCOUNTER_END"):
            stats["kept"] += 1
            out_lines.append(line + '\n')
            continue

        if enc and t and last_dt and (t - last_dt).total_seconds() > INACTIVITY_TIMEOUT_SECONDS:
            flush(0, last_ts)
        if t:
            last_dt, last_ts = t, ts_str

        fc = line.find(',')
        fields = split_payload(line[fc + 1:]) if fc >= 0 else []
        units = extract_units(fields)

        # Track player liveness for wipe detection
        for guid, name in units:
            if guid.startswith("Player-"):
                pid = guid.split("-")[3] if guid.count("-") >= 3 else guid
                if event == "UNIT_DIED":
                    alive_players.discard(pid)
                else:
                    alive_players.add(pid)

        # ---- START: any line naming a registry creature as source or dest ----
        if not enc and event.startswith(UNIT_EVENT_PREFIXES):
            for guid, name in units:
                info = TBC_BOSSES.get(name)
                if info and guid.startswith("Creature-"):
                    eid, cname, diff, gs, _ = info
                    enc = {"id": eid, "name": cname, "difficulty": diff, "group_size": gs}
                    buf = []
                    out_lines.append(
                        f'{ts_str}  ENCOUNTER_START,{eid},"{cname}",{diff},{gs},{INSTANCE_ID}\n')
                    print(f"  START: {cname} ({eid}) @ {ts_str}")
                    stats["start"] += 1
                    break

        if enc:
            buf.append(line + '\n')

            # ---- KILL: primary boss died (BOSS_KILL is authoritative if present) ----
            if event in ("BOSS_KILL", "UNIT_DIED"):
                for guid, name in units:
                    info = TBC_BOSSES.get(name)
                    if info and info[0] == enc["id"] and info[4]:
                        flush(1, ts_str)
                        break

            # ---- WIPE: whole raid dead during the fight ----
            if enc and alive_players and len(alive_players) == 0:
                flush(0, ts_str)

    if enc and buf:
        flush(0, last_ts)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)

    print(f"Injected {stats['start']} starts | {stats['kill']} kills | "
          f"{stats['wipe']} wipes | kept {stats['kept']} existing markers")
    print(f"Wrote {len(out_lines)} lines -> {output_path}")


if __name__ == "__main__":
    process(INPUT_PATH, OUTPUT_PATH)