"""Map scenes: animated satellite-map clips (parent > focus > inner areas,
glowing borders, labels, camera push-in) rendered to an ordinary MP4.

Standalone for now: ``python -m map_scene "Florida > Florida Panhandle" -o out.mp4``.
"""

from .spec import MapSpec, parse_map_prompt  # noqa: F401
from .places import Place, PlaceNotFound, find_place  # noqa: F401
