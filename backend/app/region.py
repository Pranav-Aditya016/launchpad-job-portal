"""Where a job actually is, inferred from its own text.

Region used to be copied from the *source's* first tag, so every Greenhouse
posting was "global" whether it sat in Bengaluru or Berlin. The dashboard's
region filter therefore offered two options and no India — while the user's
entire search is India, Germany and remote.

Order of evidence: the job's `location`, then its title, then the source's hint
as a last resort. When nothing matches we return "" rather than guessing,
because the user filters on this and a confidently wrong country hides real
jobs.
"""

from __future__ import annotations

import re

# Shown in the UI. Ordered deliberately: the user's own markets first.
ALL_REGIONS: tuple[tuple[str, str], ...] = (
    ("in", "India"),
    ("de", "Germany"),
    ("eu", "Europe (other)"),
    ("gb", "United Kingdom"),
    ("us", "United States"),
    ("global", "Remote / Global"),
)

# Word-boundary matched, so "Ukraine" is not the UK and "Indiana" is not India.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("in", re.compile(
        r"\b(india|bengaluru|bangalore|hyderabad|chennai|mumbai|pune|kolkata"
        r"|ahmedabad|noida|gurugram|gurgaon|new delhi|delhi ncr|delhi"
        r"|kochi|cochin|coimbatore|nagercoil|trivandrum|thiruvananthapuram"
        r"|jaipur|indore|chandigarh|bhubaneswar|mysuru|mysore|vadodara"
        r"|karnataka|telangana|maharashtra|tamil nadu|kerala|gujarat)\b", re.I)),
    ("de", re.compile(
        r"\b(germany|deutschland|\bde\b|berlin|münchen|munich|hamburg"
        r"|frankfurt|köln|koeln|cologne|stuttgart|düsseldorf|duesseldorf"
        r"|leipzig|dresden|hannover|nürnberg|nuremberg|bremen|essen|dortmund"
        r"|karlsruhe|mannheim|bonn|münster|aachen|freiburg|heidelberg)\b", re.I)),
    ("gb", re.compile(
        r"\b(united kingdom|great britain|england|scotland|wales"
        r"|london|manchester|birmingham|edinburgh|glasgow|bristol|leeds"
        r"|cambridge|oxford|u\.k\.|uk)\b", re.I)),
    ("us", re.compile(
        r"\b(united states|u\.s\.a?\.?|usa|\bus\b|new york|san francisco|seattle"
        r"|austin|boston|chicago|los angeles|denver|atlanta|dallas|houston"
        r"|indiana|indianapolis|california|texas|washington|massachusetts"
        r"|ny|ca|tx|wa|ma|il)\b", re.I)),
    ("eu", re.compile(
        r"\b(netherlands|amsterdam|france|paris|spain|madrid|barcelona"
        r"|italy|milan|rome|poland|warsaw|kraków|krakow|portugal|lisbon"
        r"|ireland|dublin|sweden|stockholm|denmark|copenhagen|norway|oslo"
        r"|finland|helsinki|austria|vienna|wien|switzerland|zurich|zürich"
        r"|belgium|brussels|czech|prague|romania|bucharest|europe|emea)\b", re.I)),
)

_REMOTE = re.compile(r"\b(remote|anywhere|worldwide|distributed|work from home|wfh)\b", re.I)


def infer(text: str | None) -> str:
    """Region code for a location string, or "" when it can't be placed.

    A concrete place always beats a bare "remote": "Remote, Berlin" is a German
    job, not an unplaceable one — which is why the country patterns run first.
    """
    if not text:
        return ""
    for code, pattern in _PATTERNS:
        if pattern.search(text):
            return code
    if _REMOTE.search(text):
        return "global"
    return ""


def for_job(job, source_hint: str = "") -> str:
    """Best region for a Job: location, then title, then URL, then the source.

    The URL matters more than it looks. Scraped board links routinely carry the
    city in the slug — "…is-hiring-for-software-developer-nagercoil" — and for
    a custom site we only ever capture a title and a link, so without this
    those postings would have no region at all and vanish from the filter.
    """
    return (
        infer(job.location)
        or infer(job.title)
        or infer(_slug(getattr(job, "url", "")))
        or (source_hint or "")
    )


def _slug(url: str) -> str:
    """URL path as spaced words, so slug segments hit the word-boundary rules."""
    if not url:
        return ""
    path = re.sub(r"^https?://[^/]+", "", url)
    return re.sub(r"[-_/+.]+", " ", path)


def label(code: str) -> str:
    return dict(ALL_REGIONS).get(code, code or "Unspecified")
