from math import floor

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