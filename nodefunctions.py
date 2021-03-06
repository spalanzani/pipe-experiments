__author__ = 'rvuine'

import random
import time
from schematools import *


def scene_importer(netapi, node=None, sheaf='default', **params):

    netapi.import_actors(node.parent_nodespace)
    netapi.import_sensors(node.parent_nodespace)

    node.get_gate("reset").gate_function(0)
    #node.get_gate("fov_x").gate_function(node.get_slot("fov-x").activation)
    #node.get_gate("fov_y").gate_function(node.get_slot("fov-y").activation)

    #node.get_gate("fov_x").gate_function(node.get_slot("fov-x").activation)
    #node.get_gate("fov_y").gate_function(node.get_slot("fov-y").activation)

    # make sure we have an importer scene register
    importer_scene_registers = netapi.get_nodes(node.parent_nodespace, "ImporterScene")
    if len(importer_scene_registers) is 0:
        importer_scene_register = netapi.create_node("Register", node.parent_nodespace, "ImporterScene")
    else:
        importer_scene_register = importer_scene_registers[0]

    # make sure we have an importer scene node
    scene = None
    for link in importer_scene_register.get_gate('gen').get_links():
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

    randomize = True

    # if the scene is fully recognized, check if there's something we can add to it in the world
    if (scene.activation > 0.8 or scene.get_slot('sur').empty) and node.get_slot("dontgrow").activation < 1:
        # what we're looking for: a feature that is active but hasn't been linked
        # for this, we move the fovea to a position we haven't looked at yet

        # build a list of fovea positions that are taken care of
        sub_field = netapi.get_nodes_in_gate_field(scene, 'sub')
        fovea_positions = []
        for sub_node in sub_field:
            fovea_positions.append((sub_node.get_state('x'), sub_node.get_state('y')))

        # current fovea position and resulting feature name
        x = int(node.get_slot("fov-x").activation)
        y = int(node.get_slot("fov-y").activation)
        featurename = "F(" + str(x) + "/" + str(y)+")"

        netapi.logger.debug("SceneImporter has stable scene, checking if current feature %s is imported.", featurename)

        randomize = False

        # now, do we have a feature for the current sensor situation?
        if (x, y) not in fovea_positions:

            netapi.logger.debug("SceneImporter: %s is not imported, importing.", featurename)

            # find the sensors to link
            active_sensors = netapi.get_nodes_active(node.parent_nodespace, 'Sensor', 1, 'gen')
            fovea_sensors_for_new_feature = []
            presence_sensors_for_new_feature = []
            for sensor in active_sensors:
                if sensor.name.startswith("fovea"):
                    fovea_sensors_for_new_feature.append(sensor)
                if sensor.name.startswith("presence"):
                    presence_sensors_for_new_feature.append(sensor)

            if len(fovea_sensors_for_new_feature) == 0:
                netapi.logger.debug("SceneImporter: Aborting import of %s, no sensors", featurename)
                randomize = True

            # and build the schema for them
            if len(fovea_sensors_for_new_feature) > 0:

                feature = netapi.create_node("Pipe", node.parent_nodespace, featurename)
                feature.set_state('x', x)
                feature.set_state('y', y)
                #feature.set_parameter('sublock', 'fovea')
                netapi.link(feature, 'gen', feature, 'gen', 0.98)     # gen loop
                #feature.set_gate_parameter('threshold', 0.1)
                netapi.link_with_reciprocal(scene, feature, "subsur")

                #recognition = netapi.create_node("Pipe", node.parent_nodespace, featurename+".Rec")
                #netapi.link_with_reciprocal(feature, recognition, "subsur")

                # create recognition script
                act = netapi.create_node("Pipe", node.parent_nodespace, featurename+".Act")
                netapi.link_with_reciprocal(feature, act, "subsur")

                sense = netapi.create_node("Pipe", node.parent_nodespace, featurename+".Sense")
                netapi.link_with_reciprocal(feature, sense, "subsur")

                netapi.link_with_reciprocal(act, sense, "porret")

                mov_x = netapi.create_node("Trigger", node.parent_nodespace, featurename+".mov-x")
                mov_y = netapi.create_node("Trigger", node.parent_nodespace, featurename+".mov-y")
                mov_x.set_parameter('response', x)
                mov_y.set_parameter('response', y)
                mov_x.set_parameter('timeout', 3)
                mov_y.set_parameter('timeout', 3)
                netapi.link_with_reciprocal(act, mov_x, "subsur")
                netapi.link_with_reciprocal(act, mov_y, "subsur")
                netapi.link(mov_x, 'sur', act, 'sur', 0.5)
                netapi.link(mov_y, 'sur', act, 'sur', 0.5)

                netapi.link_actor(mov_x, 'fov_reset')
                if x != 0:
                    netapi.link_actor(mov_x, 'fov_x', x)
                if y != 0:
                    netapi.link_actor(mov_y, 'fov_y', y)

                netapi.link_sensor(mov_x, "fov-x")
                netapi.link_sensor(mov_y, "fov-y")

                # create conditional sensor classificator
                sense_features = []
                for sensor in fovea_sensors_for_new_feature:
                    sense_feature = netapi.create_node("Pipe", node.parent_nodespace, featurename+"."+sensor.name)
                    sense_features.append(sense_feature)
                    netapi.link_with_reciprocal(sense, sense_feature, "subsur")

                    #senseproxy = netapi.create_node("Pipe", node.parent_nodespace, featurename+"."+sensor.name+".Prx")
                    #netapi.link_with_reciprocal(sense_feature, senseproxy, "subsur")

                    #netapi.link(senseproxy, 'gen', senseproxy, 'gen', 0.98)
                    netapi.link_sensor(sense_feature, sensor.name)

                sub_field = netapi.get_nodes_in_gate_field(scene, 'sub')
                netapi.logger.debug("SceneImporter imported %s.", featurename)
        else:
            netapi.logger.debug("SceneImporter: %s already imported, aborting.", featurename)
            randomize = True

        # finally some fovea randomisation for the next round if no schema is accessing the fovea right now
        if not netapi.is_locked('fovea') and randomize:
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
    for link in importer_scene_register.get_gate('gen').get_links():
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
    if len(protocol_head.get_gate("sub").get_links()) > 0:

        # if new elements have been found since the last protocol action, add them to the protocol head
        # before moving forward and creating a new protocol head
        if new_elements_scene is not None:
            old_protocolled_scene = netapi.get_nodes_in_gate_field(protocol_head, "sub")[0]
            netapi.link_with_reciprocal(old_protocolled_scene, new_elements_scene, "subsur")
            old_protocolled_elements = netapi.get_nodes_in_gate_field(old_protocolled_scene, "sub")

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
            occurrence = netapi.create_node("Pipe", node.parent_nodespace, "Occurrence")
            netapi.link_with_reciprocal(protocolled_scene, occurrence, "subsur")
            netapi.link_with_reciprocal(occurrence, candidate, "catexp")
            netapi.link_with_reciprocal(protocolled_scene, candidate, "subsur")
            scenes.append(candidate)

    # make sure we have a current scene register
    #current_scene_registers = netapi.get_nodes(node.parent_nodespace, "Sepp")
    #if len(current_scene_registers) > 0:
    #    current_scene_register = current_scene_registers[0]
    #scene = None
    #for link in current_scene_register.get_gate('gen').get_links():
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
        if len(current_protocol_element.get_gate("ret").get_links()) > 0:
            current_protocol_element = netapi.get_nodes_in_gate_field(current_protocol_element, "ret")[0]
        else:
            current_protocol_element = None

    abstraction_candidates = []

    for schema in schemas:  # level of ProtocolScene nodes
        #todo: get rid of the assumptions about structure
        netapi.logger.info("Examining protocol schema: "+schema.name)
        schema_elements = netapi.get_nodes_in_gate_field(schema, "sub")

        visual_features_in_imported_schema_element = set()
        visual_features_in_recognized_schema_element = set()

        newly_imported_schema_element = None
        recognized_schema_element = None

        for schema_element in schema_elements:  # level of occurrence node / fresh schema heads
            if len(schema_element.get_gate("sub").get_links()) > 0:
                # it's sub-connected, so it has been imported to the schema
                newly_imported_schema_element = schema_element
                visual_features_in_imported_schema_element = collect_visual_feature_names(newly_imported_schema_element, netapi)

            if len(schema_element.get_gate("cat").get_links()) > 0:
                # it's cat-connected, so it has been recognized as something already known
                recognized_schema_element = netapi.get_nodes_in_gate_field(schema_element, "cat")[0]
                visual_features_in_recognized_schema_element = collect_visual_feature_names(recognized_schema_element, netapi)
                abstraction_candidates.append(recognized_schema_element)


        if visual_features_in_recognized_schema_element > visual_features_in_imported_schema_element:
            # delete all the new elements, there is no new information
            if newly_imported_schema_element is not None:
                delete_schema(newly_imported_schema_element, netapi)
                netapi.logger.info("Redundant schema: "+newly_imported_schema_element.name)
        else:
            abstraction_candidates.append(newly_imported_schema_element)
        #    netapi.logger.info("New elements present, merging")
        #    if newly_imported_schema_element is not None and recognized_schema_element is not None:
        #        create_merged_schema([newly_imported_schema_element, recognized_schema_element], netapi)

    for candidate1 in abstraction_candidates:
        for candidate2 in abstraction_candidates:
            if candidate1 is not candidate2:
                create_common_feature_abstraction(candidate1, candidate2, netapi)

        # for every schema, check if there is sufficient overlap (what is sufficient?)
        # with any other existing schema (the most useful ones?)
        # if there is, introduce an abstraction

        # during testing of categories: keep the old specifics around?
        # probably yes, have it cleaned up by cleanup...

        # cleanup mechanism ex-protocol:
        # - remove schemas that never get touched
        # - remove schemas that always get active together and contain the same visual features


    # what we do here is offer a schema that assumes that newly observed properties are part of something
    # we have seen before

    # types of theories:
    # - newly observed properties are part of what has been seen before
    # - newly observed properties are part of something new (should be created as a new incomplete schema)
    # - two schemas are structurally similar, an abstraction should be offered


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

#    if step == 0:
#        raise "ohjemine"