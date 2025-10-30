/// Build Adalight protocol frame
pub fn build_adalight_frame(pixel_data: &[u8], stride: usize) -> Vec<u8> {
    let led_count = pixel_data.len() / stride;
    
    // Adalight header: 'Ada' + LED count high + LED count low + checksum
    let count_hi = (led_count >> 8) as u8 & 0xFF;
    let count_lo = led_count as u8 & 0xFF;
    let checksum = count_hi ^ count_lo ^ 0x55;
    
    let mut frame = Vec::with_capacity(6 + pixel_data.len());
    
    // Header
    frame.extend_from_slice(&[0x41, 0x64, 0x61]); // 'Ada'
    frame.push(count_hi);
    frame.push(count_lo);
    frame.push(checksum);
    
    // Pixel data
    frame.extend_from_slice(pixel_data);
    
    frame
}
