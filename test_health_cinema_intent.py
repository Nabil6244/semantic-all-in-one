"""Visual intent (Health Cinema CSV): the organ is not the visual subject. visual_subject / visual_intent / biological_process / visual_action choose the
3D scene before the organ; rows merge only while the same subject and process continue; a camera move never stands for a different process; and the CSV
is checked once when it is read. Old CSVs (no new columns) load and plan as before."""
import unittest

from health_cinema import direction, planner, scenes_csv as C

HEAD = "text,visual,organ,visual_subject,visual_intent,biological_process,shot,visual_action,footage\n"


def plan_of(csv_text, each=12.0):
    rows = C.parse_csv_text(csv_text); t = 0.0
    for r in rows: r["start"], r["end"] = t, t + each; t += each
    return planner.plan_directed(rows, "medical_cinema", direction.dscenes_from_rows(rows), lambda t: True, allow_footage=True)["scenes"]


class Columns(unittest.TestCase):
    def test_new_columns_load_as_plain_words_and_a_described_shot_is_kept(self):
        r = C.parse_csv_text(HEAD + "Plaque narrows it.,3d,heart,coronary_artery_plaque,show_narrowing,atherosclerosis,internal_cross_section,plaque_grows,artery\n")[0]
        self.assertEqual((r["visual_subject"], r["biological_process"], r["shot_desc"]), ("coronary artery plaque", "atherosclerosis", "internal cross section"))
        self.assertNotIn("shot", r)

    def test_an_old_csv_loads_unchanged(self):
        r = C.parse_csv_text("text,visual,organ,shot\nYour heart beats.,3d,heart,zoom\n")[0]
        self.assertEqual((r["organ"], r["shot"]), ("heart", "zoom")); self.assertNotIn("visual_subject", r)


class SubjectDecides(unittest.TestCase):
    def test_the_visual_subject_chooses_the_scene_not_the_organ(self):
        sc = plan_of(HEAD + "It starts quietly.,3d,heart,platelets,show_platelets_gathering,platelet_activation,molecular_closeup,platelets_aggregate,platelets\n")
        self.assertEqual(sc[0].visual["template"], "micro:clot:orbit"); self.assertEqual(sc[0].visual["subject"], "platelets")

    def test_the_same_subject_and_process_continuing_is_one_shot(self):
        row = "{t},3d,heart,coronary_artery_plaque,show_narrowing,atherosclerosis,,plaque_grows,artery\n"
        sc = plan_of(HEAD + row.format(t="It builds slowly.") + row.format(t="Year after year."), each=6.0)      # one shot up to 16 s
        self.assertEqual(len([s for s in sc if s.kind == "anatomy_3d"]), 1)

    def test_a_different_process_never_reuses_a_scene_with_only_another_camera(self):
        sc = plan_of(HEAD + "It builds slowly.,3d,heart,coronary_artery_plaque,show_narrowing,atherosclerosis,,plaque_grows,artery plaque animation\n"
                     + "Life goes on.,footage,,,,,,,people walking city\n"
                     + "Then the cap tears.,3d,heart,plaque_rupture,show_cap_breaking,plaque_rupture,,cap_tears,plaque rupture animation\n")
        kinds = [(s.kind, s.visual.get("template")) for s in sc]
        self.assertEqual(kinds[0], ("anatomy_3d", "micro:plaque:orbit")); self.assertEqual(kinds[2][0], "footage")
        self.assertTrue(any("camera move alone" in w for w in sc[2].decisions))


class CheckedOnRead(unittest.TestCase):
    def test_generic_organ_runs_missing_intent_and_shared_subjects_are_reported(self):
        txt = (HEAD + "A.,3d,heart,,,,,,x\nB.,3d,heart,,,,,,x\nC.,3d,heart,,,,,,x\n"
               + "D.,3d,heart,plaque,,,,,x\n"
               + "E.,3d,heart,artery,show,atherosclerosis,,grows,x\nF.,3d,heart,artery,show,rupture,,tears,x\n")
        notes = []; C.parse_csv_text(txt, notes); text = " ".join(notes)
        self.assertIn("rows 2-4: 3 3D rows in a row name only the organ (heart)", text)
        self.assertIn("row 5: visual_subject 'plaque' has no visual_intent or visual_action", text)
        self.assertIn("visual_subject 'artery' is used for different processes", text)

    def test_a_good_csv_has_no_notes(self):
        notes = []; C.parse_csv_text(HEAD + "Plaque narrows it.,3d,heart,coronary_artery_plaque,show_narrowing,atherosclerosis,,plaque_grows,artery\n", notes)
        self.assertEqual(notes, [])


if __name__ == "__main__":
    unittest.main()
