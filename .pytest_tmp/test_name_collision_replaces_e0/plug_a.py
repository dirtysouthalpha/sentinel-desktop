PLUGIN_NAME = "PluginA"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "First plugin"

def register(api):
    api.register_action("action_a", lambda **kw: {"success": True}, "Action A")
