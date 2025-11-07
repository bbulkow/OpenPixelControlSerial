use anyhow::{Context, Result};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc::{self, SyncSender, Receiver, TrySendError};
use std::thread;
use std::time::Duration;
use std::io::{Read, Write};
use serialport::SerialPort;

use crate::config::OutputConfig;
use crate::pixel_format::transform_pixels;
use crate::protocol::{build_awa_frame, build_adalight_frame};

/// All supported WLED baud rates in priority order
const WLED_BAUD_RATES: &[u32] = &[
    115200,   // Default WLED speed
    230400,
    460800,
    500000,
    576000,
    921600,
    1000000,
    1500000,
    2000000,
];

/// LED output handler with dedicated worker thread
pub struct Output {
    config: OutputConfig,
    sender: SyncSender<Vec<u8>>,
    frames_sent: Arc<AtomicU64>,
    running: Arc<AtomicBool>,
    worker_handle: Option<thread::JoinHandle<()>>,
}

impl Output {
    /// Create a new output handler
    pub fn new(config: OutputConfig, debug: bool, ddebug: bool) -> Result<Self> {
        // Handle WLED devices with baud rate detection
        let port = if config.hardware_type.as_deref() == Some("WLED") {
            Self::open_wled_port(&config, debug, ddebug)?
        } else {
            // Standard port opening for non-WLED devices
            Self::open_standard_port(&config)?
        };
        
        // Create BOUNDED channel with capacity 1 for skip-ahead behavior (like Python Queue(maxsize=1))
        let (sender, receiver) = mpsc::sync_channel::<Vec<u8>>(1);
        
        // Shared state
        let frames_sent = Arc::new(AtomicU64::new(0));
        let running = Arc::new(AtomicBool::new(true));
        
        // Spawn worker thread
        let worker_config = config.clone();
        let worker_frames_sent = Arc::clone(&frames_sent);
        let worker_running = Arc::clone(&running);
        
        let worker_handle = thread::spawn(move || {
            worker_thread(port, receiver, worker_config, worker_frames_sent, worker_running, ddebug);
        });
        
        if debug {
            println!("✓ Opened {} (channel {}, offset {}, {} @ {} baud, {} LEDs)",
                     config.port, config.opc_channel, config.opc_offset,
                     config.protocol, config.baud_rate, config.led_count);
        }
        
        Ok(Output {
            config,
            sender,
            frames_sent,
            running,
            worker_handle: Some(worker_handle),
        })
    }
    
    /// Get the configuration for this output
    pub fn config(&self) -> &OutputConfig {
        &self.config
    }
    
    /// Send a frame to this output (non-blocking, skip-ahead)
    pub fn send_frame(&self, pixel_data: Vec<u8>) -> Result<()> {
        // try_send implements skip-ahead: if channel is full, frame is discarded
        match self.sender.try_send(pixel_data) {
            Ok(_) => Ok(()),
            Err(TrySendError::Full(_)) => {
                // Channel full, frame dropped (skip-ahead behavior)
                Ok(())
            }
            Err(TrySendError::Disconnected(_)) => {
                // Channel disconnected
                Ok(())
            }
        }
    }
    
    /// Get number of frames sent
    #[allow(dead_code)]
    pub fn frames_sent(&self) -> u64 {
        self.frames_sent.load(Ordering::Relaxed)
    }
    
    /// Reset frame counter
    #[allow(dead_code)]
    pub fn reset_counter(&self) {
        self.frames_sent.store(0, Ordering::Relaxed)
    }
    
    /// Get a clone of the frames sent counter (for statistics)
    pub fn frames_sent_counter(&self) -> Arc<AtomicU64> {
        Arc::clone(&self.frames_sent)
    }
    
    /// Stop the output and wait for worker thread
    pub fn stop(&mut self) {
        self.running.store(false, Ordering::Relaxed);
        
        if let Some(handle) = self.worker_handle.take() {
            let _ = handle.join();
        }
    }
    
