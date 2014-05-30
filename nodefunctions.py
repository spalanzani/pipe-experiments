__author__ = 'rvuine'

from random import *

def scene_importer(netapi, node=None, sheaf='default', **params):

    netapi.import_actors(node.parent_nodespace)
    netapi.import_sensors(node.parent_nodespace)

    # make sure we have a current scene register
    current_scene_registers = netapi.get_nodes(node.parent_nodespace, "CurrentScene")
    if len(current_scene_registers) is 0:
        current_scene_register = netapi.create_node("Register", node.parent_nodespace, "CurrentScene")
        netapi.link(current_scene_register, 'gen', current_scene_register, 'gen')
        #TODO: inject activation
    else:
        current_scene_register = current_scene_registers[0]

    # unlink scene nodes that aren't active any more, except for empty ones
    for linkid, link in current_scene_register.get_gate('gen').outgoing.copy().items():
        if link.target_node.name.startswith("Scene") and \
                link.target_node.activation < 0.5 and \
                len(link.target_node.get_gate('sub').outgoing) > 0:
            netapi.logger.debug("SceneImporter dropping current scene %s.", link.target_node.name)
            netapi.unlink(current_scene_register, 'gen', link.target_node, 'sub')

    # make sure we have a scene node
    scene = None
    for linkid, link in current_scene_register.get_gate('gen').outgoing.items():
        if link.target_node.name.startswith("Scene"):
            scene = link.target_node
            break

    # if we do not have a current scene node and haven't had a major scene change in a while, we're
    # in a new situation and should create a new scene node
    if scene is None and node.get_slot("inh-grow").activation < 0.1 and node.get_slot('scene-inact').activation > 0.95:
        scene = netapi.create_node("Pipe", node.parent_nodespace, "Scene-"+"XXX") #TODO: create ID
        netapi.link(current_scene_register, 'gen', scene, 'sub')
        # signal we have been importing
        node.get_gate("import").gate_function(1)
        netapi.logger.debug("SceneImporter created new scene node %s.", scene.name)

    # if we do not have a current scene node now, we should find the most active scene
    if scene is None:
        bestcandidate = None
        bestactivation = 0
        candidates = netapi.get_nodes_active(node.parent_nodespace, "Pipe", 0.8)
        for candidate in candidates:
            if candidate.name.startswith("Scene") and candidate.activation > bestactivation:
                bestactivation = candidate.activation
                bestcandidate = candidate
        scene = bestcandidate
        if scene is not None:
            netapi.logger.debug("SceneImporter selecting new current scene %s.", scene.name)
            netapi.link(current_scene_register, 'gen', scene, 'sub')

    # if the current scene is still none, we will have to wait for activation to reach a scene node
    if scene is None:
        return

    # check if the scene has been fully recognized, build a list of fovea positions that are taken care of
    sub_field = netapi.get_nodes_field(scene, 'sub')
    all_subs_active = True
    fovea_positions = []
    for sub_node in sub_field:
        if sub_node.activation <= 0.75:
            all_subs_active = False
        fovea_positions.append((sub_node.get_state('x'), sub_node.get_state('y')))

    # if the scene is fully recognized, check if there's something we can add to it in the world
    if all_subs_active and node.get_slot("inh-grow").activation < 0.1:
        # what we're looking for: a feature that is active but hasn't been linked
        # for this, we move the fovea to a position we haven't looked at yet

        # current fovea position and resulting feature name
        x = int(node.get_slot("fov-x").activation)
        y = int(node.get_slot("fov-y").activation)
        featurename = "F(" + str(x) + "/" + str(y)+")"

        netapi.logger.debug("SceneImporter has stable scene, checking if current feature %s is imported.", featurename)

        # now, do we have a feature for the current sensor situation?
        if (x, y) not in fovea_positions:

            netapi.logger.debug("SceneImporter attempting to import %s.", featurename)

            # find the sensors to link
            active_sensors = netapi.get_nodes_active(node.parent_nodespace, 'Sensor', 1, 'gen')
            fovea_sensors_for_new_feature = []
            presence_sensors_for_new_feature = []
            for sensor in active_sensors:
                if sensor.name.startswith("fovea"):
                    fovea_sensors_for_new_feature.append(sensor)
                if sensor.name.startswith("presence"):
                    presence_sensors_for_new_feature.append(sensor)

            # and build the schema for them
            if len(fovea_sensors_for_new_feature) > 0:

                previousfeature = netapi.get_nodes_field(scene, 'sub', ['por'])

                feature = netapi.create_node("Pipe", node.parent_nodespace, featurename)
                feature.set_state('x', x)
                feature.set_state('y', y)
                #feature.set_parameter('sublock', 'fovea')
                netapi.link(scene, 'sub', feature, 'sub')
                netapi.link(feature, 'sur', scene, 'sur')

                #netapi.link(feature, 'gen', feature, 'gen', 0.95) # slowly fading confirmation loop

                if len(previousfeature) == 1:
                    netapi.link(previousfeature[0], 'por', feature, 'por')
                    netapi.link(feature, 'ret', previousfeature[0], 'ret')

                precondition = netapi.create_node("Pipe", node.parent_nodespace, featurename+".Prec")
                netapi.link(feature, 'sub', precondition, 'sub')
                netapi.link(precondition, 'sur', feature, 'sur')

                previous_senseproxy = None
                for sensor in presence_sensors_for_new_feature:
                    senseproxy = netapi.create_node("Pipe", node.parent_nodespace, featurename+".Prx."+sensor.name)
                    netapi.link(precondition, 'sub', senseproxy, 'sub')
                    netapi.link(senseproxy, 'sur', precondition, 'sur')

                    netapi.link(senseproxy, 'gen', senseproxy, 'gen', 0.95)

                    netapi.link_sensor(senseproxy, sensor.name)

                    # omit por/ret, presence isn't ordered
                    #if previous_senseproxy is not None:
                    #    netapi.link(previous_senseproxy, 'por', senseproxy, 'por')
                    #    netapi.link(senseproxy, 'ret', previous_senseproxy, 'ret')
                    previous_senseproxy = senseproxy

                act = netapi.create_node("Pipe", node.parent_nodespace, featurename+".Act")
                netapi.link(feature, 'sub', act, 'sub')
                netapi.link(act, 'sur', feature, 'sur', 0.1)  # fovea action success contribution isn't relevant
                netapi.link(precondition, 'por', act, 'por')
                netapi.link(act, 'ret', precondition, 'ret')

                sense = netapi.create_node("Pipe", node.parent_nodespace, featurename+".Sense")
                netapi.link(feature, 'sub', sense, 'sub')
                netapi.link(sense, 'sur', feature, 'sur')
                netapi.link(act, 'por', sense, 'por')
                netapi.link(sense, 'ret', act, 'ret')

                actproxy = netapi.create_node("Pipe", node.parent_nodespace, featurename+".Prx.fovea")
                netapi.link(act, 'sub', actproxy, 'sub')
                netapi.link(actproxy, 'sur', act, 'sur')

                netapi.link(actproxy, 'gen', actproxy, 'gen', 0.95)     # gen loop
                netapi.link(actproxy, 'sub', actproxy, 'sur')           # fovea act proxies confirm themselves

                netapi.link_actor(actproxy, 'fov_reset')
                if x != 0:
                    netapi.link_actor(actproxy, 'fov_x', x)
                if y != 0:
                    netapi.link_actor(actproxy, 'fov_y', y)

                previous_senseproxy = None
                for sensor in fovea_sensors_for_new_feature:
                    senseproxy = netapi.create_node("Pipe", node.parent_nodespace, featurename+".Prx."+sensor.name)
                    netapi.link(sense, 'sub', senseproxy, 'sub')
                    netapi.link(senseproxy, 'sur', sense, 'sur')

                    netapi.link(senseproxy, 'gen', senseproxy, 'gen', 0.95)

                    netapi.link_sensor(senseproxy, sensor.name)

                    if previous_senseproxy is not None:
                        netapi.link(previous_senseproxy, 'por', senseproxy, 'por')
                        netapi.link(senseproxy, 'ret', previous_senseproxy, 'ret')
                    previous_senseproxy = senseproxy

                netapi.logger.debug("SceneImporter imported %s.", featurename)

        # finally some fovea randomisation for the next round if no schema is accessing the fovea right now
        if not netapi.is_locked('fovea'):
            fovea_position_candidate = (randint(-2, 2), randint(-2, 2))
            i = 10
            while fovea_position_candidate not in fovea_positions and i < 10:
                i += 1
                fovea_position_candidate = (randint(-2, 2), randint(-2, 2))

            if fovea_position_candidate not in fovea_positions:

                netapi.logger.debug("Randomizing fovea to %i/%i", fovea_position_candidate[0], fovea_position_candidate[1])

                node.get_gate("reset").gate_function(1)
                node.get_gate("fov_x").gate_function(fovea_position_candidate[0])
                node.get_gate("fov_y").gate_function(fovea_position_candidate[1])


def inactivity_monitor(netapi, node=None, sheaf='default', **params):

    inact = node.get_slot('inact').activation
    reset = node.get_slot('reset').activation

    if reset > 0:
        inact = 0;
    else:
        name_prefix = node.get_parameter('name')
        if name_prefix is None or len(name_prefix) == 0 or name_prefix == '*':
            node.set_parameter('name', 'Scene')  # TODO: replace 'Scene' with '*' to make the module generic
            name_prefix = 'Scene'  # TODO: same here, once TOL-18 is resolved

        is_one_of_them_active = False
        nodes = netapi.get_nodes(node.parent_nodespace, name_prefix)
        for candidate in nodes:
            if candidate.activation > 0.5:
                is_one_of_them_active = True
                break

        if not is_one_of_them_active:
            inact += 0.1
        else:
            inact = 0

    node.get_gate('inact').gate_function(inact)