# Peer Review Findings (Simulated – Different Model / Less Context)

Reviewer context: Fresh pass on ai-product-critique; no prior code review or project history.

---

## Finding 1: Example buttons don't update the text input (app.py ~163–165)

When the user clicks an example (e.g. "Figma"), the analysis correctly runs for "Figma", but the text input widget still shows whatever was there before (or empty). The code sets a local `product_input = product` only for that run; it doesn't update the widget's value, so the UI looks inconsistent.

**Severity:** LOW (UX confusion)

---

## Finding 2: `build_prompt` could raise if user input contains `{` or `}` (prompts.py ~97–99)

`OUTPUT_TEMPLATE.format(product_input=product_input, url_context=context_section)` is used. If a user types something like "Company {internal}" or "Product } name", the `.format()` call might interpret braces and throw `KeyError` or produce wrong output.

**Severity:** MEDIUM (possible crash on edge-case input)

---

## Finding 3: Logger never configured (app.py ~12–13)

`logger = logging.getLogger(__name__)` is used and `scrape_url` logs with `logger.debug(...)`. There is no `logging.basicConfig()` or other configuration, so in many environments debug logs will not appear anywhere.

**Severity:** LOW (logging may be no-op in production)

---

## Finding 4: `response.candidates[0]` could raise IndexError (app.py ~109)

After `response.text` raises `ValueError`, the code checks `if response.candidates and response.candidates[0].finish_reason`. If `response.candidates` is a non-empty list but the first candidate has no `finish_reason` attribute, or if the SDK returns a structure where the first candidate is missing, this could raise.

**Severity:** HIGH (possible unhandled exception)

---

## Finding 5: requirements.txt versions unpinned (requirements.txt)

Dependencies use minimum versions (e.g. `streamlit>=1.40.0`). A future `pip install -r requirements.txt` could pull newer minors/majors and break the app. Reproducible builds typically pin exact versions.

**Severity:** MEDIUM (build reproducibility)

---

## Finding 6: No explicit handling for empty `product_input` after strip (app.py ~88–90)

If the user submits whitespace-only input, `product_input.strip()` is empty. Then `product_input_truncated` is `""` and we still call `build_prompt("", url_context)`. The API might accept that; unclear if we should show a validation message instead.

**Severity:** LOW (edge case; might be acceptable)
