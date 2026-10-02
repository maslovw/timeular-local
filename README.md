# timeular-local

Track time with your Timeular die over Bluetooth with no app, no account and no subscription.
`timeular.py` connects to the die directly, and every time you flip it the time spent on the
previous face is written to a local CSV file.

It uses [bleak](https://github.com/hbldh/bleak), so it runs on macOS, Linux and Windows.
Tested on macOS with a Timeular Tracker (model `Tracker_001`, firmware 2.0.0).

## Requirements

- [uv](https://docs.astral.sh/uv/). The script declares its dependencies inline (PEP 723), so `uv run` installs them for you.
- A Bluetooth LE adapter.
- The die awake (tilt it) and **not connected to the Timeular app**. While the die is connected to another device, it stops advertising and the script can't find it.

## Usage

```sh
uv run timeular.py info    # model, firmware, battery, which side is up
uv run timeular.py map     # name each face -> sides.json
uv run timeular.py track   # log flips to timeular_log.csv (Ctrl-C to stop)
uv run timeular.py track --log ~/time/2026.csv
```

### Naming faces

`map` asks you to put a face on top and press Enter, then type a name. Type `-` to mark a face
as a **pause**: time on it is not logged. The result is saved to `sides.json`:

```json
{
  "1": "Coding",
  "2": "Meetings",
  "3": "Email",
  "8": null
}
```

Faces you haven't named are logged as `side N`.

### Log format

```csv
start,end,minutes,side,label
2026-10-02T14:33:56+02:00,2026-10-02T14:34:10+02:00,0.2,7,Coding
```

Timestamps are ISO 8601 with your local offset. `track` keeps running if the die sleeps or goes
out of range: the current session stays open and the script reconnects every 10 s. Stopping it
with Ctrl-C or SIGTERM saves the session in progress.

## Bluetooth protocol

What the die exposes (GATT), as far as it has been worked out:

| Service | Characteristic | Properties | Meaning |
|---|---|---|---|
| `180a` Device Information | `2a29`, `2a24`, `2a25`, `2a27`, `2a26`, `2a28` | read | Manufacturer, model, serial, hardware, firmware, software |
| `180f` Battery | `2a19` | read, notify | Battery level, % |
| `c7e70010-…` | `c7e70012-c847-11e6-8175-8c89a55d403c` | read, indicate | **Side facing up**, 1 byte. `1`–`8` are faces, `0` means the die is moving |
| `c7e70010-…` | `c7e70011-…` | read | 3 × int32 LE, looks like raw accelerometer data |
| `c7e70030-…` | `c7e70032-…` | write, notify | Sends a ~169-byte burst on subscribe, probably per-face calibration vectors |
| `c7e70000/20/30/40-…` | others | write / indicate | Not decoded. The script never writes to the die |

The side characteristic was found from a Wireshark capture of the official app, see
[bluetooth.md](bluetooth.md).

## Related projects

- [cschomburg/timeular-linux](https://github.com/cschomburg/timeular-linux): Go, Linux (BlueZ), logs to local files
- [adn77/timeular](https://github.com/adn77/timeular): Windows command line, runs an action on each flip
- [lemariva/timeular-python](https://github.com/lemariva/timeular-python): Python, Linux

## License

[MIT](LICENSE)

Not affiliated with or endorsed by Timeular GmbH. "Timeular" is a trademark of its owner.
