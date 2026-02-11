# Code Review: AI Product Critique

## Looks Good

- **Secrets:** API key comes from env / Streamlit secrets; `.env` is in `.gitignore`. No hardcoded keys.
- **Error handling:** Centralized try/except in main flow with specific handling for 403, 429, and generic errors. User-facing messages are clear.
- **Input:** URL vs product name is handled; scraping has a timeout and truncation to avoid token overflow.
- **Types:** Function signatures use type hints (`str`, `str | None`). No `any`-style abuse.
- **Structure:** Clear separation (prompts in `prompts.py`, app logic in `app.py`), config at top.
- **Dependencies:** Pinned in `requirements.txt`; no stray debug deps.

---

## Issues Found

### **[HIGH]** [app.py:98](app.py) — Unhandled blocked or non-text Gemini response

- **Issue:** `return response.text` can raise `ValueError` when the model returns no text (e.g. safety block, or non-simple response). That exception is not caught in `analyze_product`, so the user sees a raw traceback.
- **Fix:** Before returning, check that there is text to return (e.g. `response.candidates` and `response.parts`), or wrap `response.text` in try/except and return a clear message like: "The model didn't return text (e.g. blocked by safety filters). Try a different product or wording."

### **[MEDIUM]** [app.py:58](app.py) — Bare `except Exception` in `scrape_url`

- **Issue:** All exceptions are swallowed with no logging. Failures (timeout, DNS, 403, etc.) are invisible; we only see "Couldn't read the webpage."
- **Fix:** Either log the exception (e.g. with a logger and `logger.debug(exc)` or re-raise after setting a flag) or at least capture and pass through a short reason for optional UI feedback. Prefer logging so production debugging is possible without exposing internals to the user.

### **[MEDIUM]** [app.py:151-152](app.py) — No input length limit

- **Issue:** `product_input` and (after scrape) `url_context` are sent to the model with no cap. Very long paste or scraped page could exceed model context or cause slow/expensive calls.
- **Fix:** Truncate `product_input` (e.g. first 2000 chars) before building the prompt, and rely on existing `url_context` truncation (4000 chars) so total prompt size is bounded.

### **[LOW]** [app.py:201-203](app.py) — Placeholder links in footer

- **Issue:** `YOUR-LINKEDIN` and `YOUR-GITHUB` are placeholders. Deployed app would show broken or dummy links.
- **Fix:** Replace with real LinkedIn profile URL and GitHub repo URL (or remove the links until they exist).

### **[LOW]** [prompts.py:89-96](prompts.py) — Possible prompt injection via `product_input` / `url_context`

- **Issue:** User-controlled `product_input` and `url_context` are interpolated into the prompt. A malicious user could try to override instructions (e.g. "ignore previous instructions").
- **Fix:** For a small public tool this may be acceptable. If you want to harden: sanitize or escape newlines/backslashes in user input, or put user content in a clearly delimited block and instruct the model to treat everything in that block as data only.

---

## Summary

- **Files reviewed:** 2 (`app.py`, `prompts.py`), plus `.gitignore`, `requirements.txt`.
- **Critical issues:** 0
- **High:** 1 (unhandled `response.text` when Gemini returns no text / blocked).
- **Medium:** 2 (scrape exception swallowing, no input length limit).
- **Low:** 2 (footer placeholders, prompt injection).

Recommend addressing the HIGH and MEDIUM items before treating the app as production-ready; LOW can be done as polish.
