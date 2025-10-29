#!/usr/bin/env python3
"""
OpenPixelControlSerial - Python Implementation
A bridge between OPC protocol and serial LED protocols
"""

import sys
import json
import os
import serial
import serial.tools.list_ports
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any


class ProtocolDiscovery(ABC):
    """Base class for protocol-specific device discovery"""
    
    def __init__(self, port: str):
        self.port = port
        self.device_info: Dict[str, Any] = {}
    
    @abstractmethod
    def discover(self) -> bool:
        """
        Attempt to discover if this port speaks this protocol
        Returns True if device is detected, False otherwise
        """
        pass
    
    @abstractmethod
    def get_protocol_name(self) -> str:
        """Return the name of this protocol"""
        pass
    
    def get_device_info(self) -> Dict[str, Any]:
        """Return discovered device information"""
        return self.device_info


class AdaLightDiscovery(ProtocolDiscovery):
    """
    AdaLight protocol discovery
    Listens for periodic 'Ada' frames sent by the device
    
    NOTE: NOT YET IMPLEMENTED
    """
    
    def get_protocol_name(self) -> str:
        return "AdaLight (NOT YET IMPLEMENTED)"
    
    def discover(self) -> bool:
        """
        Listen for periodic 'Ada' frames that some devices send
        during idle/initialization
        
        TODO: Implement proper AdaLight detection
        """
        # Not yet implemented
        return False


class WLEDDiscovery(ProtocolDiscovery):
    """
    WLED over serial discovery
    WLED devices can respond to JSON API commands over serial
    
    NOTE: NOT YET IMPLEMENTED
    """
    
    def get_protocol_name(self) -> str:
        return "WLED (NOT YET IMPLEMENTED)"
    
    def discover(self) -> bool:
        """
        Try to query WLED device via JSON API over serial
        WLED supports JSON commands like {"v":true} for version info
        
        TODO: Implement proper WLED detection
        """
        # Not yet implemented
        return False


