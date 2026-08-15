# Netflix Lens

An interactive Streamlit dashboard for the Netflix Movies and TV Shows dataset.

## Run locally

```bash
cd /Users/rohitk/mastering_agentic_ai/mastering_agentic_ai_projects/Week_1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run netflix_lens.py
```

Open the local address Streamlit prints in your terminal. The bundled `netflix_titles.csv` loads automatically; use **Upload Netflix CSV** to replace it.

## Included capabilities

- Date, format, content-rating, and multi-genre filtering.
- Natural-language-style keyword recommendations across title, type, maturity rating, genre, and description.
- Interactive genre distribution, Top 10 Movies/TV Shows, cast, and director views.
- A title detail panel with director, cast, rating, description, release year, poster, awards, and box-office fields.
- An OMDb enrichment workflow and enriched CSV download containing `poster_image`, `lifetime_box_office_collection`, `number_awards_won`, and `imdb_rating`.
- A persistent **My Watchlist** that saves selected Netflix title IDs locally and reuses existing data without calling OMDb.

## OMDb enrichment

Get an OMDb API key from [OMDb](https://www.omdbapi.com/apikey.aspx), then set it before starting Streamlit:

```bash
export OMDB_API_KEY="your_key_here"
streamlit run netflix_lens.py
```

Alternatively, add `OMDB_API_KEY = "your_key_here"` to `.streamlit/secrets.toml` (do not commit this file). In the dashboard sidebar, choose a small batch and select **Enrich missing titles**. OMDb is queried by title, release year, and movie/series type. It supplies the official poster URL when available, US box office for movies, IMDb star rating, award summary, and total reported award wins. The free OMDb tier has request limits, so the batch control is intentionally capped at 1,000.

The **Top 10** view uses a separate bounded workflow: it selects the 10 newest Movies and 10 newest TV Shows within the active filters, enriches only those (20 maximum), then ranks each format's candidates by IMDb stars. Failed lookups are remembered for the current session so the page does not repeatedly request them.

Every OMDb lookup is also saved locally in `omdb_enrichment_cache.csv`, including failed matches, and is restored when the app restarts. A key-specific local request counter is stored in `omdb_usage.json` and shown in the sidebar. OMDb advertises a 1,000-request daily limit for free keys, but does not publish a request-balance endpoint; therefore the “remaining” number is an estimate based only on requests made by this dashboard.

The source data does not contain these values, so the dashboard uses a poster-shaped fallback until OMDb finds a match. Award wins are OMDb's total reported wins, not country-specific “national awards”; OMDb does not expose a standardized national-award count.

Netflix's `rating` field is a maturity/advisory rating (for example, `TV-MA` or `PG-13`), not a quality rating. Once enriched, the Top 10 view ranks titles by OMDb's IMDb star rating.
