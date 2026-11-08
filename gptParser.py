#!/usr/bin/env python3
"""
TBC 2.5.3 Combat Log Cleaner

- Detects TBC raid boss encounters.
- Groups multi-boss encounters correctly.
- Generates ENCOUNTER_START and ENCOUNTER_END records.
- Removes trash combat and unrelated events.
- Removes trailing hyphens from Player GUID names.
- Preserves original combat events during boss encounters.
- Handles wipes, boss deaths and encounter inactivity.
- Processes large logs efficiently.
"""

import argparse
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# ============================================================
# CONFIGURATION
# ============================================================

DIFFICULTY_ID = 1
DEFAULT_IDLE_SECONDS = 45.0
MIN_FIGHT_SECONDS = 1.0


@dataclass(frozen=True)
class Boss:
    encounter_id: int
    instance_id: int
    canonical_name: str
    group_size: int = 25
    terminal: bool = True


BOSSES: dict[str, Boss] = {}


def add(
    names: tuple[str, ...],
    encounter_id: int,
    instance_id: int,
    canonical: str,
    group_size: int = 25,
    terminal_names: Optional[set[str]] = None,
) -> None:

    terminal_names = terminal_names or {canonical}

    for name in names:
        BOSSES[name] = Boss(
            encounter_id,
            instance_id,
            canonical,
            group_size,
            name in terminal_names,
        )


# ============================================================
# KARAZHAN - INSTANCE 34
# ============================================================

add(
    ("Attumen the Huntsman", "Midnight"),
    652, 34, "Attumen the Huntsman",
    10, {"Attumen the Huntsman"}
)

add(("Moroes",), 653, 34, "Moroes", 10)

add(("Maiden of Virtue",), 654, 34, "Maiden of Virtue", 10)

add(
    (
        "Barnes",
        "The Big Bad Wolf",
        "Little Red Riding Hood",
        "Julianne",
        "Romulo",
        "Romulo and Julianne",
        "Dorothee",
        "Tito",
        "Roar",
        "Strawman",
        "Tinhead",
        "The Crone",
        "Wizard of Oz",
    ),
    655, 34, "Opera Event", 10,
    {"The Big Bad Wolf", "Romulo and Julianne", "The Crone"}
)

add(("The Curator",), 656, 34, "The Curator", 10)

add(("Terestian Illhoof",), 657, 34, "Terestian Illhoof", 10)

add(("Shade of Aran",), 658, 34, "Shade of Aran", 10)

add(("Netherspite",), 659, 34, "Netherspite", 10)

add(("Prince Malchezaar",), 660, 34, "Prince Malchezaar", 10)

add(("Nightbane",), 661, 34, "Nightbane", 10)


# ============================================================
# GRUUL'S LAIR - INSTANCE 565
# ============================================================

add(
    (
        "High King Maulgar",
        "Olm the Summoner",
        "Kiggler the Crazed",
        "Blindeye the Seer",
        "Krosh Firehand",
    ),
    649, 565, "High King Maulgar", 25,
    {"High King Maulgar"}
)

add(
    ("Gruul the Dragonkiller",),
    650, 565, "Gruul the Dragonkiller"
)


# ============================================================
# MAGTHERIDON'S LAIR - INSTANCE 532
# ============================================================

add(
    ("Magtheridon", "Hellfire Channeler"),
    651, 532, "Magtheridon", 25,
    {"Magtheridon"}
)


# ============================================================
# SERPENTSHRINE CAVERN - INSTANCE 548
# ============================================================

add(("Hydross the Unstable",), 624, 548, "Hydross the Unstable")

add(("The Lurker Below",), 625, 548, "The Lurker Below")

add(("Leotheras the Blind",), 626, 548, "Leotheras the Blind")

add(
    (
        "Fathom-Lord Karathress",
        "Fathom-Guard Tidalvess",
        "Fathom-Guard Sharkkis",
        "Fathom-Guard Caribdis",
    ),
    627, 548, "Fathom-Lord Karathress", 25,
    {"Fathom-Lord Karathress"}
)

add(("Morogrim Tidewalker",), 628, 548, "Morogrim Tidewalker")

add(("Lady Vashj",), 629, 548, "Lady Vashj")


# ============================================================
# TEMPEST KEEP: THE EYE - INSTANCE 550
# ============================================================