    /// Open a standard serial port (non-WLED)
    fn open_standard_port(config: &OutputConfig) -> Result<Box<dyn SerialPort>> {
        let mut port = serialport::new(&config.port, config.baud_rate)
            .data_bits(serialport::DataBits::Eight)
            .parity(serialport::Parity::None)
            .stop_bits(serialport::StopBits::One)
            .flow_control(serialport::FlowControl::None)
            .open()
            .context(format!("Failed to open serial port {}", config.port))?;
        
        // Set write timeout to avoid blocking forever (like Python's timeout=1)
        port.set_timeout(Duration::from_millis(1000))
            .context("Failed to set serial port timeout")?;
        
        // Set DTR to match Python's pyserial defaults
        if let Err(e) = port.write_data_terminal_ready(true) {
            eprintln!("Warning: Failed to set DTR on {}: {}", config.port, e);
        }
        
        // Allow device to initialize
        thread::sleep(Duration::from_millis(100));
        
        Ok(port)
    }
    
    /// Open and initialize a WLED device with baud rate detection
    fn open_wled_port(config: &OutputConfig, debug: bool, ddebug: bool) -> Result<Box<dyn SerialPort>> {
        if debug {
            println!("Detecting WLED device on {}...", config.port);
        }
        
        // Build list of baud rates to try in priority order:
        // 1. Configured baud_rate (data rate)
        // 2. Configured handshake_baud_rate (control baud)
        // 3. All WLED standard rates
        let mut baud_rates_to_try = Vec::new();
        
        // Add configured data rate first
        baud_rates_to_try.push(config.baud_rate);
        
        // Add handshake baud if different and specified
        if let Some(handshake_baud) = config.handshake_baud_rate {
            if handshake_baud != config.baud_rate {
                baud_rates_to_try.push(handshake_baud);
            }
        }
        
        // Add all standard WLED rates (skip duplicates)
        for &rate in WLED_BAUD_RATES {
            if !baud_rates_to_try.contains(&rate) {
                baud_rates_to_try.push(rate);
            }
        }
        
        // Try each baud rate until we get a response
        let mut detected_baud = None;
        let mut wled_response = String::new();
        
        for &baud in &baud_rates_to_try {
            if ddebug {
                eprintln!("[DEBUG {}] Trying baud rate {}...", config.port, baud);
            }
            
            match Self::try_wled_handshake(&config.port, baud, ddebug) {
                Ok(response) => {
                    detected_baud = Some(baud);
                    wled_response = response;
                    if debug {
                        println!("✓ WLED device detected at {} baud on {}", baud, config.port);
                    }
                    break;
                }
                Err(e) => {
                    if ddebug {
                        eprintln!("[DEBUG {}] No response at {} baud: {}", config.port, baud, e);
                    }
                }
            }
        }
        
        let detected_baud = detected_baud.context(format!(
            "Failed to detect WLED device on {} (tried {} baud rates)",
            config.port,
            baud_rates_to_try.len()
        ))?;
        
        if ddebug {
            eprintln!("[DEBUG {}] WLED response: {}", config.port, wled_response);
        }
        
        // Now switch to the configured baud rate if different
        if detected_baud != config.baud_rate {
            if debug {
                println!("Switching {} from {} to {} baud...", config.port, detected_baud, config.baud_rate);
            }
            
            let mut port = serialport::new(&config.port, detected_baud)
                .data_bits(serialport::DataBits::Eight)
                .parity(serialport::Parity::None)
                .stop_bits(serialport::StopBits::One)
                .flow_control(serialport::FlowControl::None)
                .timeout(Duration::from_millis(500))
                .open()
                .context(format!("Failed to reopen {} at detected baud", config.port))?;
            
            // Set DTR
            if let Err(e) = port.write_data_terminal_ready(true) {
                eprintln!("Warning: Failed to set DTR on {}: {}", config.port, e);
            }
            thread::sleep(Duration::from_millis(100));
            
            // Send baud change command based on target rate
            let baud_byte = Self::get_wled_baud_byte(config.baud_rate)
                .context(format!("Unsupported WLED baud rate: {}", config.baud_rate))?;
            
            port.write_all(&[baud_byte])
                .context("Failed to send baud change command")?;
            port.flush().context("Failed to flush baud change command")?;
            
            // Wait for confirmation
            thread::sleep(Duration::from_millis(200));
            
            // Try to read confirmation (optional, may not always work)
            let mut buf = vec![0u8; 100];
            if let Ok(n) = port.read(&mut buf) {
                if ddebug {
                    let response = String::from_utf8_lossy(&buf[..n]);
                    eprintln!("[DEBUG {}] Baud change response: {}", config.port, response);
                }
            }
            
            // Close and reopen at new baud rate
            drop(port);
            thread::sleep(Duration::from_millis(100));
            
            let mut port = serialport::new(&config.port, config.baud_rate)
                .data_bits(serialport::DataBits::Eight)
                .parity(serialport::Parity::None)
                .stop_bits(serialport::StopBits::One)
                .flow_control(serialport::FlowControl::None)
                .timeout(Duration::from_millis(1000))
                .open()
                .context(format!("Failed to reopen {} at new baud", config.port))?;
            
            if let Err(e) = port.write_data_terminal_ready(true) {
                eprintln!("Warning: Failed to set DTR on {}: {}", config.port, e);
            }
            thread::sleep(Duration::from_millis(100));
            
            if debug {
                println!("✓ WLED device on {} now running at {} baud", config.port, config.baud_rate);
            }
            
            Ok(port)
        } else {
            // Already at correct baud, just open normally
            Self::open_standard_port(config)
        }
    }
    
