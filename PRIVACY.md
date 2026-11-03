# Privacy Policy

**Swept does not collect, transmit, or sell personal data.** There is no telemetry, no
analytics, no crash reporting, no user accounts, and no background services.

This document describes exactly what the program stores on your computer and every case in
which it uses the network.

## What Swept stores on your computer

| Where | What | Why |
|---|---|---|
| `HKEY_CURRENT_USER\Software\Swept` | `Language` (`ru` / `en`) | Remembers your interface language. |
| `HKEY_CURRENT_USER\Software\Swept` | `TweakJournal` | A list of the registry changes you applied, so they can be rolled back. Keeps the last 64 entries. |
| Portable build only | `settings.json` next to `Swept.exe` | The same two values, written to a file instead of the registry so nothing is left on the machine. |
| The path you choose | Report files (`.json`, `.html`, `.txt`) | Written only when you explicitly request a report. |

Deleted files are removed permanently. Swept does not keep copies, does not upload them, and
does not put them in a quarantine it controls.

Restore points are created by Windows itself, at your request, through the standard system
mechanism. Swept does not read or transmit their contents.

## When Swept uses the network

Only in two cases, and both start with an action you take.

**1. Update check.** When you press the update check button, Swept makes one HTTPS request
to `api.github.com/repos/vladcodex/swept/releases/latest` with the user agent
`Swept/<version>`. GitHub receives your IP address, as it does for any web request; no
identifiers, settings, file lists, or usage data are sent. Only the latest release tag is
read from the response. There is no automatic check at startup — if you never press the
button, Swept never contacts GitHub.

**2. Program downloads.** When you select a program to install, its installer is downloaded
directly from the vendor's own CDN. The full list of URLs is in
[`cleaner_installer.py`](cleaner_installer.py). The vendor sees your IP address and user
agent, exactly as if you had downloaded the file from their site in a browser. Swept does
not proxy, log, or report these downloads, and adds no referral or affiliate parameters to
the URLs.

**Swept has no backend.** There is no server operated by this project, no endpoint that
receives data from the application, and no way for the author to see how you use it.

## Third parties

- **GitHub** — hosts the releases and answers the update check.
- **Program vendors** — serve their own installers when you ask for them.

That is the complete list. There is no advertising, no bundled offers, no bundled
installers, no "recommended software", and no third-party SDKs that phone home.

## Data the program reads

Swept reads file names and sizes, and registry values, in order to show you what can be
deleted or changed. This information is displayed locally and written to a report only if
you ask for one. It is never sent anywhere.

## Children

The program is a system utility and is not directed at children. It collects no data from
anyone, of any age.

## Changes to this policy

If the program ever changes what it stores or where it connects, this document will be
updated in the same commit as the code change, and the change will be described in the
release notes. The current version is always the one in this repository.

## Contact

Questions or corrections: open an issue at
<https://github.com/vladcodex/swept/issues>.
