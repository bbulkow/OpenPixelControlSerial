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
import time
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Tuple


# ============================================================================
# Protocol Frame Builders (extracted from validate.py)
# ============================================================================

def build_adalight_frame(pixels: List[Tuple[int, int, int]]) -> bytes:
    """
    Build Adalight protocol frame
    Header: 'Ada' + LED count high + LED count low + checksum + pixel data
    NOTE: LED count field is (actual_count - 1), matching AWA protocol convention
    """
    led_count = len(pixels)
    count_minus_one = led_count - 1
    header = bytearray([
        0x41, 0x64, 0x61,  # 'Ada'
        (count_minus_one >> 8) & 0xFF,
        count_minus_one & 0xFF,
        (count_minus_one >> 8) ^ (count_minus_one & 0xFF) ^ 0x55
    ])
    
    # Build pixel data (RGB)
    data = bytearray()
    for r, g, b in pixels:
        data.append(r & 0xFF)
        data.append(g & 0xFF)
        data.append(b & 0xFF)
    
    return bytes(header + data)


def build_awa_frame(pixels: List[Tuple[int, int, int]]) -> bytes:
    """
    Build AWA protocol frame (HyperSerialPico format)
    Header: 'Awa' + LED count high + LED count low + CRC + pixel data + Fletcher checksums
    """
    led_count = len(pixels)
    
    # AWA header
    count_hi = (led_count - 1) >> 8 & 0xFF
    count_lo = (led_count - 1) & 0xFF
    crc = (count_hi ^ count_lo) ^ 0x55
    
    header = bytearray([
        0x41, 0x77, 0x61,  # 'Awa'
        count_hi,
        count_lo,
        crc
    ])
    
    # Build pixel data (RGB)
    data = bytearray()
    for r, g, b in pixels:
        data.append(r & 0xFF)
        data.append(g & 0xFF)
        data.append(b & 0xFF)
    
    # Calculate Fletcher checksums
    fletcher1 = 0
    fletcher2 = 0
    fletcher_ext = 0
    position = 0
    
    for byte in data:
        fletcher1 = (fletcher1 + byte) % 255
        fletcher2 = (fletcher2 + fletcher1) % 255
        fletcher_ext = (fletcher_ext + (byte ^ position)) % 255
        position += 1
    
    # Special case: if fletcher_ext is 0x41 ('A'), use 0xaa
    if fletcher_ext == 0x41:
        fletcher_ext = 0xaa
    
    return bytes(header + data + bytearray([fletcher1, fletcher2, fletcher_ext]))


# ============================================================================
# Test Pattern Generator
# ============================================================================

def generate_test_pattern(frame: int, led_count: int = 10) -> List[Tuple[int, int, int]]:
    """
    Generate test pattern: White → Off → Red → Off → Blue → Off → Green → Off
    Pattern cycles every 8 frames (at 0.5s interval = 4 seconds per cycle)
    """
    patterns = [
        (255, 255, 255),  # White
        (0, 0, 0),        # Off
        (255, 0, 0),      # Red
        (0, 0, 0),        # Off
        (0, 0, 255),      # Blue
        (0, 0, 0),        # Off
        (0, 255, 0),      # Green
        (0, 0, 0),        # Off
    ]
    
    color = patterns[frame % len(patterns)]
    return [color] * led_count


# ============================================================================
# User Interaction Helpers
# ============================================================================

def ask_user(question: str) -> bool:
    """Ask user a yes/no question, return True for yes, False for no"""
    while True:
        try:
            response = input(f"{question} (y/n): ").strip().lower()
            if response in ('y', 'yes'):
                return True
            elif response in ('n', 'no'):
                return False
            else:
                print("  Please enter 'y' or 'n'")
        except (KeyboardInterrupt, EOFError):
            print("\n  Interrupted by user")
            return False


def wait_for_confirmation(question: str) -> bool:
    """Wait for user to confirm they see the pattern (no timeout)"""
    return ask_user(question)


