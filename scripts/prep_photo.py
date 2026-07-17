"""
Prepare a portrait photo for clean ASCII conversion:
  1. remove the background (rembg) so the subject is isolated
  2. boost LOCAL contrast (CLAHE) so a flatly-lit face gains highlights and
     shadows -- this is what turns a dark blob into a recognizable face
  3. composite the subject onto pure white so the background reads as blank
     (white -> spaces in the ascii ramp)

Output: source-prepped.png (grayscale), consumed by make_ascii_svg.py.
Run once whenever the source photo changes; the ascii SVG itself is static.

    python scripts/prep_photo.py <input.jpg> [output.png]
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image
from rembg import remove

HERE = os.path.dirname(os.path.abspath(__file__))
INP = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "source-photo.jpg")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "source-prepped.png")

# 1. cut out the subject
cut = remove(Image.open(INP).convert("RGBA"))
rgb = np.array(cut.convert("RGB"))
alpha = np.array(cut.split()[-1])                 # 0 = background

# 2. local-contrast the luminance (CLAHE)
gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
clahe = cv2.createCLAHE(clipLimit=2.6, tileGridSize=(8, 8))
gray = clahe.apply(gray)

# a touch of global lift so the face sits in the sparse end of the ramp
gray = cv2.convertScaleAbs(gray, alpha=1.05, beta=18)

# 3. auto-crop to the subject's bounding box (from the alpha mask) so the face
#    fills the frame instead of wasting rows/cols on empty space -- this is what
#    makes the low-res ASCII grid actually resolve facial detail.
ys, xs = np.where(alpha > 20)
if len(ys) > 0:
    y0, y1 = ys.min(), ys.max()
    x0, x1 = xs.min(), xs.max()
    bh, bw = y1 - y0, x1 - x0
    # margin: a little headroom above, a little room at the sides/bottom
    top_pad = int(bh * 0.08)
    side_pad = int(bw * 0.06)
    bot_pad = int(bh * 0.03)
    y0 = max(0, y0 - top_pad)
    y1 = min(gray.shape[0], y1 + bot_pad)
    x0 = max(0, x0 - side_pad)
    x1 = min(gray.shape[1], x1 + side_pad)
    gray = gray[y0:y1, x0:x1]
    alpha = alpha[y0:y1, x0:x1]

# 4. paste onto white using the alpha mask (feathered a hair to avoid a halo)
mask = (alpha.astype(np.float32) / 255.0)
mask = cv2.GaussianBlur(mask, (0, 0), 1.0)
out = gray.astype(np.float32) * mask + 255.0 * (1.0 - mask)
out = np.clip(out, 0, 255).astype(np.uint8)

Image.fromarray(out, mode="L").save(OUT)
print("wrote", OUT, out.shape)
