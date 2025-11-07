#!/usr/bin/env python3
"""
OpenPixelControlSerial - OPC Server
Receives OPC data over TCP and outputs to serial LED strips
"""

import sys
import json
import time
import argparse
import serial
import socket
import struct
import threading
import signal
from typing import Dict, Any, Optional, Tuple
from queue import Queue, Empty, Full
from datetime import datetime

# All supported WLED baud rates in priority order
WLED_BAUD_RATES = [
    115200,   # Default WLED speed
    230400,
    460800,
    500000,
    576000,
    921600,
    1000000,
    1500000,
    2000000,
]


class LEDOutput:
    """Handles serial output to LED strips with dedicated worker thread"""
    
    def __init__(self, config: Dict[str, Any], debug: bool = False, ddebug: bool = False):
        self.port = config['port']
        self.protocol = config['protocol']
        self.baud_rate = config['baud_rate']
        self.led_count = config['led_count']
        self.opc_channel = config['opc_channel']
        self.opc_offset = config.get('opc_offset', 0)
        self.pixel_format = config.get('pixel_format', None)
        self.hardware_type = config.get('hardware_type', None)
        self.handshake_baud_rate = config.get('handshake_baud_rate', None)
        self.debug = debug
        self.ddebug = ddebug
        self.ser = None
        
        # Frame timing tracking
        self.last_frame_time = None
        self.frame_count = 0
        
        # Determine output stride based on pixel format
        if self.pixel_format in ('RGBW', 'GRBW'):
            self.stride = 4
        else:
            self.stride = 3
        
        # Queue and worker thread (one per serial output)
        self.queue = Queue(maxsize=1)
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
    
    def open(self):
        """Open serial connection with WLED baud rate detection if needed"""
        try:
            # Handle WLED devices with baud rate detection
            if self.hardware_type == "WLED":
                self.ser = self._open_wled_port()
            else:
                self.ser = self._open_standard_port(self.baud_rate)
            
            if self.ser:
                return True
            return False
        except serial.SerialException as e:
            print(f"Error opening {self.port}: {e}")
            return False
    
    def _open_standard_port(self, baud_rate: int) -> serial.Serial:
        """Open a standard serial port (non-WLED)"""
        ser = serial.Serial(
            self.port, 
            baud_rate, 
            timeout=1
        )
        time.sleep(0.1)  # Allow device to initialize
        # Clear buffers to remove any leftover data from previous operations
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        return ser
    
    def _open_wled_port(self) -> Optional[serial.Serial]:
        """Open and initialize a WLED device with baud rate detection"""
        if self.debug:
            print(f"Detecting WLED device on {self.port}...")
        
        # Build list of baud rates to try in priority order:
        # 1. Configured baud_rate (data rate)
        # 2. Configured handshake_baud_rate (control baud)
        # 3. All WLED standard rates
        baud_rates_to_try = []
        
        # Add configured data rate first
        baud_rates_to_try.append(self.baud_rate)
        
        # Add handshake baud if different and specified
        if self.handshake_baud_rate and self.handshake_baud_rate != self.baud_rate:
            baud_rates_to_try.append(self.handshake_baud_rate)
        
        # Add all standard WLED rates (skip duplicates)
        for rate in WLED_BAUD_RATES:
            if rate not in baud_rates_to_try:
                baud_rates_to_try.append(rate)
        
        # Try each baud rate until we get a response
        detected_baud = None
        wled_response = None
        
        for baud in baud_rates_to_try:
            if self.debug:
                print(f"[PROBE {self.port}] Trying baud rate {baud}...")
            
            response = self._try_wled_handshake(baud)
            if response:
                detected_baud = baud
                wled_response = response
                if self.debug:
                    print(f"✓ WLED device detected at {baud} baud on {self.port}")
                    print(f"  Response: {response.strip()[:80]}")  # First 80 chars
                break
            else:
                if self.debug:
                    print(f"  No response at {baud} baud")
        
        if not detected_baud:
            print(f"✗ Failed to detect WLED device on {self.port} (tried {len(baud_rates_to_try)} baud rates)")
            return None
        
        if self.ddebug:
            print(f"[DEBUG {self.port}] WLED response: {wled_response}")
        
        # Now switch to the configured baud rate if different
        if detected_baud != self.baud_rate:
            if self.debug:
                print(f"Switching {self.port} from {detected_baud} to {self.baud_rate} baud...")
            
            # Open at detected baud
            ser = serial.Serial(self.port, detected_baud, timeout=0.5)
            time.sleep(0.1)
            
            # Clear buffers before sending baud change command
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            # Send baud change command
            baud_byte = self._get_wled_baud_byte(self.baud_rate)
            if baud_byte is None:
                print(f"✗ Unsupported WLED baud rate: {self.baud_rate}")
                ser.close()
                return None
            
            ser.write(bytes([baud_byte]))
            ser.flush()
            
            # Wait for confirmation
            time.sleep(0.2)
            
            # Try to read confirmation (optional)
            if ser.in_waiting > 0:
                try:
                    response = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                    if self.ddebug:
                        print(f"[DEBUG {self.port}] Baud change response: {response}")
                except Exception:
                    pass
            
            # Close and reopen at new baud rate
            ser.close()
            time.sleep(0.1)
            
            ser = serial.Serial(self.port, self.baud_rate, timeout=1)
            time.sleep(0.1)  # Match discover.py timing
            
            # CRITICAL: Clear buffers to remove any leftover data from baud change
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            if self.debug:
                print(f"✓ WLED device on {self.port} now running at {self.baud_rate} baud")
            
            return ser
        else:
            # Already at correct baud, just open normally like discover.py
            return self._open_standard_port(self.baud_rate)
    
    def _try_wled_handshake(self, baud: int) -> Optional[str]:
        """Try WLED handshake at a specific baud rate"""
        ser = None
        try:
            if self.debug:
                print(f"  Opening port at {baud} baud...")
            ser = serial.Serial(self.port, baud, timeout=0.5)
            if self.debug:
                print(f"  Port opened successfully")
            time.sleep(0.15)  # Give device time to initialize
            
            # Clear any pending data aggressively
            if self.debug:
                print(f"  Clearing buffers...")
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            time.sleep(0.05)
            
            # Send WLED version query - just 'v' for quick probe
            query = b'v'
            if self.debug:
                print(f"  Sending probe: {query}")
            ser.write(query)
            ser.flush()
            if self.debug:
                print(f"  Probe sent, waiting for response...")
            
            # Wait for response (shorter timeout since response should be immediate)
            time.sleep(0.2)
            
            # Read response
            bytes_waiting = ser.in_waiting
            if self.debug:
                print(f"  Bytes available to read: {bytes_waiting}")
            
            if bytes_waiting > 0:
                response = ser.read(bytes_waiting).decode('utf-8', errors='ignore')
                if self.debug:
                    print(f"  Read {len(response)} chars: {response[:80]}")
                
                # Validate it looks like a valid response (any non-empty response is good)
                if len(response) > 0:
                    # Success - close cleanly and wait before returning
                    if self.debug:
                        print(f"  Valid response! Closing port...")
                    ser.close()
                    time.sleep(0.1)  # Let device settle after successful handshake
                    return response
            
            # No valid response - close and wait longer before next attempt
            if self.debug:
                print(f"  No valid response, closing port and waiting...")
            ser.close()
            time.sleep(0.2)  # Important: wait for device to recover before next attempt
            return None
            
        except Exception as e:
            if self.debug:
                print(f"  Exception: {e}")
            # Make sure port is closed even on exception
            if ser and ser.is_open:
                try:
                    if self.debug:
                        print(f"  Closing port after exception...")
                    ser.close()
                    time.sleep(0.2)  # Wait for device to recover
                except Exception:
                    pass
            return None
    
    @staticmethod
    def _get_wled_baud_byte(baud: int) -> Optional[int]:
        """Get the baud change byte for a given baud rate"""
        baud_map = {
            115200: 0xB0,
            230400: 0xB1,
            460800: 0xB2,
            500000: 0xB3,
            576000: 0xB4,
            921600: 0xB5,
            1000000: 0xB6,
            1500000: 0xB7,
            2000000: 0xB8,
        }
        return baud_map.get(baud)
    
    def close(self):
        """Close serial connection"""
        self.running = False
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                # Port may already be disconnected - ignore errors during close
                pass
    
    def put_frame(self, pixel_data: bytearray):
        """
        Put frame in queue (called by main thread)
        Non-blocking - replaces old frame if queue is full
        """
        try:
            self.queue.put_nowait(pixel_data)
        except Full:
            # Queue full, replace with new frame
            try:
                self.queue.get_nowait()  # Discard old frame
            except Empty:
                pass  # Race condition - someone else got it
            try:
                self.queue.put_nowait(pixel_data)
            except Full:
                pass  # Still full somehow, skip this frame
    
    def _worker(self):
        """Worker thread - blocks waiting for frames, sends to serial"""
        while self.running:
            try:
                # Block until data available (efficient, no spinning)
                pixel_data = self.queue.get(timeout=0.1)
                self._send_frame(pixel_data)
            except Empty:
                # Timeout - check if still running
                continue
    
    def _send_frame(self, pixel_data: bytearray):
        """Send a frame to the LED strip"""
        if not self.ser:
            return False
        
        try:
            # Apply pixel format transformation if specified
            if self.pixel_format:
                pixel_data = self._transform_pixels(pixel_data)
            
            # Send frame based on protocol
            if self.protocol == 'awa':
                self._send_awa_frame(pixel_data)
            elif self.protocol == 'adalight':
                self._send_adalight_frame(pixel_data)
            else:
                print(f"Protocol {self.protocol} not yet implemented")
                return False
            
            return True
            
        except serial.SerialException as e:
            print(f"✗ Serial error on {self.port}: {e}")
            print(f"✗ Output {self.port} is now disconnected")
            self.ser = None  # Mark as disconnected
            return False
        except Exception as e:
            print(f"✗ Unexpected error on {self.port}: {e}")
            return False
    
    def _transform_pixels(self, pixel_data: bytearray) -> bytearray:
        """Transform RGB pixel data based on pixel_format"""
        # RGB passthrough - no transformation needed
        if self.pixel_format == 'RGB' or self.pixel_format is None:
            return pixel_data
        
        pixel_count = len(pixel_data) // 3
        
        # For same-size 3-channel transforms, transform in-place
        if self.pixel_format == 'GRB':
            # Swap R and G channels in place
            for i in range(pixel_count):
                idx = i * 3
                pixel_data[idx], pixel_data[idx + 1] = pixel_data[idx + 1], pixel_data[idx]
            return pixel_data
        
        elif self.pixel_format == 'BGR':
            # Reverse RGB to BGR in place
            for i in range(pixel_count):
                idx = i * 3
                pixel_data[idx], pixel_data[idx + 2] = pixel_data[idx + 2], pixel_data[idx]
            return pixel_data
        
        # RGBW transforms - different size output
        elif self.pixel_format in ('RGBW', 'GRBW'):
            # Create new buffer with stride 4
            transformed = bytearray(pixel_count * 4)
            
            for i in range(pixel_count):
                src_idx = i * 3
                dst_idx = i * 4
                r = pixel_data[src_idx]
                g = pixel_data[src_idx + 1]
                b = pixel_data[src_idx + 2]
                
                # Extract white channel and subtract from RGB
                w = min(r, g, b)
                
                if self.pixel_format == 'RGBW':
                    transformed[dst_idx] = r - w
                    transformed[dst_idx + 1] = g - w
                    transformed[dst_idx + 2] = b - w
                    transformed[dst_idx + 3] = w
                else:  # GRBW
                    transformed[dst_idx] = g - w
                    transformed[dst_idx + 1] = r - w
                    transformed[dst_idx + 2] = b - w
                    transformed[dst_idx + 3] = w
            
            return transformed
        
        # Unknown format - return unchanged
        return pixel_data
    
    def _send_adalight_frame(self, pixel_data: bytearray):
        """Send Adalight protocol frame (may raise SerialException)"""
        # Track frame timing
        current_time = time.time()
        if self.last_frame_time is not None:
            frame_delay = current_time - self.last_frame_time
        else:
            frame_delay = 0
        self.last_frame_time = current_time
        self.frame_count += 1
        
        # Adalight header: 'Ada' + LED count high + LED count low + checksum
        # NOTE: LED count field is (actual_count - 1), similar to AWA protocol
        led_count = len(pixel_data) // self.stride
        count_minus_one = led_count - 1
        header = bytearray([
            0x41, 0x64, 0x61,  # 'Ada'
            (count_minus_one >> 8) & 0xFF,
            count_minus_one & 0xFF,
            (count_minus_one >> 8) ^ (count_minus_one & 0xFF) ^ 0x55
        ])
        
        # Construct complete frame
        frame = header + pixel_data
        
        # Debug: print raw frame being sent to serial
        if self.ddebug:
            ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            print(f"[{ts}] [SERIAL-TIMING] {self.port} Frame #{self.frame_count}: delay={frame_delay*1000:.1f}ms since last")
            print(f"[{ts}] [SERIAL-DATA] {self.port} Adalight: {len(frame)} bytes total")
            print(f"[{ts}] [SERIAL-DATA]   - Header: 6 bytes")
            print(f"[{ts}] [SERIAL-DATA]   - Pixel data: {len(pixel_data)} bytes")
            print(f"[{ts}] [SERIAL-DATA]   - LED count field: {led_count}")
            print(f"[{ts}] [SERIAL-DATA]   - Configured LED count: {self.led_count}")
            print(f"[{ts}] [SERIAL-DATA]   - Stride: {self.stride}")
            if led_count != self.led_count:
                print(f"[{ts}] [SERIAL-WARNING] LED count mismatch! Calculated {led_count} but config says {self.led_count}")
            hex_dump = ' '.join(f'{b:02x}' for b in frame[:48])  # First 48 bytes
            print(f"[{ts}] [SERIAL-HEX] First 48 bytes: {hex_dump}")
        
        # CRITICAL DEBUG: Log every single write operation
        if self.ddebug:
            ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            # Check for dangerous baud change bytes in pixel data
            dangerous_bytes = [0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8]
            found_dangerous = []
            for i, byte in enumerate(frame):
                if byte in dangerous_bytes:
                    found_dangerous.append((i, byte, f"0x{byte:02X}"))
            if found_dangerous:
                print(f"[{ts}] [SERIAL-WARNING] Frame contains WLED baud change bytes:")
                for pos, byte_val, hex_val in found_dangerous:
                    in_header = "HEADER" if pos < 6 else f"PIXEL[{(pos-6)//3}] byte {(pos-6)%3}"
                    print(f"[{ts}] [SERIAL-WARNING]   Position {pos} ({in_header}): {hex_val} = {byte_val}")
            
            print(f"[{ts}] [SERIAL-WRITE] Writing {len(frame)} bytes atomically")
            print(f"[{ts}] [SERIAL-WRITE] Frame checksum: 0x{sum(frame) & 0xFF:02X}")
        
        # Send frame: header + pixel data (may raise SerialException)
        bytes_written = self.ser.write(frame)
        self.ser.flush()
        
        if self.ddebug:
            ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            if bytes_written != len(frame):
                print(f"[{ts}] [SERIAL-ERROR] Partial write! Expected {len(frame)}, wrote {bytes_written}")
            else:
                print(f"[{ts}] [SERIAL-WRITE] Successfully wrote all {bytes_written} bytes and flushed")
    
    def _send_awa_frame(self, pixel_data: bytearray):
        """Send AWA protocol frame (HyperSerialPico format, may raise SerialException)"""
        led_count = len(pixel_data) // self.stride
        
        # AWA header: 'Awa' + LED count high + LED count low + CRC
        count_hi = (led_count - 1) >> 8 & 0xFF
        count_lo = (led_count - 1) & 0xFF
        crc = (count_hi ^ count_lo) ^ 0x55
        
        header = bytearray([
            0x41, 0x77, 0x61,  # 'Awa'
            count_hi,
            count_lo,
            crc
        ])
        
        # Calculate Fletcher checksums (matches HyperSerialPico implementation)
        fletcher1 = 0
        fletcher2 = 0
        fletcher_ext = 0
        position = 0
        
        for byte in pixel_data:
            fletcher1 = (fletcher1 + byte) % 255
            fletcher2 = (fletcher2 + fletcher1) % 255
            fletcher_ext = (fletcher_ext + (byte ^ position)) % 255
            position += 1
        
        # Special case: if fletcher_ext is 0x41 ('A'), use 0xaa instead
        if fletcher_ext == 0x41:
            fletcher_ext = 0xaa
        
        # Construct complete frame
        frame = header + pixel_data + bytearray([fletcher1, fletcher2, fletcher_ext])
        
        # Debug: print raw frame being sent to serial
        if self.ddebug:
            print(f"[SERIAL] {self.port} AWA: {len(frame)} bytes ({led_count} pixels)")
            print(f"[SERIAL] Header: {' '.join(f'{b:02x}' for b in header)}")
            print(f"[SERIAL] Fletcher: {fletcher1:02x} {fletcher2:02x} {fletcher_ext:02x}")
            hex_dump = ' '.join(f'{b:02x}' for b in frame)
            print(f"[SERIAL] Raw output: {hex_dump}")
        
        # Send frame: header + data + fletcher checksums
        self.ser.write(frame)
        self.ser.flush()


