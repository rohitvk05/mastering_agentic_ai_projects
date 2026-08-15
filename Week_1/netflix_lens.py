"""Netflix Lens — an interactive explorer for the Netflix titles CSV.

Run with: streamlit run netflix_lens.py
"""

from __future__ import annotations

import os
import re
import json
import hashlib
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import requests
import streamlit as st


st.set_page_config(page_title="Netflix Lens", page_icon="🎬", layout="wide")

DATA_PATH = Path(__file__).with_name("netflix_titles.csv")
CACHE_PATH = Path(__file__).with_name("omdb_enrichment_cache.csv")
USAGE_PATH = Path(__file__).with_name("omdb_usage.json")
WATCHLIST_PATH = Path(__file__).with_name("my_watchlist.csv")
REQUIRED_COLUMNS = {
    "show_id", "type", "title", "director", "cast", "date_added",
    "release_year", "rating", "duration", "listed_in", "description",
}

# This ranks the *content advisory* field supplied by Netflix. It is not a
# critic/audience score; replace it with a real numeric score if one is added.
RATING_ORDER = {
    "G": 1, "TV-Y": 1, "TV-Y7": 2, "TV-G": 2, "TV-Y7-FV": 2,
    "PG": 3, "TV-PG": 3, "PG-13": 4, "TV-14": 4, "R": 5,
    "NC-17": 6, "TV-MA": 6, "NR": 0, "UR": 0,
}

CACHE_COLUMNS = [
    "show_id", "poster_image", "lifetime_box_office_collection", "number_awards_won",
    "imdb_rating", "awards_summary", "imdb_id", "omdb_lookup_attempted",
]


def poster_url(title: str) -> str:
    """A reliable poster-shaped fallback for every title, without an API key."""
    return f"https://placehold.co/420x630/17172a/f5c96b?text={quote(title)}"


def omdb_api_key() -> str | None:
    """Read the key without placing secrets in source code or uploaded CSVs."""
    try:
        return os.getenv("OMDB_API_KEY") or st.secrets.get("OMDB_API_KEY")
    except FileNotFoundError:
        return os.getenv("OMDB_API_KEY")


def omdb_daily_limit() -> int:
    """Use the free-tier limit unless an account-specific limit is configured."""
    try:
        configured = os.getenv("OMDB_DAILY_LIMIT") or st.secrets.get("OMDB_DAILY_LIMIT", 1000)
    except FileNotFoundError:
        configured = os.getenv("OMDB_DAILY_LIMIT", 1000)
    return int(configured)


