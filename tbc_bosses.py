import re
import sys
from typing import List, Set, Optional

# --- TBC CLASSIC BOSS NPC IDs ---
TBC_BOSS_NPC_IDS: Set[int] = {
    # Karazhan
    15550,  # Attumen the Huntsman
    16151,  # Midnight
    15687,  # Moroes
    16457,  # Maiden of Virtue
    17521,  # Opera: Big Bad Wolf
    17533,  # Opera: Romulo
    17534,  # Opera: Julianne
    17540,  # Opera: The Crone
    15691,  # The Curator
    15688,  # Terestian Illhoof
    16524,  # Shade of Aran
    15689,  # Netherspite
    17225,  # Nightbane
    15690,  # Prince Malchezaar
    17229,  # Kil'rek

    # Gruul's Lair
    18831,  # High King Maulgar
    19044,  # Gruul the Dragonkiller

    # Magtheridon's Lair
    17257,  # Magtheridon

    # Serpentshrine Cavern
    21216,  # Hydross the Unstable
    21217,  # The Lurker Below
    21215,  # Leotheras the Blind
    21214,  # Fathom-Lord Karathress
    21213,  # Morogrim Tidewalker
    21212,  # Lady Vashj

    # Tempest Keep: The Eye
    19514,  # Al'ar
    19516,  # Void Reaver
    18805,  # High Astromancer Solarian
    19622,  # Kael'thas Sunstrider
}

# Regex to capture timestamp, event name, and payload
LOG_LINE_REGEX = re.compile(
    r"^(\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+([A-Z_]+),(.*)$"
)

def get_npc_id_from_guid(guid: str) -> Optional[int]:
    """Robustly extracts NPC ID from WoW Creature GUIDs via hyphen splitting."""
    if not guid or not guid.startswith("Creature"):
        return None
    parts = guid.split("-")
    # Format: Creature-Server-Instance-Zone-NPCID-SpawnUID
    if len(parts) >= 6:
        try:
            return int(parts[5])
        except ValueError:
            return None
    return None

def filter_boss_encounters(input_path: str, output_path: str):
    print(f"[*] Reading source log: {input_path}")

    total_lines = 0
    written_lines = 0
    boss_encounters_saved = 0

    current_buffer: List[str] = []
    fight_has_boss = False
    in_combat = False

    with open(input_path, "r", encoding="utf-8", errors="ignore") as infile, \
         open(output_path, "w", encoding="utf-8") as outfile:

        for line in infile:
            total_lines += 1

            # 1. Preserve headers and non-combat map states immediately
            if "COMBAT_LOG_VERSION" in line or "ZONE_CHANGE" in line or "MAP_CHANGE" in line:
                outfile.write(line)
                written_lines += 1
                continue

            match = LOG_LINE_REGEX.match(line)
            if not match:
                # If we are in an active fight buffer, keep miscellaneous lines (like zone text/emotes)
                if in_combat:
                    current_buffer.append(line)
                continue

            timestamp, event, raw_payload = match.groups()
            args = [a.strip('"') for a in raw_payload.split(",")]

            # 2. Check for explicit Blizzard encounter markers
            if event == "ENCOUNTER_START":
                # Flush previous unwritten buffer if needed
                if current_buffer and fight_has_boss:
                    outfile.writelines(current_buffer)
                    written_lines += len(current_buffer)
                    boss_encounters_saved += 1
                current_buffer = [line]
                in_combat = True
                fight_has_boss = True
                continue

            if event == "ENCOUNTER_END":
                current_buffer.append(line)
                if fight_has_boss:
                    outfile.writelines(current_buffer)
                    written_lines += len(current_buffer)
                    boss_encounters_saved += 1
                # Reset state
                current_buffer = []
                in_combat = False
                fight_has_boss = False
                continue

            # 3. Scan event arguments for source (args[0]) or destination (args[2]) Boss GUIDs
            event_has_boss = False
            guids_to_check = []
            if len(args) > 0:
                guids_to_check.append(args[0])
            if len(args) > 2:
                guids_to_check.append(args[2])

            for guid in guids_to_check:
                npc_id = get_npc_id_from_guid(guid)
                if npc_id and npc_id in TBC_BOSS_NPC_IDS:
                    event_has_boss = True
                    fight_has_boss = True
                    break

            # 4. Combat State Management
            is_combat_starter = event in {
                "SWING_DAMAGE", "RANGE_DAMAGE", "SPELL_DAMAGE", 
                "SPELL_CAST_START", "SPELL_CAST_SUCCESS"
            }

            if (is_combat_starter or event_has_boss) and not in_combat:
                # Start of a new engagement block
                in_combat = True
                current_buffer = [line]
                if event_has_boss:
                    fight_has_boss = True
            elif in_combat:
                current_buffer.append(line)
                if event_has_boss:
                    fight_has_boss = True

                # 5. Check for Boss Death (UNIT_DIED) to close out the fight block
                if event == "UNIT_DIED" and len(args) > 2:
                    target_npc = get_npc_id_from_guid(args[2])
                    if target_npc and target_npc in TBC_BOSS_NPC_IDS:
                        if fight_has_boss:
                            outfile.writelines(current_buffer)
                            written_lines += len(current_buffer)
                            boss_encounters_saved += 1
                        # Reset for next trash/boss pack
                        current_buffer = []
                        in_combat = False
                        fight_has_boss = False

        # Flush any remaining buffer at end of file
        if current_buffer and fight_has_boss:
            outfile.writelines(current_buffer)
            written_lines += len(current_buffer)
            boss_encounters_saved += 1

    print(f"\n[+] Processing Complete!")
    print(f"  - Total Lines Read: {total_lines:,}")
    print(f"  - Lines Written (Boss Encounters + Headers): {written_lines:,}")
    print(f"  - Boss Encounters Extracted: {boss_encounters_saved}")
    print(f"  - Cleaned File Saved To: {output_path}")

if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "WoWCombatLog_Cleaned.txt"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "WoWCombatLog_BossesOnly.txt"
    filter_boss_encounters(input_file, output_file)