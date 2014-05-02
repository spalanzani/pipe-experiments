__author__ = 'rvuine'

from random import *

def scene_importer(netapi, node=None, sheaf='default', **params):

    netapi.import_actors(node.parent_nodespace)
    netapi.import_sensors(node.parent_nodespace)

    # make sure we have a scene node
    scene_nodes = netapi.get_nodes(node.parent_nodespace, "Scene")
    if len(scene_nodes) is 0:
        scene = netapi.create_node("Pipe", node.parent_nodespace, "Scene")
    else:
        scene = scene_nodes[0]

    # check if the scene has been fully recognized, build a list of fovea positions that are taken care of
    sub_field = netapi.get_nodes_field(scene, 'sub')
    all_subs_active = True
    fovea_positions = []
    for sub_node in sub_field:
        if sub_node.activation <= 0:
            all_subs_active = False
        act = netapi.get_nodes_field(sub_node, 'sub', ['ret'])[0]
        fovea_positions.append((act.get_state('x'), act.get_state('y')))

    # if the scene is fully recognized, check if there's something we can add to it in the world
    if all_subs_active:
        # what we're looking for: a feature that is active but hasn't been linked
        # for this, we move the fovea to a position we haven't looked at yet

        # current fovea position and resulting feature name
        x = int(node.get_slot("fov-x").activation)
        y = int(node.get_slot("fov-y").activation)
        featurename = "F-" + str(x) + "-" + str(y)

        # now, do we have a feature for the current sensor situation?
        if (x, y) not in fovea_positions:

            # find the sensors to link
            active_sensors = netapi.get_nodes_active(node.parent_nodespace, 'Sensor', 1, 'gen')
            sensor_for_new_feature = []
            for sensor in active_sensors:
                if sensor.name.startswith("fovea"):
                    sensor_for_new_feature.append(sensor)

            # and build the schema for them
            if len(sensor_for_new_feature) > 0:
                previousfeature = netapi.get_nodes_field(scene, 'sub', 'ret')

                feature = netapi.create_node("Pipe", node.parent_nodespace, featurename)
                feature.set_parameter('sublock', 'fovea')
                netapi.link(scene, 'sub', feature, 'sub')
                netapi.link(feature, 'sur', scene, 'sur')

                if len(previousfeature) == 1:
                    netapi.link(previousfeature[0], 'por', feature, 'por')
                    netapi.link(feature, 'ret', previousfeature[0], 'ret')

                act = netapi.create_node("Pipe", node.parent_nodespace, featurename+"-Act")
                act.set_state('x', x)
                act.set_state('y', y)
                netapi.link(feature, 'sub', act, 'sub')
                netapi.link(act, 'sur', feature, 'sur')

                sense = netapi.create_node("Pipe", node.parent_nodespace, featurename+"-Sense")
                netapi.link(feature, 'sub', sense, 'sub')
                netapi.link(sense, 'sur', feature, 'sur')

                netapi.link(act, 'por', sense, 'por')
                netapi.link(sense, 'ret', act, 'ret')

                actproxy = netapi.create_node("Pipe", node.parent_nodespace, featurename+"-Prox-fovea")
                netapi.link(act, 'sub', actproxy, 'sub')
                netapi.link(actproxy, 'sur', act, 'sur')

                netapi.link_actor(actproxy, 'fov_reset')
                netapi.link_actor(actproxy, 'fov_x', x)
                netapi.link_actor(actproxy, 'fov_y', y)

                previous_senseproxy = None
                for sensor in sensor_for_new_feature:
                    senseproxy = netapi.create_node("Pipe", node.parent_nodespace, featurename+"-Prox-"+sensor.name)
                    netapi.link(sense, 'sub', senseproxy, 'sub')
                    netapi.link(senseproxy, 'sur', sense, 'sur')

                    netapi.link_sensor(senseproxy, sensor.name)

                    if previous_senseproxy is not None:
                        netapi.link(previous_senseproxy, 'por', senseproxy, 'por')
                        netapi.link(senseproxy, 'ret', previous_senseproxy, 'ret')
                    previous_senseproxy = senseproxy

        # finally some fovea randomisation for the next round if no schema is accessing the fovea right now
        if not netapi.is_locked('fovea'):
            fovea_position_candidate = (randint(-2, 2), randint(-2, 2))
            i = 10
            while fovea_position_candidate not in fovea_positions and i < 10:
                i += 1
                fovea_position_candidate = (randint(-2, 2), randint(-2, 2))

            if fovea_position_candidate not in fovea_positions:
                node.get_gate("reset").gate_function(1)
                node.get_gate("fov_x").gate_function(fovea_position_candidate[0])
                node.get_gate("fov_y").gate_function(fovea_position_candidate[1])
