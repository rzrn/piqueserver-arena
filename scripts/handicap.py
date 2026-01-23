# Copyright © 2025 rzrn

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

from random import uniform

from piqueserver.commands import command, player_only, get_player

@command('handicap', 'hic')
@player_only
def c_handicap(player, argval = None):
    """
    Give a handicap or show handicap level of a given player
    /handicap <level> or /handicap <nickname> or /hic
    """
    protocol = player.protocol

    if argval is None:
        return "You give a {} % handicap".format(player.miss_probability)
    elif argval.isdecimal():
        prob = int(argval)

        if prob < 0 or 100 < prob:
            return "Handicap level should be between 0 and 100 %"
        elif player.miss_probability == prob:
            return "Your handicap level is already at {} %".format(prob)
        else:
            player.miss_probability = prob

            if prob <= 0:
                protocol.broadcast_chat("{} no longer gives a handicap".format(player.name))
            else:
                protocol.broadcast_chat("{} gives a {} % handicap".format(player.name, prob))
    else:
        target = get_player(protocol, argval)

        return "{} gives a {} % handicap".format(target.name, target.miss_probability)

def apply_script(protocol, connection, config):
    class HandicapConnection(connection):
        def __init__(self, *w, **kw):
            connection.__init__(self, *w, **kw)

            self.miss_probability = 0

        def on_hit(self, hit_amount, player, kill_type, grenade):
            if player is None or player is self or grenade is not None:
                return connection.on_hit(self, hit_amount, player, kill_type, grenade)

            if uniform(0.0, 100.0) < self.miss_probability:
                return False
            else:
                return connection.on_hit(self, hit_amount, player, kill_type, grenade)

    return protocol, HandicapConnection
