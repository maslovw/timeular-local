# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-file offline time tracker for the Timeular (Tracker_001) die. It talks to the die directly over Bluetooth LE with `bleak`, so it works without the Timeular app or cloud account.

## Running

`timeular.py` is a PEP 723 inline-metadata script. Its dependencies (`bleak>=0.22`, Python >=3.10) are declared in the header, so `uv` resolves them and there is no requirements file or venv to manage.

```
uv run timeular.py info     # device info, battery, current side
uv run timeular.py map      # interactively label faces -> sides.json
uv run timeular.py track    # log flips to timeular_log.csv (Ctrl-C to stop)
uv run timeular.py track --log other.csv
```

The project has no tests or linter. Every command needs the physical die nearby and awake (tilt it to wake it). The scan matches devices whose name starts with `Timeular`.

## How it works

- **BLE protocol:** the side facing up is one byte on characteristic `c7e70012-c847-11e6-8175-8c89a55d403c`, which supports read and indicate. Battery is the standard `0x2A19`. Side `0` means the die is moving or not resting on a face. `bluetooth.md`, `bluetooth_com.pcapng` and `img/wireshark_screen.png` are the Wireshark capture used to reverse-engineer this.
- **`sides.json`** maps side number to label. A JSON `null` (entered as `-` in `map`) marks a pause face. A pause face, side 0 when unmapped, and any session of zero length are never logged. Other unmapped sides are logged as `side N`.
- **`Tracker`** keeps one open session (current side and start time). On each flip, `flip()` closes the previous session and `close()` appends a row to the CSV (`start,end,minutes,side,label`, ISO timestamps with local offset). The CSV header is written only when the file is created.
- **Reconnect loop:** `track` reconnects for as long as it runs. When the die sleeps, disconnects or cannot be found, the open session stays open and the script retries every 10 s. The `finally` block closes the session on exit, so a session can span a disconnect.

`sides.json` and `timeular_log.csv` are user data, not fixtures. Do not overwrite or reset them.
