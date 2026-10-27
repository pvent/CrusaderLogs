#!/usr/bin/env python3
"""
fix_combatlog.py — Inject missing ENCOUNTER_START/END lines into TBC combat logs.
Detection is 100% name-based: it looks for quoted boss names in log lines.

Usage: python fix_combatlog.py WoWCombatLog.txt [output.txt]
"""

import re
import sys
from datetime import datetime

# ─── BOSS NAMES → WCL ENCOUNTER IDS (TBC Anniversary) ────────────────────────
# Detection is by NAME. The ID is only used in the injected ENCOUNTER_START/END
# so WCL can categorize the fight correctly.
BOSS_IDS = {
    "Attumen the Huntsman": 652,
    "Midnight": 652,           # Part of Attumen fight
    "Moroes": 653,
    "Maiden of Virtue": 654,
    "Barnes": 655,             # Opera trigger
    "Little Red Riding Hood": 655,
    "Romulo and Julianne": 655,
    "Wizard of Oz": 655,
    "The Big Bad Wolf": 655,
    "The Curator": 656,
    "Terestian Illhoof": 657,
    "Shade of Aran": 658,
    "Netherspite": 659,
    "Prince Malchezaar": 660,
    "Nightbane": 661,
}

DIFFICULTY_ID = 1
GROUP_SIZE = 10
INSTANCE_ID = 34  # Karazhan

# ──────────────────────────────────────────────────────────────────────────────

TIMESTAMP_RE = re.compile(r"^(\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s{2,}")

def parse_ts(ts: str) -> float:
    dt = datetime.strptime(f"2026/{ts}", "%Y/%m/%d %H:%M:%S.%f")
    return dt.timestamp()

def find_boss(line: str) -> str | None:
    """Return the first known boss name found in this log line."""
    for name in BOSS_IDS:
        if f'"{name}"' in line:
            return name
    return None

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <input.txt> [output.txt]")
        sys.exit(1)

    infile = sys.argv[1]
    outfile = sys.argv[2] if len(sys.argv) > 2 else infile.replace(".txt", ".fixed.txt")

    with open(infile, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    output = []
    current_enc_id = None
    current_boss_name = None
    boss_start_ts = None
    last_activity_ts = None
    encounters = 0

    for line in lines:
        stripped = line.rstrip("\n")
        m = TIMESTAMP_RE.match(stripped)
        if not m:
            output.append(line)
            continue

        ts = m.group(1)
        ts_val = parse_ts(ts)

        boss = find_boss(stripped)

        if boss:
            enc_id = BOSS_IDS[boss]

            if current_enc_id is None:
                # New encounter
                output.append(f'{ts}  ENCOUNTER_START,{enc_id},"{boss}",{DIFFICULTY_ID},{GROUP_SIZE},{INSTANCE_ID}\n')
                current_enc_id = enc_id
                current_boss_name = boss
                boss_start_ts = ts_val
                last_activity_ts = ts_val
                encounters += 1

            elif enc_id != current_enc_id:
                # Boss changed — close old, open new
                fight_ms = int((ts_val - boss_start_ts) * 1000)
                output.append(f'{ts}  ENCOUNTER_END,{current_enc_id},"{current_boss_name}",{DIFFICULTY_ID},{GROUP_SIZE},1,{fight_ms}\n')
                output.append(f'{ts}  ENCOUNTER_START,{enc_id},"{boss}",{DIFFICULTY_ID},{GROUP_SIZE},{INSTANCE_ID}\n')
                current_enc_id = enc_id
                current_boss_name = boss
                boss_start_ts = ts_val
                last_activity_ts = ts_val
                encounters += 1
            else:
                last_activity_ts = ts_val

            output.append(line)

            # Check for boss death → close encounter
            if "UNIT_DIED" in stripped:
                # Format: UNIT_DIED,GUID,"BossName",flags,flags
                # Split the event part (after timestamp) by comma
                event_part = stripped.split(None, 2)  # [ts, "", "UNIT_DIED,GUID,..."]
                if len(event_part) >= 3:
                    fields = event_part[2].split(",")
                    # fields[0]=UNIT_DIED, fields[1]=GUID, fields[2]="Name"
                    if len(fields) >= 3 and fields[2] == f'"{boss}"':
                        fight_ms = int((ts_val - boss_start_ts) * 1000)
                        output.append(f'{ts}  ENCOUNTER_END,{enc_id},"{boss}",{DIFFICULTY_ID},{GROUP_SIZE},1,{fight_ms}\n')
                        current_enc_id = None
                        current_boss_name = None
                        boss_start_ts = None
                        last_activity_ts = None   

        else:
            output.append(line)
            # Timeout: 30s of no boss activity → close as wipe
            if current_enc_id is not None and last_activity_ts is not None:
                if ts_val - last_activity_ts > 30:
                    fight_ms = int((ts_val - boss_start_ts) * 1000)
                    output.append(f'{ts}  ENCOUNTER_END,{current_enc_id},"{current_boss_name}",{DIFFICULTY_ID},{GROUP_SIZE},0,{fight_ms}\n')
                    current_enc_id = None
                    current_boss_name = None
                    boss_start_ts = None
                    last_activity_ts = None

    # Close any open encounter at end of file
    if current_enc_id is not None:
        last_m = TIMESTAMP_RE.match(lines[-1])
        if last_m:
            end_val = parse_ts(last_m.group(1))
            fight_ms = int((end_val - boss_start_ts) * 1000)
            output.append(f'{last_m.group(1)}  ENCOUNTER_END,{current_enc_id},"{current_boss_name}",{DIFFICULTY_ID},{GROUP_SIZE},0,{fight_ms}\n')

    with open(outfile, "w", encoding="utf-8") as f:
        f.writelines(output)

    print(f"Done → {outfile}")
    print(f"  Encounters injected: {encounters}")

if __name__ == "__main__":
    main()   