add(("Al'ar",), 725, 550, "Al'ar")

add(("Void Reaver",), 726, 550, "Void Reaver")

add(
    ("High Astromancer Solarian",),
    727, 550, "High Astromancer Solarian"
)

add(
    (
        "Kael'thas Sunstrider",
        "Thaladred the Darkener",
        "Lord Sanguinar",
        "Grand Astromancer Capernian",
        "Master Engineer Telonicus",
    ),
    728, 550, "Kael'thas Sunstrider", 25,
    {"Kael'thas Sunstrider"}
)


# ============================================================
# BATTLE FOR MOUNT HYJAL - INSTANCE 534
# ============================================================

add(("Rage Winterchill",), 618, 534, "Rage Winterchill")

add(("Anetheron",), 619, 534, "Anetheron")

add(("Kaz'rogal",), 620, 534, "Kaz'rogal")

add(("Azgalor",), 621, 534, "Azgalor")

add(("Archimonde",), 622, 534, "Archimonde")


# ============================================================
# BLACK TEMPLE - INSTANCE 564
# ============================================================

add(
    ("High Warlord Naj'entus",),
    601, 564, "High Warlord Naj'entus"
)

add(("Supremus",), 602, 564, "Supremus")

add(("Shade of Akama",), 603, 564, "Shade of Akama")

add(("Teron Gorefiend",), 604, 564, "Teron Gorefiend")

add(("Gurtogg Bloodboil",), 605, 564, "Gurtogg Bloodboil")

add(("Reliquary of Souls",), 606, 564, "Reliquary of Souls")

add(("Mother Shahraz",), 607, 564, "Mother Shahraz")

add(
    (
        "The Illidari Council",
        "Gathios the Shatterer",
        "High Nethermancer Zerevor",
        "Lady Malande",
        "Veras Darkshadow",
    ),
    608, 564, "The Illidari Council", 25,
    {"The Illidari Council"}
)

add(("Illidan Stormrage",), 609, 564, "Illidan Stormrage")


# ============================================================
# ZUL'AMAN - INSTANCE 568
# ============================================================

add(("Nalorakk",), 1189, 568, "Nalorakk", 10)

add(("Akil'zon",), 1190, 568, "Akil'zon", 10)

add(("Jan'alai",), 1191, 568, "Jan'alai", 10)

add(("Halazzi",), 1192, 568, "Halazzi", 10)

add(("Hex Lord Malacrass",), 1193, 568, "Hex Lord Malacrass", 10)

add(("Zul'jin",), 1194, 568, "Zul'jin", 10)


# ============================================================
# REGULAR EXPRESSIONS
# ============================================================

TIMESTAMP_RE = re.compile(
    r"^(?P<stamp>\d{1,2}/\d{1,2} \d{2}:\d{2}:\d{2}\.\d{3})\s{2,}"
)

PLAYER_NAME_RE = re.compile(
    r'(Player-[^,]+,"[^"]+?)-"'
)

QUOTED_NAME_RE = re.compile(
    r'"([^"]+)"'
)

EVENT_RE = re.compile(
    r"\s{2,}([A-Z][A-Z0-9_]+),"
)

HEADER_EVENTS = {
    "COMBAT_LOG_VERSION",
    "ZONE_CHANGE",
    "MAP_CHANGE",
}


# ============================================================
# PLAYER NAME CLEANUP
# ============================================================

def clean_player_names(line: str) -> str:
    """
    Convert:
        Player-1-00002CA0,"Opilka-"

    Into:
        Player-1-00002CA0,"Opilka"
    """

    return PLAYER_NAME_RE.sub(r'\1"', line)


# ============================================================
# TIMESTAMP HANDLING
# ============================================================

def infer_year(first_stamp: str) -> int:

    now = datetime.now()

    parsed = datetime.strptime(
        first_stamp,
        "%m/%d %H:%M:%S.%f"
    )

    candidate = parsed.replace(year=now.year)

    if candidate - now > timedelta(days=180):
        candidate = candidate.replace(year=now.year - 1)

    elif now - candidate > timedelta(days=180):
        candidate = candidate.replace(year=now.year + 1)

    return candidate.year


def timestamp_value(stamp: str, year: int) -> float:

    return datetime.strptime(
        f"{year}/{stamp}",
        "%Y/%m/%d %H:%M:%S.%f"
    ).timestamp()