class AWADiscovery(ProtocolDiscovery):
    """
    AWA (Advanced Wireless Addressable) protocol discovery
    Used by HyperSerialPico and similar devices
    
    AWA is an extension of the Adalight protocol for high-speed LED control.
    It doesn't have a separate identification protocol - devices are detected
    by their ability to operate at high baud rates and respond to Adalight frames.
    """
    
    def get_protocol_name(self) -> str:
        return "AWA"
    
    def discover(self, debug=False) -> bool:
        """
        Attempt to detect AWA/Adalight protocol device
        AWA devices typically operate at 2000000 baud and use Adalight protocol
        """
        # AWA devices typically use very high baud rates
        # Standard Adalight uses 115200, AWA uses up to 2000000
        baud_rates = [2000000, 1000000, 115200]
        
        if debug:
            print(f"\n    [DEBUG] Starting AWA discovery on {self.port}")
            print(f"    [DEBUG] AWA devices use Adalight protocol at high speed")
        
        for baud_rate in baud_rates:
            if debug:
                print(f"    [DEBUG] Trying baud rate: {baud_rate}")
            
            try:
                with serial.Serial(self.port, baud_rate, timeout=2) as ser:
                    if debug:
                        print(f"    [DEBUG] Port opened successfully")
                    
                    # Clear buffers
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                    
                    # Method 1: Send Adalight header to trigger response
                    # Adalight frame: 'A' 'd' 'a' + LED count high + LED count low + checksum
                    # Use a small test frame (10 LEDs)
                    led_count = 10
                    ada_header = bytearray([
                        0x41, 0x64, 0x61,  # 'Ada' header
                        (led_count >> 8) & 0xFF,  # LED count high byte
                        led_count & 0xFF,         # LED count low byte
                        (led_count >> 8) ^ (led_count & 0xFF) ^ 0x55  # Checksum
                    ])
                    
                    if debug:
                        print(f"    [DEBUG] Sending Adalight test frame: {ada_header.hex()}")
                    
                    # Send test frame
                    ser.write(bytes(ada_header))
                    ser.flush()
                    
                    # Wait a moment for device to process
                    import time
                    time.sleep(0.1)
                    
                    # Check if device is ready (some devices send acknowledgment)
                    response = ser.read(100)
                    
                    if debug:
                        if response:
                            print(f"    [DEBUG] Received {len(response)} bytes: {response.hex()}")
                        else:
                            print(f"    [DEBUG] No response (expected for most AWA devices)")
                    
                    # Method 2: Try to detect device by USB VID/PID
                    # Raspberry Pi Pico devices have specific USB identifiers
                    try:
                        for port in serial.tools.list_ports.comports():
                            if port.device == self.port:
                                # Check for known AWA device identifiers
                                vid_pid_known = False
                                device_name = ""
                                
                                # Raspberry Pi Pico: VID=0x2E8A, PID=0x000A or 0x0009
                                if 'VID:PID=2E8A:000A' in port.hwid.upper() or 'VID:PID=2E8A:0009' in port.hwid.upper():
                                    vid_pid_known = True
                                    device_name = "Raspberry Pi Pico (RP2040)"
                                
                                # Adafruit boards typically use VID=0x239A
                                elif 'VID:PID=239A' in port.hwid.upper():
                                    vid_pid_known = True
                                    device_name = "Adafruit RP2040 board"
                                
                                if debug:
                                    print(f"    [DEBUG] USB Device: {port.description}")
                                    print(f"    [DEBUG] Hardware ID: {port.hwid}")
                                    if vid_pid_known:
                                        print(f"    [DEBUG] ✓ Recognized as: {device_name}")
                                
                                # If we found a known device that opened successfully at high baud rate
                                if vid_pid_known and baud_rate >= 1000000:
                                    if debug:
                                        print(f"    [DEBUG] ✓ AWA device detected by USB VID/PID at high baud rate!")
                                    
                                    self.device_info = {
                                        'protocol': 'awa',
                                        'detected_by': 'usb_vid_pid',
                                        'baud_rate': baud_rate,
                                        'device_name': device_name,
                                        'vid_pid': port.hwid
                                    }
                                    return True
                    except Exception as e:
                        if debug:
                            print(f"    [DEBUG] USB detection error: {e}")
                    
                    # Method 3: If high baud rate works, assume it's an AWA-capable device
                    # Regular Arduino/Adalight typically can't handle 2000000 baud reliably
                    if baud_rate >= 2000000:
                        if debug:
                            print(f"    [DEBUG] ✓ Port accepts ultra-high baud rate (2Mbps) - likely AWA device")
                        
                        self.device_info = {
                            'protocol': 'awa',
                            'detected_by': 'high_baud_rate',
                            'baud_rate': baud_rate,
                            'note': 'Device accepts 2Mbps - typical of HyperSerialPico/AWA'
                        }
                        return True
                        
            except (serial.SerialException, OSError) as e:
                if debug:
                    print(f"    [DEBUG] Error at {baud_rate}: {e}")
                continue
        
        if debug:
            print(f"    [DEBUG] No AWA device detected")
        return False


def list_serial_ports() -> List[serial.tools.list_ports.ListPortInfo]:
    """
    List all available serial ports on the system
    Cross-platform using pyserial's list_ports
    """
    ports = serial.tools.list_ports.comports()
    return sorted(ports, key=lambda p: p.device)


def print_port_info(port_info: serial.tools.list_ports.ListPortInfo):
    """Print detailed information about a serial port"""
    print(f"\nPort: {port_info.device}")
    print(f"  Description: {port_info.description}")
    print(f"  Hardware ID: {port_info.hwid}")
    if port_info.manufacturer:
        print(f"  Manufacturer: {port_info.manufacturer}")
    if port_info.product:
        print(f"  Product: {port_info.product}")
    if port_info.serial_number:
        print(f"  Serial Number: {port_info.serial_number}")


