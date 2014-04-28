__author__ = 'rvuine'


def scene_importer(netapi, node=None, **params):
    scene_nodes = netapi.get_nodes(node.parent_nodespace, "Sepp")
    if len(scene_nodes) is 0:
        sepp = netapi.create_node("Pipe", node.parent_nodespace, "Sepp")
        netapi.link(sepp.uid, "gen", node.uid, "trigger")
    else:
        netapi.unlink(scene_nodes[0].uid)
        #netapi.delete_node(scene_nodes[0].uid)