class OPCServer:
    """OPC Server that receives OPC data and outputs to serial"""
    
    # Receive buffer size (supports large frames)
    RECV_BUFFER_SIZE = 16384  # 16KB
    
    def __init__(self, config: Dict[str, Any], debug: bool = False, ddebug: bool = False):
        self.config = config
        self.debug = debug
        self.ddebug = ddebug
        self.host = config['opc']['host']
        self.port = config['opc']['port']
        self.outputs = []
        self.running = False
        self.server_socket = None
        
        # Statistics
        self.frames_received = 0
        self.frames_sent = 0
        self.last_stats_time = time.time()
    
    def setup_outputs(self):
        """Initialize serial outputs (each with worker thread)"""
        for output_config in self.config['outputs']:
            output = LEDOutput(output_config, debug=self.debug, ddebug=self.ddebug)
            if output.open():
                self.outputs.append(output)
                print(f"✓ Opened {output.port} (channel {output.opc_channel}, offset {output.opc_offset}, "
                      f"{output.protocol} @ {output.baud_rate} baud, {output.led_count} LEDs)")
            else:
                print(f"✗ Failed to open {output.port}")
        
        if not self.outputs:
            print("Error: No outputs could be opened")
            return False
        
        return True
    
    def start(self):
        """Start the OPC server"""
        if not self.setup_outputs():
            return False
        
        self.running = True
        
        # Start server socket
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            print(f"✓ OPC Server listening on {self.host}:{self.port}")
        except Exception as e:
            print(f"Error starting server: {e}")
            return False
        
        # Start stats thread if debug enabled
        if self.debug:
            stats_thread = threading.Thread(target=self._stats_worker, daemon=True)
            stats_thread.start()
        
        return True
    
    def _stats_worker(self):
        """Print statistics periodically"""
        while self.running:
            time.sleep(5.0)
            current_time = time.time()
            elapsed = current_time - self.last_stats_time
            
            if elapsed > 0:
                fps_received = self.frames_received / elapsed
                fps_sent = self.frames_sent / elapsed
                print(f"[Stats] Received: {fps_received:.1f} fps, Sent: {fps_sent:.1f} fps")
            
            self.frames_received = 0
            self.frames_sent = 0
            self.last_stats_time = current_time
    
    def run(self):
        """Main server loop"""
        print("Waiting for OPC client connection...")
        print("(Press Ctrl-C to stop)")
        
        # Set socket timeout so accept() doesn't block forever
        self.server_socket.settimeout(1.0)
        
        try:
            while self.running:
                try:
                    # Accept client connection (with timeout)
                    client_socket, client_address = self.server_socket.accept()
                    print(f"✓ Client connected from {client_address}")
                    
                    try:
                        self._handle_client(client_socket)
                    except Exception as e:
                        print(f"Error handling client: {e}")
                        if self.debug:
                            import traceback
                            traceback.print_exc()
                    finally:
                        client_socket.close()
                        print("Client disconnected")
                
                except socket.timeout:
                    # Timeout on accept - check if still running
                    continue
                except OSError as e:
                    # Socket closed
                    if self.running:
                        print(f"Socket error: {e}")
                    break
        
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.stop()
    
    def _handle_client(self, client_socket):
        """Handle OPC client connection with non-blocking TCP drain"""
        # Set socket to non-blocking mode
        client_socket.setblocking(False)
        buffer = b''
        
        while self.running:
            # Drain TCP socket (read all available data)
            while True:
                try:
                    data = client_socket.recv(self.RECV_BUFFER_SIZE)
                    if not data:
                        # Connection closed
                        return
                    buffer += data
                except BlockingIOError:
                    # No more data available right now
                    break
                except Exception as e:
                    if self.debug:
                        print(f"Error reading from socket: {e}")
                    return
            
            # Process complete OPC messages in buffer
            while len(buffer) >= 4:
                # OPC header: channel (1 byte), command (1 byte), length (2 bytes, big-endian)
                channel = buffer[0]
                command = buffer[1]
                length = struct.unpack('>H', buffer[2:4])[0]
                
                # Check if we have the complete message
                message_size = 4 + length
                if len(buffer) < message_size:
                    break
                
                # Extract message data as bytearray
                message_data = bytearray(buffer[4:message_size])
                buffer = buffer[message_size:]
                
                # Process OPC message
                if command == 0:  # Set pixel colors
                    self._process_pixel_data(channel, message_data)
                    self.frames_received += 1
            
            # Small sleep to avoid busy loop (1ms)
            time.sleep(0.001)
    
    def _process_pixel_data(self, channel: int, pixel_data: bytearray):
        """
        Process OPC pixel data - slice and distribute to serial outputs
        Each output gets its slice based on opc_offset and led_count
        """
        if self.ddebug:
            ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            print(f"[{ts}] [DEBUG] Received: channel={channel}, byte_count={len(pixel_data)}, "
                  f"pixel_count={len(pixel_data)//3}")
            # Show first few pixels as hex
            hex_dump = ' '.join(f'{b:02x}' for b in pixel_data[:30])
            print(f"[{ts}] [DEBUG] First 30 bytes received: {hex_dump}")
        
        # Distribute to each serial output listening to this channel
        for output in self.outputs:
            # Does this output listen to this channel?
            # Broadcast (channel 0) goes to outputs configured for channel 0
            # Other channels go to matching outputs
            if output.opc_channel != channel:
                # Skip if not the right channel
                if not (channel == 0 and output.opc_channel == 0):
                    continue
            
            # Calculate byte offset and length for this output
            offset_bytes = output.opc_offset * 3  # RGB stride
            needed_bytes = output.led_count * 3
            
            # Slice data for this output (handles overlaps gracefully)
            # Truncates if too much data, sends less if not enough
            end_byte = offset_bytes + needed_bytes
            sliced_data = bytearray(pixel_data[offset_bytes:end_byte])
            
            # Send to this output's queue (non-blocking)
            # Adalight header will reflect actual pixel count sent
            if self.ddebug:
                ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                print(f"[{ts}] [DEBUG] Output {output.port}: sliced={len(sliced_data)} bytes "
                      f"({len(sliced_data)//3} pixels), needed={needed_bytes} bytes")
                hex_dump = ' '.join(f'{b:02x}' for b in sliced_data[:30])
                print(f"[{ts}] [DEBUG] First 30 bytes to output: {hex_dump}")
            output.put_frame(sliced_data)
            self.frames_sent += 1
    
    def stop(self):
        """Stop the server and cleanup"""
        self.running = False
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        
        # Stop all outputs
        for output in self.outputs:
            try:
                # Try to turn off LEDs (may fail if port disconnected)
                blank_data = bytearray(output.led_count * 3)
                output.put_frame(blank_data)
                # Give worker thread a moment to process
                time.sleep(0.05)
            except Exception:
                pass
            
            # Close will stop worker thread and serial port
            output.close()
        
        print("✓ Server stopped")


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='OpenPixelControlSerial - OPC Server\n\nReceives OPC data over TCP and outputs to serial LED strips.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('config', 
                       help='Path to configuration file (JSON)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug output (statistics only)')
    parser.add_argument('--ddebug', action='store_true',
                       help='Enable detailed debug (hex dumps every frame)')
    
    args = parser.parse_args()
    
    # --ddebug implies --debug
    if args.ddebug:
        args.debug = True
    
    # Load configuration
    config = load_config(args.config)
    
    # Validate config
    if 'opc' not in config:
        print("Error: Config must contain 'opc' section")
        sys.exit(1)
    
    if 'outputs' not in config or not config['outputs']:
        print("Error: No outputs defined in config file")
        sys.exit(1)
    
    # Create and start server
    server = OPCServer(config, debug=args.debug, ddebug=args.ddebug)
    
    if not server.start():
        sys.exit(1)
    
    # Run server
    server.run()


if __name__ == "__main__":
    main()
