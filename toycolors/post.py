"""Final colour grade for Toy Vehicles Colours, applied by ffmpeg when frames are joined (and to check stills).
The reference look is very saturated with crisp contrast; Blender's Standard view stays a little flat."""
# warm balance + more colour + a touch darker: measured ours sat 0.55 val 0.82 R-B +0.06 vs the reference 0.66 / 0.75 / +0.28
# graded check stills after this: sat 0.68 R-B +0.25, 66% vivid pixels (reference 0.66 / +0.28 / 66%)
GRADE = ("colorbalance=rs=0.10:bs=-0.12:rm=0.12:bm=-0.14:rh=0.06:bh=-0.08,"
         "eq=saturation=1.85:contrast=1.10:gamma=0.88,unsharp=5:5:0.3")
STORY_GRADE = GRADE                      # the shared grade now reaches the reference on its own
