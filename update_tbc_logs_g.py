#!/usr/bin/env python3
"""
update_tbc_logs_g.py — Optimized and tightened TBC combat log cleaner.
Fixes over-triggering, eliminates false positives, and prevents empty/duplicate encounters.
"""

import re
import sys
from datetime import datetime

BOSS_IDS = {
    # --- KARAZHAN (Instance ID: 34) ---
    "Attumen the Huntsman": 652,
    "Midnight": 652,           
    "Moroes": 653,
    "Maiden of Virtue": 654,
    "Barnes": 655,             
    "The Big Bad Wolf": 655,
    "Little Red Riding Hood": 655,
    "Julianne": 655,
    "Romulo": 655,
    "Romulo and Julianne": 655,
    "Dorothee": 655,
    "Tito": 655,
    "Roar": 655,
    "Strawman": 655,
    "Tinhead": 655,
    "The Crone": 655,
    "Wizard of Oz": 655,
    "The Curator": 656,
    "Terestian Illhoof": 657,
    "Shade of Aran": 658,
    "Netherspite": 659,
    "Prince Malchezaar": 660,
    "Nightbane": 661,

    # --- GRUUL'S LAIR (Instance ID: 565) ---
    "High King Maulgar": 649,
    "Olm the Summoner": 649,
    "Kiggler the Crazed": 649,
    "Blindeye the Seer": 649,
    "Krosh Firehand": 649,
    "Gruul the Dragonkiller": 650,

    # --- MAGTHERIDON'S LAIR (Instance ID: 532) ---
    "Magtheridon": 651,
    "Hellfire Channeler": 651,

    # --- SERPENTSHRINE CAVERN (Instance ID: 548) ---
    "Hydross the Unstable": 624,
    "The Lurker Below": 625,
    "Leotheras the Blind": 626,
    "Fathom-Lord Karathress": 627,
    "Fathom-Guard Tidalvess": 627,
    "Fathom-Guard Sharkkis": 627,
    "Fathom-Guard Caribdis": 627,
    "Morogrim Tidewalker": 628,
    "Lady Vashj": 629,

    # --- TEMPEST KEEP: THE EYE (Instance ID: 550) ---
    "Al'ar": 725,
    "Void Reaver": 726,
    "High Astromancer Solarian": 727,
    "Kael'thas Sunstrider": 728,
    "Thaladred the Darkener": 728,
    "Lord Sanguinar": 728,
    "Grand Astromancer Capernian": 728,
    "Master Engineer Telonicus": 728,
}

CANONICAL_BOSS_NAMES = {
    "Midnight": "Attumen the Huntsman",
    "Barnes": "Opera Event",
    "The Big Bad Wolf": "Opera Event",
    "Little Red Riding Hood": "Opera Event",
    "Julianne": "Opera Event",
    "Romulo": "Opera Event",
    "Romulo and Julianne": "Opera Event",
    "Dorothee": "Opera Event",
    "Tito": "Opera Event",
    "Roar": "Opera Event",
    "Strawman": "Opera Event",
    "Tinhead": "Opera Event",
    "The Crone": "Opera Event",
    "Wizard of Oz": "Opera Event",
    "Shade of Aran": "Shade of Aran",
    "Olm the Summoner": "High King Maulgar",
    "Kiggler the Crazed": "High King Maulgar",
    "Blindeye the Seer": "High King Maulgar",
    "Krosh Firehand": "High King Maulgar",
    "Fathom-Guard Tidalvess": "Fathom-Lord Karathress",
    "Fathom-Guard Sharkkis": "Fathom-Lord Karathress",
    "Fathom-Guard Caribdis": "Fathom-Lord Karathress",
    "Thaladred the Darkener": "Kael'thas Sunstrider",
    "Lord Sanguinar": "Kael'thas Sunstrider",
    "Grand Astromancer Capernian": "Kael'thas Sunstrider",
    "Master Engineer Telonicus": "Kael'thas Sunstrider",
}

INSTANCE_MAP = {
    652: 34, 653: 34, 654: 34, 655: 34, 656: 34, 657: 34, 658: 34, 659: 34, 660: 34, 661: 34,
    649: 565, 650: 565,
    651: 532,
    624: 548, 625: 548, 626: 548, 627: 548, 628: 548, 629: 548,
    725: 550, 726: 550, 727: 550, 728: 550
}

DIFFICULTY_ID = 1
GROUP_SIZE = 25
MIN_FIGHT_SECONDS = 5.0  # Discard any detected "fights" shorter than 5 seconds to prevent empty/stray triggers

TIMESTAMP_RE = re.compile(r"^(\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s{2,}")

def parse_ts(ts: str) -> float:
    dt = datetime.strptime(f"2026/{ts}", "%Y/%m/%d %H:%M:%S.%f")
    return dt.timestamp()

