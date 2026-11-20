import tempfile
import unittest
from pathlib import Path

from clean_tbc_logs import detect_encounters, load_definitions, parse_log


class EncounterDefinitionsTests(unittest.TestCase):
    def test_encounters_ignore_realm_specific_zone_ids(self):
        combat_log = """\
11/12 13:15:00.000  ZONE_CHANGE,532,"Gruul's Lair",1
11/12 13:15:01.000  SPELL_DAMAGE,Player-1-00000001,"Tank",0x511,0x0,Creature-0-1-0-0-19044-000000000001,"Gruul the Dragonkiller",0x10a48,0x0,1,"Hit",0x1,100,100,0,0,0,0
11/12 13:16:00.000  UNIT_DIED,0000000000000000,nil,0x80000000,0x80000000,Creature-0-1-0-0-19044-000000000001,"Gruul the Dragonkiller",0x10a48,0x0
11/12 13:20:00.000  ZONE_CHANGE,530,"Zul'Aman",1
11/12 13:20:01.000  SPELL_DAMAGE,Player-1-00000001,"Tank",0x511,0x0,Creature-0-1-0-0-23863-000000000002,"Zul'jin",0x10a48,0x0,1,"Hit",0x1,100,100,0,0,0,0
11/12 13:30:00.000  UNIT_DIED,0000000000000000,nil,0x80000000,0x80000000,Creature-0-1-0-0-23863-000000000002,"Zul'jin",0x10a48,0x0
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "tbc.log"
            log_path.write_text(combat_log, encoding="utf-8")
            events, _ = parse_log(log_path, normalize_names=False)

        definitions = load_definitions(None)
        encounters = detect_encounters(events, definitions, confirm_window=8.0)

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

    def test_hunter_pet_owner_events_link_hopi_to_wakinyan(self):
        combat_log = """\
