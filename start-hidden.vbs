Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\SentinelDesktop"
Do
  sh.Run "cmd /c buildenv\Scripts\python.exe main.py --api --host 0.0.0.0 --port 8091 >> api.log 2>&1", 0, True
  WScript.Sleep 5000
Loop
