' autoboot_silent.vbs — Runs autoboot_master.ps1 invisibly on Windows restart
Set objShell = CreateObject("WScript.Shell")
strPath = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\scripts\autoboot_master.ps1"""
objShell.Run strPath, 0, False
