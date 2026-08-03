# Security policy

## Supported version

Security and write-safety fixes are currently applied to the latest public beta release only.

## Reporting a sensitive issue

Do not publish a detailed exploit or a reproducible destructive-write sequence in a public issue when it could:

- write outside the intended tag user area;
- overwrite UID, lock, configuration, access-control, or trailer data unexpectedly;
- bypass a target-family or memory-layout check;
- execute an unintended Proxmark3 command or local process;
- expose user dumps, keys, backups, logs, or local paths.

Use GitHub's private vulnerability-reporting feature after it is enabled for the repository. Until then, open a minimal public issue stating that you have a potentially sensitive write-safety report and wait for a private contact method.

## Scope

This project does not provide security support for Proxmark3 firmware, the RRG/Iceman client, Bambu Lab products, third-party tags, or material libraries. Report vulnerabilities in those projects to their respective maintainers.
