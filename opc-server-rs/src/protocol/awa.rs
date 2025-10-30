/// Build AWA protocol frame (HyperSerialPico format)
pub fn build_awa_frame(pixel_data: &[u8], stride: usize) -> Vec<u8> {
    let led_count = pixel_data.len() / stride;
    
    // AWA header: 'Awa' + LED count high + LED count low + CRC
    let count_hi = ((led_count - 1) >> 8) as u8 & 0xFF;
    let count_lo = (led_count - 1) as u8 & 0xFF;
    let crc = (count_hi ^ count_lo) ^ 0x55;
    
    let mut frame = Vec::with_capacity(6 + pixel_data.len() + 3);
    
    // Header
    frame.extend_from_slice(&[0x41, 0x77, 0x61]); // 'Awa'
    frame.push(count_hi);
    frame.push(count_lo);
    frame.push(crc);
    
    // Pixel data
    frame.extend_from_slice(pixel_data);
    
    // Calculate Fletcher checksums (matches HyperSerialPico implementation)
    let mut fletcher1: u16 = 0;
    let mut fletcher2: u16 = 0;
    let mut fletcher_ext: u16 = 0;
    let mut position: u16 = 0;
    
    for &byte in pixel_data {
        fletcher1 = (fletcher1 + byte as u16) % 255;
        fletcher2 = (fletcher2 + fletcher1) % 255;
        fletcher_ext = (fletcher_ext + ((byte as u16) ^ position)) % 255;
        position += 1;
    }
    
    // Special case: if fletcher_ext is 0x41 ('A'), use 0xaa instead
    if fletcher_ext == 0x41 {
        fletcher_ext = 0xaa;
    }
    
    // Checksums
    frame.push(fletcher1 as u8);
    frame.push(fletcher2 as u8);
    frame.push(fletcher_ext as u8);
    
    frame
}
