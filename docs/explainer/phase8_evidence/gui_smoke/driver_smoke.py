"""GUI smoke driver: runs the REAL patched app (scratch copy) in a live Tk event loop and drives its REAL widgets through their own commands (switch.toggle(), button.invoke()),
reading widget state as a user would see it. Modal message boxes are replaced by recorders (an unattended run cannot click them). Pixels are not captured (no screen-recording permission)."""
import os, sys, json, time, traceback, threading
APP = os.path.dirname(os.path.abspath(__file__)) + "/app"
OUT = os.path.dirname(APP)
os.chdir(APP); sys.path.insert(0, APP); sys.dont_write_bytecode = True
os.environ["HF_HUB_OFFLINE"] = "1"
PHASE = sys.argv[1]
import app as A
from project_workspace import list_projects
LOG = open(f"{OUT}/smoke_{PHASE}.log", "w")
def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, file=LOG, flush=True)
boxes = []
for n in ("showerror", "showinfo", "showwarning"):
    setattr(A.messagebox, n, (lambda nm: (lambda *a, **k: boxes.append((nm,) + tuple(str(x)[:160] for x in a))))(n))
app = A.VideoGeneratorApp()
def widgets(w):
    yield w
    for c in w.winfo_children():
        yield from widgets(c)
def find_switch(text):
    for w in widgets(app):
        try:
            if w.winfo_class() in ("Frame", "Canvas") and hasattr(w, "cget") and "CTkSwitch" in type(w).__name__ and text in str(w.cget("text")):
                return w
        except Exception:
            pass
    return None
def st():
    b = app._hybrid_explainer_btn
    return {"btn": [b.cget("state"), b.cget("text")], "busy": app._hybrid_busy, "work_id": app._hybrid_work_id, "switch": app._hybrid_explainer_var.get(),
            "plan_beats": None if app._hybrid_plan is None else len(app._hybrid_plan.beats), "plan_id": id(app._hybrid_plan), "status": app._hybrid_status_var.get()[:100],
            "progress_card_mapped": bool(app._hybrid_progress_card.winfo_ismapped()), "plan_btn": [app._hybrid_plan_btn.cget("state"), app._hybrid_plan_btn.cget("text")],
            "load_btn": app._hybrid_load_btn.cget("state"), "boxes": list(boxes)}
def settings_file():
    try:
        return json.loads(open(APP + "/settings.json").read())
    except Exception as e:
        return {"error": str(e)}
def wait(cond, timeout, then, every=500, t0=None):
    t0 = t0 or time.time()
    try:
        ok = cond()
    except Exception:
        ok = False
    if ok or time.time() - t0 > timeout:
        log("wait ended", "ok" if ok else "TIMEOUT", round(time.time() - t0, 1), "s")
        then()
    else:
        app.after(every, lambda: wait(cond, timeout, then, every, t0))
def guarded(fn):
    def run():
        try:
            fn()
        except Exception:
            log("ERROR", traceback.format_exc())
            app.after(100, app.destroy)
    return run
def finish():
    log("final settings file:", settings_file())
    log("DONE")
    app.after(300, app.destroy)

