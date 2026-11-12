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


if __name__ == "__main__":
    unittest.main()
