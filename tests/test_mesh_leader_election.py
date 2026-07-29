"""Tests for lease-based priority-ordered leader election."""
import time
import pytest
from core.mesh.leader_election import LeaderElection, Lease
from core.mesh.node import MeshNode, NodeCapabilities, NodePriority


def make_node(node_id, priority, can_orchestrate=True):
    return MeshNode(node_id=node_id, name=node_id, priority=priority,
                    capabilities=NodeCapabilities(can_orchestrate=can_orchestrate))

class TestLease:
    def test_lease_creation(self):
        lease = Lease(leader_id="n1", expires_at=time.time() + 30)
        assert lease.leader_id == "n1"
        assert lease.is_valid()

    def test_lease_expired(self):
        lease = Lease(leader_id="n1", expires_at=time.time() - 1)
        assert not lease.is_valid()

class TestLeaderElection:
    def test_highest_priority_wins(self):
        election = LeaderElection(lease_ttl=30)
        cns = make_node("cns", NodePriority.CNS)
        prime = make_node("prime", NodePriority.PRIME)
        for n in [cns, prime]:
            n.heartbeat()
        leader = election.elect_leader([cns, prime])
        assert leader is not None
        assert leader.node_id == "cns"

    def test_no_alive_nodes(self):
        election = LeaderElection(lease_ttl=30)
        node = make_node("n1", NodePriority.PRIME)
        assert election.elect_leader([node]) is None

    def test_neuralis_never_leader(self):
        election = LeaderElection(lease_ttl=30)
        neuralis = make_node("brain", NodePriority.NEURALIS, can_orchestrate=False)
        neuralis.heartbeat()
        assert election.elect_leader([neuralis]) is None

    def test_priority_fallback(self):
        election = LeaderElection(lease_ttl=30)
        cns = make_node("cns", NodePriority.CNS)
        prime = make_node("prime", NodePriority.PRIME)
        prime.heartbeat()
        leader = election.elect_leader([cns, prime])
        assert leader.node_id == "prime"
