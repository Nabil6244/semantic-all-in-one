"""StarMap's row repairs (starmap/heal.py) for the two stops the stress test (starmap/stress.py) found."""
import unittest

from starmap.heal import HealedCsv

HEAD = "beat,row,vo_anchor,mode,type,id,place,frame,date,label,sub,text,value_from,value_to,format,anchor,until,hold,asset,dur,why,extra"


class Heal(unittest.TestCase):
    def test_a_semicolon_csv_is_read_as_the_same_table(self):
        text = HEAD.replace(",", ";") + "\nplan;plan;;;;;;;2026-10-16;TITLE;;;;;;;;;;;;\nb1;beat;In November;map;;;sun;heliosphere;;;;;;;;;;;;;;\n"
        h = HealedCsv(text)
        self.assertEqual(h.rows[0][:2], ["beat", "row"])
        self.assertEqual(h.text().splitlines()[0], HEAD)
        self.assertTrue(any("semicolons" in n for n in h.notes))

    def test_a_plan_row_that_stays_broken_is_repaired_step_by_step_then_left_out(self):
        text = HEAD + "\nplan,plan,,,,x,,,2026-10-16,TITLE,,,,,,,,,,,,x\nb1,beat,In November,map,,,sun,heliosphere,,,,,,,,,,,,,,\n"
        h = HealedCsv(text)
        problem = ["row 2: Expecting value: line 1 column 1 (char 0)"]
        self.assertTrue(h.fix(problem))
        self.assertEqual((h._cell(2, "id"), h._cell(2, "date")), ("", ""))
        self.assertTrue(h.fix(problem))
        self.assertEqual(h._cell(2, "extra"), "")
        self.assertTrue(h.fix(problem))
        self.assertFalse(any(c.strip() for c in h.rows[1]))
        self.assertFalse(h.fix(problem))            # nothing left to repair on that row: the caller stops looping


if __name__ == "__main__":
    unittest.main()
