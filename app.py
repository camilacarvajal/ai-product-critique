"""AI Product Critique Tool -- Analyze any product like a senior PM."""

import ipaddress
import logging
import os
import re
import socket
from urllib.parse import urlparse

import markdown as md_lib
import streamlit as st
import google.generativeai as genai
import bleach
from dotenv import load_dotenv
from pathlib import Path

from prompts import SYSTEM_PROMPT, build_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Load .env from the app directory; override=True so .env wins over system/shell env vars
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

MAX_PRODUCT_INPUT_LENGTH = 2000

# Default product shown on first load (pre-filled in input).
DEFAULT_PRODUCT = "Example Product Breakdown"

# Header hero image URL (above title).
HEADER_IMAGE_URL = "https://cdn.pixabay.com/photo/2019/01/30/08/30/book-3964050_1280.jpg"

# Path to pre-generated default product breakdown markdown (shown on first load instead of an API call).
DEFAULT_PRODUCT_BREAKDOWN_PATH = Path(__file__).resolve().parent / "default_product_breakdown.md"

# Known product name -> canonical domain for favicon (allowlist only; no guessing).
KNOWN_PRODUCT_DOMAINS = {
    "Figma": "figma.com",
    "Notion": "notion.so",
    "Duolingo": "duolingo.com",
    "Spotify": "spotify.com",
    "ChatGPT": "openai.com",
    "Linear": "linear.app",
}

EXAMPLE_PRODUCTS = [
    "Figma",
    "Notion",
    "Duolingo",
    "Spotify",
    "ChatGPT",
    "Linear",
]

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def looks_like_url(text: str) -> bool:
    """Check if the input looks like a URL."""
    return bool(re.match(r"https?://", text.strip()))


def _is_safe_url(url: str) -> bool:
    """Return False if the URL targets localhost or private/link-local IPs (SSRF protection)."""
    try:
        parsed = urlparse(url.strip())
        host = parsed.hostname
        if not host:
            return False
        host_lower = host.lower()
        if host_lower in ("localhost", "0.0.0.0", "::", "::1"):
            return False
        if host_lower.endswith(".local"):
            return False
        # Resolve host to IP(s) and block private/loopback/link-local
        for (_, _, _, _, sockaddr) in socket.getaddrinfo(host, None):
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
                if ip.is_loopback or ip.is_private or ip.is_link_local:
                    return False
            except ValueError:
                continue
        return True
    except (socket.gaierror, OSError, ValueError):
        return False


