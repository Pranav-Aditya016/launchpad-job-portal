import re
from urllib.parse import urljoin
from app.models import Job, job_id

_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def jobs_from_markdown(md: str, base_url: str, company: str) -> list[Job]:
    """Extract jobs from markdown text containing links.

    Parses markdown links in the format [Title](URL) and converts them to Job objects.
    URLs are resolved relative to base_url using urljoin.

    Args:
        md: Markdown text containing job links
        base_url: Base URL for resolving relative links
        company: Company identifier for the Job objects

    Returns:
        List of Job objects extracted from the markdown
    """
    jobs = []
    for title, url in _LINK.findall(md):
        full = urljoin(base_url, url)
        jobs.append(Job(
            id=job_id("crawl4ai", company, full),
            source="crawl4ai",
            company=company,
            title=title.strip(),
            url=full
        ))
    return jobs


async def fetch_jobs(url: str, company: str) -> list[Job]:
    """Fetch jobs from a URL using crawl4ai and extract job listings.

    This function uses crawl4ai to fetch the page and convert it to markdown,
    then extracts job listings from the markdown.

    Args:
        url: URL to crawl for job listings
        company: Company identifier for the Job objects

    Returns:
        List of Job objects found on the page
    """
    from crawl4ai import AsyncWebCrawler

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
    return jobs_from_markdown(result.markdown or "", base_url=url, company=company)
