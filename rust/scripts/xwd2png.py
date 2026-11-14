#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
"""Convert an X11 `xwd` dump to PNG without ImageMagick. Truecolor only."""
import struct
import sys
from pathlib import Path

from PIL import Image


def convert(source, target):
    data = Path(source).read_bytes()
    header_size = struct.unpack('>I', data[:4])[0]
    header = struct.unpack('>25I', data[:100])
    version, depth, width, height = header[1], header[3], header[4], header[5]
    byte_order, bits = header[7], header[11]
    bytes_per_line = header[12]
    red_mask, green_mask, blue_mask = header[14], header[15], header[16]
    ncolors = header[19]
    offset = header_size
    if version == 7:
        name_length = struct.unpack('>I', data[offset:offset + 4])[0]
        offset += 4 + name_length
    offset += ncolors * 12
    pixels = data[offset:]
    order = 'little' if byte_order == 0 else 'big'
    assert bits in (24, 32), bits

    def channel(value, mask):
        if not mask:
            return 0
        shift = (mask & -mask).bit_length() - 1
        maximum = mask >> shift
        return ((value & mask) >> shift) * 255 // maximum

    image = Image.new('RGB', (width, height))
    output = image.load()
    step = bits // 8
    for y in range(height):
        row = pixels[y * bytes_per_line:(y + 1) * bytes_per_line]
        for x in range(width):
            value = int.from_bytes(row[x * step:x * step + step], order)
            output[x, y] = (channel(value, red_mask), channel(value, green_mask), channel(value, blue_mask))
    image.save(target)


if __name__ == '__main__':
    convert(sys.argv[1], sys.argv[2])
    print(sys.argv[2])