# ============================================================================
# Interactive Protocol Testing
# ============================================================================

def test_protocol_interactive(port: str, baud_rate: int, protocol: str, 
                              led_count: int = 10, debug: bool = False) -> bool:
    """
    Test a protocol interactively by sending visual pattern
    Returns True if user confirms LEDs are blinking
    """
    import threading
    
    try:
        if debug:
            print(f"    [DEBUG] Opening {port} at {baud_rate} baud for {protocol} test")
        
        with serial.Serial(port, baud_rate, timeout=1) as ser:
            # Allow device to initialize
            time.sleep(0.1)
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            print(f"    Testing {baud_rate} baud - Watch your LEDs!")
            print(f"    Pattern: White → Off → Red → Off → Blue → Off → Green → Off")
            
            # Flag to control pattern loop
            keep_running = threading.Event()
            keep_running.set()
            
            # Function to send pattern in background
            def send_pattern():
                frame = 0
                last_frame_time = None
                try:
                    while keep_running.is_set():
                        current_time = time.time()
                        if last_frame_time is not None:
                            frame_delay = current_time - last_frame_time
                        else:
                            frame_delay = 0
                        last_frame_time = current_time
                        
                        pixels = generate_test_pattern(frame, led_count)
                        
                        if protocol == 'awa':
                            frame_data = build_awa_frame(pixels)
                        elif protocol == 'adalight':
                            frame_data = build_adalight_frame(pixels)
                        else:
                            return
                        
                        if debug:
                            from datetime import datetime
                            ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                            print(f"[{ts}] [DISCOVER-TIMING] Frame #{frame}: delay={frame_delay*1000:.1f}ms since last")
                            print(f"[{ts}] [DISCOVER-DATA] {protocol.upper()}: {len(frame_data)} bytes total")
                            if protocol == 'adalight':
                                print(f"[{ts}] [DISCOVER-DATA]   - Header: 6 bytes")
                                print(f"[{ts}] [DISCOVER-DATA]   - Pixel data: {len(frame_data)-6} bytes")
                                print(f"[{ts}] [DISCOVER-DATA]   - LED count: {led_count}")
                            hex_dump = ' '.join(f'{b:02x}' for b in frame_data[:48])
                            print(f"[{ts}] [DISCOVER-HEX] First 48 bytes: {hex_dump}")
                        
                        ser.write(frame_data)
                        ser.flush()
                        
                        time.sleep(0.5)  # 0.5s per frame
                        frame += 1
                except:
                    pass  # Ignore errors when stopping
            
            # Start pattern in background thread
            pattern_thread = threading.Thread(target=send_pattern, daemon=True)
            pattern_thread.start()
            
            # Give pattern a moment to start
            time.sleep(0.5)
            
            try:
                # Ask user immediately while pattern plays
                result = wait_for_confirmation("    Did you see LEDs blinking in this pattern?")
                
                # Stop pattern
                keep_running.clear()
                pattern_thread.join(timeout=1.0)
                
                # Clear LEDs after test
                clear_pixels = [(0, 0, 0)] * led_count
                if protocol == 'awa':
                    ser.write(build_awa_frame(clear_pixels))
                else:
                    ser.write(build_adalight_frame(clear_pixels))
                ser.flush()
                
                return result
                
            except KeyboardInterrupt:
                print("\n    Test interrupted")
                keep_running.clear()
                return False
                
    except (serial.SerialException, OSError) as e:
        if debug:
            print(f"    [DEBUG] Error during test: {e}")
        return False


# ============================================================================
# WLED Discovery with Interactive LED Speed Testing
# ============================================================================

