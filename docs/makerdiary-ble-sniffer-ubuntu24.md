# Makerdiary BLE Sniffer Setup on Ubuntu 24.04

This guide sets up a Makerdiary `nRF52840 MDK USB Dongle` as a `nRF Sniffer for Bluetooth LE` on Ubuntu 24.04.

It is written for this repo's Bosch debugging workflow:

- capture a fresh phone-to-bike pairing
- capture the first successful reconnect after pairing
- compare that traffic with what BlueZ on `m710qa` fails to do

## What You Need

- Ubuntu 24.04
- `nRF52840 MDK USB Dongle`
- `Wireshark`
- `Python 3`
- the latest `nRF Sniffer for Bluetooth LE` package

Official references:

- [Makerdiary installation guide](https://wiki.makerdiary.com/nrf52840-mdk-usb-dongle/guides/ble-sniffer/installation/)
- [Makerdiary running guide](https://wiki.makerdiary.com/nrf52840-mdk-usb-dongle/guides/ble-sniffer/running-sniffer/)
- [Nordic nRF Sniffer user guide](https://infocenter.nordicsemi.com/pdf/nRF_Sniffer_UG_v2.2.pdf)

## 1. Install Ubuntu Packages

```bash
sudo apt update
sudo apt install -y wireshark python3 python3-pip python3-venv python3-setuptools git curl unzip
```

If the installer asks whether non-superusers should be able to capture packets, answer `yes`.

Add your user to the required groups:

```bash
sudo usermod -a -G wireshark "$USER"
sudo usermod -a -G dialout "$USER"
```

Log out and back in before continuing.

## 2. Download the Sniffer Package

Download the latest `nRF Sniffer for Bluetooth LE` package from the Nordic/Makerdiary docs linked above, then extract it:

```bash
git clone https://github.com/makerdiary/nrf52840-mdk-usb-dongle
cd nrf52840-mdk-usb-dongle/tools/ble_sniffer/extcap
uv venv
uv pip install -r requirements.txt
```

After extraction, the files you care about are:

- `firmware/ble_sniffer/`
- `tools/ble_sniffer/extcap/`
- `tools/ble_sniffer/Profile_nRF_Sniffer_Bluetooth_LE/`

## 3. Flash the Makerdiary Dongle

The Makerdiary docs say the sniffer firmware for this board is provided as a `.uf2` file.

To flash it:

1. Hold the dongle button while plugging it into USB.
2. Release the button after the RGB LED turns green.
3. Confirm it mounts as `UF2BOOT`.
4. Copy the sniffer firmware onto the mounted volume:

```bash
cp firmware/ble_sniffer/nrf_sniffer_for_bluetooth_le_*.uf2 /media/"$USER"/UF2BOOT/
sync
```

1. Unplug and replug the dongle.

After it has been programmed once, the button becomes reset. To re-enter bootloader mode later, plug it in and double-click the button.

## 4. Install the Wireshark Extcap Tool

From the extracted sniffer package:

```bash
cd ~/nrf_sniffer_for_bluetooth_le_*/tools/ble_sniffer/extcap
python3 -m pip install --user -r requirements.txt
```

Find Wireshark's personal `extcap` directory from:

- `Wireshark -> Help -> About Wireshark -> Folders -> Personal Extcap path`

Create it if needed, then copy the extcap files there:

```bash
mkdir -p ~/.local/lib/wireshark/extcap
cp -r ./* ~/.local/lib/wireshark/extcap/
chmod +x ~/.local/lib/wireshark/extcap/nrf_sniffer_ble.sh
```

If your `Personal Extcap path` in Wireshark points somewhere else, use that path instead of `~/.local/lib/wireshark/extcap`.

## 5. Install the Wireshark Profile

Create the profile directory and copy the bundled sniffer profile:

```bash
mkdir -p ~/.config/wireshark/profiles
cp -r ~/nrf52840-mdk-usb-dongle/tools/ble_sniffer/Profile_nRF_Sniffer_Bluetooth_LE \
  ~/.config/wireshark/profiles/
```

In Wireshark:

1. Open `Edit -> Configuration Profiles...`
2. Select `Profile_nRF_Sniffer_Bluetooth_LE`

## 6. Verify the Extcap Interface

Run the extcap script directly:

```bash
~/.local/lib/wireshark/extcap/nrf_sniffer_ble.sh --extcap-interfaces
```

Expected result:

- output includes `nRF Sniffer for Bluetooth LE`
- no Python import errors
- no permissions errors opening the dongle

If that works, start Wireshark and press `F5` on the capture screen. You should see an `nRF Sniffer` capture interface.

## 7. Start a Capture

General workflow:

1. Plug in the sniffer dongle.
2. Place it physically close to the bike and the phone.
3. Open Wireshark.
4. Select the `nRF Sniffer` interface.
5. If needed, enable `View -> Interface Toolbars -> nRF Sniffer for Bluetooth LE`.
6. Start capture before initiating pairing.

For BLE, distance matters. Put the sniffer within about 30 cm of the devices for the first attempt.

## 8. Capture the Bosch Pairing Flow

The highest-value capture is a fresh pairing, not an already-bonded reconnect.

Do this in order:

1. Remove the bike from the Bosch app.
2. Remove the phone from the bike if the UI allows it.
3. Turn off Bluetooth on other nearby devices that might race the connection.
4. Start Wireshark capture.
5. Start the Bosch app pairing flow.
6. Let the phone connect from scratch.
7. Save the capture immediately after the bike is fully connected and healthy.

Then do a second capture of a normal reconnect without re-pairing.

## 9. What to Look For

In Wireshark, focus on:

- `btle.advertising_address`
- `btatt`
- `btsmp`
- `btcommon.eir_ad.entry.service_uuid16`

High-value events:

- `SMP Pairing Request` / `Pairing Response`
- `LL_ENC_REQ` or encryption start
- the first `ATT Read By Group Type` after connect
- the first `ATT Write Request` to any Bosch vendor characteristic
- disconnect reason if the bike drops the link

The Bosch device we have seen usually advertises:

- `Name: smart system eBike`
- `UUID 0xfe02`

BlueZ on `m710qa` also already has cached UUIDs including:

- `1800`
- `1801`
- `180a`
- `0000eb10-eaa2-11e9-81b4-2a2ae2dbcce4`
- `0000eb20-eaa2-11e9-81b4-2a2ae2dbcce4`
- `0000eb40-eaa2-11e9-81b4-2a2ae2dbcce4`
- `0000eba0-eaa2-11e9-81b4-2a2ae2dbcce4`
- `0000ebd0-eaa2-11e9-81b4-2a2ae2dbcce4`

The main question is whether the phone performs a required authenticated write or security transition before the bike will keep the session alive.

## 10. Caveats

- If the phone is already bonded, much of the interesting GATT traffic will be encrypted.
- A fresh unpair and re-pair is the most useful capture.
- `btmon` on Linux is still useful, but it is host-side and not a substitute for over-the-air sniffing.

## 11. Quick Troubleshooting

No `UF2BOOT` volume:

- unplug the dongle
- hold the button while plugging it in
- if already flashed before, plug it in and double-click the button

No `nRF Sniffer` interface in Wireshark:

- rerun `nrf_sniffer_ble.sh --extcap-interfaces`
- confirm the files are in the `Personal Extcap path`
- confirm the script is executable
- restart Wireshark

Permissions errors:

- confirm your user is in `wireshark` and `dialout`
- log out and back in

Dongle not detected:

- try a different USB port
- avoid USB hubs for the first setup
- verify the board is running the sniffer `.uf2`, not some other firmware

## 12. Suggested Capture Files

Save captures with names like:

- `captures/bosch-phone-pairing-fresh.pcapng`
- `captures/bosch-phone-reconnect.pcapng`
- `captures/bosch-linux-connect-failure.pcapng`

Once you have a capture, the next job is to compare:

- phone's first successful connect sequence
- Linux's failed connect sequence on `m710qa`

That comparison should tell us whether the missing piece is:

- security
- an app-level initialization write
- or a transport-level disconnect before services are usable
