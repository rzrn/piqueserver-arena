from random import uniform
from time import monotonic

from twisted.internet import reactor

from pyspades.contained import IntelDrop, GrenadePacket
from pyspades.collision import vector_collision
from pyspades.common import Vertex3
from pyspades import world

from piqueserver.commands import player_only, command
from piqueserver.config import config

arena_cross_color = (255, 31, 31)

def arena_mark_bombsite(vxl, x, y, z):
    for dx, dy in (0, 0), (-1, -1), (-1, 1), (1, -1), (1, 1):
        vxl.set_point(x + dx, y + dy, z, arena_cross_color)

arena_section                 = config.section("arena")
arena_bomb_fuse               = arena_section.option("bomb_fuse", 45.0).get()
arena_bomb_explosion_duration = arena_section.option("bomb_explosion_duration", 3.0).get()
arena_bomb_defuse_time        = arena_section.option("bomb_defuse_kit", 10.0).get()
arena_defuse_kit_time         = arena_section.option("defuse_kit_time", 5.0).get()

def grenade_effect(protocol, player_id, x, y, z):
    contained           = GrenadePacket()
    contained.player_id = player_id
    contained.value     = 0
    contained.position  = (x, y, z)
    contained.velocity  = (0, 0, 0)

    protocol.broadcast_contained(contained)

def arena_bomb_effect(player, bomb):
    player.grenade_exploded(bomb, dmax = 512)

    x,  y,  z  = bomb.position.get()
    dx, dy, dz = 1.5, 1.5, 1.5

    for k in range(5):
        reactor.callLater(
            uniform(0.25, 0.75),
            grenade_effect,
            player.protocol,
            player.player_id,
            x + uniform(-dx, +dx),
            y + uniform(-dy, +dy),
            z + uniform(-dz, +dz)
        )

def get_defuse_time(player):
    if player.has_defuse_kit:
        return arena_defuse_kit_time
    else:
        return arena_bomb_defuse_time

def arena_try_defuse(player):
    wo = player.world_object
    go = player.team.other.bomb

    if wo is None or go is None:
        return

    if vector_collision(wo.position, go.position):
        if player.bomb_defusal_timer is None:
            player.bomb_defusal_timer = monotonic()
            player.send_chat_warning("DEFUSING")
        elif monotonic() - player.bomb_defusal_timer > get_defuse_time(player):
            player.bomb_defusal_timer = None
            player.has_defuse_kit     = False

            player.team.other.bomb = None

            for connection in player.protocol.players.values():
                connection.send_chat_warning("The bomb has been defused.")
    else:
        if player.bomb_defusal_timer is not None:
            player.bomb_defusal_timer = None

            player.send_chat_error("The bomb was not defused.")

@command('bombplant', 'plant', 'pla')
@player_only
def c_plant(player):
    """
    Plant a bomb
    /bombplant or /plant or /pla
    """
    if wo := player.world_object:
        if player.hp is None or wo.dead:
            return

        protocol = player.protocol
        team = player.team

        ds = protocol.map_info.extensions

        if player.team is protocol.blue_team:
            sites = ds.get('arena_blue_bombsites', None)
        elif player.team is protocol.green_team:
            sites = ds.get('arena_green_bombsites', None)
        else:
            return

        if sites is None:
            return "Your team cannot plant the bomb on this map."

        if not protocol.arena_running:
            return "The round hasn't started yet."

        if team.bomb is not None:
            return "The bomb has already been planted."

        flag = team.other.flag

        if flag is None:
            return

        if flag.player is not player:
            return "You don't have the intel."

        x, y, z = wo.position.get()

        for site in sites:
            xmin, xmax, ymin, ymax, zmin, zmax = site

            if xmin <= x <= xmax and ymin <= y <= ymax and zmin <= z <= zmax:
                flag.set(*protocol.hide_coord)
                flag.player = None

                contained           = IntelDrop()
                contained.player_id = player.player_id
                contained.x         = flag.x
                contained.y         = flag.y
                contained.z         = flag.z

                protocol.broadcast_contained(contained, save = True)

                player.on_flag_drop()

                go = protocol.world.create_object(
                    world.Grenade, arena_bomb_fuse, wo.position.copy(), None,
                    Vertex3(0, 0, 0), protocol.bomb_exploded
                )
                go.team = team

                team.bomb = go

                contained           = GrenadePacket()
                contained.player_id = player.player_id
                contained.value     = arena_bomb_fuse
                contained.position  = wo.position.get()
                contained.velocity  = (0, 0, 0)

                protocol.broadcast_contained(contained)

                delay = arena_bomb_fuse + arena_bomb_explosion_duration

                protocol.arena_limit_timer = max(protocol.arena_limit_timer, protocol.time + delay)
                protocol.arena_timer_delay = max(protocol.arena_timer_delay, monotonic() + delay)

                for connection in protocol.players.values():
                    connection.send_chat_error("The bomb has been planted.")

                return

        return "A bombsite is too far."
