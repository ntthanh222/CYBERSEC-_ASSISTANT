"""Attack graph API tests."""

from backend.tests.conftest import TEST_USER_B


def _node(**overrides):
    payload = {
        "node_type": "asset",
        "label": "Finance Gateway",
        "ip_address": "10.0.0.10",
        "status": "vulnerable",
        "severity": "high",
        "description": "Internet-facing gateway.",
        "cves": ["CVE-2026-10001"],
        "position_x": 100,
        "position_y": 120,
    }
    payload.update(overrides)
    return payload


def test_attack_graph_nodes_edges_and_graph(api_client):
    source = api_client.post(
        "/api/attack-graph/nodes", json=_node(label="External Host", node_type="attacker")
    )
    assert source.status_code == 201
    target = api_client.post(
        "/api/attack-graph/nodes", json=_node(label="Finance DB", node_type="database")
    )
    assert target.status_code == 201

    edge = api_client.post(
        "/api/attack-graph/edges",
        json={
            "source_node_id": source.json()["id"],
            "target_node_id": target.json()["id"],
            "label": "Potential lateral movement",
            "status": "potential",
        },
    )
    assert edge.status_code == 201

    graph = api_client.get("/api/attack-graph")
    assert graph.status_code == 200
    body = graph.json()
    assert len(body["nodes"]) == 2
    assert len(body["edges"]) == 1


def test_attack_graph_is_owner_isolated(api_client, switch_user):
    node = api_client.post("/api/attack-graph/nodes", json=_node())
    assert node.status_code == 201

    switch_user(TEST_USER_B)
    graph = api_client.get("/api/attack-graph")
    assert graph.status_code == 200
    assert graph.json()["nodes"] == []
    assert graph.json()["edges"] == []


def test_attack_graph_edge_rejects_cross_owner_node(api_client, switch_user):
    owner_node = api_client.post("/api/attack-graph/nodes", json=_node(label="Owner node"))
    assert owner_node.status_code == 201

    switch_user(TEST_USER_B)
    other_node = api_client.post("/api/attack-graph/nodes", json=_node(label="Other node"))
    assert other_node.status_code == 201
    edge = api_client.post(
        "/api/attack-graph/edges",
        json={
            "source_node_id": owner_node.json()["id"],
            "target_node_id": other_node.json()["id"],
            "label": "Invalid cross-owner edge",
            "status": "active",
        },
    )
    assert edge.status_code == 404


def test_attack_graph_validation_is_safe(api_client):
    invalid = api_client.post("/api/attack-graph/nodes", json=_node(status="unknown"))
    assert invalid.status_code == 422
    assert invalid.json()["message"] == "Invalid request."


def test_attack_graph_routes_require_authentication(unauthenticated_client):
    assert unauthenticated_client.get("/api/attack-graph").status_code == 401
