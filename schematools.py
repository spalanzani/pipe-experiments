__author__ = 'rvuine'


def delete_schema(node, netapi):
    """
    Deletes the given schema fully, including the given head node
    :param node: the head node of a schema to be deleted
    :param netapi: natapi
    """
    if "sub" in node.gates.keys():
        subs = netapi.get_nodes_in_gate_field(node, "sub")
        for sub_node in subs:
            if sub_node is not node:    # avoid infinite recursion on looping proxies
                delete_schema(sub_node, netapi)

    netapi.delete_node(node)


def create_merged_schema(schemas, netapi):
    """
    Creates a merged schema out of the given schemas.
    Original schemas will be unmodified.
    :param schemas: a list of schemas to be merged
    :param netapi: netapi
    """

    copied_schemas = []

    for schema in schemas:
        copied_schemas.append(copy_schema(schema, netapi))

    merge_schemas(copied_schemas, netapi)


def merge_schemas(schemas, netapi):
    """
    Merges the given list of schemas (modifying the given schemas)
    :param schemas: a list of schemas to be merged
    :param netapi: netapi
    """
    first_schema = schemas[0]
    merged_head = netapi.create_node(first_schema.type, first_schema.parent_nodespace, first_schema.name)
    merged_classifier_list = []

    for schema in schemas:
        sub_schemas = netapi.get_nodes_in_gate_field(schema, "sub")
        # todo: don't merge in features that are already there, i.e. structurally identical
        if len(sub_schemas) > 0:
            first_sub_schema = sub_schemas[0]
            if len(first_sub_schema.get_gate("por").outgoing) == len(sub_schemas):  # this is a classifier
                merged_classifier_list.extend(sub_schemas)
                netapi.delete_node(schema)
            else:                                                                   # script or alternative
                merged_classifier_list.append(schema)
                netapi.unlink_direction(schema, "gen")
                netapi.unlink_direction(schema, "por")
                netapi.unlink_direction(schema, "ret")
                netapi.unlink_direction(schema, "cat")
                netapi.unlink_direction(schema, "exp")

    for schema in merged_classifier_list:
        netapi.link_with_reciprocal(merged_head, schema, "subsur")
    netapi.link_full(merged_classifier_list, "porret")


def copy_schema(node, netapi):
    """
    Copies a schema - a node and all its sub-nodes
    Schema-internal links will be schema-internal in the copy
    External links will be present in the copy
    :param node: the head node of the schema to be copied
    :param netapi: netapi
    :return: the head node of the newly created copy
    """

    original_schema_nodes = collect_schema_nodes(node, netapi)
    copy_schema_nodes = {}

    # copy all the nodes
    for original in original_schema_nodes:
        copy_schema_node = netapi.create_node(original.type, original.parent_nodespace, original.name)
        copy_schema_nodes[original.uid] = copy_schema_node

    # now link them up
    # links to copied nodes go to the copy, links to other nodes go to the original other nodes
    for original in original_schema_nodes:
        for slot in original.slots.values():
            for link in slot.incoming.values():
                if link.source_node.uid in copy_schema_nodes:
                    # link from copy
                    if original.uid == node.uid and link.target_slot.type != "sur":
                        break;  # don't por/ret or cat/exp link the copy of the head node
                    netapi.link(
                        copy_schema_nodes[link.source_node.uid],
                        link.source_gate.type,
                        copy_schema_nodes[original.uid],
                        link.target_slot.type,
                        link.weight,
                        link.certainty)
                else:
                    # link from original
                    if original.uid == node.uid and link.target_slot.type != "sur":
                        break;  # don't por/ret or cat/exp link the copy of the head node
                    netapi.link(
                        link.source_node,
                        link.source_gate.type,
                        copy_schema_nodes[original.uid],
                        link.target_slot.type,
                        link.weight,
                        link.certainty)
        for gate in original.gates.values():
            for link in gate.outgoing.values():
                if link.target_node.uid in copy_schema_nodes:
                    # link to copy
                    if original.uid == node.uid and link.source_gate.type != "sub":
                        break;  # don't por/ret or cat/exp link the copy of the head node
                    netapi.link(
                        copy_schema_nodes[original.uid],
                        link.source_gate.type,
                        copy_schema_nodes[link.target_node.uid],
                        link.target_slot.type,
                        link.weight,
                        link.certainty)
                else:
                    # link to original
                    if original.uid == node.uid and link.source_gate.type != "sub":
                        break;  # don't por/ret or cat/exp link the copy of the head node
                    netapi.link(
                        copy_schema_nodes[original.uid],
                        link.source_gate.type,
                        link.target_node,
                        link.target_slot.type,
                        link.weight,
                        link.certainty)

    return copy_schema_nodes[node.uid]


