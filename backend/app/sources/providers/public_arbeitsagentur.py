"""Germany's federal job board (Bundesagentur für Arbeit), ~800k vacancies.

HONESTY NOTE — this source is registered `enabled_by_default=False`, same
treatment as the brief specified for Workday-if-unreliable, and for the same
reason: I could not get a real 200 out of it during verification, despite
trying every documented variant.

What was tried, from this network, all with `X-API-Key: jobboerse-jobsuche`
(the well-known public key from the official `bundesAPI/jobsuche-api` spec):
  - `pc/v4/jobs` and `pc/v4/app/jobs` (the URL this module actually calls,
    per the spec) → consistently HTTP 403 "No match found for request",
    with or without a browser User-Agent, with or without the exact mobile
    User-Agent string the reference client (`api_example.py` in that repo)
    uses.
  - `pc/v6/jobs` (a newer path turned up by the same spec search) → HTTP 401
    with an empty body, no `WWW-Authenticate` header — looks like it wants a
    different auth scheme entirely, not just this key.
The 403's "vary: ... User-Agent" response header and the total absence of a
descriptive error body both point at a WAF/bot-detection layer (TLS
fingerprinting is a known pattern for this kind of gateway) rather than a
wrong URL or a wrong key — a plain httpx client can't clear that from here,
though it may work fine from a German residential IP or with a real browser
TLS stack. The parser below follows the response schema documented in that
same spec (`stellenangebote[]` with `beruf`, `arbeitgeber`, `arbeitsort`,
`refnr`, `externeUrl`, `aktuelleVeroeffentlichungsdatum`) since a live 200
was never obtained to capture directly — see
`backend/tests/fixtures/public_arbeitsagentur.json`, which is schema-derived,
not a live capture, and is labeled as such in its test.

If you're picking this up later: try again from a German IP first, and check
whether the WAF wants a User-Agent that exactly matches a real Alamofire/iOS
build string (mine were rejected) or a completely different auth flow for v6.
"""

from __future__ import annotations

from app.models import Job, job_id
from app.sources.base import FetchContext, SourceKind, SourceMeta
from app.sources.providers import ats_common
from app.sources.registry import register

_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
_HEADERS = {"X-API-Key": "jobboerse-jobsuche"}


def parse_arbeitsagentur(data: dict) -> list[Job]:
    out = []
    for j in data.get("stellenangebote", []):
        employer = j.get("arbeitgeber", "")
        url = j.get("externeUrl", "") or ""
        ort = j.get("arbeitsort") or {}
        location = ", ".join(x for x in (ort.get("ort"), ort.get("region"), ort.get("land")) if x)
        out.append(Job(
            id=job_id("public:arbeitsagentur", employer, url or j.get("refnr", "")),
            source="public:arbeitsagentur",
            company=employer,
            title=j.get("beruf", ""),
            location=location,
            url=url,
            description=ats_common.clean(j.get("beruf", "")),
            posted=j.get("aktuelleVeroeffentlichungsdatum"),
            region="de",
        ))
    return out


@register
class ArbeitsagenturSource:
    meta = SourceMeta(
        key="public:arbeitsagentur",
        label="Bundesagentur für Arbeit (Jobbörse)",
        kind=SourceKind.PUBLIC,
        regions=("de",),
        rate_limit_s=2.0,
        daily_cap=500,
        enabled_by_default=False,
        warning=(
            "Could not be verified live from this environment — the API "
            "consistently returned HTTP 403 (v4) / 401 (v6) despite using "
            "the documented public key. Likely WAF/bot-detection, not a "
            "wrong URL. Disabled by default; see module docstring before "
            "re-enabling."
        ),
    )

    async def fetch(self, ctx: FetchContext) -> list[Job]:
        query = ctx.queries[0] if ctx.queries else "Softwareentwickler"
        try:
            r = await ctx.client.get(
                _URL,
                params={"was": query, "page": 1, "size": min(ctx.limit, 100)},
                headers=_HEADERS,
            )
            r.raise_for_status()
            jobs = parse_arbeitsagentur(r.json())
        except Exception as e:
            ctx.warn(f"public:arbeitsagentur: {e}")
            return []
        return jobs[: ctx.limit]
