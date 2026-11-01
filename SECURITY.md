# Security

Swept deletes files with administrator rights. The failure that matters is therefore a path
being removed from outside the folder a category produced, and that is treated as a
vulnerability rather than as a bug.

## Reporting

Use GitHub's private advisory form: the **Security** tab → *Report a vulnerability*. Nothing is
published until a fix is ready.

If the form is unavailable, open an issue containing only the word `security` and no details.
I will open a private channel and ask for the rest there.

Please do not post a working exploit in a public issue. There are people who will run it.

## In scope

* A file or folder deleted from outside the whitelist built by `build_allowed`.
* A junction or symlink that lets a cleanup category escape its allowed folder.
* Any code path that reaches a protected path — `System32`, `WinSxS`, `Program Files`,
  `pagefile.sys`, `$Recycle.Bin` — despite the blacklist.
* The installer accepting a download whose signature or pinned hash does not match, or
  running a downloaded file before verification.
* A tweak writing outside the registry paths it claims to touch.
* Elevation gained or kept where the manifest does not request it.

## Out of scope

* **SmartScreen and "Unknown publisher".** The certificate is self-signed on purpose and is
  never installed into the certificate store; the reasoning is in [BUILDING.md](BUILDING.md).
* **Antivirus heuristics** flagging the PyInstaller bundle. This is a known trade-off of the
  packaging, not a defect that can be fixed in code.
* **"AI wrote it."** That is a question about trust and licensing, discussed in
  [README.md](README.md) and [NOTICE](NOTICE), not a vulnerability report.
* Anything that requires an attacker who already has administrator rights on the machine.

## What happens next

One person maintains this project, unpaid, in his own time. Expect a first reply within a few
days rather than hours, and do not read silence as a decision.

If the report holds up, the fix ships in the next release and you are credited in the notes
unless you ask me not to. If it does not hold up, you get the reasoning, not just a closed
ticket.

Reports about the delete path are the ones I want most. A path that gets removed from outside
its allowed folder is worth more to this project than any feature request.
