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
        self.baud_rate = 115200  # WLED JSON API always uses 115200
        self.mac = config.get('mac', 'N/A')
        self.config = config
    
    def __str__(self):
        return f"{self.device_name} ({self.port})"


class WLEDConfigurator:
    """Handle WLED device configuration over serial"""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
    
    def _log(self, message: str):
        """Print debug messages if debug mode is enabled"""
        if self.debug:
            print(f"[DEBUG] {message}")
    
    def query_device_state(self, device: WLEDDevice) -> Optional[Dict[str, Any]]:
        """
        Query WLED device for current state
        Returns parsed JSON response or None on failure
        """
        self._log(f"Querying device state on {device.port}")
        
        try:
            with serial.Serial(device.port, device.baud_rate, timeout=1.0) as ser:
                # Let port settle
                time.sleep(0.1)
                
                # Clear buffers
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                
                # Send state query
                query = b'{"v":true}\n'
                self._log(f"Sending: {query.decode().strip()}")
                
                ser.write(query)
                ser.flush()
                
                # Wait for response
                time.sleep(0.5)
                
                if ser.in_waiting == 0:
                    self._log("No response from device")
                    return None
                
                # Read response
                response = b''
                while ser.in_waiting > 0:
                    chunk = ser.read(ser.in_waiting)
                    response += chunk
                    time.sleep(0.02)
                
                if not response:
                    self._log("Empty response")
                    return None
                
                # Parse JSON
                response_str = response.decode('utf-8', errors='ignore')
                self._log(f"Received: {response_str}")
                
                data = json.loads(response_str)
                
                # Validate response structure
                if 'info' not in data or 'state' not in data:
                    self._log("Invalid response structure")
                    return None
                
                return data
                
        except serial.SerialException as e:
            print(f"Error: Cannot open serial port {device.port}: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON response from device: {e}")
            return None
        except Exception as e:
            print(f"Error querying device: {e}")
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
        state = self.query_device_state(device)
        if state is None:
            return None
        
        info = state.get('info', {})
        live_mode = info.get('live', False)
        
        return live_mode
    
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
        for i, device in enumerate(devices, 1):
            # Query current state
            state = configurator.verify_live_mode(device)
            state_str = "ENABLED" if state else "DISABLED" if state is not None else "UNKNOWN"
            print(f"  {i}. {device}")
            print(f"     LIVE mode: {state_str}")
        
        print("\nOptions:")
        print("  [1-9]  Select device")
        print("  [a]    Configure all devices")
        print("  [q]    Quit")
        
        choice = input("\nEnter choice: ").strip().lower()
        
        if choice == 'q':
            print("Exiting...")
            break
        
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
                    
                    print(f"\nSelected: {device}")
                    print("  [1] Enable LIVE mode")
                    print("  [2] Disable LIVE mode")
                    print("  [3] Query status only")
                    print("  [c] Cancel")
                    
                    action = input("Enter choice: ").strip()
                    
                    if action == '1':
                        configurator.configure_device(device, enable_live=True)
                    elif action == '2':
                        configurator.configure_device(device, enable_live=False)
                    elif action == '3':
                        state = configurator.query_device_state(device)
                        if state:
                            print(f"\nDevice State:")
                            print(json.dumps(state, indent=2))
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
  %(prog)s --enable-live              Enable LIVE mode on single device
  %(prog)s --disable-live             Disable LIVE mode on single device
  %(prog)s --port COM4 --enable-live  Enable LIVE on specific port
  %(prog)s --interactive              Interactive mode (default)
  %(prog)s --config myconfig.json     Use alternate config file
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
    if args.enable_live or args.disable_live:
        # Command-line mode
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