class WLEDDiscovery:
    """WLED discovery with JSON API and interactive LED data speed testing"""
    
    def __init__(self, port: str):
        self.port = port
        self.device_info: Dict[str, Any] = {}
    
    def discover(self, debug: bool = False) -> Optional[Dict[str, Any]]:
        """
        Discover WLED device:
        1. Scan for JSON API baud rate (handshake speed)
        2. Extract device info
        3. Test LED data speeds interactively (starting at handshake speed, going up)
        """
        print(f"  Testing WLED...")
        
        # Step 1: Find JSON API
        json_api_baud = self._scan_for_json_api(debug)
        if not json_api_baud:
            print(f"    ✗ No WLED JSON API found")
            return None
        
        print(f"    ✓ Found WLED JSON API at {json_api_baud} baud")
        
        # Step 2: Get device info
        device_info = self._get_device_info(json_api_baud, debug)
        if not device_info:
            print(f"    ✗ Could not retrieve device info")
            return None
        
        print(f"    ✓ Device: {device_info.get('name', 'WLED')} v{device_info.get('version', '?')}")
        print(f"    ✓ LEDs: {device_info.get('led_count', '?')}")
        
        # Step 3: Test LED data speeds interactively
        print(f"\n    Now testing LED data speeds (Adalight protocol)...")
        print(f"    Starting at {json_api_baud} baud and testing higher speeds...")
        
        best_speed = self._test_led_data_speeds(json_api_baud, debug)
        
        print(f"    ✓ Best LED data speed: {best_speed} baud")
        
        # Build final device info
        device_info['protocol'] = 'adalight'
        device_info['hardware_type'] = 'WLED'
        device_info['handshake_baud_rate'] = json_api_baud
        device_info['baud_rate'] = best_speed
        
        return device_info
    
    def _scan_for_json_api(self, debug: bool = False) -> Optional[int]:
        """Scan for WLED JSON API baud rate"""
        test_rates = [115200, 230400, 460800, 500000, 576000, 921600, 1000000]
        
        for baud_rate in test_rates:
            if debug:
                print(f"    [DEBUG] Testing JSON API at {baud_rate} baud")
            
            try:
                with serial.Serial(self.port, baud_rate, timeout=1.0) as ser:
                    time.sleep(0.1)
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                    
                    query = b'{"v":true}\n'
                    ser.write(query)
                    ser.flush()
                    time.sleep(0.5)
                    
                    if ser.in_waiting > 0:
                        response = ser.read(ser.in_waiting)
                        try:
                            response_str = response.decode('utf-8', errors='ignore')
                            data = json.loads(response_str)
                            if 'info' in data and 'state' in data:
                                return baud_rate
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue
            except (serial.SerialException, OSError):
                continue
        
        return None
    
    def _get_device_info(self, baud_rate: int, debug: bool = False) -> Optional[Dict[str, Any]]:
        """Get WLED device information via JSON API"""
        try:
            with serial.Serial(self.port, baud_rate, timeout=1.0) as ser:
                time.sleep(0.1)
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                query = b'{"v":true}\n'
                ser.write(query)
                ser.flush()
                time.sleep(0.5)
                
                response = ser.read(ser.in_waiting) if ser.in_waiting > 0 else b''
                
                if not response:
                    return None
                
                response_str = response.decode('utf-8', errors='ignore')
                data = json.loads(response_str)
                
                info = data.get('info', {})
                leds_info = info.get('leds', {})
                
                # Parse light capabilities for pixel format
                lc = leds_info.get('lc', 1)
                pixel_format = self._parse_pixel_format(lc)
                
                return {
                    'name': info.get('name', 'WLED Device'),
                    'version': info.get('ver', 'unknown'),
                    'brand': info.get('brand', ''),
                    'product': info.get('product', ''),
                    'led_count': leds_info.get('count', 100),
                    'pixel_format': pixel_format,
                    'mac': info.get('mac', ''),
                    'arch': info.get('arch', ''),
                }
        except Exception as e:
            if debug:
                print(f"    [DEBUG] Error getting device info: {e}")
            return None
    
    def _parse_pixel_format(self, lc: int) -> str:
        """Parse light capabilities byte to pixel format"""
        has_rgb = bool(lc & 0x01)
        has_white = bool(lc & 0x02)
        
        if has_rgb and has_white:
            return 'GRBW'
        elif has_rgb:
            return 'GRB'
        else:
            return 'GRB'  # Default
    
    def _test_led_data_speeds(self, start_baud: int, debug: bool = False) -> int:
        """
        Test LED data speeds interactively starting at start_baud and going up
        Uses WLED baud change command to switch speeds
        Returns the highest working baud rate
        """
        # Baud rate to command byte mapping
        baud_commands = {
            115200: 0xB0,
            230400: 0xB1,
            460800: 0xB2,
            500000: 0xB3,
            576000: 0xB4,
            921600: 0xB5,
            1000000: 0xB6,
            1500000: 0xB7,
            2000000: 0xB8
        }
        
        # Test speeds starting at handshake speed and going up
        all_speeds = [115200, 230400, 460800, 500000, 576000, 921600, 1000000, 1500000, 2000000]
        test_speeds = [s for s in all_speeds if s >= start_baud]
        
        best_speed = start_baud
        
        for speed in test_speeds:
            # Send baud change command if not at start baud
            if speed != start_baud:
                if not self._change_wled_baud(best_speed, speed, baud_commands, debug):
                    print(f"    ✗ Failed to switch WLED to {speed} baud")
                    break
            
            # Test Adalight at this speed
            result = test_protocol_interactive(self.port, speed, 'adalight', led_count=10, debug=debug)
            
            if result:
                print(f"    ✓ {speed} baud works")
                best_speed = speed
            else:
                print(f"    ✗ {speed} baud failed")
                break  # Stop at first failure
        
        return best_speed
    
    def _change_wled_baud(self, current_baud: int, target_baud: int, 
                          baud_commands: dict, debug: bool = False) -> bool:
        """
        Send WLED baud change command and verify
        Returns True if successful
        """
        if target_baud not in baud_commands:
            if debug:
                print(f"    [DEBUG] No baud command for {target_baud}")
            return False
        
        try:
            if debug:
                print(f"    [DEBUG] Sending baud change command: {current_baud} -> {target_baud}")
            
            # Open at current baud rate
            with serial.Serial(self.port, current_baud, timeout=1.0) as ser:
                time.sleep(0.1)
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # Send single byte baud change command
                command_byte = bytes([baud_commands[target_baud]])
                if debug:
                    print(f"    [DEBUG] Sending byte: 0x{baud_commands[target_baud]:02X}")
                
                ser.write(command_byte)
                ser.flush()
                
                # Wait for response: "Baud is now XXXXX\n"
                time.sleep(0.2)
                
                if ser.in_waiting > 0:
                    response = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                    if debug:
                        print(f"    [DEBUG] Response: {response.strip()}")
                    
                    # Check if response confirms baud change
                    if f"Baud is now {target_baud}" in response or f"{target_baud}" in response:
                        if debug:
                            print(f"    [DEBUG] Baud change confirmed")
                        return True
                
                # Even without confirmation, try proceeding (response may be missed)
                if debug:
                    print(f"    [DEBUG] No confirmation, but proceeding anyway")
                return True
                
        except (serial.SerialException, OSError) as e:
            if debug:
                print(f"    [DEBUG] Error changing baud: {e}")
            return False


