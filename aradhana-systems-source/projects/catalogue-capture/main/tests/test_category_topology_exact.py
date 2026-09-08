import category_topology


def test_ring_is_single_not_earring_pair():
    assert category_topology.topology_for("ring")["relationship"] == "SINGLE"
    assert category_topology.topology_for("LADIES RING 22")["visible_piece_count"] == 1


def test_earrings_are_pair_and_sets_are_three_components():
    assert category_topology.topology_for("EARRING 22")["relationship"] == "PAIR"
    assert category_topology.topology_for("NECKLACE SET 22")["visible_piece_count"] == 3
    assert category_topology.topology_for("PENDENT SET 22")["visible_piece_count"] == 3