def key_fingerprint(api_key: str) -> str:
    """Track usage per key without writing the API key to disk."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]


def omdb_usage_today(api_key: str) -> int:
    if not USAGE_PATH.exists():
        return 0
    try:
        usage = json.loads(USAGE_PATH.read_text())
        if usage.get("date") != date.today().isoformat():
            return 0
        return int(usage.get("requests", {}).get(key_fingerprint(api_key), 0))
    except (OSError, ValueError, TypeError):
        return 0


def record_omdb_request(api_key: str) -> None:
    """Store a local, per-key daily count for calls made by this dashboard."""
    today = date.today().isoformat()
    try:
        usage = json.loads(USAGE_PATH.read_text()) if USAGE_PATH.exists() else {}
    except (OSError, ValueError):
        usage = {}
    if usage.get("date") != today:
        usage = {"date": today, "requests": {}}
    fingerprint = key_fingerprint(api_key)
    usage["requests"][fingerprint] = int(usage["requests"].get(fingerprint, 0)) + 1
    USAGE_PATH.write_text(json.dumps(usage, indent=2))


def apply_enrichment_cache(data: pd.DataFrame) -> pd.DataFrame:
    """Restore prior OMDb values by Netflix show ID before making any API call."""
    if not CACHE_PATH.exists():
        return data
    try:
        cache = pd.read_csv(CACHE_PATH, dtype={"show_id": str}).drop_duplicates("show_id", keep="last").set_index("show_id")
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return data
    restored = data.copy()
    for column in CACHE_COLUMNS[1:]:
        if column not in cache.columns or column not in restored.columns:
            continue
        cached = restored["show_id"].map(cache[column])
        if column == "omdb_lookup_attempted":
            cached_attempts = cached.fillna(False).astype(str).str.lower().isin(["true", "1"])
            restored[column] = restored[column] | cached_attempts
        else:
            restored.loc[cached.notna(), column] = cached[cached.notna()]
    return restored


def save_enrichment_cache(data: pd.DataFrame) -> None:
    """Persist values and failed lookups so restarting the app does not re-query OMDb."""
    rows = data[data["omdb_lookup_attempted"]][CACHE_COLUMNS].copy()
    if rows.empty:
        return
    try:
        existing = pd.read_csv(CACHE_PATH, dtype={"show_id": str}) if CACHE_PATH.exists() else pd.DataFrame(columns=CACHE_COLUMNS)
        pd.concat([existing, rows], ignore_index=True).drop_duplicates("show_id", keep="last").to_csv(CACHE_PATH, index=False)
    except OSError:
        pass


def load_watchlist() -> set[str]:
    """Load saved Netflix IDs; the watchlist never stores or fetches OMDb data."""
    if not WATCHLIST_PATH.exists():
        return set()
    try:
        saved = pd.read_csv(WATCHLIST_PATH, dtype={"show_id": str})
        return set(saved.get("show_id", pd.Series(dtype=str)).dropna())
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return set()


def persist_watchlist(show_ids: set[str]) -> None:
    try:
        pd.DataFrame({"show_id": sorted(show_ids)}).to_csv(WATCHLIST_PATH, index=False)
    except OSError:
        pass


def add_to_watchlist(show_id: str) -> None:
    saved = st.session_state.setdefault("watchlist_ids", load_watchlist())
    saved.add(show_id)
    persist_watchlist(saved)


def remove_from_watchlist(show_id: str) -> None:
    saved = st.session_state.setdefault("watchlist_ids", load_watchlist())
    saved.discard(show_id)
    persist_watchlist(saved)


def award_wins(awards: str) -> int:
    """OMDb returns prose such as '31 wins & 54 nominations.'"""
    match = re.search(r"(\d+)\s+wins?", awards or "", flags=re.IGNORECASE)
    return int(match.group(1)) if match else 0


def fetch_omdb_enrichment(item: pd.Series, api_key: str) -> dict | None:
    """Fetch by title, year and media type to reduce false matches."""
    params = {"apikey": api_key, "t": item.title}
    if pd.notna(item.release_year):
        params["y"] = int(item.release_year)
    if item.type == "Movie":
        params["type"] = "movie"
    elif item.type == "TV Show":
        params["type"] = "series"
    try:
        record_omdb_request(api_key)
        response = requests.get("https://www.omdbapi.com/", params=params, timeout=15)
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError):
        return None
    if result.get("Response") != "True":
        return None
    return {
        "poster_image": result.get("Poster") if result.get("Poster") not in (None, "N/A") else item.poster_image,
        "lifetime_box_office_collection": result.get("BoxOffice") if item.type == "Movie" and result.get("BoxOffice") not in (None, "N/A") else item.lifetime_box_office_collection,
        "number_awards_won": award_wins(result.get("Awards", "")),
        "imdb_rating": pd.to_numeric(result.get("imdbRating"), errors="coerce"),
        "awards_summary": result.get("Awards", "Not available"),
        "imdb_id": result.get("imdbID", ""),
    }


def enrich_with_omdb(
    data: pd.DataFrame,
    api_key: str,
    maximum: int,
    progress_bar,
    candidate_ids: set[str] | None = None,
    only_unattempted: bool = False,
) -> tuple[pd.DataFrame, int]:
    """Enrich missing rows, optionally restricting calls to a candidate set."""
    enriched = data.copy()
    pending = enriched[enriched["imdb_rating"].isna()]
    if candidate_ids is not None:
        pending = pending[pending["show_id"].isin(candidate_ids)]
    if only_unattempted:
        pending = pending[~pending["omdb_lookup_attempted"]]
    pending = pending.head(maximum)
    found = 0
    for position, (index, item) in enumerate(pending.iterrows(), start=1):
        values = fetch_omdb_enrichment(item, api_key)
        enriched.at[index, "omdb_lookup_attempted"] = True
        if values:
            for column, value in values.items():
                enriched.at[index, column] = value
            found += 1
        progress_bar.progress(position / len(pending), text=f"Checking OMDb: {position}/{len(pending)} titles")
    save_enrichment_cache(enriched)
    return enriched, found


def prepare_data(source) -> pd.DataFrame:
    df = pd.read_csv(source)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))

    df = df.copy()
    df["date_added"] = pd.to_datetime(df["date_added"], errors="coerce")
    df["release_year"] = pd.to_numeric(df["release_year"], errors="coerce").astype("Int64")
    for column in ["title", "director", "cast", "rating", "listed_in", "description", "duration", "type"]:
        df[column] = df[column].fillna("").astype(str)

    # Enrichment columns are preserved when supplied in a subsequent CSV.
    # Placeholder poster URLs ensure that every title is immediately visual.
    if "poster_image" not in df:
        df["poster_image"] = df["title"].map(poster_url)
    else:
        df["poster_image"] = df["poster_image"].fillna("")
        df.loc[df["poster_image"].eq(""), "poster_image"] = df.loc[df["poster_image"].eq(""), "title"].map(poster_url)
    if "lifetime_box_office_collection" not in df:
        df["lifetime_box_office_collection"] = pd.NA
    df.loc[df["type"].str.lower() != "movie", "lifetime_box_office_collection"] = pd.NA
    if "number_awards_won" not in df:
        # Preserve values from the earlier prototype column if it is present.
        df["number_awards_won"] = df.get("national_awards_won", 0)
    df["number_awards_won"] = pd.to_numeric(df["number_awards_won"], errors="coerce").fillna(0).astype(int)
    if "imdb_rating" not in df:
        df["imdb_rating"] = pd.NA
    df["imdb_rating"] = pd.to_numeric(df["imdb_rating"], errors="coerce")
    if "awards_summary" not in df:
        df["awards_summary"] = "Not enriched"
    if "imdb_id" not in df:
        df["imdb_id"] = ""
    if "omdb_lookup_attempted" not in df:
        df["omdb_lookup_attempted"] = False
    df["omdb_lookup_attempted"] = df["omdb_lookup_attempted"].fillna(False).astype(bool)
    df["rating_rank"] = df["rating"].str.upper().map(RATING_ORDER).fillna(0)
    return df


def split_people(data: pd.DataFrame, column: str) -> pd.DataFrame:
    records: list[dict] = []
    for _, row in data[["show_id", "title", "type", column]].iterrows():
        for person in str(row[column]).split(","):
            person = person.strip()
            if person:
                records.append({"name": person, "show_id": row.show_id, "title": row.title, "type": row.type})
    return pd.DataFrame(records)


def make_recommendations(data: pd.DataFrame, query: str, limit: int = 8) -> pd.DataFrame:
    terms = [term.lower() for term in re.findall(r"[\w'-]+", query) if len(term) > 1]
    if not terms:
        return data.head(limit)
    searchable = (data["type"] + " " + data["rating"] + " " + data["listed_in"] + " " + data["description"] + " " + data["title"]).str.lower()
    scored = data.copy()
    scored["match_score"] = sum(searchable.str.count(re.escape(term)) for term in terms)
    return scored[scored["match_score"] > 0].sort_values(["match_score", "release_year"], ascending=False).head(limit)


def selected_chart_label(event) -> str | None:
    """Read a Plotly selection safely across bar and treemap event payloads."""
    points = event.get("selection", {}).get("points", [])
    if not points:
        return None
    point = points[-1]
    custom_data = point.get("customdata")
    if isinstance(custom_data, (list, tuple)) and custom_data:
        return str(custom_data[0])
    if isinstance(custom_data, str) and custom_data:
        return custom_data
    return point.get("label") or point.get("y")


def title_details(item: pd.Series) -> None:
    left, right = st.columns([1, 2])
    with left:
        st.image(item.poster_image, use_container_width=True)
    with right:
        st.subheader(item.title)
        st.caption(f"{item.type} · {item.release_year if pd.notna(item.release_year) else 'Unknown year'} · {item.duration or 'Duration unavailable'}")
        st.markdown(
            f"**Rating:** {item.rating or 'Not rated'}  \n"
            f"**Director:** {item.director or 'Not listed'}  \n"
            f"**Cast:** {item.cast or 'Not listed'}"
        )
        st.write(item.description or "No description supplied.")
        st.metric("IMDb stars", f"{item.imdb_rating:.1f}/10" if pd.notna(item.imdb_rating) else "Not enriched")
        if item.type.lower() == "movie":
            st.metric("Lifetime box office", item.lifetime_box_office_collection if pd.notna(item.lifetime_box_office_collection) else "Not enriched")
        st.metric("Award wins", int(item.number_awards_won))
        st.caption(f"OMDb awards: {item.awards_summary}")


@st.dialog("Title details", width="large")
def title_details_dialog(item: pd.Series) -> None:
    """Show title metadata without moving the user away from the selected card."""
    title_details(item)


st.markdown("""
<style>
  .stApp { background: radial-gradient(circle at 20% 0%, #242447 0, #10101e 38%, #090911 100%); color: #f9f7f2; }
  [data-testid="stSidebar"] { background: #111121; }
  .hero { padding: 1.2rem 0 .5rem; }
  .hero h1 { margin: 0; color: #f5c96a; letter-spacing: -.04em; }
  .hero p { color: #bfc0ce; font-size: 1.05rem; }
  div[data-testid="stMetric"] { background: rgba(255,255,255,.055); border: 1px solid rgba(255,255,255,.1); padding: .8rem; border-radius: .75rem; }
  div[data-testid="stTabs"] [data-baseweb="tab-list"] { display: flex; gap: .6rem; justify-content: space-between; }
  div[data-testid="stTabs"] [data-baseweb="tab"] { flex: 1 1 0; justify-content: center; white-space: nowrap; }
  .top-card { height: 340px; overflow: hidden; background: rgba(255,255,255,.055); border: 1px solid rgba(255,255,255,.12); border-radius: .75rem; }
  .top-card img { display: block; width: 100%; height: 245px; object-fit: cover; background: #17172a; }
  .top-card__title { min-height: 3.4rem; padding: .55rem .65rem 0; color: #f9f7f2; font-weight: 650; line-height: 1.25; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .top-card__rating { padding: .15rem .65rem .65rem; color: #f5c96a; font-size: .85rem; }
  .recommendation-card { height: 365px; overflow: hidden; background: rgba(255,255,255,.055); border: 1px solid rgba(255,255,255,.12); border-radius: .75rem; }
  .recommendation-card img { display: block; width: 100%; height: 245px; object-fit: cover; background: #17172a; }
  .recommendation-card__title { height: 3.35rem; padding: .55rem .65rem 0; color: #f9f7f2; font-weight: 650; line-height: 1.25; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .recommendation-card__meta { height: 2.9rem; padding: .1rem .65rem .6rem; color: #bfc0ce; font-size: .82rem; line-height: 1.45; overflow: hidden; }
  .recommendation-card__stars { color: #f5c96a; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='hero'><h1>Netflix Lens</h1><p>Your cinematic discovery room — explore, filter, and find the next great watch.</p></div>", unsafe_allow_html=True)

filter_panel = st.sidebar.container()
with st.sidebar:
    st.divider()
    st.header("Data studio")
    uploaded = st.file_uploader("Upload Netflix CSV", type="csv", help="Your file must retain the standard Netflix title columns.")
    st.caption("The bundled Netflix dataset is used until you upload a file.")

try:
    data = prepare_data(uploaded if uploaded is not None else DATA_PATH)
except Exception as exc:
    st.error(f"Could not read the dataset: {exc}")
    st.stop()

source_id = f"upload:{uploaded.name}:{uploaded.size}" if uploaded is not None else f"bundled:{DATA_PATH.stat().st_mtime_ns}"
if st.session_state.get("enriched_source") == source_id:
    data = st.session_state["enriched_data"].copy()
data = apply_enrichment_cache(data)

with st.sidebar:
    st.divider()
    st.header("OMDb enrichment")
    key = omdb_api_key()
    usage_metric = None
    usage_note = None
    if key:
        st.caption("Adds poster, IMDb stars, movie box office, award wins, and OMDb award summary. Already-enriched rows are skipped.")
        requests_used = omdb_usage_today(key)
        request_limit = omdb_daily_limit()
        usage_metric = st.empty()
        usage_metric.metric("OMDb requests used today", f"{requests_used:,} / {request_limit:,}")
        usage_note = st.empty()
        usage_note.caption(f"Estimated requests remaining: {max(0, request_limit - requests_used):,}. This dashboard tracks only its own requests for this API key.")
        batch_size = st.number_input("Titles to enrich this run", min_value=1, max_value=1000, value=25, step=25, help="The OMDb free tier has request limits; use small batches.")
        if st.button("Enrich missing titles", use_container_width=True):
            progress = st.progress(0, text="Connecting to OMDb…")
            data, matched = enrich_with_omdb(data, key, int(batch_size), progress)
            progress.empty()
            st.session_state["enriched_data"] = data
            st.session_state["enriched_source"] = source_id
            updated_usage = omdb_usage_today(key)
            usage_metric.metric("OMDb requests used today", f"{updated_usage:,} / {request_limit:,}")
            usage_note.caption(f"Estimated requests remaining: {max(0, request_limit - updated_usage):,}. This dashboard tracks only its own requests for this API key.")
            st.success(f"Enriched {matched} of up to {batch_size} title(s) from OMDb.")
    else:
        st.info("Set `OMDB_API_KEY` to enable verified poster, box office, award, and IMDb-rating enrichment.")

available_types = sorted(data["type"].replace("", pd.NA).dropna().unique())
ratings = sorted(data["rating"].replace("", pd.NA).dropna().unique())
all_genres = sorted({genre.strip() for cell in data["listed_in"] for genre in cell.split(",") if genre.strip()})
with filter_panel:
    st.header("Refine your discovery")
    types = st.multiselect("Format", available_types, default=available_types)
    selected_ratings = st.multiselect("Maturity rating", ratings, default=ratings)
    selected_genres = st.multiselect("Genre", all_genres, placeholder="All genres")
    dated = data["date_added"].dropna()
    if not dated.empty:
        date_range = st.date_input("Added to Netflix", value=(dated.min().date(), dated.max().date()), min_value=dated.min().date(), max_value=dated.max().date())
    else:
        date_range = None

filtered = data[data["type"].isin(types) & data["rating"].isin(selected_ratings)].copy()
if selected_genres:
    genre_pattern = "|".join(re.escape(genre) for genre in selected_genres)
    filtered = filtered[filtered["listed_in"].str.contains(genre_pattern, case=False, regex=True, na=False)]
if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    filtered = filtered[filtered["date_added"].between(start, end)]

query = st.text_input("Ask for a recommendation", placeholder="Try: a TV-MA crime show, family animation, or romantic movie")
if query:
    recs = make_recommendations(filtered, query)
    st.subheader("Recommended for you")
    if recs.empty:
        st.info("No close matches in the current filters. Widen the filters or try different words.")
    else:
        recommendation_ids = set(recs["show_id"])
        pending_recommendation_ids = set(
            recs.loc[
                recs["imdb_rating"].isna() & ~recs["omdb_lookup_attempted"],
                "show_id",
            ]
        )
        if key:
            if pending_recommendation_ids and st.button(
                f"Enrich these recommendations ({len(pending_recommendation_ids)})",
                key="enrich_recommendations",
                use_container_width=False,
            ):
                progress = st.progress(
                    0,
                    text=f"Enriching {len(pending_recommendation_ids)} recommendation(s) with OMDb…",
                )
                data, matched = enrich_with_omdb(
                    data,
                    key,
                    maximum=len(pending_recommendation_ids),
                    progress_bar=progress,
                    candidate_ids=recommendation_ids,
                    only_unattempted=True,
                )
                progress.empty()
                filtered.update(data)
                recs = make_recommendations(filtered, query)
                st.session_state["enriched_data"] = data
                st.session_state["enriched_source"] = source_id
                if usage_metric is not None:
                    updated_usage = omdb_usage_today(key)
                    daily_limit = omdb_daily_limit()
                    usage_metric.metric(
                        "OMDb requests used today",
                        f"{updated_usage:,} / {daily_limit:,}",
                    )
                    usage_note.caption(
                        f"Estimated requests remaining: {max(0, daily_limit - updated_usage):,}. "
                        "This dashboard tracks only its own requests for this API key."
                    )
                st.success(
                    f"OMDb enrichment complete: matched {matched} of "
                    f"{len(pending_recommendation_ids)} recommendation(s)."
                )
            elif not pending_recommendation_ids:
                st.caption("OMDb lookup is complete for these recommendations.")
        else:
            st.info("Set `OMDB_API_KEY` to enrich recommendation details with OMDb.")

        cols = st.columns(min(4, len(recs)))
        for idx, (_, item) in enumerate(recs.iterrows()):
            with cols[idx % len(cols)]:
                stars = f"{item.imdb_rating:.1f}/10 IMDb" if pd.notna(item.imdb_rating) else "IMDb not available"
                title = escape(str(item.title))
                image_url = escape(str(item.poster_image), quote=True)
                media_meta = escape(f"{item.type} · {item.rating or 'Unrated'}")
                stars_text = escape(stars)
                st.markdown(
                    f'<div class="recommendation-card"><img src="{image_url}" alt="{title} poster">'
                    f'<div class="recommendation-card__title">{title}</div>'
                    f'<div class="recommendation-card__meta">{media_meta}<br>'
                    f'<span class="recommendation-card__stars">{stars_text}</span></div></div>',
                    unsafe_allow_html=True,
                )
                detail_action, save_action = st.columns(2)
                with detail_action:
                    if st.button("Details", key=f"recommendation_details_{item.show_id}", use_container_width=True):
                        title_details_dialog(item)
                with save_action:
                    if item.show_id in st.session_state.get("watchlist_ids", load_watchlist()):
                        st.button("Saved", key=f"recommendation_saved_{item.show_id}", disabled=True, use_container_width=True)
                    elif st.button("Save", key=f"recommendation_save_{item.show_id}", use_container_width=True):
                        add_to_watchlist(item.show_id)

st.divider()
m1, m2, m3, m4 = st.columns(4)
m1.metric("Titles in view", f"{len(filtered):,}")
m2.metric("Movies", int((filtered.type == "Movie").sum()))
m3.metric("TV shows", int((filtered.type == "TV Show").sum()))
m4.metric("Genres", filtered.listed_in.str.split(",").explode().str.strip().replace("", pd.NA).nunique())

overview, top_titles, cast_view, director_view, watchlist_view = st.tabs(["Genre map", "Top 10", "Cast", "Directors", "My Watchlist"])

with overview:
    genres = filtered.assign(genre=filtered.listed_in.str.split(",")).explode("genre")
    genres["genre"] = genres["genre"].str.strip()
    genres = genres[genres.genre.ne("")]
    genre_counts = genres.groupby("genre", as_index=False).size().sort_values("size", ascending=False)
    fig = px.treemap(genre_counts, path=["genre"], values="size", color="size", custom_data=["genre"], title="Genre map — area represents number of titles", color_continuous_scale=["#34335f", "#8177f6", "#f5c96a"])
    fig.update_traces(
        texttemplate="<b>%{label}</b><br>%{value} titles",
        hovertemplate="<b>%{label}</b><br>Titles: %{value}<extra></extra>",
    )
    fig.update_layout(template="plotly_dark", height=600, coloraxis_showscale=False, margin=dict(l=10, r=10, t=55, b=10))
    genre_event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points", key="genre_chart")
    selected_genre = selected_chart_label(genre_event)
    if selected_genre:
        st.session_state["selected_genre_chart"] = selected_genre
    selected_genre_chart = st.session_state.get("selected_genre_chart")
    if selected_genre_chart:
        genre_titles = genres[genres["genre"].eq(selected_genre_chart)][["title", "director", "release_year"]].drop_duplicates().sort_values("title")
        st.markdown(f"#### {selected_genre_chart} titles")
        genre_search = st.text_input("Search title, director, or release year", key="genre_result_search")
        if genre_search:
            needle = genre_search.strip()
            genre_titles = genre_titles[
                genre_titles["title"].str.contains(needle, case=False, na=False, regex=False)
                | genre_titles["director"].str.contains(needle, case=False, na=False, regex=False)
                | genre_titles["release_year"].astype(str).str.contains(needle, na=False, regex=False)
            ]
        page_size = 25
        page_count = max(1, (len(genre_titles) + page_size - 1) // page_size)
        pagination_context = (selected_genre_chart, genre_search.strip())
        if st.session_state.get("genre_pagination_context") != pagination_context:
            st.session_state["genre_pagination_context"] = pagination_context
            st.session_state["genre_results_page"] = 1
        page = min(max(1, st.session_state.get("genre_results_page", 1)), page_count)
        st.session_state["genre_results_page"] = page
        page_rows = genre_titles.iloc[(page - 1) * page_size:page * page_size]
        st.caption(f"{len(genre_titles):,} matching titles · showing up to 25 at a time. Select any column heading to sort.")
        st.dataframe(
            page_rows.rename(columns={"title": "Title", "director": "Director", "release_year": "Release Year"}),
            use_container_width=True,
            hide_index=True,
            height=680,
        )
        previous_page, page_status, next_page = st.columns([1, 2, 1])
        with previous_page:
            if st.button("← Back", key="genre_page_back", disabled=page == 1, use_container_width=True):
                st.session_state["genre_results_page"] = page - 1
                st.rerun()
        with page_status:
            st.markdown(
                f"<div style='text-align:center; padding:.45rem 0;'>Page <b>{page}</b> of <b>{page_count}</b></div>",
                unsafe_allow_html=True,
            )
        with next_page:
            if st.button("Next →", key="genre_page_next", disabled=page == page_count, use_container_width=True):
                st.session_state["genre_results_page"] = page + 1
                st.rerun()

with top_titles:
    movie_candidates = filtered[filtered.type.eq("Movie")].sort_values("release_year", ascending=False).head(10)
    show_candidates = filtered[filtered.type.eq("TV Show")].sort_values("release_year", ascending=False).head(10)
    candidate_ids = set(movie_candidates["show_id"]) | set(show_candidates["show_id"])
    pending_top_ids = set(
        filtered.loc[
            filtered["show_id"].isin(candidate_ids)
            & filtered["imdb_rating"].isna()
            & ~filtered["omdb_lookup_attempted"],
            "show_id",
        ]
    )
    if key and pending_top_ids:
        progress = st.progress(0, text=f"Enriching {len(pending_top_ids)} newest Top 10 candidate(s) with OMDb…")
        data, matched = enrich_with_omdb(
            data,
            key,
            maximum=20,
            progress_bar=progress,
            candidate_ids=candidate_ids,
            only_unattempted=True,
        )
        progress.empty()
        filtered.update(data)
        st.session_state["enriched_data"] = data
        st.session_state["enriched_source"] = source_id
        if usage_metric is not None:
            updated_usage = omdb_usage_today(key)
            daily_limit = omdb_daily_limit()
            usage_metric.metric("OMDb requests used today", f"{updated_usage:,} / {daily_limit:,}")
            usage_note.caption(f"Estimated requests remaining: {max(0, daily_limit - updated_usage):,}. This dashboard tracks only its own requests for this API key.")
        st.success(f"OMDb enrichment complete: matched {matched} of {len(pending_top_ids)} newest candidates.")

    st.caption("The 10 newest Movies and 10 newest TV Shows in the active filters are enriched with OMDb, then each Top 10 is ranked by IMDb stars.")
    movie_top = filtered[filtered["show_id"].isin(movie_candidates["show_id"])].sort_values(["imdb_rating", "release_year"], ascending=False, na_position="last").head(10)
    show_top = filtered[filtered["show_id"].isin(show_candidates["show_id"])].sort_values(["imdb_rating", "release_year"], ascending=False, na_position="last").head(10)
    a, b = st.columns(2, gap="large", border=True)
    for column, subset, label in [(a, movie_top, "Movies"), (b, show_top, "TV shows")]:
        with column:
            st.markdown(f"### Top 10 {label}")
            if subset.empty:
                st.info("No titles match these filters.")
            else:
                cards = st.columns(2)
                for position, (_, item) in enumerate(subset.iterrows()):
                    with cards[position % 2]:
                        title = escape(str(item.title))
                        image_url = escape(str(item.poster_image), quote=True)
                        stars = f"{item.imdb_rating:.1f}/10 IMDb" if pd.notna(item.imdb_rating) else "IMDb rating pending"
                        st.markdown(
                            f'<div class="top-card"><img src="{image_url}" alt="{title} poster">'
                            f'<div class="top-card__title">{position + 1}. {title}</div>'
                            f'<div class="top-card__rating">{stars}</div></div>',
                            unsafe_allow_html=True,
                        )
                        detail_action, save_action = st.columns(2)
                        with detail_action:
                            if st.button("View details", key=f"top_{label}_{item.show_id}", use_container_width=True):
                                title_details_dialog(item)
                        with save_action:
                            if item.show_id in st.session_state.get("watchlist_ids", load_watchlist()):
                                st.button("Saved", key=f"top_saved_{label}_{item.show_id}", disabled=True, use_container_width=True)
                            elif st.button("Save", key=f"top_save_{label}_{item.show_id}", use_container_width=True):
                                add_to_watchlist(item.show_id)

def people_section(data: pd.DataFrame, column: str, heading: str) -> None:
    people = split_people(data, column)
    if people.empty:
        st.info(f"No {heading.lower()} information is available for these filters.")
        return
    counts = people.groupby("name", as_index=False).size().sort_values("size", ascending=False).head(10)
    fig = px.bar(counts.sort_values("size"), x="size", y="name", orientation="h", title=f"Select a {heading[:-1].lower()} for More to Watch", labels={"size": "Titles", "name": heading[:-1]}, custom_data=["name"], color="size", color_continuous_scale=["#6f69e8", "#f5c96a"])
    fig.update_layout(template="plotly_dark", height=460, coloraxis_showscale=False, margin=dict(l=10, r=10, t=55, b=10))
    person_event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points", key=f"{column}_chart")
    selected_person_from_chart = selected_chart_label(person_event)
    if selected_person_from_chart:
        st.session_state[f"selected_{column}_person"] = selected_person_from_chart
    selected_person = st.session_state.get(f"selected_{column}_person")
    if selected_person:
        connected = people[people.name.eq(selected_person)].show_id.tolist()
        more = data[data.show_id.isin(connected)].sort_values("release_year", ascending=False).head(8)
        st.markdown(f"#### More to Watch with {selected_person}")
        st.dataframe(
            more[["title", "type", "rating", "imdb_rating", "release_year", "listed_in"]].rename(
                columns={
                    "title": "Title",
                    "type": "Format",
                    "rating": "Maturity Rating",
                    "imdb_rating": "IMDb Stars",
                    "release_year": "Release Year",
                    "listed_in": "Genres",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(f"Click a bar to see titles featuring that {heading[:-1].lower()}.")

with cast_view:
    people_section(filtered, "cast", "Cast members")
with director_view:
    people_section(filtered, "director", "Directors")
with watchlist_view:
    st.caption("Save titles here from recommendations or Top 10. This tab uses your existing dashboard data and never triggers OMDb enrichment.")
    saved_ids = st.session_state.setdefault("watchlist_ids", load_watchlist())
    available_ids = filtered["show_id"].tolist()
    if available_ids:
        add_id = st.selectbox("Add a title from the current filters", available_ids, format_func=lambda ident: filtered.loc[filtered.show_id.eq(ident), "title"].iloc[0], key="watchlist_add_title")
        if st.button("Add to My Watchlist", key="watchlist_add", use_container_width=False):
            add_to_watchlist(add_id)
            saved_ids = st.session_state["watchlist_ids"]
            st.success("Added to My Watchlist.")

    watchlist = data[data["show_id"].isin(saved_ids)].copy().sort_values(["imdb_rating", "release_year"], ascending=False, na_position="last")
    if watchlist.empty:
        st.info("Your watchlist is empty. Save a recommendation or a Top 10 title to start building it.")
    else:
        st.markdown(f"#### Saved titles ({len(watchlist)})")
        st.dataframe(
            watchlist[["title", "type", "imdb_rating", "release_year", "listed_in", "number_awards_won", "lifetime_box_office_collection"]].rename(
                columns={
                    "title": "Title",
                    "type": "Format",
                    "imdb_rating": "IMDb Stars",
                    "release_year": "Release Year",
                    "listed_in": "Genres",
                    "number_awards_won": "Award Wins",
                    "lifetime_box_office_collection": "Box Office Collection",
                }
            ),
            use_container_width=True,
            hide_index=True,
            height=520,
        )
        remove_id = st.selectbox("Remove a saved title", watchlist["show_id"].tolist(), format_func=lambda ident: watchlist.loc[watchlist.show_id.eq(ident), "title"].iloc[0], key="watchlist_remove_title")
        if st.button("Remove from My Watchlist", key="watchlist_remove", type="secondary"):
            remove_from_watchlist(remove_id)
            st.rerun()

with st.sidebar:
    st.divider()
    export = data.drop(columns=["rating_rank"])
    st.download_button("Download enriched CSV", export.to_csv(index=False).encode("utf-8"), "netflix_titles_enriched.csv", "text/csv", help="Includes OMDb poster, box office, award wins, and IMDb stars when enriched.")
    st.caption("Poster images use a generated fallback until OMDb finds a verified poster. Award wins are OMDb's total reported wins, not country-specific national awards.")
