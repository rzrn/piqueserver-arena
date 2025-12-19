from pyspades.contained import GrenadePacket, IntelDrop

from piqueserver.commands import player_only, command
from piqueserver.config import config

from arenalib.raycast import line_rasterizer

class ArenaException(Exception):
    pass

arena_section       = config.section("arena")
flag_throw_distance = arena_section.option("flag_throw_distance", 5.0).get()

@command('gbrad', 'gbr')
def c_grenade_blast_radius(connection, argval = None):
    """
    Show or set grenade blast radius
    /gbr or /gbr <radius>
    """

    protocol = connection.protocol

    if argval is None: return "{:.1f}".format(protocol.grenade_blast_radius)

    # TODO: needs to be synced with `has_permissions` from `piqueserver.commands`
    if connection.admin or c_grenade_blast_radius.command_name in connection.rights:
        radius = min(1024, max(0, float(argval)))
        protocol.grenade_blast_radius = radius

        protocol.broadcast_chat(
            "{} changed grenade blast radius to {:.1f}".format(connection.name, radius)
        )
    else:
        return "You aren't allowed to change grenade blast radius."

@command('dropflag', 'throwflag', 'df')
@player_only
def c_dropflag(player):
    """
    Drop the intel
    /dropflag or /df
    """
    if wo := player.world_object:
        if player.hp is None or wo.dead:
            return

        if player.team is None or player.team.spectator:
            return

        protocol = player.protocol
        ds = protocol.map_info.extensions

        if player.team is protocol.blue_team:
            if 'arena_green_flag' not in ds:
                return

        if player.team is protocol.green_team:
            if 'arena_blue_flag' not in ds:
                return

        flag = player.team.other.flag

        if flag is None:
            return

        if flag.player is player:
            if dest := wo.cast_ray(flag_throw_distance):
                loc = dest
            else:
                v = wo.position + wo.orientation * flag_throw_distance
                loc = protocol.get_drop_location(v.get())

            flag.set(*loc)
            flag.player = None

            contained           = IntelDrop()
            contained.player_id = player.player_id
            contained.x         = flag.x
            contained.y         = flag.y
            contained.z         = flag.z

            protocol.broadcast_contained(contained, save = True)

            player.on_flag_drop()
        else:
            return "You don't have the intel."

def wall_tunnel(player):
    if player.world_object is None:
        return

    protocol = player.protocol

    wo = player.world_object
    if loc := wo.cast_ray(3.0):
        M = protocol.map

        for x, y, z in line_rasterizer(*loc, *wo.orientation.get()):
            P = M.get_solid(x, y, z - 1)
            Q = M.get_solid(x, y, z + 0)
            R = M.get_solid(x, y, z + 1)

            if not P and not Q and not R:
                contained           = GrenadePacket()
                contained.player_id = player.player_id
                contained.value     = 0
                contained.position  = wo.position.get()
                contained.velocity  = (0, 0, 0)

                player.set_location((x, y, z))
                protocol.broadcast_contained(contained)

                return x, y, z