if PHASE == "p1":
    def s0():
        ws = list_projects(app._projects_root_path())
        app._activate_workspace(ws[0], persist=True, clear_session=True)
        log("1. project opened; voiceover bound:", os.path.basename(app.audio_var.get()), "| script chars:", len(app._vo_script_text()))
        hs = find_switch("Use Hybrid Map")
        log("   Hybrid Map switch found:", hs is not None)
        hs.toggle()
        log("   Hybrid enabled:", app._hybrid_enabled_var.get(), "| mode:", app.generation_mode)
        try:
            app._shell.navigate("visual_director")
        except Exception as e:
            log("   navigate visual_director:", repr(e)[:100])
        app.after(1500, guarded(s1))
    def s1():
        s = st()
        log("2. DEFAULT (never touched): switch =", s["switch"], "| button =", s["btn"], "| mapped on screen:", app._hybrid_explainer_btn.winfo_ismapped(), "| viewable:", app._hybrid_explainer_btn.winfo_viewable())
        log("   settings key explainer_style in file:", settings_file().get("explainer_style", "<absent>"))
        log("3. Hybrid unchanged while off: 'Write plan with AI' =", s["plan_btn"], "| 'Load beat CSV' =", s["load_btn"], "| busy =", s["busy"], "| plan =", s["plan_beats"])
        before = (app._hybrid_busy, app._hybrid_work_id, len(boxes))
        app._hybrid_explainer_direct()                      # what a click would run if the (disabled) button were pressed while the switch is off
        log("   direct() called while OFF -> no effect:", before == (app._hybrid_busy, app._hybrid_work_id, len(boxes)), "| progress card shown:", app._hybrid_progress_card.winfo_ismapped())
        sw = find_switch("Explainer look")
        log("4. Explainer switch widget found:", sw is not None, "| text:", sw.cget("text") if sw else None)
        sw.toggle()
        s = st()
        log("   after switching ON: switch =", s["switch"], "| button =", s["btn"], "| settings file explainer_style =", settings_file().get("explainer_style", "<absent>"))
        app.after(500, guarded(s2))
    def s2():
        app._hybrid_explainer_btn.invoke()                  # a click on "Direct with Explainer"
        app.after(800, guarded(s2b))
    def s2b():
        s = st()
        log("   RUNNING: button =", s["btn"], "| busy =", s["busy"], "| progress card shown =", s["progress_card_mapped"], "| title:", app._hybrid_progress_title.cget("text"), "| plan_btn:", s["plan_btn"])
        t0 = time.time()
        wait(lambda: app._hybrid_plan is not None and not app._hybrid_busy, 900, guarded(s3), 1000, t0)
    def s3():
        s = st()
        log("5. FINISHED: plan installed =", s["plan_beats"], "beats | button =", s["btn"], "| busy =", s["busy"], "| progress card shown =", s["progress_card_mapped"], "| status line:", s["status"], "| dialogs:", s["boxes"])
        modes = {}
        for b in app._hybrid_plan.beats:
            modes[b.mode] = modes.get(b.mode, 0) + 1
        log("   beat modes:", modes, "| visual plan rows (footage):", len([r for r in getattr(app, "_scene_rows", [])]), "| rows owner:", getattr(app, "_scene_rows_owner", None))
        try:
            rows = app._scene_rows
            log("   first rows:", [(str(getattr(r, 'status', ''))[:12], str(getattr(r, 'asset', getattr(r, 'path', '')))[-40:]) if not isinstance(r, dict) else (str(r.get('status', ''))[:12], str(r.get('asset', r.get('path', '')))[-40:]) for r in rows[:4]])
        except Exception as e:
            log("   rows introspection failed:", repr(e)[:100])
        app._good_plan_id = id(app._hybrid_plan)
        app._good_plan = app._hybrid_plan
        app.after(500, guarded(s4))
    def s4():
        good = app.audio_var.get()
        junk = OUT + "/projects/junk.wav"
        open(junk, "wb").write(os.urandom(2048))
        app.audio_var.set(junk)
        log("6. FAILURE: voiceover replaced by 2 KB of random bytes; clicking Direct with Explainer")
        app._junk_restore = good
        app._hybrid_explainer_btn.invoke()
        wait(lambda: not app._hybrid_busy and app._hybrid_explainer_btn.cget("text") == "Direct with Explainer", 300, guarded(s5), 500)
    def s5():
        s = st()
        log("   after failure: plan unchanged (same object) =", app._hybrid_plan is app._good_plan, "| beats =", s["plan_beats"], "| button =", s["btn"], "| busy =", s["busy"], "| progress card shown =", s["progress_card_mapped"], "| status:", s["status"], "| dialog:", s["boxes"][-1:] )
        app.audio_var.set(app._junk_restore)
        log("7. STOP: good voiceover restored; clicking Direct, then Stop")
        app._hybrid_explainer_btn.invoke()
        app.after(1200, guarded(s6))
    def s6():
        s = st()
        log("   running before Stop: button =", s["btn"], "| busy =", s["busy"], "| progress card shown =", s["progress_card_mapped"])
        app._boxes_before_stop = len(boxes)
        app._hybrid_progress_stop.invoke()                  # the card's real Stop button
        s = st()
        log("   immediately after Stop: button =", s["btn"], "| busy =", s["busy"], "| progress card shown =", s["progress_card_mapped"], "| status:", s["status"], "| plan unchanged =", app._hybrid_plan is app._good_plan)
        app.after(45000, guarded(s7))
    def s7():
        s = st()
        log("   45 s later (the stopped worker has answered by now): button =", s["btn"], "| busy =", s["busy"], "| plan unchanged =", app._hybrid_plan is app._good_plan, "| new dialogs since Stop:", boxes[app._boxes_before_stop:], "| progress card shown =", s["progress_card_mapped"])
        finish()
    app.after(5000, guarded(s0))
