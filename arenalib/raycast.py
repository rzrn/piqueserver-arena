# Copyright © 2011–2012 Mathias Kaerlev
# Copyright © 2024–2026 rzrn

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from math import copysign, floor, ceil

def cube_line(x1, y1, z1, x2, y2, z2):
    x, y, z = x1, y1, z1

    dx, dy, dz = x2 - x1, y2 - y1, z2 - z1

    ixi = -1 if dx < 0 else 1
    iyi = -1 if dy < 0 else 1
    izi = -1 if dz < 0 else 1

    if abs(dx) >= abs(dy) and abs(dx) >= abs(dz):
        dxi = 1024
        dyi = 0x3fffffff // 512 if dy == 0 else abs(dx * 1024 // dy)
        dzi = 0x3fffffff // 512 if dz == 0 else abs(dx * 1024 // dz)
    elif abs(dy) >= abs(dz):
        dxi = 0x3fffffff // 512 if dx == 0 else abs(dy * 1024 // dx)
        dyi = 1024
        dzi = 0x3fffffff // 512 if dz == 0 else abs(dy * 1024 // dz)
    else:
        dxi = 0x3fffffff // 512 if dx == 0 else abs(dz * 1024 // dx)
        dyi = 0x3fffffff // 512 if dy == 0 else abs(dz * 1024 // dy)
        dzi = 1024

    dx = dxi // 2
    dy = dyi // 2
    dz = dzi // 2

    if 0 <= ixi: dx = dxi - dx
    if 0 <= iyi: dy = dyi - dy
    if 0 <= izi: dz = dzi - dz

    yield x, y, z

    while x != x2 or y != y2 or z != z2:
        if dz <= dx and dz <= dy:
            z  += izi
            dz += dzi
    
            if z < -63 or 63 <= z:
                return
        elif dx < dy:
            x  += ixi
            dx += dxi
    
            if x < 0 or 512 <= x:
                return
        else:
            y  += iyi
            dy += dyi
    
            if y < 0 or 512 <= y:
                return

        yield x, y, z

def line_rasterizer(x, y, z, rx, ry, rz, length = 256.0):
    ex = floor(x + rx * length)
    ey = floor(y + ry * length)
    ez = floor(z + rz * length)

    yield from cube_line(x, y, z, ex, ey, ez)

def line_traverse(r, v):
    x = floor(r.x) + 1 if v.x > 0 else ceil(r.x) - 1
    y = floor(r.y) + 1 if v.y > 0 else ceil(r.y) - 1
    z = floor(r.z) + 1 if v.z > 0 else ceil(r.z) - 1

    dx, dy, dz = x - r.x, y - r.y, z - r.z

    if abs(dx) < 1e-20:
        dx = copysign(1.0, v.x)

    if abs(dy) < 1e-20:
        dy = copysign(1.0, v.y)

    if abs(dz) < 1e-20:
        dz = copysign(1.0, v.z)

    return 1 / max(v.x / dx, v.y / dy, v.z / dz)

def cast(r, v):
    t = 0

    for N in range(10_000):
        if r.x < 0 or r.x > 512: break
        if r.y < 0 or r.y > 512: break
        if r.z < 0 or r.z > 512: break

        dt = line_traverse(r, v)
        dr = v * dt

        R = r + dr * 0.5

        t += dt
        r += dr

        yield t, floor(R.x), floor(R.y), ceil(R.z)
