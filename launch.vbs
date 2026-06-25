Dim sh
Set sh = WScript.CreateObject("WScript.Shell")
sh.Run "cmd /c cd /d ""C:\Users\t.kislev\ScientificMonitor"" && ""C:\Users\t.kislev\AppData\Local\Programs\Python\Python312\python.exe"" server.py >> ""C:\Users\t.kislev\ScientificMonitor\logs\server.log"" 2>&1", 0, True
