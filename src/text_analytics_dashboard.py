"""Text Analytics Dashboard - AIO 2026 Project 1.1 (extended).

Author : Nguyen Van Thuong
Course : AIO 2026 - Module 01
Project: Project 1.1 (extended) - logged under Keep Track Day 02

An offline Streamlit dashboard that profiles a free-text column inside an
Excel/CSV file. For every row it measures length, detects the language, and
ranks keyword frequency, then visualises the result with interactive Plotly
charts. Unlike the translation app from Project 1.1, every dependency here runs
locally, so the dashboard needs no network access or API key at runtime.

Run locally:
    streamlit run text_analytics_dashboard.py

Dependencies:
    streamlit pandas plotly langdetect openpyxl
"""

from __future__ import annotations

import io
import re
from collections import Counter

import pandas as pd
import plotly.express as px
import streamlit as st
from langdetect import DetectorFactory, LangDetectException, detect

# Pin the seed so identical text always yields the same language guess.
DetectorFactory.seed = 0

# Project metadata surfaced in the UI.
AUTHOR: str = "Nguyen Van Thuong"
COURSE: str = "AIO 2026"
MODULE: str = "Module 01"
PROJECT: str = "Project 1.1 (extended)"
KEEP_TRACK: str = "Keep Track Day 02"

SUPPORTED_EXTENSIONS: tuple[str, ...] = ("csv", "xlsx")
MIN_WORD_LENGTH: int = 2
DEFAULT_TOP_N: int = 15

# Minimal English + Vietnamese stop-word list. Kept inline so the app stays
# dependency-free; pulling in NLTK's corpus would be overkill for this scope.
STOPWORDS: frozenset[str] = frozenset({
    # English
    "the", "a", "an", "and", "or", "but", "if", "then", "of", "to", "in",
    "on", "for", "with", "as", "is", "are", "was", "were", "be", "been",
    "it", "its", "this", "that", "these", "those", "i", "you", "he", "she",
    "we", "they", "at", "by", "from", "so", "not", "no", "do", "does",
    # Vietnamese
    "va", "la", "cua", "co", "khong", "duoc", "cho", "cac", "nhung", "mot",
    "toi", "ban", "da", "se", "khi", "nay", "do", "voi", "de", "trong",
    "ra", "thi", "ma", "cung", "rat", "nen", "vi", "neu",
})

# ISO code -> display name for the languages this kind of dataset usually holds.
LANGUAGE_NAMES: dict[str, str] = {
    "en": "English", "vi": "Vietnamese", "fr": "French", "de": "German",
    "es": "Spanish", "pt": "Portuguese", "ru": "Russian", "ja": "Japanese",
    "ko": "Korean", "zh-cn": "Chinese (Simplified)",
    "zh-tw": "Chinese (Traditional)", "it": "Italian", "nl": "Dutch",
    "ar": "Arabic", "th": "Thai", "id": "Indonesian", "unknown": "Unknown",
}

# Distinctive Vietnamese syllables used to recover undiacritized Vietnamese.
# langdetect ships no model for Vietnamese written without tone marks and tends
# to label it French or Spanish. These syllables are rare in English and French,
# so a short hit list is enough to correct that bias; ambiguous homographs such
# as "le", "la" or "the" are deliberately left out to avoid false positives.
VIETNAMESE_HINTS: frozenset[str] = frozenset({
    "khong", "nguoi", "nhung", "duoc", "cua", "mot", "voi", "trong", "cung",
    "rat", "neu", "toi", "hoc", "thay", "hieu", "dep", "truc", "quan",
    "ngon", "ngu", "hien", "nhanh", "dinh", "ung", "dung", "thanh", "cong",
    "noi", "them", "thuc", "lieu", "viet", "giang", "cam", "minh", "hoa",
    "phan", "bai", "tien", "dau", "chay", "tron", "muot", "tac", "tuong",
})

# Vietnamese-specific letters (tone marks plus a/e/o/u/d variants). Their
# presence is a near-certain signal that the text is Vietnamese.
VN_DIACRITICS = re.compile(
    "[\u0103\u00e2\u0111\u00ea\u00f4\u01a1\u01b0"
    "\u00e0\u00e1\u1ea1\u1ea3\u00e3\u1ea7\u1ea5\u1ead\u1ea9\u1eab"
    "\u1eb1\u1eaf\u1eb7\u1eb3\u1eb5\u00e8\u00e9\u1eb9\u1ebb\u1ebd"
    "\u1ec1\u1ebf\u1ec7\u1ec3\u1ec5\u00ec\u00ed\u1ecb\u1ec9\u0129"
    "\u00f2\u00f3\u1ecd\u1ecf\u00f5\u1ed3\u1ed1\u1ed9\u1ed5\u1ed7"
    "\u1edd\u1edb\u1ee3\u1edf\u1ee1\u00f9\u00fa\u1ee5\u1ee7\u0169"
    "\u1eeb\u1ee9\u1ef1\u1eed\u1eef\u1ef3\u00fd\u1ef5\u1ef7\u1ef9]",
    re.IGNORECASE,
)
WORD_PATTERN = re.compile(r"\w+", re.UNICODE)