    /// Try WLED handshake at a specific baud rate
    fn try_wled_handshake(port_name: &str, baud: u32, ddebug: bool) -> Result<String> {
        let mut port = serialport::new(port_name, baud)
            .data_bits(serialport::DataBits::Eight)
            .parity(serialport::Parity::None)
            .stop_bits(serialport::StopBits::One)
            .flow_control(serialport::FlowControl::None)
            .timeout(Duration::from_millis(500))
            .open()
            .context("Failed to open port")?;
        
        // Set DTR
        if let Err(e) = port.write_data_terminal_ready(true) {
            if ddebug {
                eprintln!("Warning: Failed to set DTR: {}", e);
            }
        }
        
        // Give device time to initialize
        thread::sleep(Duration::from_millis(150));
        
        // Clear any pending data aggressively
        port.clear(serialport::ClearBuffer::All).ok();
        thread::sleep(Duration::from_millis(50));
        
        // Send WLED version query
        let query = b"{\"v\":true}\n";
        port.write_all(query).context("Failed to write query")?;
        port.flush().context("Failed to flush")?;
        
        // Wait for response (increased timeout)
        thread::sleep(Duration::from_millis(300));
        
        // Read response
        let mut buffer = vec![0u8; 1024];
        let n = match port.read(&mut buffer) {
            Ok(n) => n,
            Err(e) => {
                // Close port and wait before returning error
                drop(port);
                thread::sleep(Duration::from_millis(200));
                return Err(e).context("No response received");
            }
        };
        
        if n == 0 {
            // Close port and wait before returning error
            drop(port);
            thread::sleep(Duration::from_millis(200));
            anyhow::bail!("Empty response");
        }
        
        let response = String::from_utf8_lossy(&buffer[..n]).to_string();
        
        // Validate it looks like a JSON response
        if response.contains("{") || response.contains("ver") {
            // Success - close cleanly and wait before returning
            drop(port);
            thread::sleep(Duration::from_millis(100));
            Ok(response)
        } else {
            // Invalid response - close and wait before returning error
            drop(port);
            thread::sleep(Duration::from_millis(200));
            anyhow::bail!("Invalid response: {}", response)
        }
    }
    
    /// Get the baud change byte for a given baud rate
    fn get_wled_baud_byte(baud: u32) -> Option<u8> {
        match baud {
            115200 => Some(0xB0),
            230400 => Some(0xB1),
            460800 => Some(0xB2),
            500000 => Some(0xB3),
            576000 => Some(0xB4),
            921600 => Some(0xB5),
            1000000 => Some(0xB6),
            1500000 => Some(0xB7),
            2000000 => Some(0xB8),
            _ => None,
        }
    }
}

