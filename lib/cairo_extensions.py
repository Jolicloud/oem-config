# -*- coding: utf-8 -*-

import math

# Copied from ubiquity/segmented_bar.py, whose copyright and licence notices
# read as follows:
# 
# Original author:
#   Aaron Bockover <abockover@novell.com>
#
# Translated to Python and further modifications by:
#   Evan Dandrea <evand@ubuntu.com>
#
# Copyright (C) 2008 Novell, Inc.
# Copyright (C) 2008 Canonical Ltd.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

class Color:
    def __init__(self, r, g, b, a=1.0):
        self.r = r
        self.g = g
        self.b = b
        self.a = a

class CairoCorners:
    none = 0
    top_left = 1
    top_right = 2
    bottom_left = 4
    bottom_right = 8
    all = 15

class CairoExtensions:
    @staticmethod
    def modula(number, divisor):
        return int((number % divisor) + (number - int(number)))
    
    @staticmethod
    def gdk_color_to_cairo_color(color, alpha=1.0):
        return Color((color.red >> 8) / 255.0,
            (color.green >> 8) / 255.0,
            (color.blue >> 8) / 255.0,
            alpha)

    @staticmethod
    def color_from_hsb(hue, saturation, brightness):
        hue_shift = [0, 0, 0]
        color_shift = [0, 0, 0]
        if brightness <= 0.5:
            m2 = brightness * (1 + saturation)
        else:
            m2 = brightness + saturation - brightness * saturation
        m1 = 2 * brightness - m2
        hue_shift[0] = hue + 120
        hue_shift[1] = hue
        hue_shift[2] = hue - 120
        color_shift[0] = brightness
        color_shift[1] = brightness
        color_shift[2] = brightness
        if saturation == 0:
            i = 3
        else:
            i = 0
        while i < 3:
            m3 = hue_shift[i]
            if m3 > 360:
                m3 = CairoExtensions.modula(m3, 360)
            elif m3 < 0:
                m3 = 360 - CairoExtensions.modula(abs(m3), 360)

            if m3 < 60:
                color_shift[i] = m1 + (m2 - m1) * m3 / 60
            elif m3 < 180:
                color_shift[i] = m2
            elif m3 < 240:
                color_shift[i] = m1 + (m2 - m1) * (240 - m3) / 60
            else:
                color_shift[i] = m1
            i = i + 1

        return Color(color_shift[0], color_shift[1], color_shift[2])

    @staticmethod
    def hsb_from_color(color):
        red = color.r
        green = color.g
        blue = color.b
        hue = 0
        saturation = 0
        brightness = 0

        if red > green:
            ma = max(red, blue)
            mi = min(green, blue)
        else:
            ma = max(green, blue)
            mi = min(red, blue)

        brightness = (ma + mi) / 2

        if abs(ma - mi) < 0.0001:
            hue = 0
            saturation = 0
        else:
            if brightness <= 0.5:
                saturation = (ma - mi) / (ma + mi)
            else:
                saturation = (ma - mi) / (2 - ma - mi)
            delta = ma - mi
            if red == max:
                hue = (green - blue) / delta
            elif green == max:
                hue = 2 + (blue - red) / delta
            elif blue == max:
                hue = 4 + (red - green) / delta
            hue = hue * 60
            if hue < 0:
                hue = hue + 360
        return (hue, saturation, brightness)

    @staticmethod
    def color_shade(color, ratio):
        # FIXME evand 2008-07-19: This function currently produces only deep
        # reds for non-white colors.
        return color
        h, s, b = CairoExtensions.hsb_from_color(color)
        b = max(min(b * ratio, 1), 0)
        s = max(min(s * ratio, 1), 0)
        c = CairoExtensions.color_from_hsb(h, s, b)
        c.a = color.a
        return c

    @staticmethod
    def rgba_to_color(color):
        # FIXME evand 2008-07-19: We should probably match the input of
        # rgb_to_color.
        a = ((color >> 24) & 0xff) / 255.0
        b = ((color >> 16) & 0xff) / 255.0
        c = ((color >> 8) & 0xff) / 255.0
        d = (color & 0x000000ff) / 255.0
        return Color(a, b, c, d)

    @staticmethod
    def rgb_to_color(color):
        # FIXME evand 2008-07-19: Should we assume a hex string or should we
        # copy Hyena and require a hex number?
        r, g, b = color[:2], color[2:4], color[4:]
        r, g, b = [(int(n, 16) / 255.0) for n in (r, g, b)]
        return Color(r, g, b)
        #return CairoExtensions.rgba_to_color((color << 8) | 0x000000ff)

    @staticmethod
    def rounded_rectangle(cr, x, y, w, h, r, corners=CairoCorners.all, top_bottom_falls_through=False):
        if top_bottom_falls_through and corners == CairoCorners.none:
            cr.move_to(x, y - r)
            cr.line_to(x, y + h + r)
            cr.move_to(x + w, y - r)
            cr.line_to(x + w, y + h + r)
        elif r < 0.0001 or corners == CairoCorners.none:
            cr.rectangle(x, y, w, h)

        if (corners & (CairoCorners.top_left | CairoCorners.top_right)) == 0 and top_bottom_falls_through:
            y = y - r
            h = h + r
            cr.move_to(x + w, y)
        else:
            if (corners & CairoCorners.top_left) != 0:
                cr.move_to(x + r, y)
            else:
                cr.move_to(x, y)

            if (corners & CairoCorners.top_right) != 0:
                cr.arc(x + w - r, y + r, r, math.pi * 1.5, math.pi * 2)
            else:
                cr.line_to(x + w, y)

        if (corners & (CairoCorners.bottom_left | CairoCorners.bottom_right)) == 0 and top_bottom_falls_through:
            h = h + r
            cr.line_to(x + w, y + h)
            cr.move_to(x, y + h)
            cr.line_to(x, y + r)
            cr.arc(x + r, y + r, r, math.pi, math.pi * 1.5)
        else:
            if (corners & CairoCorners.bottom_right) != 0:
                cr.arc(x + w - r, y + h - r, r, 0, math.pi * 0.5)
            else:
                cr.line_to(x + w, y + h)

            if (corners & CairoCorners.bottom_left) != 0:
                cr.arc(x + r, y + h - r, r, math.pi * 0.5, math.pi)
            else:
                cr.line_to(x, y + h)

            if (corners & CairoCorners.top_left) != 0:
                cr.arc(x + r, y + r, r, math.pi, math.pi * 1.5)
            else:
                cr.line_to(x, y)
