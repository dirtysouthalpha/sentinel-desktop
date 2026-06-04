PLUGIN_NAME = "PluginA"
PLUGIN_VERSION = "2.0.0"
PLUGIN_DESCRIPTION = "Updated plugin"

def register(api):
    api.register_action("action_a_v2", lambda **kw: {"success": True}, "Action A v2")