impl Drop for Output {
    fn drop(&mut self) {
        self.stop();
    }
}

/// Worker thread function - blocks on queue waiting for frames, sends to serial port
fn worker_thread(
    mut port: Box<dyn SerialPort>,
    receiver: Receiver<Vec<u8>>,
    config: OutputConfig,
    frames_sent: Arc<AtomicU64>,
    running: Arc<AtomicBool>,
    ddebug: bool,
) {
    // Determine stride based on pixel format
    let stride = match config.pixel_format.as_deref() {
        Some("RGBW") | Some("GRBW") => 4,
        _ => 3,
    };
    
    while running.load(Ordering::Relaxed) {
        // Block waiting for frame (like Python's queue.get())
        match receiver.recv_timeout(Duration::from_millis(100)) {
            Ok(pixel_data) => {
                // Transform pixels if needed
                let transformed = transform_pixels(
                    pixel_data,
                    config.pixel_format.as_deref()
                );
                
                // Build protocol frame
                let frame = match config.protocol.as_str() {
                    "awa" => build_awa_frame(&transformed, stride),
                    "adalight" => build_adalight_frame(&transformed, stride),
                    _ => {
                        eprintln!("Unknown protocol: {}", config.protocol);
                        continue;
                    }
                };
                
                if ddebug {
                    eprintln!("[DEBUG {}] Sending frame: {} bytes ({} pixels, {} stride)", 
                             config.port, frame.len(), transformed.len() / stride, stride);
                    
                    // Show hex dump of complete frame being sent to serial
                    let hex: String = frame.iter()
                        .map(|b| format!("{:02x}", b)).collect::<Vec<_>>().join(" ");
                    eprintln!("[DEBUG {}] Complete serial frame: {}", config.port, hex);
                }
                
                // Send to serial port - use write_all to ensure all bytes sent
                match port.write_all(&frame) {
                    Ok(_) => {
                        if ddebug {
                            let write_time = std::time::Instant::now().elapsed();
                            eprintln!("[DEBUG {}] write_all took {:?} for {} bytes", 
                                     config.port, write_time, frame.len());
                        }
                        
                        // Flush to ensure data goes out immediately
                        match port.flush() {
                            Ok(_) => {
                                if ddebug {
                                    eprintln!("[DEBUG {}] flush took {:?}", config.port, std::time::Instant::now().elapsed());
                                    eprintln!("[DEBUG {}] Total send time: {:?}", config.port, std::time::Instant::now().elapsed());
                                }
                                
                                frames_sent.fetch_add(1, Ordering::Relaxed);
                            }
                            Err(e) => {
                                if ddebug {
                                    eprintln!("[DEBUG {}] flush failed", config.port);
                                }
                                eprintln!("✗ Failed to flush {}: {}", config.port, e);
                                eprintln!("✗ Output {} is now disconnected", config.port);
                                break; // Exit worker thread on error
                            }
                        }
                    }
                    Err(e) => {
                        if ddebug {
                            eprintln!("[DEBUG {}] write_all failed", config.port);
                        }
                        eprintln!("✗ Serial error on {}: {}", config.port, e);
                        eprintln!("✗ Output {} is now disconnected", config.port);
                        break; // Exit worker thread on error
                    }
                }
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                // No data, check if still running
                continue;
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                // Channel closed, exit worker
                break;
            }
        }
    }
    
    // Try to turn off LEDs on exit (best effort)
    let blank_data = vec![0u8; config.led_count * 3];
    let transformed = transform_pixels(blank_data, config.pixel_format.as_deref());
    let frame = match config.protocol.as_str() {
        "awa" => build_awa_frame(&transformed, stride),
        "adalight" => build_adalight_frame(&transformed, stride),
        _ => return,
    };
    let _ = port.write_all(&frame);
    let _ = port.flush();
}
