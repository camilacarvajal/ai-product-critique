# Changelog

## Unreleased

### Added
- Default product breakdown (explanation of output sections) shown on first load without requiring an API key.
- Jump-to-section index with unique anchors (`section-{slug}-{index}`) so in-page links work even when titles normalize to the same slug.

### Changed
- API key required only when user clicks **Analyze**; app and default content load without a key.
- Default content file: `default_figma_analysis.md` → `default_product_breakdown.md`; constant `DEFAULT_PRODUCT_BREAKDOWN_PATH`.
- Default product label: `DEFAULT_PRODUCT = "Example Product Breakdown"`.
- Genai client configured once in `main()` when running analysis (no longer inside `analyze_product()`).
- Favicon lookup for known products is case-insensitive (e.g. "figma" and "Figma" both resolve).

### Fixed
- Favicon load failures and default markdown read failures now logged with `logger.debug` instead of silent pass.
- Section IDs made unique to avoid duplicate anchors when section titles normalize to the same slug.

### Security
- No change. (SSRF, XSS sanitization, and secrets handling unchanged.)