def get_boss_in_line(line: str) -> tuple[str, int] | None:
    if any(ignore in line for ignore in ["ENCOUNTER_START", "ENCOUNTER_END", "COMBAT_LOG_VERSION"]):
        return None

    # Must be a core combat action line to qualify
    if not any(evt in line for evt in ["SPELL_", "SWING_", "RANGE_", "UNIT_DIED", "ENVIRONMENTAL"]):
        return None

    for name, enc_id in BOSS_IDS.items():
        # Check strictly for quoted entity names to prevent substring false positives
        if f'"{name}"' in line:
            canonical_name = CANONICAL_BOSS_NAMES.get(name, name)
            return canonical_name, enc_id
    return None

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <input.txt> [output.txt]")
        sys.exit(1)

    infile = sys.argv[1]
    outfile = sys.argv[2] if len(sys.argv) > 2 else infile.replace(".txt", "_cleaned.txt")

    with open(infile, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    global_header_lines = []
    boss_encounters = []
    completed_boss_sessions = set() # Track unique session start timestamps to prevent duplicates

    current_enc_id = None
    current_boss_name = None
    current_fight_lines = []
    boss_start_ts = None
    
    found_boss_mentions = set()

    for line in lines:
        stripped = line.rstrip("\n")
        m = TIMESTAMP_RE.match(stripped)
        
        if not m:
            if not current_enc_id and not boss_encounters:
                global_header_lines.append(line)
            continue

        ts = m.group(1)
        ts_val = parse_ts(ts)
        boss_info = get_boss_in_line(stripped)

        if boss_info:
            boss, enc_id = boss_info
            found_boss_mentions.add(boss)

            if current_enc_id is None:
                current_enc_id = enc_id
                current_boss_name = boss
                boss_start_ts = ts_val
                current_fight_lines = [line]
            elif enc_id != current_enc_id:
                # Close previous encounter before opening a new one
                if current_enc_id is not None:
                    duration = ts_val - boss_start_ts
                    if duration >= MIN_FIGHT_SECONDS:
                        boss_encounters.append((current_boss_name, current_enc_id, boss_start_ts, current_fight_lines))
                
                current_enc_id = enc_id
                current_boss_name = boss
                boss_start_ts = ts_val
                current_fight_lines = [line]
            else:
                current_fight_lines.append(line)

            # Check for explicit wipe/kill conclusion via UNIT_DIED or standard reset cues
            if "UNIT_DIED" in stripped and current_enc_id is not None:
                if current_boss_name in stripped or any(sub in stripped for sub in ["Gruul the Dragonkiller", "High King Maulgar"]):
                    duration = ts_val - boss_start_ts
                    if duration >= MIN_FIGHT_SECONDS:
                        boss_encounters.append((current_boss_name, current_enc_id, boss_start_ts, current_fight_lines))
                    current_enc_id = None
                    current_boss_name = None
                    current_fight_lines = []
                    boss_start_ts = None
        else:
            if current_enc_id is not None:
                current_fight_lines.append(line)
                
                # Safety timeout check: if an active encounter goes quiet/stale for more than 15 minutes, close it automatically
                if (ts_val - boss_start_ts) > 900:
                    duration = ts_val - boss_start_ts
                    if duration >= MIN_FIGHT_SECONDS:
                        boss_encounters.append((current_boss_name, current_enc_id, boss_start_ts, current_fight_lines))
                    current_enc_id = None
                    current_boss_name = None
                    current_fight_lines = []
                    boss_start_ts = None

    # Catch any unfinished active encounter at EOF
    if current_enc_id is not None and current_fight_lines:
        duration = parse_ts(TIMESTAMP_RE.match(current_fight_lines[-1]).group(1)) - boss_start_ts
        if duration >= MIN_FIGHT_SECONDS:
            boss_encounters.append((current_boss_name, current_enc_id, boss_start_ts, current_fight_lines))

    print(f"Diagnostics - Validated boss mentions found: {list(found_boss_mentions)}")

    final_output = list(global_header_lines)
    injected_count = 0

    for boss_name, enc_id, start_ts, fight_lines in boss_encounters:
        if not fight_lines:
            continue

        m_start = TIMESTAMP_RE.match(fight_lines[0].rstrip("\n"))
        m_end = TIMESTAMP_RE.match(fight_lines[-1].rstrip("\n"))
        
        if not m_start or not m_end:
            continue

        start_ts_val = parse_ts(m_start.group(1))
        end_ts_val = parse_ts(m_end.group(1))
        fight_ms = int((end_ts_val - start_ts_val) * 1000)
        if fight_ms < 5000: # Skip anything under 5 seconds absolute duration
            continue

        instance_id = INSTANCE_MAP.get(enc_id, 565)
        group_sz = 10 if instance_id == 34 else GROUP_SIZE

        final_output.append(f'{m_start.group(1)}  ENCOUNTER_START,{enc_id},"{boss_name}",{DIFFICULTY_ID},{group_sz},{instance_id}\n')
        final_output.extend(fight_lines)
        final_output.append(f'{m_end.group(1)}  ENCOUNTER_END,{enc_id},"{boss_name}",{DIFFICULTY_ID},{group_sz},1,{fight_ms}\n')
        injected_count += 1

    with open(outfile, "w", encoding="utf-8") as f:
        f.writelines(final_output)

    print(f"Done → {outfile}")
    print(f"  Clean Boss Encounters Saved: {injected_count}")

if __name__ == "__main__":
    main()