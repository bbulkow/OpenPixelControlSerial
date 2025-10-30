use anyhow::{Context, Result};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc::{self, SyncSender, Receiver, TrySendError};
use std::thread;
use std::time::Duration;
use serialport::SerialPort;

use crate::config::OutputConfig;
use crate::pixel_format::transform_pixels;
use crate::protocol::{build_awa_frame, build_adalight_frame};

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
        // Open serial port with explicit settings to match Python's pyserial defaults
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
        
        // Set DTR and RTS to match Python's pyserial defaults (both true)
        // This is critical - some devices won't respond without these set
        if let Err(e) = port.write_data_terminal_ready(true) {
            eprintln!("Warning: Failed to set DTR on {}: {}", config.port, e);
        }
        if let Err(e) = port.write_request_to_send(true) {
            eprintln!("Warning: Failed to set RTS on {}: {}", config.port, e);
        }
        
        // Allow device to initialize (critical for Arduino-based devices that reset on DTR toggle)
        thread::sleep(Duration::from_millis(100));
        
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
