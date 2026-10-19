# UI control inventory (static)

Generated from the code (AST), not from a running app. `handler?` = the named handler is not defined in the scanned files (may live in another module; check before calling it broken). `none` = the control has no command at build time (may be configured later or be display-only).

Totals: Button 69, CheckBox 9, OptionMenu 16, SegmentedButton 9, Switch 24, key 6, menu 11; all 144

| ID | file:line | kind | label | handler | built in | flag |
|---|---|---|---|---|---|---|
| FI-0001 | app.py:1521 | Button | Switch | _open_project_picker | _build_topbar |  |
| FI-0002 | app.py:1556 | Button |  | _toggle_issues | _build_topbar |  |
| FI-0003 | app.py:1564 | Button | Close instances | _close_flow_instances | _build_topbar |  |
| FI-0004 | app.py:1571 | Button | ⚙ | _open_settings | _build_topbar |  |
| FI-0005 | app.py:1619 | SegmentedButton |  | _on_production_mode | _build_left_sections |  |
| FI-0006 | app.py:1638 | SegmentedButton |  |  | _build_left_sections | none |
| FI-0007 | app.py:1745 | Button | Export CSV | _export_ai_csv | _build_left_sections |  |
| FI-0008 | app.py:1870 | Button | Copy | _on_copy_vo_plan | _build_left_sections |  |
| FI-0009 | app.py:1877 | Button | Export JSON | _on_export_vo_plan | _build_left_sections |  |
| FI-0010 | app.py:1965 | Button | ▶  Play | _toggle_voice_playback | _build_left_sections |  |
| FI-0011 | app.py:2019 | Button | Optional + | _toggle_optional_section | _build_left_sections |  |
| FI-0012 | app.py:2064 | Button | Cancel | _on_cancel | _build_left_sections |  |
| FI-0013 | app.py:2132 | SegmentedButton |  | _on_overscaled_style_change | _build_overscaled_section |  |
| FI-0014 | app.py:2141 | Switch |  | _on_overscaled_toggle | _build_overscaled_section |  |
| FI-0015 | app.py:2980 | Button |  | _on_primary_cta | _build_style_picker |  |
| FI-0016 | app.py:3240 | Switch | Use pakMap for this generation | _on_pakmap_toggle | _build_pakmap_section |  |
| FI-0017 | app.py:3269 | Switch | pakMap sound design (effects + ambience) | _on_pakmap_sound_changed | _build_pakmap_section |  |
| FI-0018 | app.py:3274 | Switch | Add graphics from the narration (shares, sizes, counts) | _on_pakmap_auto_gfx_changed | _build_pakmap_section |  |
| FI-0019 | app.py:3426 | Switch | Use Hybrid Map for this project | _on_hybrid_toggle | _build_hybrid_section |  |
| FI-0020 | app.py:3577 | Button | Stop | _hybrid_stop_work | _hybrid_build_progress |  |
| FI-0021 | app.py:4197 | key | <Return> | apply | _hybrid_open_cell_editor |  |
| FI-0022 | app.py:4992 | Switch | Use StarMap for this project | _on_starmap_toggle | _build_starmap_section |  |
| FI-0023 | app.py:6163 | Button | Go to error | _go_to_error | _build_scenes_workspace |  |
| FI-0024 | app.py:6227 | Button | Cleanup | _on_cleanup_downloaded_assets | _build_scenes_workspace |  |
| FI-0025 | app.py:6231 | Button | Activity ▸ | _toggle_activity_log | _build_scenes_workspace |  |
| FI-0026 | app.py:6413 | Button | ▶  Open | _open_in_player | _build_scenes_workspace |  |
| FI-0027 | app.py:6429 | Button | Open Folder | _open_output_folder | _build_scenes_workspace |  |
| FI-0028 | app.py:6625 | menu | Clear plan… | _clear_visual_plan | _open_workspace_overflow |  |
| FI-0029 | app.py:6631 | menu |  | _on_cleanup_downloaded_assets | _open_workspace_overflow |  |
| FI-0030 | app.py:6637 | menu |  | _toggle_activity_log | _open_workspace_overflow |  |
| FI-0031 | app.py:6638 | menu | Rate finished videos… | _open_rating_history | _open_workspace_overflow |  |
| FI-0032 | app.py:6639 | menu | CSV Generator… | _open_csv_generator | _open_workspace_overflow |  |
| FI-0033 | app.py:6640 | menu | Learning… | _open_learning | _open_workspace_overflow |  |
| FI-0034 | app.py:10493 | CheckBox |  | _on_header_select_all | _build_scene_list_header |  |
| FI-0035 | app.py:10582 | CheckBox |  | _on_scene_check | _decorate_scene_row |  |
| FI-0036 | app.py:10668 | Button | Open | _open_scene_asset | _decorate_scene_row |  |
| FI-0037 | app.py:10677 | Button | Src | _change_source_dialog | _decorate_scene_row |  |
| FI-0038 | app.py:11570 | key | <Return> | ok | _ask_map_place |  |
| FI-0039 | app.py:13246 | Switch | Accept Ultra HD (4K) footage | _toggle_uhd | _open_settings |  |
| FI-0040 | app.py:13263 | Switch | Export in 4K | _toggle_export | _open_settings |  |
| FI-0041 | app.py:2050 | Button | Choose project | _on_primary_cta | _build_left_sections |  |
| FI-0042 | app.py:12085 | menu | All issues ({…}) | _select_scenes_by_source_bucket | _open_select_by_source_menu |  |
| FI-0043 | app.py:12099 | menu | Queued ({…}) | _select_scenes_by_source_bucket | _open_select_by_source_menu |  |
| FI-0044 | app.py:12101 | menu | With error ({…}) | _select_scenes_by_source_bucket | _open_select_by_source_menu |  |
| FI-0045 | app.py:12108 | menu | {…} ({…}) | _select_scenes_by_source_bucket | _open_select_by_source_menu |  |
| FI-0046 | app.py:12285 | Button | Scene {…} {…} — {…} | _focus_scene | _rebuild_issues |  |
| FI-0047 | app.py:12575 | menu |  | _details_action | _show_scene_context_menu |  |
| FI-0048 | app.py:12925 | Button |  | _set_theme | _open_settings |  |
| FI-0049 | app.py:2173 | Switch | Local Visual Planner (experimental) — the CSV only needs sce | _on_overscaled_local_planner_toggle | _build_overscaled_section |  |
| FI-0050 | app.py:3451 | Switch | Add graphics from the narration (shares, sizes, counts) | _on_hybrid_auto_gfx_changed | _build_hybrid_section |  |
| FI-0051 | app.py:3483 | Switch | Sound effects + ambience | _save_hybrid_settings | _build_hybrid_section |  |
| FI-0052 | app.py:4032 | Button |  | IfExp | _hybrid_chip | handler? |
| FI-0053 | app.py:4122 | OptionMenu |  | set | _hybrid_open_cell_editor |  |
| FI-0054 | app.py:5028 | Switch | Sound effects + ambience | _save_starmap_settings | _build_starmap_section |  |
| FI-0055 | app.py:5050 | Switch | Use Cinema for this project | _save_starmap_cinema | _build_starmap_cinema_tab |  |
| FI-0056 | app.py:9151 | Button | Cancel | cancel | _on_paste_claude_csv |  |
| FI-0057 | app.py:9157 | Button | Import CSV | apply_paste | _on_paste_claude_csv |  |
| FI-0058 | app.py:13096 | CheckBox | Show keys | toggle_show_keys | _open_settings |  |
| FI-0059 | app.py:13110 | CheckBox | Use Gemini |  | _open_settings | none |
| FI-0060 | app.py:13111 | CheckBox | Use Groq |  | _open_settings | none |
| FI-0061 | app.py:13200 | OptionMenu |  |  | _open_settings | none |
| FI-0062 | app.py:13208 | Switch | Captions |  | _open_settings | none |
| FI-0063 | app.py:13213 | SegmentedButton |  |  | _open_settings | none |
| FI-0064 | app.py:13474 | Switch | Fast Flow images (agent mode) | _toggle_agent | _open_settings |  |
| FI-0065 | app.py:4012 | Button |  | _hybrid_toggle_warnings | _hybrid_refresh_chips |  |
| FI-0066 | app.py:4015 | Button | Fix with AI | _hybrid_repair_errors | _hybrid_refresh_chips |  |
| FI-0067 | app.py:4037 | Button | Fix | _hybrid_open_cell_editor | _hybrid_chip |  |
| FI-0068 | app.py:5058 | CheckBox |  | _save_starmap_cinema | _build_starmap_cinema_tab |  |
| FI-0069 | app.py:12969 | Button | Sign out | do_sign_out | _open_settings |  |
| FI-0070 | app.py:13432 | OptionMenu |  | on_choice | _open_settings |  |
| FI-0071 | app.py:15505 | Button | Retry | destroy | _show_error_dialog |  |
| FI-0072 | app.py:15510 | Button | Dismiss | destroy | _show_error_dialog |  |
| FI-0073 | app.py:4143 | Button |  | set | _hybrid_open_cell_editor |  |
| FI-0074 | app.py:12305 | Button | Retry | _on_qa_decision | _rebuild_issues |  |
| FI-0075 | app.py:12311 | Button | Keep | _on_qa_decision | _rebuild_issues |  |
| FI-0076 | app.py:13564 | Button | Remove | connect_and | _open_settings |  |
| FI-0077 | app.py:13571 | Button | Sign in | connect_and | _open_settings |  |
| FI-0078 | app.py:13758 | Button | Set Default | set_default_profile | _open_settings |  |
| FI-0079 | app.py:13764 | Button | Delete | delete_profile | _open_settings |  |
| FI-0080 | app.py:13809 | CheckBox |  | toggle_account | _open_settings |  |
| FI-0081 | ui/views.py:310 | Switch | Off | _on_brand_toggle | __init__ |  |
| FI-0082 | ui/views.py:326 | OptionMenu |  | _on_selection_changed | __init__ |  |
| FI-0083 | ui/views.py:335 | OptionMenu |  | _on_mode_changed | __init__ |  |
| FI-0084 | ui/views.py:348 | OptionMenu |  | _on_selection_changed | __init__ |  |
| FI-0085 | ui/views.py:366 | OptionMenu |  | _on_allocation_preset_changed | __init__ |  |
| FI-0086 | ui/views.py:378 | OptionMenu |  | _on_allocation_changed | __init__ |  |
| FI-0087 | ui/views.py:390 | OptionMenu |  | _on_allocation_changed | __init__ |  |
| FI-0088 | ui/views.py:402 | OptionMenu |  | _on_allocation_changed | __init__ |  |
| FI-0089 | ui/views.py:943 | key | <Return> | _on_add_listing | __init__ |  |
| FI-0090 | ui/views.py:2464 | key | <Return> | _rename | _build_row |  |
| FI-0091 | ui/views.py:956 | OptionMenu |  |  | __init__ | none |
| FI-0092 | ui/views.py:1132 | OptionMenu |  |  | __init__ | none |
| FI-0093 | ui/views.py:1855 | SegmentedButton |  | _changed | __init__ |  |
| FI-0094 | ui/views.py:2446 | Switch |  | _toggle | _build_row |  |
| FI-0095 | ui/views.py:1838 | Switch |  | _toggled | __init__ |  |
| FI-0096 | ui/shell.py:111 | Button |  | Subscript | _build_topbar | handler? |
| FI-0097 | ui/shell.py:145 | Button |  | Subscript | _build_topbar | handler? |
| FI-0098 | ui/shell.py:158 | Button | Close browsers | Subscript | _build_topbar | handler? |
| FI-0099 | ui/shell.py:179 | Button |  | Subscript | _build_topbar | handler? |
| FI-0100 | ui/shell.py:187 | Button | Choose project | Subscript | _build_topbar | handler? |
| FI-0101 | ui/shell.py:173 | Button |  | Subscript | _build_topbar | handler? |
| FI-0102 | ui/shell.py:230 | Button | {…}   {…} | navigate | _build_sidebar |  |
| FI-0103 | ui/widgets.py:62 | Button |  | command | make_button | handler? |
| FI-0104 | ui/widgets.py:340 | Button | {…}  {…} | _toggle | __init__ |  |
| FI-0105 | csv_generator/ui.py:61 | Button | Generate |  | open_generator | none |
| FI-0106 | csv_generator/ui.py:63 | Button | Cancel |  | open_generator | none |
| FI-0107 | csv_generator/ui.py:76 | Button | Save CSV… |  | open_generator | none |
| FI-0108 | csv_generator/ui.py:78 | Button | Use in this project |  | open_generator | none |
| FI-0109 | csv_generator/ui.py:39 | OptionMenu |  |  | open_generator | none |
| FI-0110 | csv_generator/ui.py:54 | CheckBox |  |  | open_generator | none |
| FI-0111 | learning/rating_ui.py:86 | Button | Save | _save | __init__ |  |
| FI-0112 | learning/rating_ui.py:55 | Button | ☆ | _set | __init__ |  |
| FI-0113 | learning/rating_ui.py:65 | OptionMenu |  |  | __init__ | none |
| FI-0114 | learning/rating_ui.py:73 | CheckBox |  |  | __init__ | none |
| FI-0115 | learning/rating_ui.py:88 | Button | Skip | _skip | __init__ |  |
| FI-0116 | learning/rating_ui.py:159 | Button |  | RatingDialog | open_history | handler? |
| FI-0117 | learning/self_learning_ui.py:37 | Button | Analyze Existing CSVs |  | open_learning | none |
| FI-0118 | learning/self_learning_ui.py:39 | Button | Cancel |  | open_learning | none |
| FI-0119 | learning/self_learning_ui.py:142 | Button | Roll back to previous version | rollback | open_learning | handler? |
| FI-0120 | learning/self_learning_ui.py:120 | Button |  | act_on | open_learning |  |
| FI-0121 | learning/self_learning_ui.py:147 | Button | Disable | disable | open_learning | handler? |
| FI-0122 | whatif/app_section.py:117 | Switch | Use What If for this project | on_toggle | build |  |
| FI-0123 | whatif/app_section.py:147 | Button | Generate video | on_generate_click | build |  |
| FI-0124 | whatif/app_section.py:128 | Button |  | cmd | build | handler? |
| FI-0125 | whatif/app_section.py:140 | SegmentedButton |  | on_flow_mode | build |  |
| FI-0126 | whatif/app_section.py:142 | Switch | Sound effects + ambience | save_state | build |  |
| FI-0127 | weather/app_section.py:251 | Switch | Use Weather for this project | on_toggle | build |  |
| FI-0128 | weather/app_section.py:308 | Button | Load plan… | browse | build |  |
| FI-0129 | weather/app_section.py:1690 | Switch | Show the Weather style (locked: asks for the password) | toggle | build_settings |  |
| FI-0130 | weather/app_section.py:275 | Button |  | cmd | build | handler? |
| FI-0131 | weather/app_section.py:285 | SegmentedButton |  | on_style | build |  |
| FI-0132 | weather/app_section.py:289 | SegmentedButton |  | on_format | build |  |
| FI-0133 | weather/app_section.py:303 | SegmentedButton |  | on_method | build |  |
| FI-0134 | weather/app_section.py:349 | Switch | Sound effects + ambience | save_state | build |  |
| FI-0135 | weather/app_section.py:1727 | Button | Choose… | pick_lib | build_settings |  |
| FI-0136 | weather/app_section.py:1752 | Switch | Prepare the forecast every morning (5:30 AM Central) | toggle_schedule | build_settings |  |
| FI-0137 | weather/app_section.py:1549 | Button | Make this report (copy the prompt) | take | show_suggestions |  |
| FI-0138 | project_picker.py:134 | key | <Escape> | _handle_dismiss | __init__ |  |
| FI-0139 | project_picker.py:223 | key | <Return> | _handle_create | _build_create_card |  |
| FI-0140 | project_picker.py:225 | Button | Create | _handle_create | _build_create_card |  |
| FI-0141 | project_picker.py:254 | OptionMenu |  |  | _build_create_card | none |
| FI-0142 | project_picker.py:273 | OptionMenu |  |  | _build_create_card | none |
| FI-0143 | project_picker.py:383 | Button | Open folder… | _handle_open_folder | _build_footer |  |
| FI-0144 | project_picker.py:182 | Button | ⚙ | _handle_settings | _build_header |  |

## Handlers defined but never referenced (4)

`_on_*` / `_open_*` methods whose name appears only at their definition: candidate features with no control.

- `_on_failed_check`
- `_on_project_menu`
- `_on_scroll`
- `_open_folder_path`