# --------------------------------------------------------------------------- #
# Core logic (no Streamlit calls, so each function is unit-testable)
# --------------------------------------------------------------------------- #
def tokenize(text: str) -> list[str]:
    """Split text into lower-cased word tokens (Unicode-aware)."""
    return [match.lower() for match in WORD_PATTERN.findall(str(text))]


def count_words(text: str) -> int:
    """Return the number of word tokens in text."""
    return len(tokenize(text))


def _looks_vietnamese(tokens: list[str]) -> bool:
    """Flag Vietnamese typed without diacritics via a syllable hit ratio."""
    if len(tokens) < 3:
        return False
    hits = sum(1 for token in tokens if token in VIETNAMESE_HINTS)
    return hits >= 2 and hits / len(tokens) >= 0.2


def detect_language(text: str) -> str:
    """Detect the ISO language code of text, or 'unknown' when undecidable.

    langdetect covers most scripts well but cannot recognise Vietnamese typed
    without tone marks, so we short-circuit on Vietnamese letters and apply a
    syllable heuristic before trusting the statistical guess.
    """
    text = (text or "").strip()
    if len(text) < MIN_WORD_LENGTH:
        return "unknown"
    if VN_DIACRITICS.search(text):
        return "vi"
    try:
        code = detect(text)
    except LangDetectException:
        return "unknown"
    # Override the common false positive where undiacritized Vietnamese is read
    # as a Romance language.
    if code != "vi" and _looks_vietnamese(tokenize(text)):
        return "vi"
    return code


def language_label(code: str) -> str:
    """Map an ISO language code to a human-readable name."""
    return LANGUAGE_NAMES.get(code, code)


def count_keywords(texts: pd.Series, remove_stopwords: bool = True) -> pd.DataFrame:
    """Tally word frequencies across a text column, ranked high to low."""
    counter: Counter[str] = Counter()
    for text in texts.dropna():
        for token in tokenize(text):
            if len(token) < MIN_WORD_LENGTH:
                continue
            if remove_stopwords and token in STOPWORDS:
                continue
            counter[token] += 1
    return pd.DataFrame(counter.most_common(), columns=["word", "count"])


def top_keywords(
    texts: pd.Series,
    top_n: int = DEFAULT_TOP_N,
    remove_stopwords: bool = True,
) -> pd.DataFrame:
    """Return the top-N most frequent keywords."""
    ranked = count_keywords(texts, remove_stopwords)
    return ranked.head(top_n).reset_index(drop=True)


