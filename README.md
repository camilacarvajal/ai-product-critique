# AI Product Critique

Analyze any product like a senior PM. Get a structured breakdown of what it does, what's working, what's not, and how to talk about it in an interview -- in 30 seconds.

**[Try the live app](https://your-app-name.streamlit.app)** (link updated after deployment)

---

## The Problem

Product managers constantly need to quickly understand products -- for interview prep, competitive analysis, or sharpening their product sense. But assembling this information is scattered across Google, Glassdoor, company blogs, and analyst reports. It takes 1-2 hours to build a solid picture of a single product.

## The Insight

A structured product analysis follows a predictable framework: what it does, who it's for, how it competes, what's working, what isn't, and what you'd measure. An LLM can generate this framework in seconds, giving you a strong starting point that would take hours to assemble manually.

## The Solution

One input. One click. Six sections of structured analysis:

1. **Product Overview** -- What it does, who it's for, business model
2. **Competitive Landscape** -- Competitors, moat, market position
3. **Product Strengths** -- 3 specific things working well
4. **Areas for Improvement** -- 3 specific things to fix
5. **Key Metrics** -- What to measure and why
6. **Interview Prep** -- Smart questions to ask if interviewing at this company

Supports both product names (uses AI knowledge) and URLs (scrapes the page for additional context).

## What I'd Measure

- **Output quality:** User ratings on analysis accuracy (thumbs up/down)
- **Repeat usage:** Do people come back to analyze more products?
- **Time saved:** Compared to manual research (survey)
- **Most-analyzed products:** Reveals what people are interviewing for

## What's Next

- Save and compare analyses side by side
- Export to PDF for interview prep binders
- "Practice mode" -- write your own product critique, then compare to the AI's
- Historical data integration (funding rounds, user growth, recent news)

---

## Tech Stack

- **Frontend:** Streamlit
- **LLM:** Google Gemini 2.5 Flash (free tier)
- **Scraping:** BeautifulSoup (for URL inputs)
- **Hosting:** Streamlit Community Cloud (free)

## Run Locally

```bash
# Clone the repo
git clone https://github.com/camilacarvajal/ai-product-critique.git
cd ai-product-critique

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Add your API key
cp .env.example .env
# Edit .env and add your Google AI API key (free at https://ai.google.dev)

# Run the app
streamlit run app.py
```

## About

Built by [Camila](https://www.linkedin.com/in/camilacarvajal/) -- AI Product Manager, ex-engineer, building products that help people use AI more effectively. Currently pursuing an M.S. in AI at UT Austin.

This tool was built in one day as a portfolio project and a practical tool for PM interview prep. The goal was to demonstrate product sense through the product itself: identifying a real problem, designing a focused solution, and thinking about what to measure and what to build next.
