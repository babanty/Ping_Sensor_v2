import ctypes
import math
import struct
from ctypes import wintypes
from dataclasses import dataclass


TICK = 0.030
STEPS = 200
DARK = (35, 40, 45)
GREEN = (48, 226, 108)
RED = (249, 62, 65)


@dataclass(frozen=True)
class Frame:
    color: tuple[int, int, int]
    level: int
    opacity: int = STEPS


@dataclass(frozen=True)
class Phase:
    start: float
    end: float
    result: int

    def frame(self, now):
        elapsed = max(0.0, now - self.start)
        progress = min(1.0, elapsed / (self.end - self.start))
        level = int(progress * STEPS)
        if self.result < 0:
            return Frame(RED, level)
        return Frame(GREEN, level, STEPS - level)


create_icon = ctypes.WinDLL("user32", use_last_error=True).CreateIconFromResourceEx
create_icon.argtypes = [
    ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
create_icon.restype = wintypes.HICON


class Disc:
    def __init__(self, size):
        self.size = size
        self.radius = (size - 1) / 2
        self.pixels = []
        for y in range(size):
            for x in range(size):
                distance = math.hypot(x - self.radius, y - self.radius)
                coverage = min(1.0, max(0.0, self.radius - distance + 0.5))
                self.pixels.append((distance, coverage))

    def resource(self, frame):
        # A Windows icon resource holds BGRA pixels and a DWORD-aligned AND mask.
        size = self.size
        mask = bytes(((size + 31) // 32) * 4 * size)
        header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, size * size * 4, 0, 0, 0, 0)
        radius = self.radius * frame.level / STEPS
        pixels = bytearray()
        for distance, coverage in self.pixels:
            # At full radius the entire disc, including its soft outer edge, is colored.
            if frame.level == 0:
                fill = 0.0
            elif frame.level == STEPS:
                fill = 1.0
            else:
                fill = min(1.0, max(0.0, radius - distance + 0.5))
            # Composite the color with its current opacity over the dark disc.
            fill *= frame.opacity / STEPS
            for channel in (2, 1, 0):
                intensity = DARK[channel] + (frame.color[channel] - DARK[channel]) * fill
                pixels.append(round(intensity * coverage))
            pixels.append(round(255 * coverage))
        return header + pixels + mask

    def icon(self, frame):
        data = self.resource(frame)
        handle = create_icon(data, len(data), True, 0x30000, self.size, self.size, 0)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle
