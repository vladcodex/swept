---
name: Wrong cleanup or false positive
about: Swept deleted something it should not have, or flagged a folder you need
title: "[CLEANUP] "
labels: bug, cleanup
---

**What was deleted or flagged**
Name the category from the Cleanup tab (for example "Browser caches" or "GPU shader cache")
and say whether it was a real deletion or just an Analyze result.

**The path**
Open the **Log** tab and copy the full path of the entry. The path matters more than the
name: the whitelist works on resolved paths, so `C:\Users\you\AppData\Local\Temp\...` and
`C:\Users\you\Documents\...` are treated very differently.

```
paste the log line here
```

**What you expected**
Was the folder supposed to be skipped, or was it in the wrong category, or should the
category not exist at all?

**Can it be restored**
- Recycle Bin: yes / no
- System restore point: yes / no
- Gone for good: yes / no

**Environment**
- Windows version: (e.g. Windows 11 24H2, build 26100)
- Swept version: (window title or the "About" tab)
- Running as administrator: yes / no
- Portable ZIP or installer: ZIP / setup

**Log**
"Log" tab → copy the last lines. The program never sends anything on its own — the log
stays on your machine.
