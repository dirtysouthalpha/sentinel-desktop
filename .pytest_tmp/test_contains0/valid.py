PLUGIN_NAME = "TestPlugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "A test plugin"

def register(api):
    api.register_action("greet", lambda **kw: {"success": True}, "Say hello")
    api.register_command("hi", lambda text: {"success": True}, keywords=["hello"])
    api.register_setting("theme", default="dark", label="Color theme")
