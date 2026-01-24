# Copyright © 2012, 2017 Yourself
# Copyright © 2012 duckslingers
# Copyright © 2012 triplefox
# Copyright © 2016–2018 Samuel Walladge
# Copyright © 2017 1AmYF
# Copyright © 2017, 2019 NotAFile
# Copyright © 2017–2018 godwhoa
# Copyright © 2022 DryByte
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

from itertools import product
from time import monotonic
from random import choice
import math

from twisted.internet import reactor

from pyspades.contained import (
    HitPacket, BlockAction, KillAction, IntelPickup,
    IntelDrop, GrenadePacket, WeaponInput
)

from pyspades.packet import register_packet_handler
from pyspades.collision import vector_collision
from pyspades.player import ServerConnection
from pyspades.common import Vertex3
from pyspades.constants import *
from pyspades import world

from piqueserver.config import config

from arenalib.defusal import (
    arena_try_defuse, arena_bomb_effect,
    arena_bomb_explosion_duration
)
from arenalib.common import ArenaException, wall_tunnel

arena_section = config.section("arena")

# How long should be spent between rounds in arena (seconds)
arena_break_time = arena_section.option("break_time", 10.0).get()

assert 5.0 <= arena_break_time

# Maximum duration that a round can last (seconds). Set to 0 to disable the time limit
arena_time_limit = arena_section.option("time_limit", 120.0).get()

# Delay before first round in game (seconds)
arena_map_change_delay = arena_section.option("map_change_delay", 15.0).get()

def get_team_alive_count(team):
    return sum(player.is_alive() for player in team.get_players())

def is_team_dead(team):
    return all(not player.is_alive() for player in team.get_players())

