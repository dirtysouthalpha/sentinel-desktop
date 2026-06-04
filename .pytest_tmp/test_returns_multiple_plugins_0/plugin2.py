PLUGIN_NAME = "PluginTwo"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Second plugin"

def register(api):
    api.register_command("bye", lambda text: None, keywords=["goodbye"])
