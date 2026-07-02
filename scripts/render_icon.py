"""Render the 🚦 emoji to a 1024px PNG for use as the VibeSignal icon."""
import sys

from AppKit import (
    NSBitmapImageRep,
    NSFont,
    NSFontAttributeName,
    NSImage,
    NSString,
)

OUT = sys.argv[1]
SIZE = 1024.0

img = NSImage.alloc().initWithSize_((SIZE, SIZE))
img.lockFocus()
attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(760.0)}
s = NSString.stringWithString_("🚦")
b = s.sizeWithAttributes_(attrs)
s.drawAtPoint_withAttributes_(((SIZE - b.width) / 2.0, (SIZE - b.height) / 2.0), attrs)
img.unlockFocus()

rep = NSBitmapImageRep.imageRepWithData_(img.TIFFRepresentation())
png = rep.representationUsingType_properties_(4, None)  # 4 = PNG
ok = png.writeToFile_atomically_(OUT, True)
print("written" if ok else "FAILED", OUT)
