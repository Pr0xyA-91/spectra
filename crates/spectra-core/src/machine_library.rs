//! Machine Library Matching & Offset Resolution Primitives for SPECTRA.

/// Normalizes an EF hardware code into uppercase trimmed form.
#[inline]
pub fn normalize_ef_code(code: &str) -> String {
    code.trim().to_uppercase()
}

/// Checks whether a catalog machine entry matches the active connected hardware identity
/// via EF firmware family code, commercial/domestic article number, or fuzzy model substring.
pub fn matches_connected_machine(
    ef_code: &str,
    article_numbers: &[String],
    model_family: &str,
    detected_ef: &str,
    detected_art: &str,
    detected_model: &str,
) -> bool {
    let det_ef = normalize_ef_code(detected_ef);
    let det_art = detected_art.trim();
    let det_model = detected_model.trim().to_lowercase();

    if !det_ef.is_empty() && normalize_ef_code(ef_code) == det_ef {
        return true;
    }
    if !det_art.is_empty() && article_numbers.iter().any(|a| a.trim() == det_art) {
        return true;
    }
    if !det_model.is_empty() && !model_family.trim().is_empty() {
        let mf = model_family.trim().to_lowercase();
        if mf == det_model || mf.contains(&det_model) || det_model.contains(&mf) {
            return true;
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_machine_matching_logic() {
        let arts = vec!["15141".to_string(), "15420".to_string()];
        assert!(matches_connected_machine(
            "EF535M",
            &arts,
            "Jura WE8",
            " ef535m ",
            "",
            ""
        ));
        assert!(matches_connected_machine(
            "EF535M",
            &arts,
            "Jura WE8",
            "",
            "15420",
            ""
        ));
        assert!(matches_connected_machine(
            "EF535M",
            &arts,
            "WE8",
            "",
            "",
            "Jura WE8 Chrome"
        ));
        assert!(!matches_connected_machine(
            "EF535M",
            &arts,
            "WE8",
            "EF518M",
            "15084",
            "Impressa XJ5"
        ));
    }
}