def collect_schema_nodes(node, netapi):
    # collects all sub nodes (the whole schema)
    sub_nodes = set()
    sub_nodes.add(node)
    if "sub" in node.gates.keys():
        subs = netapi.get_nodes_in_gate_field(node, "sub")
        for sub_node in subs:
            if sub_node is not node and sub_node.type == node.type:    # avoid infinite recursion on looping proxies
                sub_nodes |= collect_schema_nodes(sub_node, netapi)
    return sub_nodes


def collect_visual_feature_names(node, netapi):
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
                visual_features |= collect_visual_feature_names(sub_node, netapi)

    return visual_features


def collect_features(node, netapi):
    """
    Collects all features in a given schema.
    A feature can be:
    - a node which has a single cat-link
    - a direct sensor proxy
    - a script
    Scripts and cats are opaque and will not be searched for features themselves.
    :param node: the head node of the schema to search
    :param netapi: netapi
    :return: a set of features names, a dict of feature names to feature head nodes
    """

    feature_names = set()
    feature_nodes = {}

    sub_field = netapi.get_nodes_in_gate_field(node, "sub")

    is_a_feature = False

    # a feature can be an exp of a single cat, read "inherit all features of this category"
    if len(sub_field) == 0:
        cat_field = netapi.get_nodes_in_gate_field(node, "cat")
        if len(cat_field) == 1:
            name = "exp-"+cat_field[0].uid
            feature_names.add(name)
            feature_nodes[name] = node
            is_a_feature = True

    # a feature can be a direct sensor standin/proxy
    if len(sub_field) == 1:
        if sub_field[0].type == "Sensor":
            name = "sns-"+sub_field[0].get_parameter["datasource"]
            feature_names.add(name)
            feature_nodes[name] = node
            is_a_feature = True

    # a feature can be a script
    if len(sub_field) > 1:
        leftmost = netapi.get_nodes_in_gate_field(node, "sub", ["ret"])
        if len(leftmost) == 1:

            # todo: check for real script equivalence instead of using this signature cheat
            visual_feature_names = collect_visual_feature_names(node, netapi)
            name = "scp-"
            for vf_name in visual_feature_names:
                name += vf_name

            feature_names.add(name)
            feature_nodes[name] = node
            is_a_feature = True

    if not is_a_feature and "sub" in node.gates.keys():
        for sub_node in sub_field:
            if sub_node is not node:    # avoid infinite recursion on looping proxies
                sub_names, sub_nodes = collect_features(sub_node, netapi)
                feature_names |= sub_names
                feature_nodes.update(sub_nodes)

    return feature_names, feature_nodes


def create_common_feature_abstraction(schema1, schema2, netapi):
    """
    Creates an abstract schema out of two given schemas and links the three schemas using cat/exp
    :param schema1: The first schema to abstract from
    :param schema2: The second schema to abstract from
    :param netapi: netapi
    :return: the newly created abstract schema head node or None if no abstraction has been created
    """

    feature_names_in_schema1, features_in_schema1 = collect_features(schema1, netapi)
    feature_names_in_schema2, features_in_schema2 = collect_features(schema2, netapi)

    common_feature_names = feature_names_in_schema1 & feature_names_in_schema2      # that's intersection for you

    if len(common_feature_names) < (len(features_in_schema1)+len(feature_names_in_schema2)) / 6:
        return None             # do not do anything if less than a third of the schemas matches

    features = {}
    features.update(features_in_schema1)
    features.update(features_in_schema2)

    # now build the new category
    abstraction = netapi.create_node(schema1.type, schema1.parent_nodespace, "Common-"+schema1.name+"-and-"+schema2.name)
    for common_feature_name in common_feature_names:
        feature = features[common_feature_name]
        feature_clone = copy_schema(feature, netapi)
        netapi.link_with_reciprocal(abstraction, feature_clone, "subsur")

    # por-ret the sub-field of the newly created abstraction
    feature_clones = netapi.get_nodes_in_gate_field(abstraction, "sub")
    netapi.link_full(feature_clones, "porret")

    # start to modify schema1
    # first, remove the common features
    for common_feature_name in common_feature_names:
        feature = features[common_feature_name]
        netapi.unlink(schema1, "sub", feature)
        netapi.unlink(feature, "sur", schema1)
    # second, install the new abstraction
    nature = netapi.create_node(schema1.type, schema1.parent_nodespace, "Nature-"+abstraction.name)
    netapi.link_with_reciprocal(schema1, nature, "subsur")
    netapi.link_with_reciprocal(nature, abstraction, "catexp")

    # start to modify schema2
    # first, remove the common features
    for common_feature_name in common_feature_names:
        feature = features[common_feature_name]
        netapi.unlink(schema2, "sub", feature)
        netapi.unlink(feature, "sur", schema2)
    # second, install the new abstraction
    nature = netapi.create_node(schema2.type, schema2.parent_nodespace, "Nature-"+abstraction.name)
    netapi.link_with_reciprocal(schema2, nature, "subsur")
    netapi.link_with_reciprocal(nature, abstraction, "catexp")

    return abstraction