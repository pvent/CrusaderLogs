#!/usr/bin/env python3
"""Reconstruct Warcraft Logs encounter boundaries for custom TBC 2.5.3 logs.

Default output preserves the complete source log. Use --purge to retain only
encounter windows plus the log header/zone/map metadata.

This is an experimental parser for the observed custom-server format. It does
not assume ENCOUNTER_START/ENCOUNTER_END exist in the source log.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

TIMESTAMP_RE = re.compile(r"^(\d{1,2}/\d{1,2} \d{2}:\d{2}:\d{2}\.\d{3})\s{2,}(.*)$")
CREATURE_GUID_RE = re.compile(r"^Creature-[^-]+-[^-]+-[^-]+-[^-]+-(\d+)-")

# Events that can be used as the initial pull candidate. A candidate must be
# followed by hard combat evidence within --confirm-window-seconds.
CANDIDATE_EVENTS = {
    "SPELL_CAST_SUCCESS", "SPELL_DAMAGE", "SPELL_MISSED",
    "SPELL_PERIODIC_DAMAGE", "SPELL_PERIODIC_MISSED",
    "RANGE_DAMAGE", "RANGE_MISSED", "SWING_DAMAGE", "SWING_MISSED",
    "DAMAGE_SHIELD", "DAMAGE_SPLIT", "ENVIRONMENTAL_DAMAGE",
}
HARD_COMBAT_EVENTS = {
    "SPELL_DAMAGE", "SPELL_MISSED", "SPELL_PERIODIC_DAMAGE",
    "SPELL_PERIODIC_MISSED", "RANGE_DAMAGE", "RANGE_MISSED",
    "SWING_DAMAGE", "SWING_MISSED", "DAMAGE_SHIELD", "DAMAGE_SPLIT",
    "ENVIRONMENTAL_DAMAGE",
}

DEFAULT_DEFINITIONS: dict[str, Any] = {
    "schema_version": 1,
    "description": "Initial test definitions for the supplied custom TBC 2.5.3 log.",
    "encounters": [
        {
            "name": "High King Maulgar",
            "encounter_id": 649,
            "instance_id": 565,
            "zone_names": ["Gruul's Lair"],
            "start_targets": [18831, 18832, 18834, 18835, 18836],
            "members": [
                {"npc_id": 18831, "name": "High King Maulgar"},
                {"npc_id": 18832, "name": "Krosh Firehand"},
                {"npc_id": 18834, "name": "Olm the Summoner"},
                {"npc_id": 18835, "name": "Kiggler the Crazed"},
                {"npc_id": 18836, "name": "Blindeye the Seer"},
            ],
            "completion": {"type": "all_members_dead"},
        },
        {
            "name": "Gruul the Dragonkiller",
            "encounter_id": 650,
            "instance_id": 565,
            "zone_names": ["Gruul's Lair"],
            "start_targets": [19044],
            "members": [{"npc_id": 19044, "name": "Gruul the Dragonkiller"}],
            "completion": {"type": "all_members_dead"},
        },
    ],
}


@dataclass
class Event:
    line_number: int
    raw_line: str
    timestamp_text: Optional[str] = None
    timestamp: Optional[datetime] = None
    fields: Optional[list[str]] = None
    event_type: Optional[str] = None
    source_guid: str = ""
    source_name: str = ""
    dest_guid: str = ""
    dest_name: str = ""
    normalized_line: Optional[str] = None
    malformed_reason: Optional[str] = None

    @property
    def output_line(self) -> str:
        return self.normalized_line if self.normalized_line is not None else self.raw_line


@dataclass
class EncounterResult:
    name: str
    encounter_id: int
    instance_id: int
    start_index: int
    start_timestamp: datetime
    start_line_number: int
    end_index: Optional[int]
    end_timestamp: Optional[datetime]
    end_line_number: Optional[int]
    status: str
    completion_rule: str
    required_members: list[str]
    confirmed_deaths: list[dict[str, Any]]
    seen_member_guids: dict[str, list[str]]
    warnings: list[str]

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    @property
    def duration_ms(self) -> Optional[int]:
        if self.end_timestamp is None:
            return None
        return int((self.end_timestamp - self.start_timestamp).total_seconds() * 1000)


def parse_timestamp(text: str, current_day: Optional[datetime]) -> tuple[datetime, datetime]:
    # The log omits year. A stable synthetic year is sufficient for durations.
    parsed = datetime.strptime("2026/" + text, "%Y/%m/%d %H:%M:%S.%f")
    if current_day is not None and parsed < current_day - timedelta(hours=12):
        parsed += timedelta(days=1)
    return parsed, parsed


def parse_csv_payload(payload: str) -> list[str]:
    return next(csv.reader([payload], skipinitialspace=False))


def csv_payload(fields: list[str]) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(fields)
    return stream.getvalue()


def extract_npc_id(guid: str) -> Optional[int]:
    match = CREATURE_GUID_RE.match(guid)
    if match:
        return int(match.group(1))
    # Some client builds may serialize creature GUIDs in a hexadecimal form.
    # This fallback is intentionally not guessed; those GUIDs remain name-matchable.
    return None


def normalize_player_names(fields: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    """Remove the server's observed trailing '-' suffix from Player GUID names."""
    changed: list[dict[str, str]] = []
    result = list(fields)
    # Standard source and destination unit columns in this combat-log format.
    for guid_index, name_index, role in ((1, 2, "source"), (5, 6, "destination")):
        if len(result) <= name_index or len(result) <= guid_index:
            continue
        guid = result[guid_index]
        name = result[name_index]
        if guid.startswith("Player-") and name.endswith("-") and name != "-":
            updated = name[:-1]
            changed.append({"role": role, "guid": guid, "before": name, "after": updated})
            result[name_index] = updated
    return result, changed