# ============================================================================
# AWA Interactive Discovery
# ============================================================================

class AWADiscovery:
    """AWA protocol discovery with interactive visual confirmation"""
    
    def __init__(self, port: str):
        self.port = port
    
    def discover(self, debug: bool = False) -> Optional[Dict[str, Any]]:
        """
        Discover AWA protocol via interactive test at 2Mbps
        """
        print(f"  Testing AWA...")
        
        result = test_protocol_interactive(self.port, 2000000, 'awa', led_count=10, debug=debug)
        
        if result:
            print(f"    ✓ AWA detected at 2Mbps")
            return {
                'protocol': 'awa',
                'baud_rate': 2000000,
                'led_count': 100,  # Default, user should adjust
                'pixel_format': 'GRB'
            }
        else:
            print(f"    ✗ AWA not detected")
            return None


# ============================================================================
# Adalight Interactive Discovery
# ============================================================================

class AdalightDiscovery:
    """Adalight protocol discovery with interactive multi-speed testing"""
    
    def __init__(self, port: str):
        self.port = port
    
    def discover(self, debug: bool = False) -> Optional[Dict[str, Any]]:
        """
        Discover Adalight protocol by testing multiple baud rates interactively
        """
        print(f"  Testing Adalight...")
        
        test_speeds = [115200, 230400, 460800, 500000, 576000, 921600, 1000000, 1500000, 2000000]
        
        for speed in test_speeds:
            result = test_protocol_interactive(self.port, speed, 'adalight', led_count=10, debug=debug)
            
            if result:
                print(f"    ✓ Adalight detected at {speed} baud")
                return {
                    'protocol': 'adalight',
                    'baud_rate': speed,
                    'led_count': 100,  # Default, user should adjust
                    'pixel_format': 'GRB'
                }
            else:
                print(f"    ✗ {speed} baud failed")
        
        print(f"    ✗ Adalight not detected at any speed")
        return None


