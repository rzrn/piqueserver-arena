from colorsys import hsv_to_rgb

from pyspades.contained import BlockAction, BlockLine, GrenadePacket
from pyspades.constants import BUILD_BLOCK, DESTROY_BLOCK
from pyspades.common import Vertex3
from pyspades import world

from arenalib.raycast import cube_line

def denorm8(x):
    return int(x * 255)

def RGB3fAs3i(r, g, b):
    return denorm8(r), denorm8(g), denorm8(b)

def HSV3fAsRGB3i(h, s, v):
    r, g, b = hsv_to_rgb(h, s, v)
    return RGB3fAs3i(r, g, b)

def doBlockLinePacket(player, x1, y1, z1, x2, y2, z2):
    protocol = player.protocol
    M = protocol.map

    for x, y, z in cube_line(x1, y1, z1, x2, y2, z2):
        if M.get_solid(x, y, z):
            continue

        if not M.build_point(x, y, z, player.color):
            break

    contained           = BlockLine()
    contained.player_id = player.player_id
    contained.x1        = x1
    contained.y1        = y1
    contained.z1        = z1
    contained.x2        = x2
    contained.y2        = y2
    contained.z2        = z2

    protocol.broadcast_contained(contained, save = True)

def doBlockBuildPacket(player, x, y, z):
    protocol = player.protocol
    M = protocol.map

    if M.get_solid(x, y, z) is False:
        M.set_point(x, y, z, player.color)

        contained           = BlockAction()
        contained.x         = x
        contained.y         = y
        contained.z         = z
        contained.player_id = player.player_id
        contained.value     = BUILD_BLOCK

        protocol.broadcast_contained(contained, save = True)

def doBlockRemovePacket(player, x, y, z):
    protocol = player.protocol
    M = protocol.map

    if M.get_solid(x, y, z):
        if protocol.is_indestructable(x, y, z):
            return

        M.destroy_point(x, y, z)

        contained           = BlockAction()
        contained.x         = x
        contained.y         = y
        contained.z         = z
        contained.player_id = player.player_id
        contained.value     = DESTROY_BLOCK

        protocol.broadcast_contained(contained, save = True)

def doGrenadePacket(player, fuse, x, y, z, vx, vy, vz):
    protocol = player.protocol

    grenade = protocol.world.create_object(
        world.Grenade, fuse, Vertex3(x, y, z), None,
        Vertex3(vx, vy, vz), player.grenade_exploded
    )

    contained           = GrenadePacket()
    contained.player_id = player.player_id
    contained.value     = grenade.fuse
    contained.position  = grenade.position.get()
    contained.velocity  = grenade.velocity.get()

    protocol.broadcast_contained(contained)

    return grenade
