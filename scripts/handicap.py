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
            if uniform(0.0, 100.0) < self.miss_probability:
                return False
            else:
                return connection.on_hit(self, hit_amount, player, kill_type, grenade)

    return protocol, HandicapConnection