# ============================================================================
# Serial Port Listing
# ============================================================================

def list_serial_ports() -> List[serial.tools.list_ports.ListPortInfo]:
    """List all available serial ports"""
    ports = serial.tools.list_ports.comports()
    return sorted(ports, key=lambda p: p.device)


def print_port_info(port_info: serial.tools.list_ports.ListPortInfo):
    """Print detailed information about a serial port"""
    print(f"\nPort: {port_info.device}")
    print(f"  Description: {port_info.description}")
    if port_info.manufacturer:
        print(f"  Manufacturer: {port_info.manufacturer}")
    if port_info.product:
        print(f"  Product: {port_info.product}")


# ============================================================================
# Port Scanning with Interactive Protocol Selection
# ============================================================================

def scan_port(port: str, debug: bool = False) -> Optional[Dict[str, Any]]:
    """
    Scan a port for LED protocols with user confirmation for each protocol
    Tests in order: WLED → AWA → Adalight
    WLED detection skips AWA and Adalight
    """
    print(f"\nScanning {port}...")
    
    # Test WLED first (most feature-rich)
    if ask_user(f"  Test WLED on {port}?"):
        wled = WLEDDiscovery(port)
        result = wled.discover(debug=debug)
        if result:
            result['port'] = port
            print(f"  ✓ WLED detected - skipping AWA and Adalight tests")
            return result
    
    # Test AWA
    if ask_user(f"  Test AWA on {port}?"):
        awa = AWADiscovery(port)
        result = awa.discover(debug=debug)
        if result:
            result['port'] = port
            return result
    
    # Test Adalight
    if ask_user(f"  Test Adalight on {port}?"):
        adalight = AdalightDiscovery(port)
        result = adalight.discover(debug=debug)
        if result:
            result['port'] = port
            return result
    
    print(f"  ✗ No protocols detected on {port}")
    return None


# ============================================================================
# Configuration Generation
# ============================================================================