11/14 16:06:21.510  SPELL_AURA_APPLIED,Player-1-0000470A,"Hopi-",0x512,0x0,Pet-0-1-0-0-1638196-0000000004,"Wakinyan",0x1112,0x0,19574,"Bestial Wrath",0x1,BUFF
11/14 16:06:21.638  SPELL_ENERGIZE,Player-1-0000470A,"Hopi-",0x512,0x0,Pet-0-1-0-0-1638196-0000000004,"Wakinyan",0x1112,0x0,34953,"Go for the Throat",0x1,0000000000000000,0000000000000000,0,0,0,0,0,-1,0,0,0,0.00,0.00,333,0.0000,0,50.0000,0.0000,2,0
11/14 16:06:21.700  SPELL_AURA_APPLIED,Player-1-0000470A,"Hopi-",0x512,0x0,Pet-0-1-0-0-1638196-0000000004,"Wakinyan",0x1112,0x0,27046,"Mend Pet",0x8,BUFF
11/14 16:06:21.752  SPELL_DAMAGE,Pet-0-1-0-0-1638196-0000000004,"Wakinyan",0x1112,0x0,Creature-0-1-0-0-23574-000056ABAA,"Akil'zon",0x10a48,0x0,25012,"Lightning Breath",0x8,0000000000000000,0000000000000000,0,0,0,0,0,-1,0,0,0,0.00,0.00,333,0.0000,0,212,212,-1,8,0,0,0,nil,nil,nil
11/14 16:06:21.800  SPELL_DAMAGE,Pet-0-1-0-0-1638196-000000000B,"Unknown",0x1112,0x0,Creature-0-1-0-0-23574-000056ABAA,"Akil'zon",0x10a48,0x0,25012,"Lightning Breath",0x8,0000000000000000,0000000000000000,0,0,0,0,0,-1,0,0,0,0.00,0.00,333,0.0000,0,212,212,-1,8,0,0,0,nil,nil,nil
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "tbc.log"
            log_path.write_text(combat_log, encoding="utf-8")
            events, diagnostics = parse_log(log_path, normalize_names=True)

        pet_attack = events[3]
        self.assertEqual(pet_attack.source_guid, "Player-1-0000470A")
        self.assertEqual(pet_attack.source_name, "Hopi")
        self.assertIn("SPELL_DAMAGE,Player-1-0000470A,Hopi,", pet_attack.output_line)
        self.assertEqual(
            diagnostics["pet_owner_mappings"]["Pet-0-1-0-0-1638196-0000000004"],
            {"guid": "Player-1-0000470A", "name": "Hopi"},
        )
        self.assertEqual(events[4].source_guid, "Player-1-0000470A")

    def test_shadowfiend_and_sacrificed_demon_link_back_to_owners(self):
        combat_log = """\
11/14 16:07:25.010  SWING_DAMAGE,Pet-0-1-0-0-1720348-0000000005,"Shadowfiend",0x1111,0x0,Creature-0-1-0-0-23574-000056ABAA,"Akil'zon",0x10a48,0x0,0000000000000000,0000000000000000,0,0,0,0,0,-1,0,0,0,0.00,0.00,333,0.0000,0,116,116,-1,32,0,0,0,nil,1,nil
11/14 16:07:26.628  SPELL_ENERGIZE,Pet-0-1-0-0-1720348-0000000005,"Shadowfiend",0x1111,0x0,Player-1-000041CE,"Pfent-",0x511,0x0,34650,"Mana Leech",0x20,0000000000000000,0000000000000000,0,0,0,0,0,-1,0,0,0,0.00,0.00,333,0.0000,0,290.0000,0.0000,0,0
11/14 16:07:30.000  SPELL_DAMAGE,Pet-0-1-0-0-1555654-0000000002,"Heswena",0x1114,0x0,Creature-0-1-0-0-18836-0000895712,"Blindeye the Seer",0xa48,0x80,35298,"Gore",0x1,0000000000000000,0000000000000000,0,0,0,0,0,-1,0,0,0,0.00,0.00,330,0.0000,0,74,74,-1,1,0,0,0,1,nil
11/14 16:07:31.000  SPELL_INSTAKILL,Pet-0-1-0-0-1555654-0000000002,"Heswena",0x1114,0x0,Player-1-000044DF,"Creeshu-",0x514,0x0,18788,"Demonic Sacrifice",0x20
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "tbc.log"
            log_path.write_text(combat_log, encoding="utf-8")
            events, diagnostics = parse_log(log_path, normalize_names=True)

        self.assertEqual(events[0].source_name, "Pfent")
        self.assertIn("SWING_DAMAGE,Player-1-000041CE,Pfent,", events[0].output_line)
        self.assertEqual(events[2].source_name, "Creeshu")
        self.assertIn("SPELL_DAMAGE,Player-1-000044DF,Creeshu,", events[2].output_line)
        self.assertEqual(
            diagnostics["pet_owner_mappings"]["Pet-0-1-0-0-1720348-0000000005"],
            {"guid": "Player-1-000041CE", "name": "Pfent"},
        )
        self.assertEqual(
            diagnostics["pet_owner_mappings"]["Pet-0-1-0-0-1555654-0000000002"],
            {"guid": "Player-1-000044DF", "name": "Creeshu"},
        )

    def test_conflicting_owner_evidence_does_not_guess_for_sibling_pet_guid(self):
        combat_log = """\
11/14 16:06:21.510  SPELL_AURA_APPLIED,Player-1-0000470A,"Hopi",0x512,0x0,Pet-0-1-0-0-1638196-0000000004,"Wakinyan",0x1112,0x0,19574,"Bestial Wrath",0x1,BUFF
11/14 16:06:22.510  SPELL_AURA_APPLIED,Player-1-000041CE,"Pfent",0x511,0x0,Pet-0-1-0-0-1638196-0000000006,"Wakinyan",0x1112,0x0,19574,"Bestial Wrath",0x1,BUFF
11/14 16:06:23.510  SPELL_DAMAGE,Pet-0-1-0-0-1638196-000000000B,"Wakinyan",0x1112,0x0,Creature-0-1-0-0-23574-000056ABAA,"Akil'zon",0x10a48,0x0,25012,"Lightning Breath",0x8,0000000000000000,0000000000000000,0,0,0,0,0,-1,0,0,0,0.00,0.00,333,0.0000,0,212,212,-1,8,0,0,0,nil,nil,nil
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "tbc.log"
            log_path.write_text(combat_log, encoding="utf-8")
            events, diagnostics = parse_log(log_path, normalize_names=False)

        self.assertEqual(events[2].source_guid, "Pet-0-1-0-0-1638196-000000000B")
        self.assertEqual(diagnostics["unmapped_pet_guids"], [
            {"guid": "Pet-0-1-0-0-1638196-000000000B", "names": ["Wakinyan"]},
        ])


if __name__ == "__main__":
    unittest.main()