def scrape_url(url: str) -> str | None:
    """Try to extract text content from a URL. Returns None on failure or unsafe URL."""
    if not _is_safe_url(url):
        logger.debug("scrape_url rejected unsafe URL (SSRF protection)")
        return None
    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {"User-Agent": "Mozilla/5.0 (compatible; ProductCritiqueTool/1.0)"}
        response = requests.get(
            url.strip(), headers=headers, timeout=10, allow_redirects=False
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove script and style elements
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        # Truncate to avoid hitting token limits
        max_chars = 4000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n[...truncated]"

        return text
    except Exception as e:
        logger.debug("scrape_url failed: %s", e, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Analysis display helpers
# ---------------------------------------------------------------------------

# Theme primary color for section borders (matches .streamlit/config.toml)
SECTION_BORDER_COLOR = "#E67E22"

# Google favicon API: safe, read-only; we only pass a validated domain.
FAVICON_BASE_URL = "https://www.google.com/s2/favicons"

# Allowed tags when sanitizing LLM markdown→HTML (prevents XSS).
ALLOWED_TAGS = [
    "p", "br", "strong", "em", "b", "i", "u", "code", "pre",
    "h1", "h2", "h3", "h4", "ul", "ol", "li", "a", "hr",
    "table", "thead", "tbody", "tr", "td", "th", "blockquote",
]
ALLOWED_ATTRS = {"a": ["href", "title"]}


def parse_analysis_sections(full_markdown: str) -> list[str]:
    """Split LLM analysis by ## headers so each section can be rendered in a card.

    Returns a list of markdown strings, each starting with '## Section Title'
    (or the first block as-is if it has no ##). Handles missing/different headers
    by treating the whole response as one section when no split is found.
    """
    text = full_markdown.strip()
    if not text:
        return []
    parts = re.split(r"\n## ", text, flags=re.IGNORECASE)
    sections = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        if i == 0:
            # First segment: ensure it has ## for consistent rendering
            sections.append(part if part.startswith("## ") else "## " + part)
        else:
            sections.append("## " + part)
    return sections if sections else [text]


def _section_title_and_slug(section_text: str, index: int) -> tuple[str, str]:
    """Extract display title and URL-safe slug from a section (starts with '## Title').
    Falls back to 'Section N' and 'section-N' when no ## header is found.
    """
    first_line = section_text.strip().split("\n")[0] if section_text else ""
    if first_line.startswith("## "):
        title = first_line[3:].strip()
    else:
        title = f"Section {index + 1}"
    # Slug: lowercase, replace non-alnum with single hyphen, strip leading/trailing hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or f"section-{index}"
    return title, slug


def markdown_to_safe_html(markdown_text: str) -> str:
    """Convert markdown to HTML and sanitize so it is safe for unsafe_allow_html=True."""
    html = md_lib.markdown(
        markdown_text,
        extensions=["tables", "nl2br"],
    )
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)


def get_favicon_url(product_input: str) -> str | None:
    """Return a safe favicon URL for a product name or URL.

    - For URLs: uses Google's favicon API with the validated hostname only.
    - For product names: uses KNOWN_PRODUCT_DOMAINS allowlist (e.g. 'Figma' -> figma.com).
    Returns None for unknown product names to avoid guessing domains.
    """
    raw = product_input.strip()
    # Product name: resolve via allowlist (case-insensitive)
    if not looks_like_url(raw):
        raw_lower = raw.lower()
        domain = next(
            (v for k, v in KNOWN_PRODUCT_DOMAINS.items() if k.lower() == raw_lower),
            None,
        )
        if domain:
            return f"{FAVICON_BASE_URL}?domain={domain}&sz=128"
        return None
    # URL: validate and use hostname
    if not _is_safe_url(raw):
        return None
    try:
        parsed = urlparse(raw)
        host = parsed.hostname
        if not host:
            return None
        return f"{FAVICON_BASE_URL}?domain={host}&sz=128"
    except Exception:
        return None


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def analyze_product(product_input: str, api_key: str) -> str:
    """Call Gemini to analyze the product. Caller must configure genai with api_key before calling."""
    # Check if URL and try to scrape
    url_context = ""
    if looks_like_url(product_input):
        with st.spinner("Reading webpage..."):
            scraped = scrape_url(product_input)
            if scraped:
                url_context = scraped
                st.caption("Webpage content loaded successfully.")
            else:
                st.caption("Couldn't read the webpage. Using AI knowledge instead.")

    product_input_truncated = product_input.strip()[:MAX_PRODUCT_INPUT_LENGTH]
    if len(product_input.strip()) > MAX_PRODUCT_INPUT_LENGTH:
        product_input_truncated += "\n[...truncated]"
    prompt = build_prompt(product_input_truncated, url_context)

    # Use gemini-2.5-flash (available on free tier; 1.5-flash variants returned 404 for this API)
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=SYSTEM_PROMPT,
    )

    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.7,
            max_output_tokens=4096,
        ),
    )

    try:
        return response.text
    except ValueError:
        if response.candidates and response.candidates[0].finish_reason:
            reason = str(response.candidates[0].finish_reason)
            if "SAFETY" in reason.upper() or "BLOCK" in reason.upper():
                raise ValueError(
                    "The model didn't return text (response was blocked by safety filters). "
                    "Try a different product or wording."
                )
        raise ValueError(
            "The model didn't return text. Try a different product or try again."
        )


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------


