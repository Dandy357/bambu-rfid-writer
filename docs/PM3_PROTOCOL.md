# PM3 process and command protocol

## Persistent process

An operation starts one RRG/Iceman client process and keeps it open for preflight, backup, write, and verification. This preserves RF/session context and avoids repeated startup cost.

## Startup handshake

Piped PM3 input does not provide a reliable standalone idle prompt. Immediately after process creation the application sends a harmless remark with a random marker. The session is ready only after the marker is echoed and processed.

## Command completion

Every command is followed by another random marker:

```text
<command>
rem BRW_DONE_<random token>
```

The reader thread consumes stdout byte by byte. It emits complete output lines to the live GUI while retaining the full byte stream for marker detection and the final command result. Marker lines are filtered from user-visible output.

## Timeouts

Four independent limits exist:

- startup;
- idle without output;
- one command;
- complete operation.

A zero value disables the corresponding limit. Receiving output resets only the idle timer. Cancellation terminates the process tree and returns a partial report.

## Command validation

Read-only free-form commands pass an allow-list validator. Destructive operations do not accept arbitrary text; they use methods on `ProxmarkWriteRunner` that validate:

- page/block range;
- key length;
- data length and hexadecimal form;
- source filenames created by the operation workspace;
- maximum encoded command length.

Long Type 2 page writes are split into bounded batches. The global Type 2 safety limit remains page 225, and pages above the legacy NTAG215 range require an explicitly detected known profile.

## MIFARE Classic programmed-target flow

A previously programmed target is authenticated using the key file found for its current UID. The complete current dump is persisted when backup is enabled and is always compared with the selected source.

- An exact 1024/1024 match returns a successful no-change result and performs no write.
- Different programmed content is unsupported in the stable 0.9.0 workflow and is blocked before any `wrbl` or restore command.

The application does not use a normal authenticated block-0 write as proof of a chip-specific Magic/backdoor mechanism. A future programmed-target rewrite requires a separately documented and physically verified implementation for the exact tag family.
