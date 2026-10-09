#!/usr/bin/env python3
"""
Test ESP32 Bluetooth Proxy connection to Bosch eBike.

This script:
1. Sets up ESP32 proxy connection
2. Boops the bike to wake it up
3. Immediately attempts to connect
4. Reports results

Run with: uv run --with aioesphomeapi python test_esphome_proxy.py
"""

import asyncio
import os
import sys
from aioesphomeapi import APIClient
from bosch_ble import esphome_proxy
from bleak.backends.device import BLEDevice
from bleak_esphome.backend.client import ESPHomeClient

BIKE_ADDRESS = '00:04:63:BA:64:FC'
ESPHOME_HOST = 'bosch-ble-proxy.local'
BOOPER_HOST = 'bike-button-booper.local'
BOOPER_PORT = 6053

async def main():
    print("=" * 60)
    print("ESP32 Bluetooth Proxy Test")
    print("=" * 60)
    
    # Step 1: Set up ESP32 proxy
    print("\n[1/4] Setting up ESP32 proxy...")
    config = esphome_proxy.ESPHomeConfig(host=ESPHOME_HOST)
    try:
        conn = await esphome_proxy.setup_esphome_proxy(config)
        print("✓ Proxy connected")
    except Exception as e:
        print(f"✗ Failed to connect to proxy: {e}")
        return 1
    
    # Step 2: Boop the bike
    print("\n[2/4] Booping bike...")
    try:
        booper = APIClient(
            BOOPER_HOST,
            BOOPER_PORT,
            password="",
            noise_psk=os.environ["BOOPER_API_KEY"],
        )
        await booper.connect(login=True)
        entities, _ = await booper.list_entities_services()
        relay_key = next(e.key for e in entities if 'switch' in type(e).__name__.lower())
        booper.switch_command(relay_key, True)
        await asyncio.sleep(0.2)
        booper.switch_command(relay_key, False)
        await booper.disconnect()
        print("✓ Bike booped")
    except Exception as e:
        print(f"✗ Failed to boop bike: {e}")
        conn._cleanup()
        return 1
    
    # Step 3: Scan for bike
    print("\n[3/4] Scanning for bike...")
    try:
        devices = await esphome_proxy.scan_via_esphome(config, timeout=5.0)
        bike_found = False
        for device, adv in devices:
            if device.address == BIKE_ADDRESS:
                print(f"✓ Bike visible: {device.name}")
                bike_found = True
                break
        
        if not bike_found:
            print(f"✗ Bike not visible (scanned {len(devices)} devices)")
            conn._cleanup()
            return 1
    except Exception as e:
        print(f"✗ Scan failed: {e}")
        conn._cleanup()
        return 1
    
    # Step 4: Connect to bike
    print("\n[4/4] Connecting to bike (pair=True)...")
    bike_device = BLEDevice(
        address=BIKE_ADDRESS,
        name='smart system eBike',
        details={"source": config.host, "address_type": 0},
    )
    
    try:
        client = ESPHomeClient(bike_device, client_data=conn.client_data, timeout=30.0)
        await asyncio.wait_for(client.connect(pair=True), timeout=25.0)
        print(f"✓ Connected: {client.is_connected}")
        
        # Discover services
        discovered_services = client.services
        if discovered_services is None:
            raise RuntimeError("Service discovery did not return services")
        services = list(discovered_services)
        print(f"✓ Found {len(services)} services")
        for s in services[:10]:
            print(f"  Service: {s.uuid}")
        
        await client.disconnect()
        print("✓ Disconnected")
        print("\n" + "=" * 60)
        print("SUCCESS: ESP32 proxy connection works!")
        print("=" * 60)
        
    except asyncio.TimeoutError:
        print("✗ Connection timed out")
        print("\n" + "=" * 60)
        print("FAILED: Connection timeout")
        print("=" * 60)
        conn._cleanup()
        return 1
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print("\n" + "=" * 60)
        print("FAILED: Connection error")
        print("=" * 60)
        conn._cleanup()
        return 1
    
    conn._cleanup()
    return 0

if __name__ == "__main__":
    if "BOOPER_API_KEY" not in os.environ:
        print("Error: BOOPER_API_KEY environment variable not set")
        print("Run: source .envrc")
        sys.exit(1)
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
