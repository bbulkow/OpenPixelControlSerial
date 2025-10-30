/// Pixel format transformation
pub fn transform_pixels(data: Vec<u8>, format: Option<&str>) -> Vec<u8> {
    match format {
        None | Some("RGB") => data, // No transformation needed
        Some("GRB") => transform_grb(data),
        Some("BGR") => transform_bgr(data),
        Some("RGBW") => transform_rgbw(data),
        Some("GRBW") => transform_grbw(data),
        _ => data, // Unknown format, passthrough
    }
}

/// Transform RGB to GRB (swap R and G channels in-place)
fn transform_grb(mut data: Vec<u8>) -> Vec<u8> {
    let pixel_count = data.len() / 3;
    
    for i in 0..pixel_count {
        let idx = i * 3;
        data.swap(idx, idx + 1); // Swap R and G
    }
    
    data
}

/// Transform RGB to BGR (swap R and B channels in-place)
fn transform_bgr(mut data: Vec<u8>) -> Vec<u8> {
    let pixel_count = data.len() / 3;
    
    for i in 0..pixel_count {
        let idx = i * 3;
        data.swap(idx, idx + 2); // Swap R and B
    }
    
    data
}

/// Transform RGB to RGBW (extract white channel)
fn transform_rgbw(data: Vec<u8>) -> Vec<u8> {
    let pixel_count = data.len() / 3;
    let mut result = Vec::with_capacity(pixel_count * 4);
    
    for i in 0..pixel_count {
        let idx = i * 3;
        let r = data[idx];
        let g = data[idx + 1];
        let b = data[idx + 2];
        
        // Extract white channel as minimum of RGB
        let w = r.min(g).min(b);
        
        // Subtract white from RGB channels
        result.push(r - w);
        result.push(g - w);
        result.push(b - w);
        result.push(w);
    }
    
    result
}

/// Transform RGB to GRBW (extract white channel, swap R and G)
fn transform_grbw(data: Vec<u8>) -> Vec<u8> {
    let pixel_count = data.len() / 3;
    let mut result = Vec::with_capacity(pixel_count * 4);
    
    for i in 0..pixel_count {
        let idx = i * 3;
        let r = data[idx];
        let g = data[idx + 1];
        let b = data[idx + 2];
        
        // Extract white channel as minimum of RGB
        let w = r.min(g).min(b);
        
        // Subtract white from RGB channels, then arrange as GRBW
        result.push(g - w);
        result.push(r - w);
        result.push(b - w);
        result.push(w);
    }
    
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rgb_passthrough() {
        let data = vec![255, 0, 0, 0, 255, 0, 0, 0, 255];
        let result = transform_pixels(data.clone(), Some("RGB"));
        assert_eq!(result, data);
    }

    #[test]
    fn test_grb_transform() {
        let data = vec![255, 0, 0]; // Red in RGB
        let result = transform_pixels(data, Some("GRB"));
        assert_eq!(&result[..], &[0, 255, 0]); // Should be red in GRB
    }

    #[test]
    fn test_bgr_transform() {
        let data = vec![255, 0, 0]; // Red in RGB
        let result = transform_pixels(data, Some("BGR"));
        assert_eq!(&result[..], &[0, 0, 255]); // Should be red in BGR
    }

    #[test]
    fn test_rgbw_transform() {
        let data = vec![255, 255, 255]; // White
        let result = transform_pixels(data, Some("RGBW"));
        assert_eq!(&result[..], &[0, 0, 0, 255]); // Should extract white
        
        let data = vec![255, 128, 128]; // Pink
        let result = transform_pixels(data, Some("RGBW"));
        assert_eq!(&result[..], &[127, 0, 0, 128]); // Red + white
    }

    #[test]
    fn test_grbw_transform() {
        let data = vec![255, 255, 255]; // White
        let result = transform_pixels(data, Some("GRBW"));
        assert_eq!(&result[..], &[0, 0, 0, 255]); // Should extract white
        
        let data = vec![255, 0, 0]; // Red in RGB
        let result = transform_pixels(data, Some("GRBW"));
        assert_eq!(&result[..], &[0, 255, 0, 0]); // Red in GRBW format
    }
}
