#!/usr/bin/env python3
"""
WLED Configuration Tool
Configure WLED devices over serial port using JSON API
"""

import sys
import json
import os
import serial
import argparse
import time
from typing import List, Dict, Optional, Any


class WLEDDevice:
    """Represents a WLED device and its configuration"""
    
    def __init__(self, config: Dict[str, Any]):
        self.port = config.get('port')
        self.device_name = config.get('device_name', 'WLED Device')
        self.device_type = config.get('device_type', 'WLED')
        self.baud_rate = 115200  # Default - will be auto-detected if different
        self.led_data_baud_rate = config.get('baud_rate', 115200)  # Baud rate for LED data (Adalight/AWA)
        self.mac = config.get('mac', 'N/A')
        self.config = config
        self.baud_rate_verified = False  # Track if we've verified the baud rate
    
    def __str__(self):
        return f"{self.device_name} ({self.port})"


class WLEDConfigurator:
    """Handle WLED device configuration over serial"""
    
    # Baud rates supported by WLED serial protocol
    # Maps baud rate to the byte command to set it
    BAUD_RATE_COMMANDS = {
        115200: 0xB0,
        230400: 0xB1,
        460800: 0xB2,
        500000: 0xB3,
        576000: 0xB4,
        921600: 0xB5,
        1000000: 0xB6,
        1500000: 0xB7,
        2000000: 0xB8,  # Not in official docs, but trying next byte for 2MB
    }
    
    COMMON_BAUD_RATES = list(BAUD_RATE_COMMANDS.keys())
    
    def __init__(self, debug: bool = False):
        self.debug = debug
    
    def _log(self, message: str):
        """Print debug messages if debug mode is enabled"""
        if self.debug:
            print(f"[DEBUG] {message}")
    
    def detect_json_api_baud_rate(self, device: WLEDDevice) -> Optional[int]:
        """
        Scan for the baud rate that WLED's JSON API is actually using.
        WLED documentation says JSON API works at any baud rate, but in practice
        it may only respond at the configured rate.
        
        Returns the working baud rate, or None if none found
        """
        self._log(f"Scanning for JSON API baud rate on {device.port}")
        
        # Try common baud rates, starting with default
        test_rates = [115200, 230400, 460800, 500000, 576000, 921600, 1000000, 1500000]
        
        for baud_rate in test_rates:
            self._log(f"Testing JSON API at {baud_rate} baud")
            
            try:
                with serial.Serial(device.port, baud_rate, timeout=1.0) as ser:
                    # Let port settle
                    time.sleep(0.1)
                    
                    # Clear buffers
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                    
                    # Send JSON query
                    query = b'{"v":true}\n'
                    ser.write(query)
                    ser.flush()
                    
                    # Wait for response
                    time.sleep(0.5)
                    
                    if ser.in_waiting > 0:
                        response = ser.read(ser.in_waiting)
                        
                        # Try to parse as JSON
                        try:
                            response_str = response.decode('utf-8', errors='ignore')
                            data = json.loads(response_str)
                            
                            # Validate it's a WLED response
                            if 'info' in data and 'state' in data:
                                self._log(f"✓ JSON API responds at {baud_rate} baud")
                                return baud_rate
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue
                            
            except (serial.SerialException, OSError):
                continue
        
        self._log(f"✗ JSON API not responding at any tested baud rate")
        return None
    
    def query_device_state(self, device: WLEDDevice, retry_count: int = 2) -> Optional[Dict[str, Any]]:
        """
        Query WLED device for current state
        Returns parsed JSON response or None on failure
        """
        for attempt in range(retry_count + 1):
            if attempt > 0:
                self._log(f"Retry {attempt}/{retry_count}")
                time.sleep(0.5)  # Wait before retry
            
            self._log(f"Querying device state on {device.port}")
            
            try:
                with serial.Serial(device.port, device.baud_rate, timeout=2.0) as ser:
                    # Let port settle - WLED needs time
                    time.sleep(0.2)
                    
                    # Clear buffers multiple times to ensure clean state
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                    time.sleep(0.1)
                    ser.reset_input_buffer()
                    
                    # Send state query
                    query = b'{"v":true}\n'
                    self._log(f"Sending: {query.decode().strip()}")
                    
                    ser.write(query)
                    ser.flush()
                    
                    # Wait longer for response - WLED can be slow
                    time.sleep(0.8)
                    
                    if ser.in_waiting == 0:
                        if attempt < retry_count:
                            continue  # Try again
                        print(f"Error querying {device.port}: No response from device")
                        print(f"  Device may be:")
                        print(f"    - Not powered on")
                        print(f"    - Not a WLED device")
                        print(f"    - Using a different baud rate for JSON API")
                        print(f"    - Busy processing other commands")
                        return None
                    
                    # Read response
                    response = b''
                    while ser.in_waiting > 0:
                        chunk = ser.read(ser.in_waiting)
                        response += chunk
                        time.sleep(0.02)
                    
                    if not response:
                        if attempt < retry_count:
                            continue  # Try again
                        print(f"Error querying {device.port}: Empty response after reading")
                        return None
                    
                    # Parse JSON
                    response_str = response.decode('utf-8', errors='ignore')
                    self._log(f"Received: {response_str}")
                    
                    try:
                        data = json.loads(response_str)
                    except json.JSONDecodeError as e:
                        if attempt < retry_count:
                            continue  # Try again
                        print(f"Error querying {device.port}: Invalid JSON response")
                        print(f"  Received: {response_str[:100]}{'...' if len(response_str) > 100 else ''}")
                        print(f"  JSON error: {e}")
                        print(f"  Device may not be a WLED device or is sending corrupt data")
                        return None
                    
                    # Validate response structure
                    if 'info' not in data or 'state' not in data:
                        if attempt < retry_count:
                            continue  # Try again
                        print(f"Error querying {device.port}: Invalid WLED response structure")
                        print(f"  Missing required fields: 'info' and/or 'state'")
                        print(f"  Device may not be a WLED device")
                        return None
                    
                    # Success!
                    return data
                    
            except serial.SerialException as e:
                if attempt < retry_count:
                    continue  # Try again
                print(f"Error querying {device.port}: Cannot open serial port")
                print(f"  Details: {e}")
                print(f"  Possible causes:")
                print(f"    - Port is already in use by another program")
                print(f"    - Device is not connected")
                print(f"    - Insufficient permissions (try running as administrator/sudo)")
                print(f"    - Wrong port specified in config")
                return None
            except Exception as e:
                if attempt < retry_count:
                    continue  # Try again
                print(f"Error querying {device.port}: Unexpected error")
                print(f"  Details: {e}")
                return None
        
        # Should never reach here
        return None
    
    def set_live_mode(self, device: WLEDDevice, enable: bool) -> bool:
        """
        Enable or disable LIVE mode on WLED device
        Returns True on success, False on failure
        """
        mode_str = "ENABLED" if enable else "DISABLED"
        self._log(f"Setting LIVE mode to {mode_str} on {device.port}")
        
        try:
            with serial.Serial(device.port, device.baud_rate, timeout=1.0) as ser:
                # Let port settle
                time.sleep(0.1)
                
                # Clear buffers
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # Send LIVE mode command
                # The 'live' property is sent directly to /json/state, not nested in 'state'
                command = json.dumps({"live": enable}) + "\n"
                command_bytes = command.encode('utf-8')
                
                self._log(f"Sending: {command.strip()}")
                
                ser.write(command_bytes)
                ser.flush()
                
                # Wait for acknowledgment
                time.sleep(0.3)
                
                # Some WLED versions may send a response, others may not
                # We'll verify by querying the state afterwards
                if ser.in_waiting > 0:
                    response = ser.read(ser.in_waiting)
                    self._log(f"Response: {response.decode('utf-8', errors='ignore')}")
                
                return True
                
        except serial.SerialException as e:
            print(f"Error: Cannot open serial port {device.port}: {e}")
            return False
        except Exception as e:
            print(f"Error setting LIVE mode: {e}")
            return False
    
    def verify_live_mode(self, device: WLEDDevice) -> Optional[bool]:
        """
        Verify current LIVE mode state
        Returns True if enabled, False if disabled, None on error
        """
        # Auto-detect baud rate if not verified
        if not device.baud_rate_verified:
            detected_rate = self.detect_json_api_baud_rate(device)
            if detected_rate and detected_rate != device.baud_rate:
                print(f"  Note: JSON API detected at {detected_rate} baud (not {device.baud_rate})")
                device.baud_rate = detected_rate
            device.baud_rate_verified = True
        
        state = self.query_device_state(device)
        if state is None:
            return None
        
        info = state.get('info', {})
        live_mode = info.get('live', False)
        
        return live_mode
    
    def discover_baud_rates(self, device: WLEDDevice) -> List[int]:
        """
        Discover which baud rates the device supports for LED data
        Tests common baud rates used for Adalight/AWA protocols
        Returns list of working baud rates
        """
        self._log(f"Discovering supported baud rates on {device.port}")
        working_rates = []
        
        for baud_rate in self.COMMON_BAUD_RATES:
            self._log(f"Testing baud rate: {baud_rate}")
            
            try:
                # Try to open port at this baud rate
                with serial.Serial(device.port, baud_rate, timeout=0.5) as ser:
                    # Clear buffers
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                    
                    # Send a small Adalight test frame
                    # 'Ada' + LED count (10) + checksum + 30 bytes of RGB data
                    led_count = 10
                    ada_header = bytearray([
                        0x41, 0x64, 0x61,  # 'Ada' header
                        (led_count >> 8) & 0xFF,
                        led_count & 0xFF,
                        (led_count >> 8) ^ (led_count & 0xFF) ^ 0x55
                    ])
                    # Add some dummy RGB data (30 bytes for 10 LEDs)
                    ada_header.extend([0, 0, 0] * led_count)
                    
                    ser.write(bytes(ada_header))
                    ser.flush()
                    
                    time.sleep(0.05)
                    
                    # If port opened successfully and accepted data, consider it working
                    working_rates.append(baud_rate)
                    self._log(f"  ✓ {baud_rate} baud works")
                    
            except (serial.SerialException, OSError) as e:
                self._log(f"  ✗ {baud_rate} baud failed: {e}")
                continue
        
        return working_rates
    
    def set_device_baud_rate(self, device: WLEDDevice, baud_rate: int) -> bool:
        """
        Set the LED data baud rate on the WLED device using serial byte command
        
        This sends a byte command to temporarily change the baud rate.
        The change takes effect immediately but is not persistent across reboots
        unless saved with save_settings().
        
        Returns True on success, False on failure
        """
        if baud_rate not in self.BAUD_RATE_COMMANDS:
            print(f"Error: Unsupported baud rate: {baud_rate}")
            print(f"Supported rates: {', '.join(map(str, self.COMMON_BAUD_RATES))}")
            return False
        
        cmd_byte = self.BAUD_RATE_COMMANDS[baud_rate]
        self._log(f"Setting baud rate to {baud_rate} using command byte 0x{cmd_byte:02X}")
        
        try:
            with serial.Serial(device.port, device.baud_rate, timeout=1.0) as ser:
                # Let port settle
                time.sleep(0.1)
                
                # Clear buffers
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # Send baud rate change command (single byte)
                ser.write(bytes([cmd_byte]))
                ser.flush()
                
                self._log(f"Baud rate command sent")
                
                # Give device time to process
                time.sleep(0.3)
                
                return True
                
        except serial.SerialException as e:
            print(f"Error: Cannot open serial port {device.port}: {e}")
            return False
        except Exception as e:
            print(f"Error setting baud rate: {e}")
            return False
    
    def save_settings(self, device: WLEDDevice) -> bool:
        """
        Save current settings to WLED device persistent storage
        Sends POST to /save endpoint
        Returns True on success, False on failure
        """
        self._log(f"Saving settings on {device.port}")
        
        try:
            with serial.Serial(device.port, device.baud_rate, timeout=1.0) as ser:
                # Let port settle
                time.sleep(0.1)
                
                # Clear buffers
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # Send save command
                command = b'/save\n'
                self._log(f"Sending: {command.decode().strip()}")
                
                ser.write(command)
                ser.flush()
                
                # Wait for acknowledgment
                time.sleep(0.5)
                
                if ser.in_waiting > 0:
                    response = ser.read(ser.in_waiting)
                    self._log(f"Response: {response.decode('utf-8', errors='ignore')}")
                
                return True
                
        except serial.SerialException as e:
            print(f"Error: Cannot open serial port {device.port}: {e}")
            return False
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False
    
    def get_realtime_timeout(self, device: WLEDDevice) -> Optional[int]:
        """
        Get the current realtime timeout value in milliseconds
        Returns timeout value or None on error
        """
        state = self.query_device_state(device)
        if state is None:
            return None
        
        # realtimeTimeoutMs is in the state section
        state_data = state.get('state', {})
        timeout_ms = state_data.get('lor', None)  # 'lor' is the JSON key for realtime timeout
        
        return timeout_ms
    
    def set_realtime_timeout(self, device: WLEDDevice, timeout_ms: int) -> bool:
        """
        Set the realtime timeout value in milliseconds
        0 = no timeout (realtime mode stays on indefinitely)
        Returns True on success, False on failure
        """
        self._log(f"Setting realtime timeout to {timeout_ms}ms on {device.port}")
        
        try:
            with serial.Serial(device.port, device.baud_rate, timeout=1.0) as ser:
                # Let port settle
                time.sleep(0.1)
                
                # Clear buffers
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # Send realtime timeout command
                # The 'lor' property sets realtime timeout
                command = json.dumps({"lor": timeout_ms}) + "\n"
                command_bytes = command.encode('utf-8')
                
                self._log(f"Sending: {command.strip()}")
                
                ser.write(command_bytes)
                ser.flush()
                
                # Wait for acknowledgment
                time.sleep(0.3)
                
                if ser.in_waiting > 0:
                    response = ser.read(ser.in_waiting)
                    self._log(f"Response: {response.decode('utf-8', errors='ignore')}")
                
                return True
                
        except serial.SerialException as e:
            print(f"Error: Cannot open serial port {device.port}: {e}")
            return False
        except Exception as e:
            print(f"Error setting realtime timeout: {e}")
            return False
    
    def configure_device(self, device: WLEDDevice, enable_live: bool) -> bool:
        """
        Configure device and verify the change
        Returns True on success, False on failure
        """
        mode_str = "ENABLED" if enable_live else "DISABLED"
        
        print(f"\nConfiguring {device}...")
        print(f"  Target: LIVE mode {mode_str}")
        
        # Query current state
        print(f"  Checking current state...")
        current_state = self.verify_live_mode(device)
        
        if current_state is None:
            print(f"  ✗ Failed to query device state")
            return False
        
        print(f"  Current LIVE mode: {'ENABLED' if current_state else 'DISABLED'}")
        
        # Check if change is needed
        if current_state == enable_live:
            print(f"  ℹ LIVE mode is already {mode_str}")
            return True
        
        # Apply change
        print(f"  Setting LIVE mode to {mode_str}...")
        if not self.set_live_mode(device, enable_live):
            print(f"  ✗ Failed to set LIVE mode")
            return False
        
        # Verify change
        print(f"  Verifying change...")
        time.sleep(0.5)  # Give device time to apply change
        
        new_state = self.verify_live_mode(device)
        if new_state is None:
            print(f"  ⚠ Could not verify change (device may have rebooted)")
            return False
        
        if new_state == enable_live:
            print(f"  ✓ LIVE mode successfully set to {mode_str}")
            return True
        else:
            print(f"  ✗ LIVE mode verification failed")
            print(f"    Expected: {mode_str}")
            print(f"    Actual: {'ENABLED' if new_state else 'DISABLED'}")
            return False