def generate_config(detected_devices: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Generate OpenPixelControlSerial configuration from detected devices"""
    config = {
        "opc": {
            "host": "0.0.0.0",
            "port": 7890
        },
        "outputs": []
    }
    
    offset = 0
    
    for port, device_info in detected_devices.items():
        output = {
            "port": port,
            "protocol": device_info.get('protocol', 'unknown'),
            "baud_rate": device_info.get('baud_rate', 115200),
            "opc_channel": 0,
            "led_count": device_info.get('led_count', 100),
            "opc_offset": offset,
            "pixel_format": device_info.get('pixel_format', 'GRB')
        }
        
        # Add WLED-specific fields
        if device_info.get('hardware_type') == 'WLED':
            output['hardware_type'] = 'WLED'
            output['handshake_baud_rate'] = device_info.get('handshake_baud_rate', 115200)
            output['device_name'] = device_info.get('name', 'WLED Device')
            
            if device_info.get('version'):
                output['wled_version'] = device_info['version']
            if device_info.get('brand'):
                output['wled_brand'] = device_info['brand']
            if device_info.get('product'):
                output['wled_product'] = device_info['product']
            if device_info.get('mac'):
                output['mac'] = device_info['mac']
        
        config['outputs'].append(output)
        offset += device_info.get('led_count', 100)
    
    return config


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main entry point"""
    debug = '--debug' in sys.argv or '-d' in sys.argv
    
    print("=" * 70)
    print("OpenPixelControlSerial - Interactive Discovery Tool")
    print("=" * 70)
    if debug:
        print("DEBUG MODE ENABLED")
        print("=" * 70)
    print()
    print("⚠️  IMPORTANT: WLED Device Setup")
    print("=" * 70)
    print("If you have WLED devices, you MUST power cycle them BEFORE running")
    print("this tool. WLED's baud rate changes are temporary and don't persist")
    print("across reboots. Power cycling ensures we detect the correct default")
    print("baud rate.")
    print()
    print("Steps:")
    print("  1. Unplug all WLED devices from power")
    print("  2. Wait 5 seconds")
    print("  3. Plug them back in")
    print("  4. Wait for them to fully boot (LEDs should show startup pattern)")
    print("=" * 70)
    print()
    
    # Require user confirmation
    if not ask_user("Have you power cycled all WLED devices?"):
        print("\nPlease power cycle your WLED devices and run this tool again.")
        return 0
    
    print()
    print("This tool will test each serial port for LED controller protocols.")
    print("You'll be asked to confirm if LEDs blink during each test.")
    print()
    
    # List all serial ports
    ports = list_serial_ports()
    
    if not ports:
        print("No serial ports found on this system.")
        return 1
    
    print(f"Found {len(ports)} serial port(s):")
    for port_info in ports:
        print(f"  • {port_info.device} - {port_info.description}")
    
    print("\n" + "=" * 70)
    print("Starting Interactive Discovery")
    print("=" * 70)
    
    # Scan each port
    detected_devices = {}
    
    for port_info in ports:
        result = scan_port(port_info.device, debug=debug)
        if result:
            detected_devices[port_info.device] = result
    
    # Summary
    print("\n" + "=" * 70)
    print("Discovery Summary")
    print("=" * 70)
    
    if detected_devices:
        for port, info in detected_devices.items():
            print(f"\n{port}:")
            print(f"  Protocol: {info.get('protocol')}")
            if info.get('hardware_type') == 'WLED':
                print(f"  Hardware: WLED")
                print(f"  Device: {info.get('name')}")
                print(f"  JSON API: {info.get('handshake_baud_rate')} baud")
                print(f"  LED Data: {info.get('baud_rate')} baud")
            else:
                print(f"  Baud Rate: {info.get('baud_rate')}")
            print(f"  LED Count: {info.get('led_count')} (adjust as needed)")
            print(f"  Pixel Format: {info.get('pixel_format')}")
        
        # Generate and save config
        print("\n" + "=" * 70)
        print("Generating Configuration")
        print("=" * 70)
        
        config = generate_config(detected_devices)
        config_path = "config.json"
        
        if os.path.exists(config_path):
            print(f"\nWARNING: {config_path} already exists and will be overwritten.")
            if not ask_user("Continue?"):
                print("Configuration not saved.")
                return 0
        
        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"\n✓ Configuration saved to: {config_path}")
            print(f"  Review and adjust LED counts and other settings as needed.")
        except Exception as e:
            print(f"\n✗ Error writing config file: {e}")
            return 1
    else:
        print("\nNo LED controller devices detected.")
        print("Make sure your devices are connected and powered on.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
