# Copyright © 2025–2026 rzrn

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from colorsys import hsv_to_rgb
from math import inf

from pyspades.contained import BlockAction, BlockLine, GrenadePacket
from pyspades.constants import BUILD_BLOCK, DESTROY_BLOCK
from pyspades.common import Vertex3
from pyspades.entities import Flag
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

def CTF(**kw):
    ds = dict(
        arena                  = True,
        arena_break_time       = 0,
        arena_map_change_delay = 0,
        arena_time_limit       = 0,
        arena_respawn_time     = 10,
        arena_heartbeat_rate   = inf,
        arena_has_refill       = True
    )

    ds.update(kw)
    return ds

def respawn_on_flag_sunken(protocol, entity):
    if isinstance(entity, Flag):
        if entity.player is None and 63 <= entity.z:
            entity.team.set_flag().update()

def refill_on_flag_taken(player):
    player.refill()
