# Hypothesis

Controller privacy is the remaining host-side variable preventing Linux from getting past the pre-SMP link drop with the Bosch bike.

# Setup

- Hardware and host:
  - Linux host addressed by `REMOTE_HOST`
  - nRF52840 USB dongle acting as `hci0`
  - Bosch bike on the Bluetooth pairing screen
- Relevant reference capture:
  - `captures/bosch-2026-04-19-2108-with-pairing.pcapng`
- Host preparation commands:

```bash
sudo btmgmt power off
sudo btmgmt set-sysconfig -v 0017:2:1800 0018:2:1800 0019:2:0000 001a:2:4800
sudo btmgmt privacy off
sudo btmgmt bondable on
sudo btmgmt power on
bluetoothctl pairable on
bluetoothctl connect 00:04:63:BA:64:FC
```

- Trace used for the successful privacy-off connect attempt:
  - `final-privacy-off-1776758694.log`
- Control traces from failing pair-first attempts:
  - `manual-pair-1776758573.log`

# Observations

- With `privacy on`, connection attempts consistently stopped after:
  - `LE Enhanced Connection Complete`
  - `LE Read Remote Used Features`
  - disconnect reason `Connection Failed to be Established (0x3e)`
- With `privacy off`, a plain `bluetoothctl connect` succeeded while the bike was on the pairing screen:
  - `Connected: yes`
  - `Connection successful`
- The privacy-off trace advanced beyond the old dead point and showed:
  - `LE L2CAP: Connection Parameter Update Request`
  - `LE Connection Update`
  - `ATT: Exchange MTU Request`
  - `ATT: Exchange MTU Response`
  - `ATT: Read By Group Type Request`
  - `ATT: Read By Group Type Response`
- A fresh pair attempt still failed even in the same pairing-screen state:
  - `Failed to pair: org.bluez.Error.AuthenticationCanceled`
- The bike advertisement in the successful state matched the known-good phone scenario:
  - `LE Limited Discoverable Mode`
  - Bosch manufacturer scan response `10eb01030001`

# Result

Turning controller privacy off is necessary to move Linux past the pre-SMP disconnect and into ATT/GATT traffic on this host and bike combination.

# Conclusion

The remaining repo-side blocker is not Bosch MCSP or MessageBus logic. The working host path is connect-first with controller privacy off. The current repo path still fails because it performs pair-first setup via `assist_connection()`, while the known-good host behavior is:

1. connect with privacy off
2. reach ATT/GATT successfully
3. let later security staging trigger pairing only if encryption is actually required

# Next questions

1. Does switching the shared repo connection path from pair-first to connect-first make `bosch-ble-dump-gatt` succeed with the existing live security staging?
2. Once the shared path is connect-first, does `stage_bosch_security()` still need any explicit pairing adjustments, or will the encrypted read/write boundary trigger the correct bond flow naturally?
3. Are there any live activities still calling `assist_connection()` directly instead of going through the new connect-first path?
