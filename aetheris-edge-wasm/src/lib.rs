#[no_mangle]
pub extern "C" fn z_score_from_stats(sum: f64, sum_sq: f64, count: u32, amount: f64) -> f64 {
    if count < 5 {
        return 0.0;
    }

    let n = count as f64;
    let mean = sum / n;
    let variance = (sum_sq / n) - (mean * mean);

    if !variance.is_finite() || variance <= 0.0 {
        return 0.0;
    }

    let std_dev = variance.sqrt();
    let z = (amount - mean) / std_dev;

    if z.is_finite() {
        z
    } else {
        0.0
    }
}

#[cfg(test)]
mod tests {
    use super::z_score_from_stats;

    #[test]
    fn returns_zero_for_small_windows() {
        let z = z_score_from_stats(100.0, 2000.0, 4, 10.0);
        assert_eq!(z, 0.0);
    }

    #[test]
    fn computes_expected_value() {
        // values: [10, 20, 30, 40, 50], next=60
        let z = z_score_from_stats(150.0, 5500.0, 5, 60.0);
        assert!(z > 2.0);
    }
}
