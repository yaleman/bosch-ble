#!/usr/bin/env python3
"""
Quick test to see if bike is visible via ESP32 proxy.
No booping - just scan and report.
"""

import asyncio
from bosch_ble import esphome_proxy

BIKE_ADDRESS = '00:04:63:BA:64:FC'
ESPHOME_HOST = 'bosch-ble-proxy.local'

async def main():
    print("Scanning for bike via ESP32 proxy (10s)...")
    config = esphome_proxy.ESPHomeConfig(host=ESPHOME_HOST)
    
    try:
        devices = await esphome_proxy.scan_via_esphome(config, timeout=10.0)
        print(f"Found {len(devices)} devices")
        
        bike_found = False
        for device, adv in devices:
            if device.address == BIKE_ADDRESS:
                print(f"✓ Bike visible: {device.address} - {device.name}")
                bike_found = True
        
        if not bike_found:
            print("✗ Bike not visible")
            print("\nFirst 10 devices:")
            for device, adv in devices[:10]:
                print(f"  {device.address}: {device.name or 'Unknown'}")
        
    except Exception as e:
        print(f"✗ Scan failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
