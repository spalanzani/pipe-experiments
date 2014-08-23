__author__ = 'rvuine'

import random
import time


def scene_importer(netapi, node=None, sheaf='default', **params):

    netapi.import_actors(node.parent_nodespace)
    netapi.import_sensors(node.parent_nodespace)

    # make sure we have an importer scene register
    importer_scene_registers = netapi.get_nodes(node.parent_nodespace, "ImporterScene")
    if len(importer_scene_registers) is 0:
        importer_scene_register = netapi.create_node("Register", node.parent_nodespace, "ImporterScene")
    else:
        importer_scene_register = importer_scene_registers[0]

    # make sure we have an importer scene node
    scene = None
    for linkid, link in importer_scene_register.get_gate('gen').outgoing.items():
        if link.target_node.name.startswith("Scene"):
            scene = link.target_node
            break

    # when triggered, we create a new scene to add features to
    if node.get_slot("newscene").activation >= 1:
        scene = netapi.create_node("Pipe", node.parent_nodespace, "Scene-"+str(time.time()))
        netapi.unlink(importer_scene_register, 'gen')
        netapi.link(importer_scene_register, 'gen', scene, 'sub')
        # signal we have been importing
        node.get_gate("import").gate_function(1)
        netapi.logger.debug("SceneImporter created new scene node %s.", scene.name)

    # if the current scene is still none, we will have to wait for activation to reach a scene node
    if scene is None:
        return

    # check if the scene has been fully recognized, build a list of fovea positions that are taken care of
    sub_field = netapi.get_nodes_in_gate_field(scene, 'sub')
    all_subs_active = True
    fovea_positions = []
    for sub_node in sub_field:
        if sub_node.activation <= 0.75:
            all_subs_active = False
        fovea_positions.append((sub_node.get_state('x'), sub_node.get_state('y')))

    # if the scene is fully recognized, check if there's something we can add to it in the world
    if all_subs_active and node.get_slot("dontgrow").activation < 1:
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

                previousfeature = netapi.get_nodes_in_gate_field(scene, 'sub', ['por'])

                feature = netapi.create_node("Pipe", node.parent_nodespace, featurename)
                feature.set_state('x', x)
                feature.set_state('y', y)
                #feature.set_parameter('sublock', 'fovea')
                netapi.link_with_reciprocal(scene, feature, "subsur")

                if len(previousfeature) == 1:
                    netapi.link_with_reciprocal(previousfeature[0], feature, "porret")

                precondition = netapi.create_node("Pipe", node.parent_nodespace, featurename+".Prec")
                netapi.link_with_reciprocal(feature, precondition, "subsur")

                recognition = netapi.create_node("Pipe", node.parent_nodespace, featurename+".Rec")
                netapi.link_with_reciprocal(feature, recognition, "subsur")

                netapi.link_full([precondition, recognition])

                #create precondition classificator
                prec_features = []
                for sensor in presence_sensors_for_new_feature:
                    prec_feature = netapi.create_node("Pipe", node.parent_nodespace, featurename+"."+sensor.name)
                    prec_features.append(prec_feature)
                    netapi.link_with_reciprocal(precondition, prec_feature, "subsur")

                    senseproxy = netapi.create_node("Pipe", node.parent_nodespace, featurename+"."+sensor.name+".Prx")
                    netapi.link_with_reciprocal(prec_feature, senseproxy, "subsur")

                    netapi.link_sensor(senseproxy, sensor.name)

                netapi.link_full(prec_features)

                # create recognition script
                act = netapi.create_node("Pipe", node.parent_nodespace, featurename+".Act")
                netapi.link_with_reciprocal(recognition, act, "subsur")

                sense = netapi.create_node("Pipe", node.parent_nodespace, featurename+".Sense")
                netapi.link_with_reciprocal(recognition, sense, "subsur")

                netapi.link_with_reciprocal(act, sense, "porret")

                actproxy = netapi.create_node("Pipe", node.parent_nodespace, featurename+".Prx.fovea")
                netapi.link_with_reciprocal(act, actproxy, "subsur")

                netapi.link(actproxy, 'gen', actproxy, 'gen', 0.95)     # gen loop
                netapi.link(actproxy, 'sub', actproxy, 'sur')           # fovea act proxies confirm themselves

                netapi.link_actor(actproxy, 'fov_reset')
                if x != 0:
                    netapi.link_actor(actproxy, 'fov_x', x)
                if y != 0:
                    netapi.link_actor(actproxy, 'fov_y', y)

                # create conditional sensor classificator
                sense_features = []
                for sensor in fovea_sensors_for_new_feature:
                    sense_feature = netapi.create_node("Pipe", node.parent_nodespace, featurename+"."+sensor.name)
                    sense_features.append(sense_feature)
                    netapi.link_with_reciprocal(sense, sense_feature, "subsur")

                    senseproxy = netapi.create_node("Pipe", node.parent_nodespace, featurename+"."+sensor.name+".Prx")
                    netapi.link_with_reciprocal(sense_feature, senseproxy, "subsur")

                    netapi.link(senseproxy, 'gen', senseproxy, 'gen', 0.95)
                    netapi.link_sensor(senseproxy, sensor.name)
                netapi.link_full(sense_features)

                sub_field = netapi.get_nodes_in_gate_field(scene, 'sub')
                if len(sub_field) > 1:
                    netapi.link_full(sub_field)

                netapi.logger.debug("SceneImporter imported %s.", featurename)

        # finally some fovea randomisation for the next round if no schema is accessing the fovea right now
        if not netapi.is_locked('fovea'):
            fovea_position_candidate = (random.randint(-2, 2), random.randint(-2, 2))
            i = 10
            while fovea_position_candidate not in fovea_positions and i < 10:
                i += 1
                fovea_position_candidate = (random.randint(-2, 2), random.randint(-2, 2))

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
            inact += 0.05
        else:
            inact = 0

    node.get_gate('inact').gate_function(inact)