def apply_script(protocol, connection, config):
    class ArenaConnection(connection):
        last_spadenade_usage = 0
        last_death_time      = 0
        grenade_unpin_time   = 0
        bomb_defusal_timer   = None
        has_defuse_kit       = False

        def is_alive(self):
            if wo := self.world_object:
                return wo.dead is False
            else:
                return False

        def remove_last_killer(self):
            protocol = self.protocol

            if team := self.team:
                if team.last_killer is self:
                    team.last_killer = None

        def on_disconnect(self):
            self.remove_last_killer()

            connection.on_disconnect(self)

        def set_team(self, team):
            if team is self.team:
                return

            self.remove_last_killer()

            self.drop_flag()
            self.hp = None

            if wo := self.weapon_object:
                wo.reset()

            if wo := self.world_object:
                wo.dead = True

            old_team, self.team = self.team, team

            self.on_team_changed(old_team)

            contained              = KillAction()
            contained.kill_type    = TEAM_CHANGE_KILL
            contained.killer_id    = self.player_id
            contained.player_id    = self.player_id
            contained.respawn_time = self.get_respawn_time() + 1

            self.protocol.broadcast_contained(contained, save = True)

            self.respawn()

        def on_secondary_fire_set(self, secondary):
            connection.on_secondary_fire_set(self, secondary)

            if secondary and self.tool == SPADE_TOOL:
                if self.protocol.arena_running is False:
                    wall_tunnel(self)

        def on_tool_set_attempt(self, tool):
            if connection.on_tool_set_attempt(self, tool) is False:
                return False

            if self.tool == SPADE_TOOL and self.world_object.secondary_fire:
                self.last_spadenade_usage = monotonic()

            if self.tool != tool:
                if tool == GRENADE_TOOL and self.world_object.primary_fire:
                    self.grenade_unpin_time = monotonic()
                else:
                    self.grenade_unpin_time = 0

        def on_hit(self, damage, player, kill_type, grenade):
            # Disallow spade-teamkill to prevent accidental kills while digging trenches.
            if kill_type == MELEE_KILL and player.team is self.team:
                return False

            if self.protocol.arena_running is False:
                self.send_chat_error("The round hasn't started yet")

                return False

            return connection.on_hit(self, damage, player, kill_type, grenade)

        def on_kill(self, killer, kill_type, grenade):
            retval = connection.on_kill(self, killer, kill_type, grenade)

            if retval is False: return False

            if killer is not None and killer.team is not self.team:
                killer.team.last_killer = killer

            self.last_death_time = monotonic()

            if self.tool == GRENADE_TOOL and self.grenade_unpin_time > 0:
                dt = max(0, monotonic() - self.grenade_unpin_time)
                fuse = max(0, 3.0 - dt)

                protocol = self.protocol

                grenade = protocol.world.create_object(
                    world.Grenade, fuse,
                    self.world_object.position.copy(), None,
                    Vertex3(0, 0, 0), self.grenade_exploded
                )
                grenade.team = self.team
    
                contained           = GrenadePacket()
                contained.player_id = self.player_id
                contained.value     = fuse
                contained.position  = grenade.position.get()
                contained.velocity  = grenade.velocity.get()
    
                protocol.broadcast_contained(contained)

                protocol.arena_timer_delay = max(protocol.arena_timer_delay, monotonic() + fuse)

            self.grenade_unpin_time = 0

            return retval

        def get_respawn_time(self):
            if self.team.spectator:
                return 0
            elif self.protocol.arena_running:
                ds = self.protocol.map_info.extensions
                return ds.get('arena_respawn_time', -1)
            else:
                return 0

        assert connection.respawn is ServerConnection.respawn

        def respawn(self):
            if self.spawn_call is not None:
                return

            respawn_time = self.get_respawn_time()

            if 0 < respawn_time:
                self.spawn_call = reactor.callLater(respawn_time, self.spawn)
            elif respawn_time < 0:
                return
            else:
                self.spawn()

        def on_spawn(self, pos):
            retval = connection.on_spawn(self, pos)

            self.bomb_defusal_timer = None
            self.has_defuse_kit     = False

            if self.get_respawn_time() < 0:
                self.kill()
            else:
                return retval

        def on_spawn_location(self, pos):
            x, y, z = choice(self.team.arena_spawns)
            return x + 0.5, y + 0.5, self.protocol.map.get_z(x, y, z) - 3

        def on_flag_take(self):
            ds = self.protocol.map_info.extensions

            if self.protocol.arena_running:
                if self.team.other.flag.id == BLUE_FLAG:
                    return 'arena_blue_flag' in ds

                if self.team.other.flag.id == GREEN_FLAG:
                    return 'arena_green_flag' in ds

            return False

        def capture_flag(self):
            protocol = self.protocol

            if team := self.team:
                if team.other.flag.player is not self:
                    return

                connection.capture_flag(self)

                for player in protocol.players.values():
                    player.send_chat_status(
                        "{} team wins the round".format(team.name)
                    )

                protocol.begin_arena_countdown(protocol.arena_break_time)
                protocol.arena_spawn()

        def drop_flag(self):
            protocol = self.protocol

            for flag in protocol.team_1.flag, protocol.team_2.flag:
                if flag.player is self:
                    ds = protocol.map_info.extensions

                    has_blue  = flag.id == BLUE_FLAG  and 'arena_blue_flag'  in ds
                    has_green = flag.id == GREEN_FLAG and 'arena_green_flag' in ds

                    if has_blue or has_green:
                        r = flag.player.world_object.position

                        x, y, z = protocol.map.get_safe_coords(r.x, r.y, r.z)
                        loc = x, y, protocol.map.get_z(x, y, z)
                    else:
                        loc = protocol.hide_coord

                    flag.set(*loc)
                    flag.player = None

                    contained           = IntelDrop()
                    contained.player_id = self.player_id
                    contained.x         = flag.x
                    contained.y         = flag.y
                    contained.z         = flag.z

                    protocol.broadcast_contained(contained, save = True)

                    self.on_flag_drop()

        def on_refill(self):
            retval = connection.on_refill(self)

            ds = self.protocol.map_info.extensions
            arena_has_refill = ds.get('arena_has_refill', False)

            if self.protocol.arena_running and arena_has_refill is False:
                return False

            return retval

        def on_grenade(self, fuse):
            self.grenade_unpin_time = 0

            if self.protocol.arena_running:
                if monotonic() - self.last_spadenade_usage < 1.0:
                    self.on_spadenade_attempt()

                    return False

                return connection.on_grenade(self, fuse)
            else:
                return False

        def on_grenade_thrown(self, grenade):
            protocol = self.protocol
            protocol.arena_timer_delay = max(protocol.arena_timer_delay, monotonic() + grenade.fuse)

            connection.on_grenade_thrown(self, grenade)

        def on_spadenade_attempt(self):
            protocol = self.protocol

            grenade = protocol.world.create_object(
                world.Grenade, 0, self.world_object.position.copy(), None,
                Vertex3(0, 0, 0), self.grenade_exploded
            )
            grenade.team = self.team

            contained           = GrenadePacket()
            contained.player_id = self.player_id
            contained.value     = 0
            contained.position  = grenade.position.get()
            contained.velocity  = grenade.velocity.get()

            protocol.broadcast_contained(contained)
            protocol.broadcast_chat("{} spadenaded himself".format(self.name))

        def grenade_destroy(self, xf, yf, zf):
            if xf < 0 or xf > 512 or yf < 0 or yf > 512 or zf < 0 or zf > 64:
                return

            x, y, z = math.floor(xf), math.floor(yf), math.floor(zf)

            protocol = self.protocol
            M = protocol.map

            if self.on_block_destroy(x, y, z, GRENADE_DESTROY) is not False:
                for X, Y, Z in product(range(x - 1, x + 2), range(y - 1, y + 2), range(z - 1, z + 2)):
                    count = M.destroy_point(X, Y, Z)

                    if count > 0:
                        self.total_blocks_removed += count
                        self.on_block_removed(X, Y, Z)

                contained           = BlockAction()
                contained.x         = x
                contained.y         = y
                contained.z         = z
                contained.value     = GRENADE_DESTROY
                contained.player_id = self.player_id

                protocol.broadcast_contained(contained, save = True)
            else:
                for X, Y, Z in product(range(x - 1, x + 2), range(y - 1, y + 2), range(z - 1, z + 2)):
                    if self.on_block_destroy(X, Y, Z, DESTROY_BLOCK) is not False:
                        count = M.destroy_point(X, Y, Z)

                        if count > 0:
                            self.total_blocks_removed += count
                            self.on_block_removed(X, Y, Z)

                            contained           = BlockAction()
                            contained.x         = X
                            contained.y         = Y
                            contained.z         = Z
                            contained.value     = DESTROY_BLOCK
                            contained.player_id = self.player_id

                            protocol.broadcast_contained(contained, save = True)

            protocol.update_entities()

        def grenade_exploded(self, grenade, dmax = None):
            if self.name is None:
                return

            dmax = dmax or self.protocol.grenade_blast_radius

            position = grenade.position
            xf, yf, zf = position.get()

            self.grenade_destroy(xf, yf, zf)

            protocol = self.protocol

            for player in protocol.connections.values():
                if not player.hp or player.name is None or player.team.spectator:
                    continue

                if not protocol.friendly_fire and player is not self and player.team is grenade.team:
                    continue

                if wo := player.world_object:
                    dx = wo.position.x - xf
                    dy = wo.position.y - yf
                    dz = wo.position.z - zf

                    damage = 0

                    nmax = 3 * dmax * dmax

                    if abs(dx) < dmax and abs(dy) < dmax and abs(dz) < dmax and wo.can_see(xf, yf, min(62.9, zf)):
                        norm = dx * dx + dy * dy + dz * dz
                        damage = min(nmax / norm, 100) if norm > 1e-3 else 100

                    if damage <= 0:
                        continue

                    self.on_unvalidated_hit(damage, player, GRENADE_KILL, grenade)

                    returned = self.on_hit(damage, player, GRENADE_KILL, grenade)

                    if returned == False:
                        continue
                    elif returned is not None:
                        damage = returned

                    player.set_hp(
                        player.hp - damage, self,
                        hit_indicator = position.get(),
                        kill_type = GRENADE_KILL,
                        grenade = grenade
                    )

        def on_fall(self, damage):
            if self.protocol.arena_running:
                return connection.on_fall(self, damage)
            else:
                return False

        @register_packet_handler(HitPacket)
        def on_hit_recieved(self, contained):
            world_object = self.world_object

            if world_object is None:
                return # already died

            value = contained.value
            is_melee = value == MELEE

            if is_melee:
                kill_type = MELEE_KILL
            elif contained.value == HEAD:
                kill_type = HEADSHOT_KILL
            else:
                kill_type = WEAPON_KILL

            if player := self.protocol.players.get(contained.player_id):
                if player.world_object is None:
                    return # something is wrong

                v1 = world_object.position
                v2 = player.world_object.position

                if is_melee:
                    hit_amount = self.protocol.melee_damage
                else:
                    hit_amount = self.weapon_object.get_damage(value, v1, v2)

                self.on_unvalidated_hit(hit_amount, player, kill_type, None)

                hit_time = monotonic() - self.latency / 1000
                if not self.hp and self.last_death_time < hit_time:
                    return

                if not is_melee and self.weapon_object.is_empty():
                    return

                valid_hit = world_object.validate_hit(
                    player.world_object, value,
                    HIT_TOLERANCE, self.rubberband_distance
                )

                if not valid_hit:
                    return

                if is_melee:
                    if not vector_collision(v1, v2, MELEE_DISTANCE):
                        return

                    x, y, z = v2.get()
                    if not world_object.can_see(x, y, z):
                        return

                retval = self.on_hit(hit_amount, player, kill_type, None)

                if retval is False:
                    return
                elif retval is not None:
                    hit_amount = retval

                player.hit(hit_amount, self, kill_type)

        @register_packet_handler(WeaponInput)
        def on_weapon_input_recieved(self, contained):
            if wo := self.world_object:
                if wo.primary_fire != contained.primary and self.tool == GRENADE_TOOL:
                    if contained.primary:
                        self.grenade_unpin_time = monotonic()
                    else:
                        self.grenade_unpin_time = 0

            connection.on_weapon_input_recieved(self, contained)

        def try_give_defuse_kit(self):
            if self.has_defuse_kit:
                return
            else:
                self.has_defuse_kit = True

                self.send_chat_warning("You've been given a defuse kit.")

        def check_refill(self):
            if self.protocol.arena_running is False:
                return

            if self.team is None:
                return

            ds = self.protocol.map_info.extensions

            green_has_bomb = 'arena_green_bombsites' in ds
            blue_has_bomb  = 'arena_blue_bombsites'  in ds

            if self.team is self.protocol.blue_team and green_has_bomb:
                self.try_give_defuse_kit()
            elif self.team is self.protocol.green_team and blue_has_bomb:
                self.try_give_defuse_kit()
            else:
                connection.check_refill(self)

    class ArenaProtocol(protocol):
        game_mode = CTF_MODE

        # Coordinates to hide the tent and the intel
        hide_coord = (math.inf, math.inf, 128)

        grenade_blast_radius = None

        def __init__(self, *w, **kw):
            protocol.__init__(self, *w, **kw)

            self.arena_timer_delay = 0

            self.team_spectator.last_killer = None

            self.team_1.last_killer = None
            self.team_2.last_killer = None

            self.team_1.bomb = None
            self.team_2.bomb = None

            self.arena_running          = False
            self.arena_counting_down    = False
            self.arena_countdown_timers = None
            self.arena_time_limit       = 0
            self.arena_limit_timer      = math.inf
            self.arena_heartbeat_rate   = math.inf

            self.time          = monotonic()
            self.stopwatch     = 0
            self.players_alive = 0

        def on_world_update(self):
            dt = monotonic() - self.time
            self.time += dt

            self.stopwatch += dt
            if self.arena_heartbeat_rate <= self.stopwatch:
                self.stopwatch = 0

                if map_info := self.map_info:
                    if map_on_arena_heartbeat := getattr(map_info.info, 'on_arena_heartbeat', None):
                        map_on_arena_heartbeat(self, self.time)

                if self.arena_running and self.arena_timer_delay <= self.time:
                    players_alive = sum(player.is_alive() for player in self.players.values())

                    if self.players_alive == players_alive:
                        self.check_round_end()

                    self.players_alive = players_alive

                    if self.arena_limit_timer <= self.time:
                        self.on_arena_time_limit()

                for player in self.players.values():
                    if player.hp is None or player.name is None:
                        continue

                    if player.team is None or player.team.spectator:
                        continue

                    arena_try_defuse(player)

        def bomb_exploded(self, bomb):
            if self.team_1.bomb is not bomb and self.team_2.bomb is not bomb:
                if team := bomb.team: self.arena_win(team.other)

                return

            bomb.team.bomb = None

            if player := self.get_arbitrary_player(bomb.team):
                arena_bomb_effect(player, bomb)

            reactor.callLater(arena_bomb_explosion_duration, self.arena_win, bomb.team)

        def check_round_end(self, killer = None):
            P1 = is_team_dead(self.team_1)
            P2 = is_team_dead(self.team_2)

            if P1 and P2:
                self.broadcast_chat('Draw')

                self.begin_arena_countdown(self.arena_break_time)
                self.arena_spawn()
            elif P1:
                self.arena_win(self.team_2)
            elif P2:
                self.arena_win(self.team_1)
            else:
                return

        def on_arena_time_limit(self):
            ds = self.map_info.extensions

            self.arena_limit_timer = math.inf

            green_team     = self.green_team
            blue_team      = self.blue_team
            green_count    = get_team_alive_count(green_team)
            blue_count     = get_team_alive_count(blue_team)
            green_has_bomb = 'arena_green_bombsites' in ds
            blue_has_bomb  = 'arena_blue_bombsites'  in ds

            if blue_has_bomb and not green_has_bomb:
                self.arena_win(green_team)
            elif green_has_bomb and not blue_has_bomb:
                self.arena_win(blue_team)
            elif green_count > blue_count:
                self.arena_win(green_team)
            elif green_count < blue_count:
                self.arena_win(blue_team)
            else:
                self.broadcast_chat('Tie')

                self.begin_arena_countdown(self.arena_break_time)
                self.arena_spawn()

        def get_arbitrary_player(self, team):
            if player := team.last_killer:
                return player
            else:
                rem = list(player for player in team.get_players() if player.hp is not None)
                if len(rem) <= 0: rem = list(team.get_players()) # prefer alive players

                if len(rem) <= 0: return # team is empty, nothing to return

                player = choice(rem)

                if player.team is None:
                    return

                if player.team.other is None:
                    return

                return player

        def arena_win(self, team):
            if not self.arena_running:
                return

            if player := team.other.flag.player:
                killer = player
            else:
                killer = self.get_arbitrary_player(team)
                if killer is None: return

                flag        = killer.team.other.flag
                flag.player = killer

                contained           = IntelPickup()
                contained.player_id = killer.player_id

                self.broadcast_contained(contained, save = True)

            killer.capture_flag()

        def on_map_change(self, M):
            self.team_1.last_killer = None
            self.team_2.last_killer = None

            self.grenade_blast_radius = 128.0

            extensions = self.map_info.extensions

            self.arena_map_change_delay = extensions.get('arena_map_change_delay', arena_map_change_delay)
            self.arena_break_time       = extensions.get('arena_break_time', arena_break_time)
            self.arena_time_limit       = extensions.get('arena_time_limit', arena_time_limit)
            self.arena_heartbeat_rate   = extensions.get('arena_heartbeat_rate', 1.0)

            if 'arena_green_spawns' in extensions:
                self.green_team.arena_spawns = extensions['arena_green_spawns']
            elif 'arena_green_spawn' in extensions:
                self.green_team.arena_spawns = (extensions['arena_green_spawn'],)
            else:
                raise ArenaException('No arena_green_spawns given in map metadata.')

            if 'arena_blue_spawns' in extensions:
                self.blue_team.arena_spawns = extensions['arena_blue_spawns']
            elif 'arena_blue_spawn' in extensions:
                self.blue_team.arena_spawns = (extensions['arena_blue_spawn'],)
            else:
                raise ArenaException('No arena_blue_spawns given in map metadata.')

            if timers := self.arena_countdown_timers:
                for timer in timers:
                    if timer.active():
                        timer.cancel()

            self.arena_counting_down = False
            self.begin_arena_countdown(self.arena_map_change_delay)

            self.arena_spawn()

            return protocol.on_map_change(self, M)

        def arena_spawn(self):
            if self.map_info.extensions.get('swap_spawns', False):
                self.blue_team.arena_spawns, self.green_team.arena_spawns = self.green_team.arena_spawns, self.blue_team.arena_spawns

            for team in self.blue_team, self.green_team:
                if team is None or team.flag is None or team.base is None:
                    continue

                if player := team.flag.player:
                    player.drop_flag()

                team.set_flag().update()
                team.set_base().update()

                if go := team.bomb:
                    go.team   = None
                    team.bomb = None

            for player in self.players.values():
                if player.team.spectator:
                    continue

                x, y, z = choice(player.team.arena_spawns)
                z = self.map.get_z(x, y, z) - 3

                if player.world_object is not None and player.world_object.dead:
                    player.spawn((x + 0.5, y + 0.5, z))
                else:
                    player.set_location((x, y, z))
                    player.refill()

        def refill_all(self):
            for player in self.players.values():
                if player.team.spectator:
                    continue

                player.refill()

        def game_start_warning(self, seconds):
            for team in self.green_team, self.blue_team:
                if team.count() == 0:
                    return

            o = self.map_info.info

            if map_on_arena_warning := getattr(o, 'on_arena_warning', None):
                warning = map_on_arena_warning(self, seconds)
            else:
                warning = "{} seconds".format(seconds)

            if warning is not None:
                for player in self.players.values():
                    player.send_chat_warning(warning)

        def begin_arena_countdown(self, delay):
            if delay <= 0.0:
                self.begin_arena(await_players = False)
                return

            if math.isfinite(self.arena_limit_timer):
                self.arena_limit_timer = math.inf

            if self.arena_counting_down:
                return

            self.arena_running       = False
            self.arena_counting_down = True
            self.building            = False

            o = self.map_info.info

            if map_on_arena_end := getattr(o, 'on_arena_end', None):
                map_on_arena_end(self)

            self.arena_countdown_timers = [
                reactor.callLater(delay - 5, self.game_start_warning, 5),
                reactor.callLater(delay, self.begin_arena)
            ]

        def begin_arena(self, await_players = True):
            self.arena_counting_down = False

            if await_players is True:
                for team in self.green_team, self.blue_team:
                    if team.count() == 0:
                        self.begin_arena_countdown(self.arena_break_time)
                        return

            self.arena_running = True
            self.building      = self.map_info.extensions.get('building_enabled', True)

            o = self.map_info.info

            if map_on_arena_begin := getattr(o, 'on_arena_begin', None):
                map_on_arena_begin(self)

            self.refill_all()

            if self.arena_time_limit > 0:
                self.broadcast_chat(
                    "There is a time limit of {:.0f} seconds for this round".format(self.arena_time_limit)
                )

                self.arena_limit_timer = self.time + self.arena_time_limit
            else:
                self.arena_limit_timer = math.inf

        def get_drop_location(self, loc):
            x, y, z = self.map.get_safe_coords(*loc)
            return x, y, self.map.get_z(x, y, z)

        def on_base_spawn(self, x, y, z, base, entity_id):
            ds = self.map_info.extensions

            if entity_id == BLUE_BASE:
                if loc := ds.get('arena_blue_base', None):
                    return self.get_drop_location(loc)

            if entity_id == GREEN_BASE:
                if loc := ds.get('arena_green_base', None):
                    return self.get_drop_location(loc)

            return self.hide_coord

        def on_flag_spawn(self, x, y, z, flag, entity_id):
            ds = self.map_info.extensions

            if entity_id == BLUE_FLAG:
                if loc := ds.get('arena_blue_flag', None):
                    return self.get_drop_location(loc)

            if entity_id == GREEN_FLAG:
                if loc := ds.get('arena_green_flag', None):
                    return self.get_drop_location(loc)

            return self.hide_coord

    return ArenaProtocol, ArenaConnection
