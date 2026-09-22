[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

throw @'
DEPRECATED WORKFLOW - REFUSING TO RESTORE THE PRE-STEAM RAVEN DCB DIRECTORY.

The preserved pre-Steam installation came from a rolled-back Raven state and is forensic/recovery evidence only. Restoring it would violate the current Legendary-on-proven-Ravens workflow.

After Steam Verify, use:
  tools\v0.10.5\audit-current-steam-mapmaster-legendary-compatibility-and-push.ps1

That workflow validates the current Steam-native mapmaster as a distinct source profile and caches it only after the accepted Legendary catalogue projection is reproduced exactly. The field-proven Raven release is installed separately afterwards.
'@