elif PHASE == "p3":
    import glob
    def s0():
        ws = list_projects(app._projects_root_path())
        app._activate_workspace(ws[0], persist=True, clear_session=True)
        hs = find_switch("Use Hybrid Map")
        if not app._hybrid_enabled_var.get():
            hs.toggle()
        try:
            app._shell.navigate("visual_director")
        except Exception:
            pass
        app.after(1500, guarded(s1))
    def s1():
        s = st()
        log("9. STOP (slow run): at start switch =", s["switch"], "| button =", s["btn"], "| plan restored from the project =", s["plan_beats"])
        ws = app._workspace
        gone = 0
        for f in glob.glob(str(ws.hybrid_dir / "explainer" / "*.mp4")):
            os.remove(f); gone += 1
        log("   cached board clips deleted (so the director must encode again):", gone)
        app._plan0 = app._hybrid_plan
        app._hybrid_explainer_btn.invoke()
        app.after(2500, guarded(s2))
    def s2():
        s = st()
        log("   running: button =", s["btn"], "| busy =", s["busy"], "| progress card shown =", s["progress_card_mapped"], "| title:", app._hybrid_progress_title.cget("text"))
        app._n_boxes = len(boxes)
        app._hybrid_progress_stop.invoke()
        s = st()
        log("   immediately after Stop: button =", s["btn"], "| busy =", s["busy"], "| progress card shown =", s["progress_card_mapped"], "| status:", s["status"], "| plan unchanged =", app._hybrid_plan is app._plan0, "| plan beats =", s["plan_beats"])
        t0 = time.time()
        ws = app._workspace
        wait(lambda: len(glob.glob(str(ws.hybrid_dir / "explainer" / "*.mp4"))) >= 9 and time.time() - t0 > 20, 120, guarded(s3), 1000, t0)
    def s3():
        app.after(20000, guarded(s4))
    def s4():
        s = st()
        log("   worker finished and answered late (clips re-encoded in the background): button =", s["btn"], "| busy =", s["busy"], "| plan unchanged =", app._hybrid_plan is app._plan0, "| dialogs since Stop:", boxes[app._n_boxes:], "| progress card shown =", s["progress_card_mapped"], "| status:", s["status"])
        log("10. START AGAIN right after: button invoke works =", app._hybrid_explainer_btn.cget("state"))
        finish()
    app.after(4000, guarded(s0))
elif PHASE == "p4":
    def s0():
        ws = list_projects(app._projects_root_path())
        app._activate_workspace(ws[0], persist=True, clear_session=True)
        hs = find_switch("Use Hybrid Map")
        if not app._hybrid_enabled_var.get():
            hs.toggle()
        app.after(1500, guarded(s1))
    def s1():
        rows = getattr(app, "_scene_rows", [])
        log("11. Visual Plan rows after reopening the project with the Explainer plan:", len(rows), "| owner:", getattr(app, "_scene_rows_owner", None), "| plan beats:", None if app._hybrid_plan is None else len(app._hybrid_plan.beats))
        for r in rows[:12]:
            d = r if isinstance(r, dict) else getattr(r, "__dict__", {})
            log("   row:", {k: str(v)[:60] for k, v in list(d.items())[:8]})
        try:
            from hybrid import identity
            desc = identity.row_descriptors(app._hybrid_plan)
            log("   hybrid row descriptors (rows that need a picture or clip):", len(desc))
        except Exception as e:
            log("   descriptors:", repr(e)[:100])
        finish()
    app.after(4000, guarded(s0))
elif PHASE == "p2":
    def s0():
        s0v = app._hybrid_explainer_var.get()
        log("8. RESTART: switch restored =", s0v, "| settings file explainer_style =", settings_file().get("explainer_style", "<absent>"))
        ws = list_projects(app._projects_root_path())
        app._activate_workspace(ws[0], persist=True, clear_session=True)
        hs = find_switch("Use Hybrid Map")
        log("   project reopened; Hybrid switch (per project) =", app._hybrid_enabled_var.get())
        if not app._hybrid_enabled_var.get():
            hs.toggle()
        app.after(1000, guarded(s1))
    def s1():
        s = st()
        log("   after Hybrid shown: Explainer switch =", s["switch"], "| button =", s["btn"], "| plan restored from project =", s["plan_beats"])
        sw = find_switch("Explainer look"); sw.toggle()
        s = st()
        log("   switched OFF: switch =", s["switch"], "| button =", s["btn"], "| settings file explainer_style =", settings_file().get("explainer_style", "<absent>"))
        finish()
    app.after(4000, guarded(s0))
app.mainloop()
log("mainloop ended")