def protocol_builder(netapi, node=None, sheaf='default', **params):

    # only do something if triggered
    if node.get_slot("trigger").activation < 1:
        return

    # collect new things to add to the previous protocol node
    importer_scene_registers = netapi.get_nodes(node.parent_nodespace, "ImporterScene")
    if len(importer_scene_registers) > 0:
        importer_scene_register = importer_scene_registers[0]
    new_elements_scene = None
    for linkid, link in importer_scene_register.get_gate('gen').outgoing.items():
        if link.target_node.name.startswith("Scene"):
            new_elements_scene = link.target_node
            break

    # find the protocol chain in the node space
    protocol_super_nodes = netapi.get_nodes(node.parent_nodespace, "Chain")

    # no protocol chain found, create one
    if len(protocol_super_nodes) < 1:
        protocol_super_node = netapi.create_node("Pipe", node.parent_nodespace, "Chain")
        initial_protocol_head = netapi.create_node("Pipe", node.parent_nodespace, "proto-0")
        initial_protocol_head.set_state("index", "0")
        netapi.link_with_reciprocal(protocol_super_node, initial_protocol_head, "subsur")
        protocol_super_nodes.append(protocol_super_node)

    # pick a protocol to extend
    protocol_super_node = protocol_super_nodes[0]   # todo: Handle cases with multiple protocols

    # get the current head of the protocol, the pormost node
    protocol_head = netapi.get_nodes_in_gate_field(protocol_super_node, "sub", ["por"])[0]

    # if the head is already referring to something, we need to record new_elements_scene,
    # extend the protocol and move the head
    if len(protocol_head.get_gate("sub").outgoing) > 0:

        # if new elements have been found since the last protocol action, add them to the protocol head
        # before moving forward and creating a new protocol head
        if new_elements_scene is not None:
            old_protocolled_scene = netapi.get_nodes_in_gate_field(protocol_head, "sub")[0]
            netapi.link_with_reciprocal(old_protocolled_scene, new_elements_scene, "subsur")
            old_protocolled_elements = netapi.get_nodes_in_gate_field(old_protocolled_scene, "sub")
            netapi.link_full(old_protocolled_elements, "porret")

        head_index = int(protocol_head.get_state("index"))
        new_head_index = head_index + 1
        new_protocol_head = netapi.create_node("Pipe", node.parent_nodespace, "proto-"+str(new_head_index))
        new_protocol_head.set_state("index", str(new_head_index))
        netapi.link_with_reciprocal(protocol_super_node, new_protocol_head, "subsur")
        netapi.link_with_reciprocal(protocol_head, new_protocol_head, "porret")
        protocol_head = new_protocol_head

    # now we have a clean protocol head, ready to be used for protocolling something

    # create a new scene as registered in the protocol
    protocolled_scene = netapi.create_node("Pipe", node.parent_nodespace, "ProtScene-"+str(time.time()))
    netapi.link_with_reciprocal(protocol_head, protocolled_scene, "subsur")

    # link all occurrences of things we already know
    candidates = netapi.get_nodes_active(node.parent_nodespace, "Pipe", 0.8)
    scenes = []
    for candidate in candidates:
        if candidate.name.startswith("Scene"):
            #occurrence = netapi.create_node("Pipe", node.parent_nodespace, "Occurrence")
            #netapi.link_with_reciprocal(protocolled_scene, occurrence, "subsur")
            #netapi.link_with_reciprocal(occurrence, candidate, "catexp")
            netapi.link_with_reciprocal(protocolled_scene, candidate, "subsur")
            scenes.append(candidate)
    netapi.link_full(scenes, "porret")

    # todo: link new things

    # make sure we have a current scene register
    #current_scene_registers = netapi.get_nodes(node.parent_nodespace, "Sepp")
    #if len(current_scene_registers) > 0:
    #    current_scene_register = current_scene_registers[0]
    #scene = None
    #for linkid, link in current_scene_register.get_gate('gen').outgoing.items():
    #    if link.target_node.name.startswith("Scene"):
    #        scene = link.target_node
    #        break
    #if scene is not None:
    #    netapi.link_with_reciprocal(protocol_head, scene, "subsur")

    # if we do not have a current scene node now, we should find the most active scene
    #if scene is None:
    #    bestcandidate = None
    #    bestactivation = 0
    #    candidates = netapi.get_nodes_active(node.parent_nodespace, "Pipe", 0.8)
    #    for candidate in candidates:
    #        if candidate.name.startswith("Scene") and candidate.activation > bestactivation:
    #            bestactivation = candidate.activation
    #            bestcandidate = candidate
    #    scene = bestcandidate
    #    if scene is not None:
    #        netapi.logger.debug("SceneImporter selecting new current scene %s.", scene.name)
    #        netapi.link(importer_scene_register, 'gen', scene, 'sub')

    node.get_gate("done").gate_function(1)


