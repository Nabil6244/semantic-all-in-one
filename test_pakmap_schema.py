"""pakMap CSV reading: every problem names its row."""

import unittest

from pakmap.schema import CsvError, parse_csv

HEAD = "item_no,vo_anchor,layer_type,layer_id,geo_ref,label_text,value_to,value_format,params\n"


def read(body, head=HEAD):
    return parse_csv(None, text=head + body)


class TestParse(unittest.TestCase):
    def test_a_normal_row(self):
        rows, warns = read('1,kenya has,stat,pop,,KENYA,"47,000","#,##0","{""per_million"": 150}"\n')
        r = rows[0]
        self.assertEqual((r.line, r.item_no, r.layer_type, r.layer_id, r.value_to, r.value_format), (2, 1, "stat", "pop", 47000.0, "#,##0", ))
        self.assertEqual(r.params, {"per_million": 150})
        self.assertEqual(warns, [])

    def test_headers_are_forgiving_and_aliases_work(self):
        rows, _ = parse_csv(None, text="﻿Item No, Layer Type ,Geo-Ref\n1,title,\n2,zone,Kenya\n")
        self.assertEqual([r.layer_type for r in rows], ["hud_title", "zone_label"])
        self.assertEqual(rows[1].geo_ref, "Kenya")

    def test_unknown_column_is_a_warning_with_a_hint(self):
        _, warns = parse_csv(None, text="item_no,layer_type,vo_ancor\n1,caption,x\n")
        self.assertTrue(any("vo_ancor" in w and "vo_anchor" in w for w in warns))

    def test_blank_lines_are_skipped_but_row_numbers_stay_true(self):
        rows, _ = read("1,a,caption,,,X,,,\n\n1,b,caption,,,Y,,,\n")
        self.assertEqual([r.line for r in rows], [2, 4])

    def test_every_problem_is_reported_with_its_row(self):
        with self.assertRaises(CsvError) as cm:
            read("1,a,capton,,,X,,,\n1,b,stat,,,Y,abc,,\n1,c,caption,,,Z,,,{broken\n1,d,marker,m,,M,,,\n")
        p = " | ".join(cm.exception.problems)
        self.assertIn("row 2: unknown layer_type 'capton' (did you mean 'caption'?)", p)
        self.assertIn("row 3: value_to is not valid ('abc')", p)
        self.assertIn("row 4: params is not valid", p)

    def test_out_rows_lat_lon_pairs_and_actions(self):
        with self.assertRaises(CsvError) as cm:
            parse_csv(None, text="item_no,layer_type,layer_action,lat,camera_action,frame\n1,stat,out,5,,\n1,camera,in,,teleport,\n1,camera,in,,fly_to,planet\n")
        p = " | ".join(cm.exception.problems)
        self.assertIn("row 2: an 'out' row needs the layer_id", p)
        self.assertIn("row 2: give both lat and lon", p)
        self.assertIn("row 3: camera_action must be one of", p)
        self.assertIn("row 4: frame must be one of", p)

    def test_a_comma_inside_an_unquoted_cell_is_explained(self):
        with self.assertRaises(CsvError) as cm:
            parse_csv(None, text="item_no,layer_type,value_format\n1,stat,UP TO #,##0 MM\n")
        self.assertIn("must be wrapped in double quotes", cm.exception.problems[0])
        self.assertIn("row 2", cm.exception.problems[0])

    def test_empty_inputs(self):
        with self.assertRaisesRegex(CsvError, "empty"):
            parse_csv(None, text="")
        with self.assertRaisesRegex(CsvError, "no rows"):
            parse_csv(None, text="item_no,layer_type\n")
        with self.assertRaisesRegex(CsvError, "layer_type column"):
            parse_csv(None, text="item_no,label_text\n1,x\n")


if __name__ == "__main__":
    unittest.main()
