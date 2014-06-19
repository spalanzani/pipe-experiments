__author__ = 'rvuine'

import random

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

                sub_field = netapi.get_nodes_field(scene, 'sub')
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


def structure_abstraction_builder(netapi, node=None, sheaf='default', **params):
    pass


def backpropagator(netapi, node=None, sheaf='default', **params):
    """
        Assumptions:
        - Only one feed-forward classificator in this node space
        - Layers are fully feed-forward linked
        - Output layer neuron names are prefixed OLN_
        - Target value neuron names are prefixed TVN_
        - Input layer neuron names are prefixed ILN_
    """
    learning_constant = 0.6
    tolerable_error = 0.15

    if node.get_slot("trigger").activation <= 0:
        return

    global_error = 0

    all_nodes = []

    # find the output layer neurons
    ol_neurons = netapi.get_nodes(node.parent_nodespace, "OLN_")
    tv_neurons = netapi.get_nodes(node.parent_nodespace, "TVN_")

    if len(ol_neurons) == 0 or len(tv_neurons) == 0:
        netapi.logger.warn("Backpropagator: no output node or no target value node found")
        return

    # calculate the errors for the output layer
    for ol_node in ol_neurons:
        all_nodes.append(ol_node)
        tv_node = None
        for candidate in tv_neurons:
            if candidate.name[4:] == ol_node.name[4:]:
                tv_node = candidate
                break
        if tv_node is None:
            netapi.logger.warn("Backpropagator: output node "+ol_node+" has no corresponding target value node")
            tv_node = ol_node

        is_value = float(ol_node.get_gate("gen").activation)
        target_value = float(tv_node.get_gate("gen").activation)
        delta = float(is_value * (1-is_value) * (target_value-is_value))

        ol_node.parameters['error'] = delta
        global_error += target_value-is_value

    node.activation = 0
    node.get_gate("error").gate_function(global_error)

    if global_error <= tolerable_error:
        node.get_gate("idle").gate_function(1)
        return
    else:
        node.get_gate("idle").gate_function(0)

    # calculate the errors for hidden layers
    layer = netapi.get_nodes_feed(ol_neurons[0], "gen", None, node.parent_nodespace)
    while layer is not None and len(layer) > 0:
        for layer_node in layer:
            all_nodes.append(layer_node)
            layer_node_value = layer_node.get_gate("gen").activation
            higher_layer_error_sum = 0
            for linkid, forwardlink in layer_node.get_gate("gen").outgoing.items():
                higher_layer_error_sum += forwardlink.target_node.parameters['error'] * forwardlink.weight

            delta = layer_node_value * (1-layer_node_value) * higher_layer_error_sum
            layer_node.parameters['error'] = delta

        layer_node = layer[0]
        first_link = list(layer_node.get_slot("gen").incoming.values())[0]
        if len(layer_node.get_slot("gen").incoming) > 0 and not first_link.source_node.type == "Sensor":
            layer = netapi.get_nodes_feed(layer_node, "gen", None, node.parent_nodespace)
        else:
            layer = None

    # adjust link weights and thetas (apply delta rule)
    for node in all_nodes:
        error = node.parameters['error']
        del node.parameters['error']

        # adjust theta
        node.get_gate("gen").parameters['theta'] -= (learning_constant * error)

        # adjust link weights
        for linkid, link in node.get_slot("gen").incoming.items():
            new_weight = link.weight + (learning_constant * error * link.source_gate.activation)
            netapi.link(link.source_node, "gen", link.target_node, "gen", new_weight)


def feedforward_generator(netapi, node=None, sheaf='default', **params):

    LAYERS = 2
    NODES_PER_LAYER = 10
    OUTPUT_NODES = 1

    # input layer
    sensor_layer = netapi.import_sensors(node.parent_nodespace, "pxl")
    for sensor in sensor_layer:
        sensor.get_gate('gen').parameters['theta'] = random.random() * 5 * (-1 if random.random() > 0.5 else 1)

    # hidden layers
    hidden_layers = []
    for i in range(0, LAYERS):
        hidden_layers.append([])
        for j in range(0, NODES_PER_LAYER):
            register = netapi.create_node("Register", node.parent_nodespace)
            register.get_gate('gen').parameters['theta'] = random.random() * 5 * (-1 if random.random() > 0.5 else 1)
            hidden_layers[i].append(register)

    # output layer
    output_layer = []
    for i in range(0, OUTPUT_NODES):
        register = netapi.create_node("Register", node.parent_nodespace, "OLN_"+str(i))
        register.get_gate('gen').parameters['theta'] = random.random() * 5 * (-1 if random.random() > 0.5 else 1)
        output_layer.append(register)

    # wire it all up
    layer_counter = 0
    down_layer = sensor_layer
    up_layer = hidden_layers[layer_counter]
    while not up_layer is None:
        for down in down_layer:
            for up in up_layer:
                netapi.link(down, "gen", up, "gen", random.random())
        down_layer = up_layer
        if up_layer is not output_layer:
            if layer_counter < LAYERS-1:
                layer_counter += 1
                up_layer = hidden_layers[layer_counter]
            else:
                up_layer = output_layer
        else:
            up_layer = None

    netapi.set_gatefunction(node.parent_nodespace, "Register", "gen", "return 1/(1+math.exp(t*x))")


def patternchanger(netapi, node=None, sheaf='default', **params):
    """
     Assumptions:
     - Pattern change actor names are prefixed ILN_
    """

    minimum_pattern_exposure = 20

    netapi.unlink(node, "fire")

    # if we're not triggered yet, we don't do anything
    if node.get_slot("trigger").activation <= 0:
        return

    # if we haven't shown the pattern for long enough, we're also not creating a new one
    lastchange = node.get_parameter("lastchange")
    if lastchange is not None and lastchange + minimum_pattern_exposure < netapi.step:
        return

    # ok, so we're being triggered, and the old pattern was up for long enough
    pattern_activators = netapi.get_nodes(node.parent_nodespace, "PAT_")
    random_pattern = pattern_activators[random.randint(0, len(pattern_activators)-1)]

    netapi.link(node, "fire", random_pattern, "gen")
    node.get_gate("fire").gate_function(1)
    node.set_parameter("lastchange", netapi.step)


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



