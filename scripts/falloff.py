# Copyright © 2011–2012 mat^2
# Copyright © 2012 Ben Aksoy
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

from math import ceil

from pyspades.collision import distance_3d_vector
from pyspades import contained as loaders
from pyspades.weapon import BaseWeapon
from pyspades.constants import *

class Weapon(BaseWeapon):
    discard_reloading = False

    def get_damage(self, value, v1, v2):
        d = distance_3d_vector(v1, v2)

        t = (d - self.near) / (self.far - self.near)
        t = 1 - max(0, min(1, t))

        return ceil(self.damage[value] * t)

    def on_reload(self):
        self.reloading = False

        if self.slow_reload:
            self.current_ammo += 1
            self.current_stock -= 1

            self.reload_callback()
            self.reload()
        elif self.discard_reloading:
            ammo_taken = min(self.ammo, self.current_stock)

            self.current_ammo = ammo_taken
            self.current_stock -= ammo_taken

            self.reload_callback()
        else:
            ammo_taken = min(self.ammo - self.current_ammo, self.current_stock)

            self.current_ammo += ammo_taken
            self.current_stock -= ammo_taken

            self.reload_callback()

class Rifle(Weapon):
    id          = RIFLE_WEAPON
    name        = 'Rifle'
    delay       = 0.5
    ammo        = 10
    stock       = 50
    reload_time = 2.5
    slow_reload = False
    near        = 512
    far         = 1024

    damage = {
        TORSO: 100,
        HEAD:  100,
        ARMS:  80,
        LEGS:  80
    }

class SMG(Weapon):
    id          = SMG_WEAPON
    name        = 'SMG'
    delay       = 0.11
    ammo        = 30
    stock       = 120
    reload_time = 2.5
    slow_reload = False
    near        = 30
    far         = 150

    damage = {
        TORSO: 60,
        HEAD:  100,
        ARMS:  30,
        LEGS:  30
    }

class Shotgun(Weapon):
    id          = SHOTGUN_WEAPON
    name        = 'Shotgun'
    delay       = 1.0
    ammo        = 6
    stock       = 48
    reload_time = 0.5
    slow_reload = True
    near        = 15
    far         = 95

    damage = {
        TORSO: 40,
        HEAD:  100,
        ARMS:  20,
        LEGS:  20
    }

def apply_script(protocol, connection, config):
    class FalloffConnection(connection):
        def get_weapon(self, weapon):
            if weapon == RIFLE_WEAPON:
                return Rifle

            if weapon == SMG_WEAPON:
                return SMG

            if weapon == SHOTGUN_WEAPON:
                return Shotgun

        def set_weapon(self, weapon, local = False, no_kill = False):
            if weapon_class := self.get_weapon(weapon):
                self.weapon = weapon

                if self.weapon_object is not None:
                    self.weapon_object.reset()

                self.weapon_object = weapon_class(self._on_reload)

                ds = self.protocol.map_info.extensions
                self.weapon_object.discard_reloading = ds.get("arena_discard_reloading", False)

                if local is False and self.world_object is not None:
                    change_weapon = loaders.ChangeWeapon()
                    self.protocol.broadcast_contained(change_weapon, save = True)

                    if not no_kill: self.kill(kill_type = CLASS_CHANGE_KILL)

        def on_spawn(self, pos):
            self._on_reload()

            return connection.on_spawn(self, pos)

    return protocol, FalloffConnection