def parse_log(path: Path, normalize_names: bool) -> tuple[list[Event], dict[str, Any]]:
    events: list[Event] = []
    diagnostics: dict[str, Any] = {
        "input": str(path), "lines_total": 0, "timestamped_events": 0,
        "malformed_lines": [], "unrecognized_event_types": {},
        "name_changes": [], "zone_changes": [], "headers": [],
    }
    current_day: Optional[datetime] = None
    known_types: set[str] = set()

    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        for line_number, raw in enumerate(handle, 1):
            diagnostics["lines_total"] += 1
            line = raw.rstrip("\r\n")
            match = TIMESTAMP_RE.match(line)
            if not match:
                events.append(Event(line_number=line_number, raw_line=raw))
                if any(token in line for token in ("COMBAT_LOG_VERSION", "ZONE_CHANGE", "MAP_CHANGE")):
                    diagnostics["headers"].append(line)
                continue

            timestamp_text, payload = match.groups()
            try:
                timestamp, current_day = parse_timestamp(timestamp_text, current_day)
                fields = parse_csv_payload(payload)
                if not fields:
                    raise ValueError("empty CSV record")
            except Exception as exc:
                event = Event(line_number, raw, timestamp_text=timestamp_text,
                              malformed_reason=f"CSV/timestamp parse error: {exc}")
                events.append(event)
                diagnostics["malformed_lines"].append({"line": line_number, "reason": event.malformed_reason})
                continue

            event_type = fields[0]
            known_types.add(event_type)
            source_guid = fields[1] if len(fields) > 1 else ""
            source_name = fields[2] if len(fields) > 2 else ""
            dest_guid = fields[5] if len(fields) > 5 else ""
            dest_name = fields[6] if len(fields) > 6 else ""

            normalized_line = None
            if normalize_names:
                normalized_fields, changes = normalize_player_names(fields)
                if changes:
                    # Replace only the two player-name columns in the original
                    # serialized line. This preserves the server's exact CSV
                    # quoting, spacing, field order and all unknown extra fields.
                    normalized_line = raw
                    for change in changes:
                        needle = f'{change["guid"]},{json.dumps(change["before"], ensure_ascii=False)},'
                        replacement = f'{change["guid"]},{json.dumps(change["after"], ensure_ascii=False)},'
                        if needle in normalized_line:
                            normalized_line = normalized_line.replace(needle, replacement, 1)
                        else:
                            # Defensive fallback for an unusual unquoted name.
                            plain_needle = f'{change["guid"]},{change["before"]},'
                            plain_replacement = f'{change["guid"]},{change["after"]},'
                            normalized_line = normalized_line.replace(plain_needle, plain_replacement, 1)
                        change["line"] = line_number
                        diagnostics["name_changes"].append(change)
                    source_name = normalized_fields[2] if len(normalized_fields) > 2 else source_name
                    dest_name = normalized_fields[6] if len(normalized_fields) > 6 else dest_name

            event = Event(
                line_number=line_number, raw_line=raw, timestamp_text=timestamp_text,
                timestamp=timestamp, fields=fields, event_type=event_type,
                source_guid=source_guid, source_name=source_name,
                dest_guid=dest_guid, dest_name=dest_name,
                normalized_line=normalized_line,
            )
            events.append(event)
            diagnostics["timestamped_events"] += 1
            if event_type == "ZONE_CHANGE" and len(fields) > 2:
                try:
                    diagnostics["zone_changes"].append({"line": line_number, "instance_id": int(fields[1]), "zone_name": fields[2]})
                except ValueError:
                    diagnostics["zone_changes"].append({"line": line_number, "instance_id": None, "zone_name": fields[2]})

    # Collapse repetitive per-line name edits into one mapping per player while
    # retaining every affected source line for auditability.
    grouped_changes: dict[tuple[str, str, str], dict[str, Any]] = {}
    for change in diagnostics["name_changes"]:
        key = (change["guid"], change["before"], change["after"])
        item = grouped_changes.setdefault(key, {
            "guid": change["guid"], "before": change["before"], "after": change["after"],
            "occurrence_count": 0, "line_numbers": [], "roles": set(),
        })
        item["occurrence_count"] += 1
        item["line_numbers"].append(change["line"])
        item["roles"].add(change["role"])
    diagnostics["name_changes"] = [
        {**item, "roles": sorted(item["roles"])}
        for item in grouped_changes.values()
    ]
    diagnostics["name_change_occurrences"] = sum(x["occurrence_count"] for x in diagnostics["name_changes"])
    diagnostics["event_types_seen"] = len(known_types)
    return events, diagnostics


