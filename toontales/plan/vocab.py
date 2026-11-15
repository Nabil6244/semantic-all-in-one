"""Print everything a Toon Tales plan may use (for the toon-tales skill): cast, sets/marks/spots, actions,
poses, faces, cameras, moves, props, overlays, sounds, beats.

Run: python3 -m toontales.plan.vocab
"""
import sys

from toontales.plan import schema as S

sys.path[:0] = [str(S.TT / "library"), str(S.TT / "cast")]
import actions as A  # noqa: E402
import faces  # noqa: E402


def main():
    cast, nar = S.load_cast()
    print("CAST")
    for cid, c in cast.items():
        print(f"  {cid}: {c.get('role', '')} — {'; '.join(c.get('traits', []))}")
    print(f"  narrator: {'; '.join(nar.get('traits', []))}")
    print("SETS")
    for k, kit in S.load_kits().items():
        print(f"  {k}: {kit['about']}")
        print(f"    marks: {', '.join(kit['marks'])}")
        print(f"    fixed props: {', '.join(kit['props'])}   prop spots: {', '.join(kit['spots'])}")
    print("ACTIONS (do)")
    for n, (fn, dur, moves, about) in A.ACTIONS.items():
        if n not in A.HOLDS:
            print(f"  {n:13} {dur:.1f}s  {about}")
    print("POSES (do, held):", ", ".join(sorted(A.HOLDS)))
    print("EYES:", ", ".join(faces.EYES))
    print("MOUTHS (expressions; speech mouths are automatic):", ", ".join(faces.MOUTHS[9:]))
    print("CAMERAS:", ", ".join(S.CAMERAS))
    print("MOVES:", ", ".join(S.MOVES))
    print("PROPS:", ", ".join(f"{k}{' (text)' if v else ''}" for k, v in S.PROP_TYPES.items()))
    print("OVERLAYS:", ", ".join(S.OVERLAYS))
    print("SFX:", ", ".join(S.SFX))
    print("BEATS (in order):", " -> ".join(S.BEATS))
    print(f"RULES: shots {S.SHOT_MIN}-{S.SHOT_MAX}s, nothing still > {S.STILL_MAX}s, story {S.STORY_MIN:.0f}-{S.STORY_MAX:.0f}s")
    used = S.used_topics()
    print("USED TOPICS:", ", ".join(u.get("topic", u.get("id", "")) for u in used) or "(none yet)")


if __name__ == "__main__":
    main()