def main():
    st.set_page_config(
        page_title="AI Product Critique",
        page_icon="🔍",
        layout="centered",
    )

    # --- Header: hero image + title + tagline (full width of main container) ---
    # Use <img> so the browser loads the image (Pixabay often blocks server-side fetches).
    st.markdown(
        f'<img src="{HEADER_IMAGE_URL}" alt="Header" '
        'style="width:100%; max-height:280px; object-fit:cover; border-radius:8px;">',
        unsafe_allow_html=True,
    )
    st.title("AI Product Critique")
    st.markdown(
        "Analyze any product like a senior PM. Get a structured breakdown "
        "of what it does, what's working, what's not, and how to talk about it "
        "in an interview -- in 30 seconds."
    )

    # --- API Key ---
    api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()

    # Allow override via Streamlit secrets (for deployed version)
    if not api_key and hasattr(st, "secrets") and "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]

    # If still no key, let the user paste one
    if not api_key:
        api_key = st.text_input(
            "Google AI API Key",
            type="password",
            help="Get a free key at https://ai.google.dev",
        )

    if not api_key:
        st.info(
            "Enter your Google AI API key above to get started. "
            "[Get a free key here.](https://ai.google.dev)"
        )

    # --- Input ---
    st.divider()

    # Transfer example-button choice into widget key before widget exists (Streamlit forbids
    # writing to a key after its widget is created). Next run the input will show that product.
    if "pending_product" in st.session_state:
        st.session_state["product_input"] = st.session_state.pop("pending_product")
    if "product_input" not in st.session_state:
        st.session_state["product_input"] = DEFAULT_PRODUCT

    col1, col2 = st.columns([3, 1])

    with col1:
        product_input = st.text_input(
            "Product name or URL",
            placeholder="e.g. Figma, Notion, https://linear.app",
            key="product_input",
        )

    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        analyze_clicked = st.button("Analyze", type="primary", use_container_width=True)

    # --- Quick examples ---
    st.markdown("**Try an example:**")
    example_cols = st.columns(len(EXAMPLE_PRODUCTS))
    for i, product in enumerate(EXAMPLE_PRODUCTS):
        with example_cols[i]:
            if st.button(product, key=f"example_{product}", use_container_width=True):
                st.session_state["pending_product"] = product
                analyze_clicked = True

    # Use clicked example for this run if any; otherwise use text input value.
    product_to_analyze = st.session_state.get("pending_product") or product_input

    # --- Default product content: on first load, show pre-provided breakdown markdown if available (no API call) ---
    if (
        "last_result" not in st.session_state
        and product_input == DEFAULT_PRODUCT
        and not st.session_state.get("default_breakdown_loaded")
    ):
        st.session_state["default_breakdown_loaded"] = True
        default_md = ""
        if DEFAULT_PRODUCT_BREAKDOWN_PATH.is_file():
            try:
                default_md = DEFAULT_PRODUCT_BREAKDOWN_PATH.read_text(encoding="utf-8").strip()
            except Exception as e:
                logger.debug("Could not load default product breakdown: %s", e)
        if default_md:
            st.session_state["last_result"] = default_md
            st.session_state["last_product"] = DEFAULT_PRODUCT
        # If no file or empty, user can click Analyze to run an analysis.

    # --- Analysis ---
    st.divider()

    if analyze_clicked and product_to_analyze:
        if not api_key:
            st.error(
                "Enter your Google AI API key above to run an analysis. "
                "[Get a free key here.](https://ai.google.dev)"
            )
        else:
            with st.spinner("Analyzing product... this takes about 15-30 seconds."):
                try:
                    genai.configure(api_key=api_key)
                    result = analyze_product(product_to_analyze, api_key)
                    st.session_state["last_result"] = result
                    st.session_state["last_product"] = product_to_analyze
                except Exception as e:
                    error_msg = str(e)
                    if "API_KEY" in error_msg.upper() or "403" in error_msg:
                        st.error(
                            "Invalid API key. Please check your Google AI API key "
                            "and try again. [Get a free key here.](https://ai.google.dev)"
                        )
                    elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg.upper() or "quota" in error_msg.lower():
                        st.error(
                            "Rate limit or quota hit. The free tier has limits per minute. "
                            "Wait 60 seconds and try again. If you only made one request, "
                            "Google sometimes returns this on cold start — retry once."
                        )
                        st.code(error_msg, language=None)
                    else:
                        st.error(f"Something went wrong: {error_msg}")
                    st.stop()

    # Display results (persists across reruns)
    if "last_result" in st.session_state:
        last_product = st.session_state["last_product"]
        last_result = st.session_state["last_result"]

        # Analysis header: optional favicon (URL input only) + title
        favicon_url = get_favicon_url(last_product)
        if favicon_url:
            col_logo, col_title = st.columns([1, 20])
            with col_logo:
                try:
                    st.image(favicon_url, width=40)
                except Exception as e:
                    logger.debug("Favicon load failed: %s", e)
                    # Fallback: no logo, title still shown
            with col_title:
                st.markdown(f"### Analysis: {last_product}")
        else:
            st.markdown(f"### Analysis: {last_product}")

        # Inject CSS once for section cards and index (we control the class, so styling is reliable)
        st.markdown(
            f"""
            <style>
            .analysis-section-card {{
                border-left: 4px solid {SECTION_BORDER_COLOR};
                padding: 1rem 1.5rem;
                margin: 1.25rem 0;
                border-radius: 0 8px 8px 0;
                background-color: rgba(255,255,255,0.05);
            }}
            .analysis-index {{
                margin-bottom: 1rem;
                padding: 0.75rem 1rem;
                background-color: rgba(255,255,255,0.05);
                border-radius: 8px;
            }}
            .analysis-index a {{ color: #E67E22; text-decoration: none; }}
            .analysis-index a:hover {{ text-decoration: underline; }}
            </style>
            """,
            unsafe_allow_html=True,
        )
        sections = parse_analysis_sections(last_result)
        # Build index: list of (title, slug, index) for anchor links; index ensures unique IDs
        index_items = [(*_section_title_and_slug(sec, i), i) for i, sec in enumerate(sections)]
        # Render clickable index (jump to section by id)
        index_links = " · ".join(
            f'<a href="#section-{slug}-{i}">{title}</a>' for title, slug, i in index_items
        )
        st.markdown(
            f'<div class="analysis-index"><strong>Jump to:</strong> {index_links}</div>',
            unsafe_allow_html=True,
        )
        # Render each section in its own card with unique id for in-page links
        for i, section_text in enumerate(sections):
            _, slug = _section_title_and_slug(section_text, i)
            safe_html = markdown_to_safe_html(section_text)
            st.markdown(
                f'<div id="section-{slug}-{i}" class="analysis-section-card">{safe_html}</div>',
                unsafe_allow_html=True,
            )

    # --- Footer ---
    st.divider()
    st.caption(
        "Built by [Camila](https://www.linkedin.com/in/camilacarvajal/) | "
        "Powered by Google Gemini | "
        "[GitHub](https://github.com/camilacarvajal/ai-product-critique)"
    )


if __name__ == "__main__":
    main()
