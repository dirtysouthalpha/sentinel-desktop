PLUGIN_NAME = "CrashPlugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Crashes during register"

def register(api):
    raise RuntimeError("boom")
