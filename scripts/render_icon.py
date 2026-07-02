"""Render the vector-drawn VibeSignal app icon without emoji fonts."""
import sys

from AppKit import (
    NSBitmapImageRep,
    NSBezierPath,
    NSColor,
    NSImage,
)
from Foundation import NSMakeRect

OUT = sys.argv[1]
SIZE = 1024.0


def color(hex_value, alpha=1.0):
    value = hex_value.lstrip("#")
    r = int(value[0:2], 16) / 255.0
    g = int(value[2:4], 16) / 255.0
    b = int(value[4:6], 16) / 255.0
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, alpha)


def rounded_rect(x, y, w, h, radius, fill, stroke=None, width=1.0):
    path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(x, y, w, h), radius, radius
    )
    fill.setFill()
    path.fill()
    if stroke is not None:
        stroke.setStroke()
        path.setLineWidth_(width)
        path.stroke()


def circle(cx, cy, radius, fill, stroke=None, width=1.0):
    path = NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(cx - radius, cy - radius, radius * 2, radius * 2)
    )
    fill.setFill()
    path.fill()
    if stroke is not None:
        stroke.setStroke()
        path.setLineWidth_(width)
        path.stroke()


img = NSImage.alloc().initWithSize_((SIZE, SIZE))
img.lockFocus()

rounded_rect(72, 72, 880, 880, 210, color("#0f172a"), color("#34d399"), 18)
rounded_rect(184, 154, 656, 716, 156, color("#111827"), color("#64748b"), 12)

circle(512, 720, 88, color("#ef4444"), color("#fee2e2"), 12)
circle(512, 512, 88, color("#facc15"), color("#fef3c7"), 12)
circle(512, 304, 88, color("#22c55e"), color("#dcfce7"), 12)

img.unlockFocus()

rep = NSBitmapImageRep.imageRepWithData_(img.TIFFRepresentation())
png = rep.representationUsingType_properties_(4, None)  # 4 = PNG
ok = png.writeToFile_atomically_(OUT, True)
print("written" if ok else "FAILED", OUT)
