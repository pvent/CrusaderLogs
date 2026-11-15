import tempfile
import unittest
from pathlib import Path

from clean_tbc_logs import detect_encounters, get_zone_instances, load_definitions, parse_log


class EncounterDefinitionsTests(unittest.TestCase):
    def test_default_definitions_detect_gruul_and_zuljin_across_zone_changes(self):
        combat_log = """\
11/12 13:15:00.000  ZONE_CHANGE,565,"Gruul's Lair",1
11/12 13:15:01.000  SPELL_DAMAGE,Player-1-00000001,"Tank",0x511,0x0,Creature-0-1-0-0-19044-000000000001,"Gruul the Dragonkiller",0x10a48,0x0,1,"Hit",0x1,100,100,0,0,0,0
11/12 13:16:00.000  UNIT_DIED,0000000000000000,nil,0x80000000,0x80000000,Creature-0-1-0-0-19044-000000000001,"Gruul the Dragonkiller",0x10a48,0x0
11/12 13:20:00.000  ZONE_CHANGE,568,"Zul'Aman",1
11/12 13:20:01.000  SPELL_DAMAGE,Player-1-00000001,"Tank",0x511,0x0,Creature-0-1-0-0-23863-000000000002,"Zul'jin",0x10a48,0x0,1,"Hit",0x1,100,100,0,0,0,0
11/12 13:30:00.000  UNIT_DIED,0000000000000000,nil,0x80000000,0x80000000,Creature-0-1-0-0-23863-000000000002,"Zul'jin",0x10a48,0x0
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "tbc.log"
            log_path.write_text(combat_log, encoding="utf-8")
            events, _ = parse_log(log_path, normalize_names=False)

        definitions = load_definitions(None)
        encounters = detect_encounters(
            events, definitions, confirm_window=8.0,
            zone_instances=get_zone_instances(events),
        )

        self.assertEqual(
            [(encounter.encounter_id, encounter.status) for encounter in encounters],
            [(650, "completed"), (1194, "completed")],
        )


class PetOwnerAssignmentTests(unittest.TestCase):
    def test_summoned_pet_events_use_owner_source_identity(self):
        combat_log = """\
11/12 13:15:00.000  SPELL_SUMMON,Player-1-00000001,"Hunter",0x511,0x0,Pet-0-0-0-0-00000001,"Wolf",0xa48,0x0,123,1
11/12 13:15:01.000  SPELL_DAMAGE,Pet-0-0-0-0-00000001,"Wolf",0xa48,0x0,Creature-0-1-0-0-19044-000000000001,"Gruul the Dragonkiller",0x10a48,0x0,1,"Hit",0x1,100,100,0,0,0,0
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "tbc.log"
            log_path.write_text(combat_log, encoding="utf-8")
            events, diagnostics = parse_log(log_path, normalize_names=False)

        pet_attack = events[1]
        self.assertEqual(pet_attack.source_guid, "Player-1-00000001")
        self.assertEqual(pet_attack.source_name, "Hunter")
        self.assertIn("SPELL_DAMAGE,Player-1-00000001,Hunter,", pet_attack.output_line)
        self.assertIn('Creature-0-1-0-0-19044-000000000001,"Gruul the Dragonkiller"', pet_attack.output_line)
        self.assertEqual(diagnostics["pet_event_rewrites"], 1)

    def test_spirit_bond_links_pet_to_hunter_without_summon_event(self):
        combat_log = """\
11/12 13:15:00.000  SPELL_PERIODIC_HEAL,Pet-0-1-0-0-1509702-0000000003,"Udon",0x1114,0x0,Player-1-00004216,"Caryoptera-",0x514,0x0,24529,"Spirit Bond",0x8,0000000000000000,0000000000000000,0,0,0,0,0,-1,0,0,0,0.00,0.00,330,0.0000,0,160,160,0,0,nil
11/12 13:15:01.000  SPELL_DAMAGE,Pet-0-1-0-0-1509702-0000000003,"Udon",0x1114,0x0,Creature-0-1-0-0-19044-000000000001,"Gruul the Dragonkiller",0x10a48,0x0,25012,"Lightning Breath",0x8,0000000000000000,0000000000000000,0,0,0,0,0,-1,0,0,0,0.00,0.00,330,0.0000,0,201,201,-1,8,0,0,0
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "tbc.log"
            log_path.write_text(combat_log, encoding="utf-8")
            events, diagnostics = parse_log(log_path, normalize_names=True)

        pet_attack = events[1]
        self.assertEqual(pet_attack.source_guid, "Player-1-00004216")
        self.assertEqual(pet_attack.source_name, "Caryoptera")
        self.assertIn("SPELL_DAMAGE,Player-1-00004216,Caryoptera,", pet_attack.output_line)
        self.assertEqual(
            diagnostics["pet_owner_mappings"]["Pet-0-1-0-0-1509702-0000000003"],
            {"guid": "Player-1-00004216", "name": "Caryoptera"},
        )


if __name__ == "__main__":
    unittest.main()
