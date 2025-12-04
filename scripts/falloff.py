from math import ceil

from pyspades.collision import distance_3d_vector
from pyspades import contained as loaders
from pyspades.weapon import BaseWeapon
from pyspades.constants import *

class Weapon(BaseWeapon):
    def get_damage(self, value, v1, v2):
        d = distance_3d_vector(v1, v2)

        t = (d - self.near) / (self.far - self.near)
        t = 1 - max(0, min(1, t))

        return ceil(self.damage[value] * t)

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

weapons = {
    RIFLE_WEAPON:   Rifle,
    SMG_WEAPON:     SMG,
    SHOTGUN_WEAPON: Shotgun,
}

def apply_script(protocol, connection, config):
    class FalloffConnection(connection):
        def set_weapon(self, weapon, local = False, no_kill = False):
            self.weapon = weapon

            if self.weapon_object is not None:
                self.weapon_object.reset()

            self.weapon_object = weapons[weapon](self._on_reload)

            if not local and self.world_object is not None:
                change_weapon = loaders.ChangeWeapon()
                self.protocol.broadcast_contained(change_weapon, save = True)

                if not no_kill: self.kill(kill_type = CLASS_CHANGE_KILL)

        def on_spawn(self, pos):
            self._on_reload()
            return connection.on_spawn(self, pos)

    return protocol, FalloffConnection