def discover_protocols(port: str, debug: bool = False) -> List[ProtocolDiscovery]:
    """
    Attempt to discover which protocols a port speaks
    Returns list of successful protocol discoveries
    """
    discoveries = [
        AdaLightDiscovery(port),
        WLEDDiscovery(port),
        AWADiscovery(port)
    ]
    
    detected = []
    for discovery in discoveries:
        print(f"  Trying {discovery.get_protocol_name()}...", end=" ")
        
        # Pass debug flag to AWA discovery
        if isinstance(discovery, AWADiscovery):
            result = discovery.discover(debug=debug)
        else:
            result = discovery.discover()
        
        if result:
            print("✓ DETECTED")
            detected.append(discovery)
        else:
            print("✗")
    
    return detected


def main():
    """Main entry point"""
    # Check for debug flag
    debug = '--debug' in sys.argv or '-d' in sys.argv
    
    print("OpenPixelControlSerial - Python Implementation")
    print("=" * 50)
    if debug:
        print("DEBUG MODE ENABLED")
        print("=" * 50)
    print()
    
    # List all available serial ports
    ports = list_serial_ports()
    
    if not ports:
        print("No serial ports found on this system.")
        return 1
    
    print(f"Found {len(ports)} serial port(s):\n")
    
    # Display port information
    for port_info in ports:
        print_port_info(port_info)
    
    print("\n" + "=" * 50)
    print("Attempting protocol discovery on each port...")
    print("=" * 50)
    
    # Try to discover protocols on each port
    all_discovered = {}
    for port_info in ports:
        print(f"\nScanning {port_info.device}...")
        discovered = discover_protocols(port_info.device, debug=debug)
        
        if discovered:
            all_discovered[port_info.device] = discovered
    
    # Summary
    print("\n" + "=" * 50)
    print("Discovery Summary")
    print("=" * 50)
    
    if all_discovered:
        for port, discoveries in all_discovered.items():
            print(f"\n{port}:")
            for discovery in discoveries:
                print(f"  - {discovery.get_protocol_name()}")
                info = discovery.get_device_info()
                for key, value in info.items():
                    if key != 'response':  # Don't print full response
                        print(f"    {key}: {value}")
        
        # Generate config file
        print("\n" + "=" * 50)
        print("Generating Configuration")
        print("=" * 50)
        
        config = generate_config(all_discovered)
        config_path = "config.json"
        
        # Check if file exists and warn user
        if os.path.exists(config_path):
            print(f"\nWARNING: {config_path} already exists and will be overwritten.")
        
        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"\n✓ Configuration saved to: {config_path}")
            print(f"  Review and adjust LED counts and pixel formats as needed.")
        except Exception as e:
            print(f"\n✗ Error writing config file: {e}")
            return 1
    else:
        print("\nNo LED controller devices detected.")
        print("Make sure your devices are connected and powered on.")
    
    return 0


def generate_config(discovered_devices: Dict[str, List[ProtocolDiscovery]]) -> Dict[str, Any]:
    """
    Generate OpenPixelControlSerial configuration from discovered devices
    """
    config = {
        "opc": {
            "host": "0.0.0.0",
            "port": 7890
        },
        "outputs": []
    }
    
    offset = 0
    for port, discoveries in discovered_devices.items():
        for discovery in discoveries:
            info = discovery.get_device_info()
            protocol = info.get('protocol', 'unknown')
            
            # Only process known protocols
            if protocol in ['awa', 'adalight', 'wled']:
                output = {
                    "port": port,
                    "protocol": protocol,
                    "baud_rate": info.get('baud_rate', 115200),
                    "opc_channel": 0,  # Default to broadcast channel
                    "led_count": 100,  # Default, user should adjust
                    "opc_offset": offset
                }
                
                config['outputs'].append(output)
                offset += 100  # Increment offset for next device
    
    return config


if __name__ == "__main__":
    sys.exit(main())
