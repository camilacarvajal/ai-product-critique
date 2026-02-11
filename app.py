"""AI Product Critique Tool -- Analyze any product like a senior PM."""

import ipaddress
import logging
import os
import re
import socket
from urllib.parse import urlparse

import streamlit as st
import google.generativeai as genai
from dotenv import load_dotenv

from prompts import SYSTEM_PROMPT, build_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

MAX_PRODUCT_INPUT_LENGTH = 2000

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
# LLM call
# ---------------------------------------------------------------------------

def analyze_product(product_input: str, api_key: str) -> str:
    """Call Gemini to analyze the product."""
    genai.configure(api_key=api_key)

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
        layout="wide",
    )

    # --- Header ---
    st.title("AI Product Critique")
    st.markdown(
        "Analyze any product like a senior PM. Get a structured breakdown "
        "of what it does, what's working, what's not, and how to talk about it "
        "in an interview -- in 30 seconds."
    )

    # --- API Key ---
    api_key = os.getenv("GOOGLE_API_KEY", "")

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
        st.stop()

    # --- Input ---
    st.divider()

    col1, col2 = st.columns([3, 1])

    with col1:
        product_input = st.text_input(
            "Product name or URL",
            placeholder="e.g. Figma, Notion, https://linear.app",
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
                product_input = product
                analyze_clicked = True

    # --- Analysis ---
    st.divider()

    if analyze_clicked and product_input:
        with st.spinner("Analyzing product... this takes about 15-30 seconds."):
            try:
                result = analyze_product(product_input, api_key)
                st.session_state["last_result"] = result
                st.session_state["last_product"] = product_input
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
        st.markdown(f"### Analysis: {st.session_state['last_product']}")
        st.markdown(st.session_state["last_result"])

    # --- Footer ---
    st.divider()
    st.caption(
        "Built by [Camila](https://www.linkedin.com/in/camilacarvajal/) | "
        "Powered by Google Gemini | "
        "[GitHub](https://github.com/camilacarvajal/ai-product-critique)"
    )


if __name__ == "__main__":
    main()
