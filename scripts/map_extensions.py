"""
Provides extensions to the map metadata (e.g. water damage).

.. codeauthor:: triplefox, mat^2
"""

def apply_boundary_damage(player, o):
    x, y, z = player.world_object.position.get()

    xmin = o.get('left',   0)
    xmax = o.get('right',  512)
    ymin = o.get('top',    0)
    ymax = o.get('bottom', 512)
    zmin = o.get('near',  -64)
    zmax = o.get('far',   +64)

    if x <= xmin or x >= xmax or y <= ymin or y >= ymax or z <= zmin or z >= zmax:
        player.environment_hit(o.get('damage', 100))

def apply_script(protocol, connection, config):
    class MapExtensionConnection(connection):
        def on_grenade_thrown(self, grenade):
            connection.on_grenade_thrown(self, grenade)

            o = self.protocol.map_info.info

            if map_on_grenade_thrown := getattr(o, 'on_grenade_thrown', None):
                map_on_grenade_thrown(self, grenade)

        def on_kill(self, killer, kill_type, grenade):
            connection.on_kill(self, killer, kill_type, grenade)

            o = self.protocol.map_info.info

            if map_on_kill := getattr(o, 'on_kill', None):
                map_on_kill(self, killer, kill_type, grenade)

        def on_flag_capture(self):
            connection.on_flag_capture(self)

            o = self.protocol.map_info.info

            if map_on_flag_capture := getattr(o, 'on_flag_capture', None):
                map_on_flag_capture(self)

        def on_block_build(self, x, y, z):
            connection.on_block_build(self, x, y, z)

            o = self.protocol.map_info.info

            if map_on_block_build := getattr(o, 'on_block_build', None):
                map_on_block_build(self, x, y, z)

        def on_line_build(self, points):
            connection.on_line_build(self, points)

            o = self.protocol.map_info.info

            if map_on_line_build := getattr(o, 'on_line_build', None):
                map_on_line_build(self, points)

        def on_block_removed(self, x, y, z):
            connection.on_block_removed(self, x, y, z)

            o = self.protocol.map_info.info

            if map_on_block_removed := getattr(o, 'on_block_removed', None):
                map_on_block_removed(self, x, y, z)

        def on_position_update(self):
            i = self.protocol.map_info

            extensions = i.extensions

            if water_damage := extensions.get('water_damage'):
                if self.world_object.position.z >= 61:
                    self.environment_hit(water_damage)

            if ds := extensions.get('boundary_damage'):
                apply_boundary_damage(self, ds)

            if self.team is self.protocol.blue_team:
                if ds1 := extensions.get('boundary_blue_team'):
                    apply_boundary_damage(self, ds1)

            if self.team is self.protocol.green_team:
                if ds2 := extensions.get('boundary_green_team'):
                     apply_boundary_damage(self, ds2)

            if teleporters := extensions.get('teleporters'):
                x, y, z = self.world_object.position.get()

                for teleporter in teleporters:
                    xmin = teleporter['xmin']
                    xmax = teleporter['xmax']
                    ymin = teleporter['ymin']
                    ymax = teleporter['ymax']
                    zmin = teleporter['zmin']
                    zmax = teleporter['zmax']
                    xout = teleporter['xout']
                    yout = teleporter['yout']
                    zout = teleporter['zout']

                    if xmin <= x <= xmax and ymin <= y <= ymax and zmin <= z <= zmax:
                        self.set_location((xout + 0.5, yout + 0.5, zout))

                        break

            o = i.info

            if map_on_position_update := getattr(o, 'on_position_update', None):
                map_on_position_update(self)

            if is_inaccessible := getattr(o, 'is_inaccessible', None):
                x, y, z = self.world_object.position.get()

                if is_inaccessible(x, y, z):
                    self.environment_hit(100)

            connection.on_position_update(self)

        def environment_hit(self, value):
            if self.hp is None:
                return

            if value < 0 and 100 <= self.hp:  # do nothing at max health
                return

            self.set_hp(self.hp - value)

        def on_command(self, command, parameters):
            disabled = self.protocol.map_info.extensions.get('disabled_commands', [])
            if command in disabled:
                self.send_chat("Command '{}' disabled for this map".format(command))
                return

            return connection.on_command(self, command, parameters)

    return protocol, MapExtensionConnection
