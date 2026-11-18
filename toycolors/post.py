"""Final colour grade for Toy Vehicles Colours, applied by ffmpeg when frames are joined (and to check stills).
The reference look is very saturated with crisp contrast; Blender's Standard view stays a little flat."""
GRADE = "eq=saturation=1.52:contrast=1.08:gamma=1.0,unsharp=5:5:0.3"
# Stories: a little more colour on top (graded stills measured 0.55 mean saturation vs the reference's 0.70)
STORY_GRADE = GRADE + ",eq=saturation=1.15"
