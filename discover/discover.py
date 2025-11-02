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
    AdaLight protocol discovery via "magic word"
    
    Traditional Adalight devices periodically transmit "Ada\n" (every 1-5 seconds)
    when idle as a discovery/keepalive signal.
    """
    
    def get_protocol_name(self) -> str:
        return "AdaLight"
    
    def discover(self, debug=False, skip=False) -> bool:
        """
        Listen for periodic 'Ada\n' magic word that traditional Adalight devices send
        
        Args:
            debug: Enable debug output
            skip: If True, skip detection (used when WLED or AWA already detected)
        """
        if skip:
            if debug:
                print(f"\n    [DEBUG] Skipping Adalight magic word detection (already detected via other protocol)")
            return False
        
        if debug:
            print(f"\n    [DEBUG] Starting Adalight magic word discovery on {self.port}")
            print(f"    [DEBUG] Listening for 'Ada\\n' keepalive signal (waiting up to 5 seconds)")
        
        try:
            with serial.Serial(self.port, 115200, timeout=6) as ser:
                if debug:
                    print(f"    [DEBUG] Port opened at 115200 baud")
                
                # Clear buffers
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # Listen for "Ada\n" magic word
                # Traditional Adalight sends this every 1-5 seconds when idle
                import time
                start_time = time.time()
                buffer = b''
                
                while time.time() - start_time < 5.5:
                    if ser.in_waiting > 0:
                        data = ser.read(ser.in_waiting)
                        buffer += data
                        
                        if debug and data:
                            print(f"    [DEBUG] Received: {data}")
                        
                        # Check for "Ada\n" pattern
                        if b'Ada\n' in buffer or b'Ada\r\n' in buffer:
                            if debug:
                                print(f"    [DEBUG] ✓ Detected Adalight magic word!")
                            
                            self.device_info = {
                                'protocol': 'adalight',
                                'detected_by': 'magic_word',
                                'baud_rate': 115200,
                                'note': 'Detected via Ada\\n keepalive signal'
                            }
                            return True
                    
                    time.sleep(0.1)
                
                if debug:
                    print(f"    [DEBUG] No Adalight magic word detected after 5 seconds")
                    
        except (serial.SerialException, OSError) as e:
            if debug:
                print(f"    [DEBUG] Error: {e}")
        
        return False


class WLEDDiscovery(ProtocolDiscovery):
    """
    WLED over serial discovery
    WLED devices respond to JSON API commands over serial
    """
    
    def get_protocol_name(self) -> str:
        return "WLED"
    
    def discover(self, debug=False) -> bool:
        """
        Try to query WLED device via JSON API over serial
        WLED JSON API only works at 115200 baud
        Note: WLED's Adalight protocol for LED data may work at higher speeds,
        but this cannot be detected via JSON API
        """
        if debug:
            print(f"\n    [DEBUG] Starting WLED discovery on {self.port}")
            print(f"    [DEBUG] WLED JSON API only responds at 115200 baud")
        
        try:
            with serial.Serial(self.port, 115200, timeout=0.5) as ser:
                if debug:
                    print(f"    [DEBUG] Port opened successfully")
                
                # Clear buffers
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # Send JSON API query for state and info
                query = b'{"v":true}\n'
                if debug:
                    print(f"    [DEBUG] Sending: {query.decode().strip()}")
                
                ser.write(query)
                ser.flush()
                
                # Wait for response (500ms total timeout for request-response)
                import time
                time.sleep(0.2)
                
                # Quick check if any data is waiting
                if ser.in_waiting == 0:
                    if debug:
                        print(f"    [DEBUG] No response from WLED JSON API")
                    return False
                
                # Read response
                response = b''
                while ser.in_waiting > 0:
                    chunk = ser.read(ser.in_waiting)
                    response += chunk
                    time.sleep(0.02)
                
                if debug:
                    print(f"    [DEBUG] Received {len(response)} bytes")
                
                if not response:
                    if debug:
                        print(f"    [DEBUG] No data after reading")
                    return False
                
                # Try to parse as JSON
                try:
                    response_str = response.decode('utf-8', errors='ignore')
                    if debug:
                        print(f"    [DEBUG] Full JSON Response from WLED:")
                        print(f"    [DEBUG] {response_str}")
                    
                    import json
                    data = json.loads(response_str)
                    
                    # Validate it's a WLED response
                    if 'info' not in data or 'state' not in data:
                        if debug:
                            print(f"    [DEBUG] Invalid WLED response structure")
                        return False
                    
                    # Extract device information
                    info = data.get('info', {})
                    leds_info = info.get('leds', {})
                    wifi_info = info.get('wifi', {})
                    
                    # Parse light capabilities
                    lc = leds_info.get('lc', 1)
                    pixel_format = self._parse_pixel_format(lc, debug)
                    
                    if debug:
                        print(f"    [DEBUG] VALID WLED DEVICE DETECTED!")
                        print(f"    [DEBUG] Version: {info.get('ver')}")
                        print(f"    [DEBUG] LED count: {leds_info.get('count')}")
                        print(f"    [DEBUG] Light capabilities: {lc} -> {pixel_format}")
                        print(f"    [DEBUG] Detected at baud rate: 115200")
                    
                    # Store device info including brand/product from JSON
                    self.device_info = {
                        'protocol': 'wled',
                        'detected_by': 'json_api',
                        'baud_rate': 115200,
                        'version': info.get('ver', 'unknown'),
                        'name': info.get('name', 'WLED Device'),
                        'brand': info.get('brand', ''),
                        'product': info.get('product', ''),
                        'led_count': leds_info.get('count', 100),
                        'capabilities': {
                            'rgb': bool(lc & 0x01),
                            'white': bool(lc & 0x02),
                            'cct': bool(lc & 0x04)
                        },
                        'pixel_format': pixel_format,
                        'supported_protocols': ['adalight', 'tpm2'],
                        'mac': info.get('mac', ''),
                        # WiFi info for display only
                        'wifi_ip': info.get('ip', ''),
                        'wifi_signal': wifi_info.get('signal', 0),
                        'wifi_bssid': wifi_info.get('bssid', ''),
                        'wifi_channel': wifi_info.get('channel', 0),
                        # Store full JSON for user reference
                        'full_json': data
                    }
                    return True
                    
                except json.JSONDecodeError as e:
                    if debug:
                        print(f"    [DEBUG] JSON decode error: {e}")
                    return False
                    
        except (serial.SerialException, OSError) as e:
            if debug:
                print(f"    [DEBUG] Error opening port: {e}")
            return False
        
        # Fallback: Try version query command (byte 0x76)
        if debug:
            print(f"    [DEBUG] JSON API failed, trying version query fallback")
        
        try:
            with serial.Serial(self.port, 115200, timeout=2) as ser:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # Send version query
                ser.write(b'v')
                ser.flush()
                
                import time
                time.sleep(0.2)
                
                response = ser.read(100)
                if response and len(response) > 0:
                    response_str = response.decode('utf-8', errors='ignore').strip()
                    if debug:
                        print(f"    [DEBUG] Version response: {response_str}")
                    
                    # Store minimal info
                    self.device_info = {
                        'protocol': 'wled',
                        'detected_by': 'version_query',
                        'baud_rate': 115200,
                        'version': response_str,
                        'name': 'WLED Device',
                        'led_count': 100,  # Default
                        'pixel_format': 'GRB',
                        'supported_protocols': ['adalight', 'tpm2'],
                        'note': 'Limited info - JSON API failed'
                    }
                    return True
        except:
            pass
        
        if debug:
            print(f"    [DEBUG] No WLED device detected")
        return False
    
    def _parse_pixel_format(self, lc: int, debug: bool = False) -> str:
        """
        Parse light capabilities byte to determine pixel format
        lc bit 0: RGB support
        lc bit 1: White channel support
        lc bit 2: CCT support
        """
        has_rgb = bool(lc & 0x01)
        has_white = bool(lc & 0x02)
        
        if has_rgb and has_white:
            # RGBW - most common order is GRBW for addressable LEDs
            return 'GRBW'
        elif has_rgb:
            # RGB - most common order is GRB for addressable LEDs like WS2812B
            return 'GRB'
        elif has_white:
            # White only
            return 'W'
        else:
            # Default
            return 'GRB'


class ImprovDiscovery(ProtocolDiscovery):
    """
    Improv WiFi provisioning protocol discovery
    A standardized protocol for device identification over serial
    """
    
    def get_protocol_name(self) -> str:
        return "Improv"
    
    def discover(self, debug=False) -> bool:
        """
        Try to detect Improv-capable device
        Improv requires 115200 baud (fixed)
        """
        if debug:
            print(f"\n    [DEBUG] Starting Improv discovery on {self.port}")
        
        try:
            with serial.Serial(self.port, 115200, timeout=0.5) as ser:
                if debug:
                    print(f"    [DEBUG] Port opened at 115200 baud")
                
                # Clear buffers
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # Build RPC Command: Request Device Information (0x03)
                # Packet format: 'IMPROV' + version + type + command + length + data + checksum
                command_packet = self._build_device_info_request()
                
                if debug:
                    print(f"    [DEBUG] Sending device info request: {command_packet.hex()}")
                
                ser.write(command_packet)
                ser.flush()
                
                # Wait for response (500ms timeout for request-response)
                import time
                time.sleep(0.2)
                
                # Read response
                response = ser.read(256)
                
                if debug:
                    print(f"    [DEBUG] Received {len(response)} bytes: {response.hex()}")
                
                if len(response) < 10:
                    if debug:
                        print(f"    [DEBUG] Response too short")
                    return False
                
                # Parse Improv response
                device_info = self._parse_improv_response(response, debug)
                
                if device_info:
                    if debug:
                        print(f"    [DEBUG] ✓ Valid Improv device detected!")
                        print(f"    [DEBUG] Firmware: {device_info.get('firmware_name')}")
                        print(f"    [DEBUG] Hardware: {device_info.get('hardware')}")
                    
                    # Also get current state
                    state = self._get_provisioning_state(ser, debug)
                    if state:
                        device_info['provisioning_state'] = state
                    
                    self.device_info = device_info
                    return True
                
        except (serial.SerialException, OSError) as e:
            if debug:
                print(f"    [DEBUG] Error: {e}")
        
        if debug:
            print(f"    [DEBUG] No Improv device detected")
        return False
    
    def _build_device_info_request(self) -> bytes:
        """Build Improv RPC command to request device information"""
        # Packet: 'IMPROV' + version(1) + type(0x03) + command(0x03) + length(0) + checksum
        packet = bytearray(b'IMPROV')
        packet.append(0x01)  # Version
        packet.append(0x03)  # Type: RPC Command
        packet.append(0x00)  # Length: 0 (no data for device info request)
        
        # Calculate checksum (sum of all bytes after header, except checksum itself)
        checksum = sum(packet[6:]) & 0xFF
        packet.append(checksum)
        
        return bytes(packet)
    
    def _get_provisioning_state(self, ser, debug=False) -> str:
        """Request current provisioning state"""
        # Build state request command (0x02)
        packet = bytearray(b'IMPROV')
        packet.append(0x01)  # Version
        packet.append(0x03)  # Type: RPC Command
        packet.append(0x01)  # Length: 1
        packet.append(0x02)  # Command: Request current state
        checksum = sum(packet[6:]) & 0xFF
        packet.append(checksum)
        
        ser.write(bytes(packet))
        ser.flush()
        
        import time
        time.sleep(0.2)
        
        response = ser.read(100)
        if len(response) >= 10 and response[:6] == b'IMPROV':
            # Parse state from response
            if response[7] == 0x01:  # Current state packet
                state_code = response[9] if len(response) > 9 else 0
                state_map = {
                    0x02: 'Ready',
                    0x03: 'Provisioning',
                    0x04: 'Provisioned'
                }
                return state_map.get(state_code, 'Unknown')
        
        return 'Unknown'
    
    def _parse_improv_response(self, response: bytes, debug: bool = False) -> Optional[Dict[str, Any]]:
        """Parse Improv RPC result packet"""
        # Check header
        if len(response) < 10 or response[:6] != b'IMPROV':
            if debug:
                print(f"    [DEBUG] Invalid Improv header")
            return None
        
        version = response[6]
        packet_type = response[7]
        length = response[8]
        
        if debug:
            print(f"    [DEBUG] Version: {version}, Type: {packet_type}, Length: {length}")
        
        # We expect RPC Result (0x04)
        if packet_type != 0x04:
            if debug:
                print(f"    [DEBUG] Not an RPC result packet")
            return None
        
        # Parse strings from data section
        strings = []
        offset = 9
        
        while offset < len(response) - 1:  # -1 for checksum
            if offset >= len(response):
                break
            
            str_len = response[offset]
            offset += 1
            
            if str_len == 0 or offset + str_len > len(response):
                break
            
            string = response[offset:offset + str_len].decode('utf-8', errors='ignore')
            strings.append(string)
            offset += str_len
        
        if debug:
            print(f"    [DEBUG] Parsed strings: {strings}")
        
        # Device info should have at least 4 strings:
        # firmware_name, firmware_version, hardware, device_name
        if len(strings) >= 4:
            return {
                'protocol': 'improv',
                'detected_by': 'device_info_response',
                'baud_rate': 115200,
                'firmware_name': strings[0],
                'firmware_version': strings[1],
                'hardware': strings[2],
                'device_name': strings[3],
                'improv_capable': True
            }
        
        return None


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
                with serial.Serial(self.port, baud_rate, timeout=0.5) as ser:
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
                    
                    # Wait a moment for device to process (500ms timeout)
                    import time
                    time.sleep(0.05)
                    
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
    # AWA comes before Adalight since it has a defined protocol (not timeout-based)
    discoveries = [
        ImprovDiscovery(port),
        WLEDDiscovery(port),
        AWADiscovery(port),
        AdaLightDiscovery(port)
    ]
    
    detected = []
    wled_detected = False
    awa_detected = False
    
    for discovery in discoveries:
        print(f"  Trying {discovery.get_protocol_name()}...")
        sys.stdout.flush()  # Ensure output appears immediately
        
        # Skip Adalight magic word detection if WLED or AWA already detected
        skip_adalight = isinstance(discovery, AdaLightDiscovery) and (wled_detected or awa_detected)
        
        # Pass appropriate flags to discoveries
        if isinstance(discovery, AdaLightDiscovery):
            result = discovery.discover(debug=debug, skip=skip_adalight)
        elif isinstance(discovery, (AWADiscovery, WLEDDiscovery, ImprovDiscovery)):
            result = discovery.discover(debug=debug)
        else:
            result = discovery.discover()
        
        if result:
            print("    → DETECTED")
            detected.append(discovery)
            
            # Track what was detected
            if discovery.get_device_info().get('protocol') == 'wled':
                wled_detected = True
            elif discovery.get_device_info().get('protocol') == 'awa':
                awa_detected = True
        else:
            if skip_adalight:
                print("    → SKIPPED (already detected via other protocol)")
            else:
                print("    → NOT DETECTED")
    
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
                
                # Pretty-print WLED device information
                if info.get('protocol') == 'wled' and info.get('full_json'):
                    print(f"\n  WLED Device Information:")
                    print(f"  " + "="*60)
                    wled_data = info['full_json']
                    wled_info = wled_data.get('info', {})
                    
                    print(f"  Device: {wled_info.get('brand', 'Unknown')} {wled_info.get('product', '')}")
                    print(f"  Name: {wled_info.get('name', 'WLED')}")
                    print(f"  Version: {wled_info.get('ver', 'unknown')}")
                    print(f"  MAC Address: {wled_info.get('mac', 'N/A')}")
                    
                    # LED configuration
                    leds = wled_info.get('leds', {})
                    print(f"\n  LED Configuration:")
                    print(f"    Count: {leds.get('count', 0)} LEDs")
                    print(f"    Power: {leds.get('pwr', 0)}mW")
                    print(f"    FPS: {leds.get('fps', 0)}")
                    print(f"    Max Segments: {leds.get('maxseg', 0)}")
                    
                    # WiFi information if available
                    wifi = wled_info.get('wifi', {})
                    if wifi.get('ip') or wifi.get('bssid'):
                        print(f"\n  WiFi Information:")
                        if wifi.get('ip'):
                            print(f"    IP Address: {wifi['ip']}")
                        if wifi.get('bssid'):
                            print(f"    BSSID: {wifi['bssid']}")
                        if wifi.get('signal'):
                            print(f"    Signal: {wifi['signal']}%")
                        if wifi.get('channel'):
                            print(f"    Channel: {wifi['channel']}")
                    
                    # Hardware info
                    print(f"\n  Hardware:")
                    print(f"    Architecture: {wled_info.get('arch', 'Unknown')}")
                    print(f"    Core Version: {wled_info.get('core', 'Unknown')}")
                    print(f"    Flash Size: {wled_info.get('getflash', 0) // 1024}KB")
                    print(f"    Free Flash: {wled_info.get('getfreeflash', 0) // 1024}KB")
                    print(f"    Free Heap: {wled_info.get('freeheap', 0)} bytes")
                    print(f"    CPU Frequency: {wled_info.get('cpufreqmhz', 0)}MHz")
                    print(f"    Uptime: {wled_info.get('uptime', 0)} seconds")
                    
                    print(f"  " + "="*60)
                
                # Print standard info for all devices
                print(f"\n  Configuration:")
                for key, value in info.items():
                    if key not in ['response', 'full_json']:  # Don't print full response or JSON
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
    processed_ports = set()
    
    for port, discoveries in discovered_devices.items():
        # Skip ports we've already processed
        if port in processed_ports:
            continue
        
        # Find the best protocol for this port (prefer specific protocols over generic)
        # Priority: WLED > Improv > Adalight > AWA
        best_discovery = None
        for discovery in discoveries:
            protocol = discovery.get_device_info().get('protocol')
            if protocol == 'wled':
                best_discovery = discovery
                break
            elif protocol == 'improv' and (not best_discovery or best_discovery.get_device_info().get('protocol') == 'awa'):
                best_discovery = discovery
            elif protocol == 'adalight' and (not best_discovery or best_discovery.get_device_info().get('protocol') == 'awa'):
                best_discovery = discovery
            elif protocol == 'awa' and not best_discovery:
                best_discovery = discovery
        
        if best_discovery:
            info = best_discovery.get_device_info()
            protocol = info.get('protocol', 'unknown')
            
            # Check if AWA was also detected on this port
            awa_detection = next((d for d in discoveries if d.get_device_info().get('protocol') == 'awa'), None)
            awa_also_detected = awa_detection is not None
            
            # Handle WLED devices
            if protocol == 'wled':
                supported_protocols = info.get('supported_protocols', ['adalight', 'tpm2']).copy()
                
                # Determine best protocol and baud rate
                # If AWA was also detected, prefer AWA at high speed for LED data
                if awa_also_detected:
                    if 'awa' not in supported_protocols:
                        supported_protocols.append('awa')
                    protocol_to_use = "awa"
                    baud_rate = awa_detection.get_device_info().get('baud_rate', 2000000)
                    protocol_note = "Using AWA protocol at high speed for LED data, JSON API works at 115200"
                else:
                    protocol_to_use = "adalight"
                    baud_rate = info.get('baud_rate', 115200)
                    protocol_note = "Using Adalight protocol"
                
                output = {
                    "port": port,
                    "protocol": protocol_to_use,
                    "supported_protocols": supported_protocols,
                    "baud_rate": baud_rate,
                    "opc_channel": 0,
                    "led_count": info.get('led_count', 100),
                    "opc_offset": offset,
                    "pixel_format": info.get('pixel_format', 'GRB'),
                    "device_name": info.get('name', 'WLED Device'),
                    "device_type": "WLED",
                    "wled_version": info.get('version', 'unknown'),
                    "wled_brand": info.get('brand', ''),
                    "wled_product": info.get('product', ''),
                    "note": protocol_note
                }
                
                # Add WiFi info if available
                if info.get('wifi_ip'):
                    output['wifi_ip'] = info['wifi_ip']
                if info.get('mac'):
                    output['mac'] = info['mac']
                    
                config['outputs'].append(output)
                offset += info.get('led_count', 100)
            
            # Handle Improv-only devices
            elif protocol == 'improv':
                output = {
                    "port": port,
                    "protocol": "unknown_improv",
                    "baud_rate": 115200,
                    "opc_channel": 0,
                    "led_count": 100,  # Placeholder - must configure manually
                    "opc_offset": offset,
                    "pixel_format": "GRB",  # Default
                    "needs_configuration": True,
                    "device_name": info.get('device_name', 'Unknown Device'),
                    "firmware": info.get('firmware_name', 'Unknown'),
                    "hardware": info.get('hardware', 'Unknown')
                }
                config['outputs'].append(output)
                offset += 100
            
            # Handle AWA devices
            elif protocol == 'awa':
                output = {
                    "port": port,
                    "protocol": "awa",
                    "baud_rate": info.get('baud_rate', 2000000),
                    "opc_channel": 0,
                    "led_count": 100,  # User should adjust
                    "opc_offset": offset,
                    "pixel_format": "GRB"
                }
                config['outputs'].append(output)
                offset += 100
            
            # Handle Adalight devices (when implemented)
            elif protocol == 'adalight':
                output = {
                    "port": port,
                    "protocol": "adalight",
                    "baud_rate": info.get('baud_rate', 115200),
                    "opc_channel": 0,
                    "led_count": 100,  # User should adjust
                    "opc_offset": offset,
                    "pixel_format": "GRB"
                }
                config['outputs'].append(output)
                offset += 100
            
            processed_ports.add(port)
    
    return config


if __name__ == "__main__":
    sys.exit(main())