def load_definitions(path: Optional[Path]) -> dict[str, Any]:
    if path is None:
        return DEFAULT_DEFINITIONS
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("encounters"), list):
        raise ValueError("Definitions JSON must contain an 'encounters' array")
    return data


def event_member_matches(event: Event, member: dict[str, Any]) -> bool:
    npc_id = member.get("npc_id")
    name = member.get("name")
    source_id = extract_npc_id(event.source_guid)
    dest_id = extract_npc_id(event.dest_guid)
    if npc_id is not None and (source_id == int(npc_id) or dest_id == int(npc_id)):
        return True
    return bool(name and (event.source_name == name or event.dest_name == name))


def event_is_hard_combat(event: Event, member_by_key: list[dict[str, Any]]) -> bool:
    return bool(event.event_type in HARD_COMBAT_EVENTS and any(event_member_matches(event, m) for m in member_by_key))


def find_start(events: list[Event], definition: dict[str, Any], confirm_window: float) -> Optional[int]:
    members = definition["members"]
    start_ids = {int(x) for x in definition.get("start_targets", [])}
    start_names = {m.get("name") for m in members if m.get("npc_id") in start_ids}

    candidates: list[int] = []
    hard_indices: list[int] = []
    for idx, event in enumerate(events):
        if event.timestamp is None or event.event_type is None:
            continue
        source_id = extract_npc_id(event.source_guid)
        dest_id = extract_npc_id(event.dest_guid)
        involves_start = (source_id in start_ids or dest_id in start_ids or
                          event.source_name in start_names or event.dest_name in start_names)
        if not involves_start:
            continue
        if event.event_type in CANDIDATE_EVENTS:
            candidates.append(idx)
        if event_is_hard_combat(event, members):
            hard_indices.append(idx)

    # A pre-pull mark/debuff can mention a boss long before combat. Require a
    # real damage/miss/swing event involving an encounter member soon afterwards.
    for candidate_idx in candidates:
        candidate_time = events[candidate_idx].timestamp
        assert candidate_time is not None
        for hard_idx in hard_indices:
            hard_time = events[hard_idx].timestamp
            if hard_time is None:
                continue
            delta = (hard_time - candidate_time).total_seconds()
            if 0 <= delta <= confirm_window:
                return candidate_idx
    return None


