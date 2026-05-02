# Copyright © 2026 rzrn

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

from math import sin, cos, radians
from dataclasses import dataclass
from random import uniform

from twisted.internet.reactor import callLater

from pyspades.contained import SetColor, BlockAction, GrenadePacket
from pyspades.common import Vertex3, make_color
from pyspades.constants import BUILD_BLOCK
from pyspades.world import Grenade

from arenalib.raycast import cast

tuple3i = tuple[int, int, int]
tuple3f = tuple[float, float, float]

@property
def NotImplementedField(self):
    raise NotImplementedError

@dataclass
class LightFieldGun:
    firing_azimuth  : float
    barrel_blocks   : list[tuple3i]
    muzzle_position : tuple3f

    trigger_block_color = (255, 0, 0)
    near_firing_range   = NotImplementedField
    far_firing_range    = NotImplementedField
    muzzle_velocity     = NotImplementedField
    max_deviation       = NotImplementedField
    rate_of_fire        = NotImplementedField
    blast_radius        = NotImplementedField

    shell_explode_call = None
    shell_reload_call  = None

    def do_release_trigger(self, protocol, x, y, z):
        protocol.map.set_point(x, y, z, self.trigger_block_color)

        set_color           = SetColor()
        set_color.player_id = 32
        set_color.value     = make_color(*self.trigger_block_color)

        protocol.send_contained(set_color, save = True)

        block_action           = BlockAction()
        block_action.x         = x
        block_action.y         = y
        block_action.z         = z
        block_action.player_id = 32
        block_action.value     = BUILD_BLOCK

        protocol.send_contained(block_action, save = True)

        self.shell_reload_call = None

    def do_muzzle_flash(self, protocol):
        contained           = GrenadePacket()
        contained.player_id = 32
        contained.value     = 0
        contained.position  = self.muzzle_position
        contained.velocity  = (0, 0, 0)

        protocol.broadcast_contained(contained)

    def do_explode_shell(self, player, x, y, z):
        protocol = player.protocol

        contained           = GrenadePacket()
        contained.player_id = player.player_id
        contained.value     = 0
        contained.position  = (x, y, z)
        contained.velocity  = (0, 0, 0)

        protocol.broadcast_contained(contained)

        grenade = Grenade(protocol.world, 0.0, Vertex3(x, y, z), None, Vertex3(0, 0, 0))
        player.grenade_exploded(grenade, dmax = self.blast_radius)

        self.shell_explode_call = None

    def is_barrel_broken(self, protocol):
        for x, y, z in self.barrel_blocks:
            if protocol.map.get_solid(x, y, z) is False:
                return True

        return False

    def do_fire_gun(self, player, x0, y0, z0):
        if self.shell_reload_call is not None:
            return

        protocol = player.protocol

        if self.is_barrel_broken(protocol):
            self.do_explode_shell(player, x0, y0, z0)
        else:
            self.do_muzzle_flash(protocol)

            φ0, Δφ = radians(self.firing_azimuth), radians(self.max_deviation)

            d = uniform(self.near_firing_range, self.far_firing_range)
            φ = uniform(φ0 - Δφ, φ0 + Δφ)

            x1, y1, z1 = self.muzzle_position

            x2 = x1 + d * cos(φ)
            y2 = y1 + d * sin(φ)
            z2 = protocol.map.get_z(x2, y2, z1)

            r = Vertex3(x1, y1, z1)
            v = Vertex3(x2 - x1, y2 - y1, z2 - z1).normal() * self.muzzle_velocity

            # We assume that the map is small enough and the shell is fast enough so that the shell
            # flies almost in a straight line. Hence, we ignore gravitation, aerodynamic drag
            # and other forces, and do a simple raycast.

            for t, x, y, z in cast(r, v):
                if protocol.map.get_solid(x, y, z):
                    self.shell_explode_call = callLater(t, self.do_explode_shell, player, x, y, z - 1)

                    break

        self.shell_reload_call = callLater(60 / self.rate_of_fire, self.do_release_trigger, protocol, x0, y0, z0)

def fire_gun_on_block_removed(game_field_guns):
    def on_block_removed(player, x, y, z):
        protocol = player.protocol

        if field_gun := game_field_guns.get((x, y, z), None):
            field_gun.do_fire_gun(player, x, y, z)

    return on_block_removed

def unload_guns_on_map_unloaded(game_field_guns):
    def on_map_unloaded(protocol, rot_info):
        for field_gun in game_field_guns.values():
            if defer := field_gun.shell_explode_call:
                field_gun.shell_explode_call = None

                if defer.active():
                    defer.cancel()

            if defer := field_gun.shell_reload_call:
                field_gun.shell_reload_call = None

                if defer.active():
                    defer.cancel()

    return on_map_unloaded
