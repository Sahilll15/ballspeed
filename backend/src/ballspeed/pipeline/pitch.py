"""Pitch geometry from the MCC Laws of Cricket (Law 7 and Law 8), in metres."""

from typing import Final

STUMP_TO_STUMP_M: Final = 20.12
POPPING_CREASE_OFFSET_M: Final = 1.22
RETURN_CREASE_HALF_WIDTH_M: Final = 1.32
RETURN_CREASE_SPACING_M: Final = 2 * RETURN_CREASE_HALF_WIDTH_M
PITCH_WIDTH_M: Final = 3.05
STUMP_HEIGHT_M: Final = 0.711
WICKET_WIDTH_M: Final = 0.2286
BALL_DIAMETER_M: Final = 0.072

# Release roughly over the front foot at the bowler's popping crease, flight ends at the far stumps.
FRAME_COUNT_DISTANCE_M: Final = STUMP_TO_STUMP_M - POPPING_CREASE_OFFSET_M

MS_TO_KMH: Final = 3.6