def structure_abstraction_builder(netapi, node=None, sheaf='default', **params):

    # build a list of schemas encountered
    protocol_super_nodes = netapi.get_nodes(node.parent_nodespace, "Chain")
    if len(protocol_super_nodes) < 1:
        return
    protocol_super_node = protocol_super_nodes[0]   # todo: Handle cases with multiple protocols
    protocol_head = netapi.get_nodes_in_gate_field(protocol_super_node, "sub", ["por"])[0]

    schemas = []
    current_protocol_element = protocol_head
    i = 0
    while i < 50 and current_protocol_element is not None:
        schemas.extend(netapi.get_nodes_in_gate_field(current_protocol_element, "sub"))
        i += 1
        if len(current_protocol_element.get_gate("ret").outgoing) > 0:
            current_protocol_element = netapi.get_nodes_in_gate_field(current_protocol_element, "ret")[0]
        else:
            current_protocol_element = None

    for schema in schemas:  # level of ProtocolScene nodes
        #todo: get rid of the assumptions about structure
        netapi.logger.info("Examining protocol schema: "+schema.name)
        schema_elements = netapi.get_nodes_in_gate_field(schema, "sub")

        visual_features_in_imported_schema_element = set()
        visual_features_in_recognized_schema_element = set()

        for schema_element in schema_elements:  # level of occurrence node / fresh schema heads
            if len(schema_element.get_gate("sub").outgoing) > 0:
                newly_imported_schema_element = schema_element
                visual_features_in_imported_schema_element = find_visual_features_in(newly_imported_schema_element, netapi)
            if len(schema_element.get_gate("cat").outgoing) > 0:
                recognized_schema_element = netapi.get_nodes_in_gate_field(schema_element, "cat")[0]
                visual_features_in_recognized_schema_element = find_visual_features_in(recognized_schema_element, netapi)

        if visual_features_in_recognized_schema_element > visual_features_in_imported_schema_element:
            netapi.logger.info("Recognition sufficient")
            # delete all the new elements, there is no new information
        else:
            netapi.logger.info("New elements present:")
            # merge the new elements in?
            # or create new schema with the merge?
            # then test both?
            # in cases with more than one recognized schema: merge with all of them?
            # then test all of them?

        # for every schema, check if there is sufficient overlap (what is sufficient?)
        # with any other existing schema (the most useful ones?)
        # if there is, introduce an abstraction

        # during testing of categories: keep the old specifics around?
        # probably yes, have it cleaned up by cleanup...

        # cleanup mechanism ex-protocol:
        # - remove schemas that never get touched
        # - remove schemas that always get active together and contain the same visual features

def signalsource(netapi, node=None, sheaf='default', **params):
    step = node.get_parameter('step')
    if step is None:
        step = -1
    step += 1
    node.set_parameter('step', step)

    step %= 100
    step -= 50
    step *= 2
    linear = (1 / 100) * step
    node.get_gate('linear').gate_function(linear)


def find_visual_features_in(node, netapi):
    # finds visual feature structures
    # right now, this is using node names, which should be changed to use states instead
    # note that the reliance on strings is for convenience only, all the information in the strings is
    # also in the linkage structure towards sensors and could be extracted from there
    visual_features = set()

    # look for sensor proxy nodes
    if node.name.endswith(".Prx"):
        visual_features.add(node.name)

    if "sub" in node.gates.keys():
        subs = netapi.get_nodes_in_gate_field(node, "sub")
        for sub_node in subs:
            if sub_node is not node:    # avoid infinite recursion on looping proxies
                visual_features |= find_visual_features_in(sub_node, netapi)

    return visual_features