def load_config(config_path: str = "config.json") -> Optional[Dict[str, Any]]:
    """Load configuration file"""
    # Try multiple locations
    search_paths = [
        config_path,
        os.path.join(os.getcwd(), config_path),
        os.path.join(os.path.dirname(__file__), "..", config_path),
        os.path.join(os.path.dirname(__file__), config_path)
    ]
    
    for path in search_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading config from {path}: {e}")
                continue
    
    return None


def find_wled_devices(config: Dict[str, Any]) -> List[WLEDDevice]:
    """Find all WLED devices in configuration"""
    devices = []
    outputs = config.get('outputs', [])
    
    for output in outputs:
        # Check if this is a WLED device
        device_type = output.get('device_type', '').upper()
        protocol = output.get('protocol', '').lower()
        
        # WLED devices are marked as device_type="WLED" or have wled_ prefixed keys
        is_wled = (
            device_type == 'WLED' or
            'wled_version' in output or
            'wled_brand' in output
        )
        
        if is_wled:
            devices.append(WLEDDevice(output))
    
    return devices


def interactive_mode(devices: List[WLEDDevice], configurator: WLEDConfigurator):
    """Interactive device configuration menu"""
    if not devices:
        print("No WLED devices found in configuration.")
        return
    
    while True:
        print("\n" + "=" * 60)
        print("WLED Device Configuration - Interactive Mode")
        print("=" * 60)
        
        print("\nAvailable WLED Devices:")
        has_errors = False
        for i, device in enumerate(devices, 1):
            # Query current state
            state = configurator.verify_live_mode(device)
            if state is None:
                has_errors = True
                print(f"  {i}. {device}")
                print(f"     ✗ ERROR: Failed to query device state")
                print(f"     Please check:")
                print(f"       - Device is connected and powered on")
                print(f"       - No other program is using the serial port")
                print(f"       - Correct port in config.json")
            else:
                state_str = "ENABLED" if state else "DISABLED"
                print(f"  {i}. {device}")
                print(f"     LIVE mode: {state_str}")
        
        if has_errors:
            print(f"\n⚠ WARNING: Some devices could not be queried. Check errors above.")
        
        print("\nOptions:")
        print("  [1-9]  Select device")
        print("  [a]    Configure all devices")
        print("  [r]    Rescan devices")
        print("  [q]    Quit")
        
        choice = input("\nEnter choice: ").strip().lower()
        
        if choice == 'q':
            print("Exiting...")
            break
        
        elif choice == 'r':
            # Rescan - just continue the loop to re-query devices
            print("\nRescanning devices...")
            continue
        
        elif choice == 'a':
            # Configure all devices
            print("\nConfigure all devices:")
            print("  [1] Enable LIVE mode on all")
            print("  [2] Disable LIVE mode on all")
            print("  [c] Cancel")
            
            action = input("Enter choice: ").strip()
            
            if action == '1':
                print("\nEnabling LIVE mode on all devices...")
                for device in devices:
                    configurator.configure_device(device, enable_live=True)
            elif action == '2':
                print("\nDisabling LIVE mode on all devices...")
                for device in devices:
                    configurator.configure_device(device, enable_live=False)
        
        else:
            # Try to parse as device number
            try:
                device_num = int(choice)
                if 1 <= device_num <= len(devices):
                    device = devices[device_num - 1]
                    
                    # Device menu loop - stay here until user cancels
                    while True:
                        print(f"\n{'=' * 60}")
                        print(f"Device: {device}")
                        print("=" * 60)
                        print("  [1] Enable LIVE mode")
                        print("  [2] Disable LIVE mode")
                        print("  [3] Query status only")
                        print("  [4] Set LED data baud rate")
                        print("  [5] Get/Set realtime timeout")
                        print("  [6] Save settings to device")
                        print("  [b] Back to device list")
                        
                        action = input("\nEnter choice: ").strip().lower()
                        
                        if action == 'b':
                            break  # Return to main menu
                        elif action == '1':
                            configurator.configure_device(device, enable_live=True)
                        elif action == '2':
                            configurator.configure_device(device, enable_live=False)
                        elif action == '3':
                            state = configurator.query_device_state(device)
                            if state:
                                print(f"\nDevice State:")
                                print(json.dumps(state, indent=2))
                        elif action == '4':
                            print(f"\nSet LED data baud rate on device")
                            print(f"\nAvailable baud rates:")
                            for i, rate in enumerate(configurator.COMMON_BAUD_RATES, 1):
                                print(f"  [{i}] {rate}")
                            print(f"  [c] Cancel")
                            
                            baud_choice = input("\nSelect baud rate: ").strip()
                            if baud_choice.isdigit():
                                idx = int(baud_choice) - 1
                                if 0 <= idx < len(configurator.COMMON_BAUD_RATES):
                                    new_rate = configurator.COMMON_BAUD_RATES[idx]
                                    print(f"\nSetting device baud rate to {new_rate}...")
                                    
                                    if configurator.set_device_baud_rate(device, new_rate):
                                        print(f"✓ Baud rate command sent to device")
                                        print(f"\nIMPORTANT:")
                                        print(f"  - This change is TEMPORARY (until device reboots)")
                                        print(f"  - Use option [6] to save settings for persistence")
                                        print(f"  - For 2000000 baud with AWA, ensure LIVE mode is enabled")
                                    else:
                                        print(f"✗ Failed to set baud rate on device")
                        elif action == '5':
                            # Get/Set realtime timeout
                            print(f"\nRealtime Timeout Configuration")
                            current_timeout = configurator.get_realtime_timeout(device)
                            if current_timeout is not None:
                                if current_timeout == 0:
                                    print(f"  Current timeout: 0ms (no timeout - stays on indefinitely)")
                                else:
                                    print(f"  Current timeout: {current_timeout}ms")
                            else:
                                print(f"  ✗ Failed to query current timeout")
                            
                            print(f"\n  [1] Set to 0 (no timeout - recommended for AWA)")
                            print(f"  [2] Set to 5000ms (5 seconds)")
                            print(f"  [3] Set to 10000ms (10 seconds)")
                            print(f"  [4] Set to 30000ms (30 seconds)")
                            print(f"  [5] Set custom value")
                            print(f"  [c] Cancel")
                            
                            timeout_choice = input("\nSelect timeout: ").strip()
                            new_timeout = None
                            
                            if timeout_choice == '1':
                                new_timeout = 0
                            elif timeout_choice == '2':
                                new_timeout = 5000
                            elif timeout_choice == '3':
                                new_timeout = 10000
                            elif timeout_choice == '4':
                                new_timeout = 30000
                            elif timeout_choice == '5':
                                try:
                                    new_timeout = int(input("Enter timeout in milliseconds: ").strip())
                                except ValueError:
                                    print("✗ Invalid timeout value")
                            
                            if new_timeout is not None:
                                print(f"\nSetting realtime timeout to {new_timeout}ms...")
                                if configurator.set_realtime_timeout(device, new_timeout):
                                    print(f"✓ Realtime timeout set successfully")
                                    print(f"\nIMPORTANT: To persist this change, use option [6] to save settings")
                                else:
                                    print(f"✗ Failed to set realtime timeout")
                        
                        elif action == '6':
                            # Save settings
                            print(f"\nSaving settings to device persistent storage...")
                            print(f"This will persist current settings including:")
                            print(f"  - LIVE mode status")
                            print(f"  - Realtime timeout")
                            print(f"  - Baud rate")
                            print(f"  - Other device settings")
                            
                            confirm = input("\nContinue? (y/n): ").strip().lower()
                            if confirm == 'y':
                                if configurator.save_settings(device):
                                    print(f"✓ Settings saved successfully")
                                    print(f"Settings will persist across device reboots")
                                else:
                                    print(f"✗ Failed to save settings")
                        else:
                            print("Invalid choice")
                else:
                    print("Invalid device number")
            except ValueError:
                print("Invalid choice")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Configure WLED devices over serial port',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --enable-live                      Enable LIVE mode on single device
  %(prog)s --disable-live                     Disable LIVE mode on single device
  %(prog)s --port COM4 --enable-live          Enable LIVE on specific port
  %(prog)s --discover-baud                    Discover supported baud rates
  %(prog)s --set-baud 2000000                 Set LED data baud rate to 2MB
  %(prog)s --port COM4 --set-baud 2000000     Set baud rate on specific port
  %(prog)s --interactive                      Interactive mode (default)
  %(prog)s --config myconfig.json             Use alternate config file
        """
    )
    
    parser.add_argument('--config', '-c', default='config.json',
                        help='Configuration file path (default: config.json)')
    parser.add_argument('--port', '-p',
                        help='Serial port name (e.g., COM4, /dev/ttyUSB0)')
    parser.add_argument('--enable-live', action='store_true',
                        help='Enable LIVE mode on device(s)')
    parser.add_argument('--disable-live', action='store_true',
                        help='Disable LIVE mode on device(s)')
    parser.add_argument('--discover-baud', action='store_true',
                        help='Discover supported baud rates for LED data')
    parser.add_argument('--set-baud', type=int, metavar='RATE',
                        help='Set LED data baud rate (e.g., 115200, 2000000)')
    parser.add_argument('--get-timeout', action='store_true',
                        help='Get current realtime timeout value')
    parser.add_argument('--set-timeout', type=int, metavar='MS',
                        help='Set realtime timeout in milliseconds (0 = no timeout)')
    parser.add_argument('--save', action='store_true',
                        help='Save settings to device persistent storage')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Interactive mode (default if no action specified)')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug output')
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    if config is None:
        print(f"Error: Could not load configuration file: {args.config}")
        print(f"Please ensure config.json exists in the current directory")
        return 1
    
    # Find WLED devices
    devices = find_wled_devices(config)
    
    if not devices:
        print("No WLED devices found in configuration.")
        print("Run discover.py to detect and configure WLED devices.")
        return 1
    
    # Create configurator
    configurator = WLEDConfigurator(debug=args.debug)
    
    # Determine mode
    if args.discover_baud:
        # Baud rate discovery mode
        # Filter devices by port if specified
        if args.port:
            devices = [d for d in devices if d.port == args.port]
            if not devices:
                print(f"Error: No WLED device found on port {args.port}")
                return 1
        
        print(f"\nDiscovering supported baud rates...")
        print(f"Testing: {', '.join(map(str, configurator.COMMON_BAUD_RATES))}\n")
        
        for device in devices:
            print(f"{device}:")
            working_rates = configurator.discover_baud_rates(device)
            if working_rates:
                print(f"  ✓ Supports {len(working_rates)} baud rate(s):")
                for rate in working_rates:
                    current = " (current)" if rate == device.led_data_baud_rate else ""
                    print(f"    - {rate}{current}")
            else:
                print(f"  ✗ No working baud rates found")
        
        return 0
    
    elif args.set_baud:
        # Set baud rate mode - actually sets on device
        new_rate = args.set_baud
        
        # Validate baud rate
        if new_rate not in configurator.COMMON_BAUD_RATES:
            print(f"Error: {new_rate} is not a supported baud rate.")
            print(f"Supported rates are: {', '.join(map(str, configurator.COMMON_BAUD_RATES))}")
            return 1
        
        # Filter devices by port if specified
        if args.port:
            devices = [d for d in devices if d.port == args.port]
            if not devices:
                print(f"Error: No WLED device found on port {args.port}")
                return 1
        elif len(devices) > 1:
            print(f"Warning: Multiple WLED devices found, setting baud rate on all:")
            for device in devices:
                print(f"  - {device}")
        
        # Set baud rate on devices
        print(f"\nSetting baud rate to {new_rate}...")
        success = True
        for device in devices:
            print(f"  {device}...", end=" ")
            if configurator.set_device_baud_rate(device, new_rate):
                print("✓")
            else:
                print("✗")
                success = False
        
        if success:
            print(f"\n✓ Baud rate set successfully")
            print(f"\nIMPORTANT:")
            print(f"  - This change is TEMPORARY (until device reboots)")
            print(f"  - Use --save to persist this change across reboots")
            print(f"  - For AWA protocol at 2000000 baud, ensure LIVE mode is enabled")
        
        return 0 if success else 1
    
    elif args.get_timeout:
        # Get realtime timeout
        if args.port:
            devices = [d for d in devices if d.port == args.port]
            if not devices:
                print(f"Error: No WLED device found on port {args.port}")
                return 1
        
        print(f"\nRealtime Timeout Status:\n")
        for device in devices:
            timeout_ms = configurator.get_realtime_timeout(device)
            if timeout_ms is not None:
                if timeout_ms == 0:
                    print(f"{device}: 0ms (no timeout - stays on indefinitely)")
                else:
                    print(f"{device}: {timeout_ms}ms")
            else:
                print(f"{device}: ✗ Failed to query timeout")
        
        return 0
    
    elif args.set_timeout is not None:
        # Set realtime timeout
        timeout_ms = args.set_timeout
        
        if args.port:
            devices = [d for d in devices if d.port == args.port]
            if not devices:
                print(f"Error: No WLED device found on port {args.port}")
                return 1
        elif len(devices) > 1:
            print(f"Warning: Multiple WLED devices found, setting timeout on all:")
            for device in devices:
                print(f"  - {device}")
        
        print(f"\nSetting realtime timeout to {timeout_ms}ms...")
        success = True
        for device in devices:
            print(f"  {device}...", end=" ")
            if configurator.set_realtime_timeout(device, timeout_ms):
                print("✓")
            else:
                print("✗")
                success = False
        
        if success:
            print(f"\n✓ Timeout set successfully")
            print(f"IMPORTANT: Use --save to persist this change across reboots")
        
        return 0 if success else 1
    
    elif args.save:
        # Save settings
        if args.port:
            devices = [d for d in devices if d.port == args.port]
            if not devices:
                print(f"Error: No WLED device found on port {args.port}")
                return 1
        elif len(devices) > 1:
            print(f"Warning: Multiple WLED devices found, saving settings on all:")
            for device in devices:
                print(f"  - {device}")
        
        print(f"\nSaving settings to device persistent storage...")
        success = True
        for device in devices:
            print(f"  {device}...", end=" ")
            if configurator.save_settings(device):
                print("✓")
            else:
                print("✗")
                success = False
        
        if success:
            print(f"\n✓ Settings saved successfully")
            print(f"Settings will persist across device reboots")
        
        return 0 if success else 1
    
    elif args.enable_live or args.disable_live:
        # LIVE mode configuration
        enable_live = args.enable_live
        
        # Filter devices by port if specified
        if args.port:
            devices = [d for d in devices if d.port == args.port]
            if not devices:
                print(f"Error: No WLED device found on port {args.port}")
                return 1
        elif len(devices) > 1:
            print(f"Warning: Multiple WLED devices found, configuring all:")
            for device in devices:
                print(f"  - {device}")
        
        # Configure devices
        success = True
        for device in devices:
            if not configurator.configure_device(device, enable_live):
                success = False
        
        return 0 if success else 1
    
    else:
        # Interactive mode (default)
        interactive_mode(devices, configurator)
        return 0


if __name__ == "__main__":
    sys.exit(main())