# ============================================================
# EVENT PARSING
# ============================================================

def event_and_names(line: str):

    event_match = EVENT_RE.search(line)

    event = (
        event_match.group(1)
        if event_match
        else None
    )

    names = set(
        QUOTED_NAME_RE.findall(line)
    )

    return event, names


# ============================================================
# ENCOUNTER STATE
# ============================================================

@dataclass
class Encounter:

    boss: Boss

    start_ts: float

    start_stamp: str

    lines: list[str]

    last_boss_ts: float

    last_boss_stamp: str

    terminal_seen: bool = False


def make_encounter_line(stamp: str, event: str) -> str:

    return f"{stamp}  {event}\n"


# ============================================================
# MAIN PROCESSING
# ============================================================

def process(
    input_path: Path,
    output_path: Path,
    idle_seconds: float = DEFAULT_IDLE_SECONDS,
):

    with input_path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace"
    ) as src:

        first_stamp = None

        for line in src:

            match = TIMESTAMP_RE.match(line)

            if match:

                first_stamp = match.group("stamp")
                break

        if first_stamp is None:

            raise ValueError(
                "Input contains no recognizable combat-log timestamps."
            )

        year = infer_year(first_stamp)

        src.seek(0)

        with output_path.open(
            "w",
            encoding="utf-8",
            newline=""
        ) as dst:

            header = []

            current = None

            encounter_count = 0

            boss_mentions = set()

            # ------------------------------------------------
            # WRITE ENCOUNTER
            # ------------------------------------------------

            def write_encounter(
                enc: Encounter,
                end_stamp: str,
                end_ts: float,
            ):

                nonlocal encounter_count

                duration_ms = max(
                    0,
                    int((end_ts - enc.start_ts) * 1000)
                )

                if duration_ms < int(MIN_FIGHT_SECONDS * 1000):
                    return

                boss = enc.boss

                dst.write(
                    make_encounter_line(
                        enc.start_stamp,
                        (
                            f'ENCOUNTER_START,'
                            f'{boss.encounter_id},'
                            f'"{boss.canonical_name}",'
                            f'{DIFFICULTY_ID},'
                            f'{boss.group_size},'
                            f'{boss.instance_id}'
                        )
                    )
                )

                dst.writelines(enc.lines)

                dst.write(
                    make_encounter_line(
                        end_stamp,
                        (
                            f'ENCOUNTER_END,'
                            f'{boss.encounter_id},'
                            f'"{boss.canonical_name}",'
                            f'{DIFFICULTY_ID},'
                            f'{boss.group_size},'
                            f'1,{duration_ms}'
                        )
                    )
                )

                encounter_count += 1

            # ------------------------------------------------
            # PROCESS INPUT
            # ------------------------------------------------

            for raw_line in src:

                line = clean_player_names(raw_line)

                stamp_match = TIMESTAMP_RE.match(line)

                if not stamp_match:

                    if current is None and not encounter_count:
                        header.append(line)

                    continue

                stamp = stamp_match.group("stamp")

                ts = timestamp_value(stamp, year)

                event, names = event_and_names(line)

                # --------------------------------------------
                # METADATA
                # --------------------------------------------

                if event in HEADER_EVENTS:

                    if current is not None:

                        write_encounter(
                            current,
                            current.last_boss_stamp,
                            current.last_boss_ts
                        )

                        current = None

                    header.append(line)

                    continue

                # --------------------------------------------
                # BOSS DETECTION
                # --------------------------------------------

                matched = [
                    (name, BOSSES[name])
                    for name in names
                    if name in BOSSES
                ]

                # --------------------------------------------
                # ENCOUNTER TIMEOUT
                # --------------------------------------------

                if (
                    current is not None
                    and ts - current.last_boss_ts > idle_seconds
                ):

                    write_encounter(
                        current,
                        current.last_boss_stamp,
                        current.last_boss_ts
                    )

                    current = None

                # --------------------------------------------
                # IDENTIFY BOSS
                # --------------------------------------------

                if matched:

                    selected_name, selected_boss = matched[0]

                    # Prefer the main boss over encounter adds.
                    for name, boss in matched:

                        if boss.terminal:

                            selected_name = name
                            selected_boss = boss

                            break

                    boss_mentions.add(selected_name)

                    # ----------------------------------------
                    # START NEW ENCOUNTER
                    # ----------------------------------------

                    if current is None:

                        current = Encounter(
                            selected_boss,
                            ts,
                            stamp,
                            [],
                            ts,
                            stamp,
                        )

                    # ----------------------------------------
                    # DIFFERENT ENCOUNTER
                    # ----------------------------------------

                    elif (
                        selected_boss.encounter_id
                        != current.boss.encounter_id

                        or selected_boss.instance_id
                        != current.boss.instance_id
                    ):

                        write_encounter(
                            current,
                            current.last_boss_stamp,
                            current.last_boss_ts
                        )

                        current = Encounter(
                            selected_boss,
                            ts,
                            stamp,
                            [],
                            ts,
                            stamp,
                        )

                    else:

                        current.last_boss_ts = ts

                        current.last_boss_stamp = stamp

                        if selected_boss.terminal:

                            current.terminal_seen = True

                # --------------------------------------------
                # PRESERVE ALL EVENTS DURING ENCOUNTER
                # --------------------------------------------

                if current is not None:

                    current.lines.append(line)

                    # ----------------------------------------
                    # BOSS DEATH
                    # ----------------------------------------

                    if event == "UNIT_DIED":

                        dead_terminal = any(
                            name in names
                            and BOSSES[name].terminal
                            and BOSSES[name].encounter_id
                            == current.boss.encounter_id

                            for name in names

                            if name in BOSSES
                        )

                        if dead_terminal:

                            current.terminal_seen = True

                            # Single-boss encounters can close
                            # immediately after the boss dies.
                            #
                            # Multi-boss encounters must remain
                            # open because surviving encounter
                            # members may still be active.

                            member_count = sum(
                                1
                                for boss in BOSSES.values()
                                if (
                                    boss.encounter_id
                                    == current.boss.encounter_id
                                    and boss.instance_id
                                    == current.boss.instance_id
                                )
                            )

                            if member_count == 1:

                                write_encounter(
                                    current,
                                    stamp,
                                    ts
                                )

                                current = None

            # ------------------------------------------------
            # CLOSE FINAL ENCOUNTER
            # ------------------------------------------------

            if current is not None and current.lines:

                write_encounter(
                    current,
                    current.last_boss_stamp,
                    current.last_boss_ts
                )

    # ========================================================
    # PREPEND METADATA
    # ========================================================

    if header:

        temp_path = output_path.with_suffix(
            output_path.suffix + ".tmp"
        )

        seen = set()

        with temp_path.open(
            "w",
            encoding="utf-8",
            newline=""
        ) as out:

            for item in header:

                key = item.strip()

                if key and key not in seen:

                    out.write(
                        item if item.endswith("\n")
                        else item + "\n"
                    )

                    seen.add(key)

            with output_path.open(
                "r",
                encoding="utf-8",
                errors="replace"
            ) as cleaned:

                for item in cleaned:

                    out.write(item)

        temp_path.replace(output_path)

    # ========================================================
    # DIAGNOSTICS
    # ========================================================

    print(f"Cleaned log: {output_path}")

    print(
        f"Boss encounters written: {encounter_count}"
    )

    if boss_mentions:

        print(
            "Bosses detected: "
            + ", ".join(sorted(boss_mentions))
        )


# ============================================================
# ENTRY POINT
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "TBC 2.5.3 WoW combat log boss encounter cleaner."
        )
    )

    parser.add_argument(
        "input",
        nargs="?",
        default="WoWCombatLog.txt"
    )

    parser.add_argument(
        "output",
        nargs="?",
        default="WoWCombatLog_GPTed.txt"
    )

    parser.add_argument(
        "--idle-seconds",
        type=float,
        default=DEFAULT_IDLE_SECONDS,
        help="Seconds without boss activity before closing an encounter."
    )

    args = parser.parse_args()

    input_path = Path(args.input)

    output_path = Path(args.output)

    if not input_path.is_file():

        parser.error(
            f"Input file not found: {input_path}"
        )

    if input_path.resolve() == output_path.resolve():

        parser.error(
            "Input and output paths must be different."
        )

    process(
        input_path,
        output_path,
        args.idle_seconds
    )


if __name__ == "__main__":

    main()