def get_death_member(event: Event, members: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if event.event_type != "UNIT_DIED":
        return None
    # UNIT_DIED uses null source fields followed by the dead unit in destination columns.
    dead_id = extract_npc_id(event.dest_guid)
    for member in members:
        if dead_id is not None and member.get("npc_id") is not None and dead_id == int(member["npc_id"]):
            return member
        if member.get("name") and event.dest_name == member["name"]:
            return member
    return None


def detect_encounters(events: list[Event], definitions: dict[str, Any], confirm_window: float,
                      zone_instance: Optional[int]) -> list[EncounterResult]:
    results: list[EncounterResult] = []
    for definition in definitions["encounters"]:
        instance_id = int(definition["instance_id"])
        if zone_instance is not None and instance_id != zone_instance:
            continue
        start_index = find_start(events, definition, confirm_window)
        if start_index is None:
            continue

        start_event = events[start_index]
        assert start_event.timestamp is not None
        members = definition["members"]
        required_ids = {int(m["npc_id"]) for m in members if m.get("npc_id") is not None}
        deaths_by_id: dict[int, dict[str, Any]] = {}
        seen_guids: dict[str, set[str]] = {str(m.get("npc_id", m.get("name"))): set() for m in members}
        for idx in range(start_index, len(events)):
            event = events[idx]
            for member in members:
                key = str(member.get("npc_id", member.get("name")))
                for guid, name in ((event.source_guid, event.source_name), (event.dest_guid, event.dest_name)):
                    if ((member.get("npc_id") is not None and extract_npc_id(guid) == int(member["npc_id"])) or
                            (member.get("name") and name == member["name"])):
                        if guid and guid != "0000000000000000":
                            seen_guids[key].add(guid)
            dead_member = get_death_member(event, members)
            if dead_member and event.timestamp and event.timestamp >= start_event.timestamp:
                npc_id = int(dead_member["npc_id"]) if dead_member.get("npc_id") is not None else -1
                if npc_id not in deaths_by_id:
                    deaths_by_id[npc_id] = {
                        "npc_id": npc_id, "name": dead_member.get("name"),
                        "guid": event.dest_guid, "timestamp": event.timestamp_text,
                        "line": event.line_number,
                    }

            completion_type = definition.get("completion", {}).get("type", "all_members_dead")
            if completion_type == "all_members_dead" and required_ids and required_ids.issubset(deaths_by_id.keys()):
                # The final required death is the completion timestamp.
                final_death = max(deaths_by_id.values(), key=lambda item: item["line"])
                end_index = next(i for i in range(start_index, idx + 1)
                                 if events[i].line_number == final_death["line"])
                end_event = events[end_index]
                assert end_event.timestamp is not None
                results.append(EncounterResult(
                    name=definition["name"], encounter_id=int(definition["encounter_id"]),
                    instance_id=instance_id, start_index=start_index,
                    start_timestamp=start_event.timestamp, start_line_number=start_event.line_number,
                    end_index=end_index, end_timestamp=end_event.timestamp, end_line_number=end_event.line_number,
                    status="completed", completion_rule=completion_type,
                    required_members=[m.get("name", str(m.get("npc_id"))) for m in members],
                    confirmed_deaths=list(deaths_by_id.values()),
                    seen_member_guids={k: sorted(v) for k, v in seen_guids.items()}, warnings=[]
                ))
                break
        else:
            results.append(EncounterResult(
                name=definition["name"], encounter_id=int(definition["encounter_id"]),
                instance_id=instance_id, start_index=start_index,
                start_timestamp=start_event.timestamp, start_line_number=start_event.line_number,
                end_index=None, end_timestamp=None, end_line_number=None,
                status="incomplete_no_required_death_sequence", completion_rule=definition.get("completion", {}).get("type", "all_members_dead"),
                required_members=[m.get("name", str(m.get("npc_id"))) for m in members],
                confirmed_deaths=list(deaths_by_id.values()),
                seen_member_guids={k: sorted(v) for k, v in seen_guids.items()},
                warnings=["No complete required-member death sequence was found; no successful ENCOUNTER_END was generated."]
            ))
    return sorted(results, key=lambda result: result.start_index)


def get_zone_instance(diagnostics: dict[str, Any]) -> Optional[int]:
    changes = diagnostics.get("zone_changes", [])
    return changes[-1].get("instance_id") if changes else None


def format_synthetic(timestamp_text: str, event_type: str, encounter: EncounterResult,
                     difficulty: int, group_size: int, success: Optional[int] = None) -> str:
    # Preserve the source timestamp spelling (e.g. 11/5 rather than 11/05).
    quoted_name = json.dumps(encounter.name, ensure_ascii=False)
    if event_type == "ENCOUNTER_START":
        payload = f'{event_type},{encounter.encounter_id},{quoted_name},{difficulty},{group_size},{encounter.instance_id}'
    else:
        payload = f'{event_type},{encounter.encounter_id},{quoted_name},{difficulty},{group_size},{success},{encounter.duration_ms}'
    return f"{timestamp_text}  {payload}\n"


def build_output(events: list[Event], encounters: list[EncounterResult], purge: bool,
                 pre_pull: float, post_pull: float, difficulty: int, group_size: int) -> tuple[list[str], dict[str, int]]:
    insert_before: dict[int, list[str]] = {}
    insert_after: dict[int, list[str]] = {}
    for encounter in encounters:
        if encounter.completed:
            assert encounter.end_index is not None and encounter.end_timestamp is not None
            insert_before.setdefault(encounter.start_index, []).append(
                format_synthetic(events[encounter.start_index].timestamp_text or encounter.start_timestamp.strftime("%m/%d %H:%M:%S.%f")[:-3], "ENCOUNTER_START", encounter, difficulty, group_size))
            insert_after.setdefault(encounter.end_index, []).append(
                format_synthetic(events[encounter.end_index].timestamp_text or encounter.end_timestamp.strftime("%m/%d %H:%M:%S.%f")[:-3], "ENCOUNTER_END", encounter, difficulty, group_size, success=1))

    keep_indices: set[int] = set(range(len(events)))
    if purge:
        keep_indices.clear()
        # Keep all non-timestamped file headers and zone/map declarations.
        for idx, event in enumerate(events):
            if event.timestamp is None:
                keep_indices.add(idx)
            elif event.event_type in {"COMBAT_LOG_VERSION", "ZONE_CHANGE", "MAP_CHANGE"}:
                keep_indices.add(idx)
        for encounter in encounters:
            start = encounter.start_timestamp - timedelta(seconds=pre_pull)
            end = (encounter.end_timestamp if encounter.end_timestamp is not None else
                   (events[-1].timestamp if events and events[-1].timestamp else encounter.start_timestamp))
            end = end + timedelta(seconds=post_pull)
            for idx, event in enumerate(events):
                if event.timestamp is not None and start <= event.timestamp <= end:
                    keep_indices.add(idx)

    output: list[str] = []
    retained = 0
    removed = 0
    for idx, event in enumerate(events):
        if idx in insert_before:
            output.extend(insert_before[idx])
        if idx in keep_indices:
            output.append(event.output_line)
            retained += 1
            if idx in insert_after:
                output.extend(insert_after[idx])
        else:
            removed += 1
    return output, {"original_events_retained": retained, "original_events_removed": removed,
                    "synthetic_encounter_starts": sum(len(v) for v in insert_before.values()),
                    "synthetic_encounter_ends": sum(len(v) for v in insert_after.values())}


def serialize_encounter(encounter: EncounterResult, events: list[Event]) -> dict[str, Any]:
    data = asdict(encounter)
    data["start_timestamp"] = encounter.start_timestamp.isoformat(timespec="milliseconds")
    data["end_timestamp"] = encounter.end_timestamp.isoformat(timespec="milliseconds") if encounter.end_timestamp else None
    data["duration_ms"] = encounter.duration_ms
    data["start_event"] = events[encounter.start_index].event_type
    data["start_event_line"] = events[encounter.start_index].output_line.strip()
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconstruct encounter boundaries in custom TBC 2.5.3 combat logs.")
    parser.add_argument("input", type=Path, help="Source combat log")
    parser.add_argument("-o", "--output", type=Path, help="Output log path")
    parser.add_argument("--purge", action="store_true", help="Remove events outside detected encounter windows")
    parser.add_argument("--definitions", type=Path, help="Optional JSON encounter definitions file")
    parser.add_argument("--difficulty", type=int, default=1, help="Difficulty value written to synthetic encounter events (default: 1)")
    parser.add_argument("--group-size", type=int, default=25, help="Group size written to synthetic encounter events (default: 25)")
    parser.add_argument("--confirm-window-seconds", type=float, default=8.0,
                         help="Time allowed between an initial target interaction and confirming combat (default: 8)")
    parser.add_argument("--pre-pull-seconds", type=float, default=5.0, help="Context retained before encounters in purge mode")
    parser.add_argument("--post-pull-seconds", type=float, default=5.0, help="Context retained after encounters in purge mode")
    parser.add_argument("--no-name-normalization", action="store_true",
                         help="Do not remove the observed trailing '-' from Player GUID names")
    parser.add_argument("--write-default-definitions", type=Path,
                         help="Write the built-in Maulgar/Gruul definitions to this JSON file and exit")
    args = parser.parse_args()

    if args.write_default_definitions:
        args.write_default_definitions.write_text(json.dumps(DEFAULT_DEFINITIONS, indent=2), encoding="utf-8")
        print(f"Wrote definitions: {args.write_default_definitions}")
        return 0

    if not args.input.exists():
        parser.error(f"Input file does not exist: {args.input}")
    if args.group_size < 1:
        parser.error("--group-size must be at least 1")

    output_path = args.output or args.input.with_name(
        args.input.stem + ("_purged" if args.purge else "_processed") + args.input.suffix)
    report_path = output_path.with_suffix(output_path.suffix + ".diagnostics.json")

    definitions = load_definitions(args.definitions)
    events, diagnostics = parse_log(args.input, normalize_names=not args.no_name_normalization)
    zone_instance = get_zone_instance(diagnostics)
    encounters = detect_encounters(events, definitions, args.confirm_window_seconds, zone_instance)
    output_lines, output_counts = build_output(
        events, encounters, args.purge, args.pre_pull_seconds, args.post_pull_seconds,
        args.difficulty, args.group_size)

    output_path.write_text("".join(output_lines), encoding="utf-8", newline="")
    diagnostics.update({
        "output": str(output_path), "diagnostics_report": str(report_path),
        "purge_enabled": args.purge, "name_normalization_enabled": not args.no_name_normalization,
        "zone_instance_id_used": zone_instance, "difficulty_written": args.difficulty,
        "group_size_written": args.group_size, "output_counts": output_counts,
        "encounters": [serialize_encounter(encounter, events) for encounter in encounters],
        "encounter_counts": {
            "detected": len(encounters),
            "completed": sum(e.completed for e in encounters),
            "incomplete": sum(not e.completed for e in encounters),
        },
        "notes": [
            "Only completed encounters receive synthetic ENCOUNTER_START/ENCOUNTER_END pairs.",
            "An encounter without all required UNIT_DIED records is reported as incomplete; success is not guessed.",
            "The built-in definitions currently cover High King Maulgar and Gruul only.",
            "Player-name normalization removes one trailing hyphen only for Player- GUID source/destination names.",
        ],
    })
    report_path.write_text(json.dumps(diagnostics, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"Input: {args.input}")
    print(f"Output: {output_path}")
    print(f"Mode: {'PURGE' if args.purge else 'FULL LOG'}")
    print(f"Parsed timestamped events: {diagnostics['timestamped_events']}")
    print(f"Malformed lines: {len(diagnostics['malformed_lines'])}")
    print(f"Player-name mappings: {len(diagnostics['name_changes'])} ({diagnostics['name_change_occurrences']} occurrences)")
    print(f"Encounter candidates: {diagnostics['encounter_counts']['detected']}")
    for encounter in encounters:
        duration = f"{encounter.duration_ms} ms" if encounter.duration_ms is not None else "unknown"
        print(f"  - {encounter.name}: {encounter.status}; start line {encounter.start_line_number}; duration {duration}")
        if encounter.warnings:
            for warning in encounter.warnings:
                print(f"      WARNING: {warning}")
    print(f"Original events retained: {output_counts['original_events_retained']}")
    print(f"Original events removed: {output_counts['original_events_removed']}")
    print(f"Synthetic boundaries: {output_counts['synthetic_encounter_starts']} starts / {output_counts['synthetic_encounter_ends']} ends")
    print(f"Diagnostics: {report_path}")
    if diagnostics["malformed_lines"]:
        print("WARNING: malformed lines were preserved as-is; inspect diagnostics.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
