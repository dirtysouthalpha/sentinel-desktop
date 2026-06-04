PLUGIN_NAME = "PluginA"
PLUGIN_VERSION = "3.0.0"
PLUGIN_DESCRIPTION = "Collision plugin"

def register(api):
    api.register_action("collision_action", lambda **kw: {"success": True}, "Collision")