def analyze(df: pd.DataFrame, text_column: str) -> pd.DataFrame:
    """Append char_count, word_count and language columns for text_column."""
    if text_column not in df.columns:
        raise KeyError(f"Column '{text_column}' is not present in the data.")
    result = df.copy()
    text = result[text_column].fillna("").astype(str)
    result["char_count"] = text.str.len()
    result["word_count"] = text.map(count_words)
    # Detect once per distinct value; real-world columns repeat heavily, and
    # language detection is the most expensive step in the pipeline.
    codes = {value: detect_language(value) for value in text.unique()}
    result["language"] = text.map(lambda value: language_label(codes[value]))
    return result


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Serialise a DataFrame to in-memory XLSX bytes for download."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="analysis")
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# Cached data layer (keyed by file bytes so reruns stay cheap)
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def load_table(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Read a CSV/XLSX payload into a DataFrame and trim column names."""
    buffer = io.BytesIO(file_bytes)
    if filename.lower().endswith(".csv"):
        df = pd.read_csv(buffer)
    else:
        df = pd.read_excel(buffer)
    df.columns = [str(column).strip() for column in df.columns]
    return df


@st.cache_data(show_spinner="Analysing text...")
def run_analysis(file_bytes: bytes, filename: str, text_column: str) -> pd.DataFrame:
    """Load and analyse the chosen column. Cached on its inputs."""
    return analyze(load_table(file_bytes, filename), text_column)


@st.cache_data(show_spinner=False)
def cached_keywords(
    file_bytes: bytes, filename: str, text_column: str, remove_stopwords: bool
) -> pd.DataFrame:
    """Cache the full keyword tally so moving the top-N slider stays instant."""
    df = load_table(file_bytes, filename)
    return count_keywords(df[text_column], remove_stopwords)


# --------------------------------------------------------------------------- #
# UI rendering
# --------------------------------------------------------------------------- #
def render_overview_tab(
    analyzed: pd.DataFrame, keywords: pd.DataFrame, top_n: int
) -> None:
    """Word-count distribution and the most frequent keywords."""
    fig_hist = px.histogram(
        analyzed, x="word_count", nbins=30,
        title="Word count distribution",
        color_discrete_sequence=["#4C78A8"],
    )
    fig_hist.update_layout(xaxis_title="Words", yaxis_title="Rows")
    st.plotly_chart(fig_hist, use_container_width=True)

    if keywords.empty:
        st.info("Not enough data to rank keywords.")
        return
    top = keywords.head(top_n)
    fig_kw = px.bar(
        top, x="count", y="word", orientation="h",
        title=f"Top {top_n} keywords",
        color="count", color_continuous_scale="Blues",
    )
    fig_kw.update_layout(
        yaxis=dict(autorange="reversed"),
        xaxis_title="Frequency", yaxis_title="Keyword",
    )
    st.plotly_chart(fig_kw, use_container_width=True)


def render_language_tab(analyzed: pd.DataFrame) -> None:
    """Language mix as a donut chart plus the underlying counts."""
    counts = analyzed["language"].value_counts().reset_index()
    counts.columns = ["language", "count"]
    fig = px.pie(
        counts, names="language", values="count",
        title="Language distribution", hole=0.4,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(counts, use_container_width=True)


def render_data_tab(analyzed: pd.DataFrame) -> None:
    """Full enriched table with CSV and Excel export buttons."""
    st.dataframe(analyzed, use_container_width=True)
    col_csv, col_xlsx = st.columns(2)
    col_csv.download_button(
        "Download CSV",
        analyzed.to_csv(index=False).encode("utf-8-sig"),
        file_name="text_analysis.csv", mime="text/csv",
    )
    col_xlsx.download_button(
        "Download Excel", to_excel_bytes(analyzed),
        file_name="text_analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def main() -> None:
    """Application entry point."""
    st.set_page_config(
        page_title="Text Analytics Dashboard", page_icon="\U0001F4CA",
        layout="wide",
    )
    st.title("Text Analytics Dashboard")
    st.caption(f"{COURSE} - {MODULE} - {PROJECT} - {KEEP_TRACK} - {AUTHOR}")

    with st.sidebar:
        st.header("Options")
        uploaded = st.file_uploader("Upload a data file", type=SUPPORTED_EXTENSIONS)
        remove_stopwords = st.checkbox("Remove stop words", value=True)
        top_n = st.slider("Keywords to show", 5, 40, DEFAULT_TOP_N, step=5)
        st.divider()
        st.caption(f"Extends Project 1.1 (Streamlit NLP apps).")
        st.caption(f"Author: {AUTHOR} - {COURSE} - {MODULE}")

    # Defensive guard: nothing to do until a file is supplied.
    if uploaded is None:
        st.info("Upload a .xlsx or .csv file with a text column to begin.")
        st.stop()

    file_bytes = uploaded.getvalue()
    try:
        df = load_table(file_bytes, uploaded.name)
    except Exception as exc:  # noqa: BLE001 - report any parse failure to the user
        st.error(f"Could not read the file: {exc}")
        st.stop()

    if df.empty:
        st.warning("The file contains no rows.")
        st.stop()

    text_column = st.sidebar.selectbox("Text column", list(df.columns))
    analyzed = run_analysis(file_bytes, uploaded.name, text_column)
    keywords = cached_keywords(
        file_bytes, uploaded.name, text_column, remove_stopwords
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rows", f"{len(analyzed):,}")
    col2.metric("Total words", f"{int(analyzed['word_count'].sum()):,}")
    col3.metric("Avg. length (chars)", f"{analyzed['char_count'].mean():.1f}")
    col4.metric("Languages", f"{analyzed['language'].nunique()}")

    tab_overview, tab_lang, tab_data = st.tabs(["Overview", "Languages", "Data"])
    with tab_overview:
        render_overview_tab(analyzed, keywords, top_n)
    with tab_lang:
        render_language_tab(analyzed)
    with tab_data:
        render_data_tab(analyzed)


if __name__ == "__main__":
    main()
