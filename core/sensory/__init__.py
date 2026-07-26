"""Sensory network agents — the eyes and ears of Neuralis.

ScreenAgent — watches the desktop for visual changes
ProcessAgent — monitors running processes for new/crashing/resource hogs
NetworkAgent — discovers and monitors Tailscale mesh peers
SensoryFusion — combines all sensory streams into a unified world model
WorldModel — persistent sensory memory for long-term context
"""

from .fusion import SensoryFusion, WorldState
from .network_agent import NetworkAgent, NetworkConfig, NetworkEvent, PeerInfo
from .process_agent import ProcessAgent, ProcessConfig, ProcessEvent
from .screen_agent import ScreenAgent, ScreenConfig, ScreenEvent
from .world_model import WorldModel

__all__ = [
    "ScreenEvent", "ScreenConfig", "ScreenAgent",
    "ProcessEvent", "ProcessConfig", "ProcessAgent",
    "PeerInfo", "NetworkEvent", "NetworkConfig", "NetworkAgent",
    "WorldState", "SensoryFusion",
    "WorldModel",
]
