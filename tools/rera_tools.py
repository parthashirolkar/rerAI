import asyncio
import json
import re
from typing import Optional

from bs4 import BeautifulSoup
from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_core.tools import tool

BASE_URL = "https://maharera.maharashtra.gov.in"
DIVISION_API = f"{BASE_URL}/get-division-data"
DISTRICT_API = f"{BASE_URL}/div-district-data"
SEARCH_URL = f"{BASE_URL}/projects-search-result"
PROJECT_VIEW_URL = f"{BASE_URL}/public/project/view"
STATE_CODE = "27"
LANG_ID = "1"


async def _fetch_html(url: str) -> str:
    loader = AsyncHtmlLoader([url])
    docs = await asyncio.to_thread(loader.load)
    if docs and len(docs) > 0:
        return docs[0].page_content
    return ""


async def _get_divisions() -> dict[str, str]:
    url = (
        f"{DIVISION_API}?"
        f"stateCode={STATE_CODE}&"
        f"langID={LANG_ID}&"
        f"form_code=custom_search_form&"
        f"field_code=project_division"
    )
    html = await _fetch_html(url)
    matches = re.findall(r'<option value="(\d+)">([^<]+)</option>', html)
    return {name.strip(): code for code, name in matches if code}


async def _get_districts_for_division(division_code: str) -> dict[str, str]:
    url = (
        f"{DISTRICT_API}?"
        f"state_code={STATE_CODE}&"
        f"lang_id={LANG_ID}&"
        f"division_code={division_code}&"
        f"district_form=custom_search_form&"
        f"distruct_field=project_district"
    )
    html = await _fetch_html(url)
    matches = re.findall(r'<option value="(\d+)">([^<]+)</option>', html)
    return {name.strip(): code for code, name in matches if code and name.strip()}


async def _resolve_district_code(district_name: str) -> str:
    divisions = await _get_divisions()
    all_districts: dict[str, str] = {}
    for _, division_code in divisions.items():
        districts = await _get_districts_for_division(division_code)
        all_districts.update(districts)

    key = district_name.strip().lower()
    district_map = {name.lower(): code for name, code in all_districts.items()}
    if key in district_map:
        return district_map[key]

    for name, code in all_districts.items():
        if key in name.lower() or name.lower() in key:
            return code

    available = sorted(set(all_districts.keys()))
    raise ValueError(
        f"District '{district_name}' not found. "
        f"Available ({len(available)}): {', '.join(available[:30])}..."
    )


def _extract_project_from_card(card_soup) -> Optional[dict]:
    try:
        rera_elem = card_soup.find("p", class_="p-0")
        rera_id = None
        if rera_elem:
            rera_text = rera_elem.get_text(strip=True)
            if rera_text.startswith("#"):
                rera_id = rera_text[1:].strip()

        name_elem = card_soup.find("h4", class_="title4")
        project_name = None
        if name_elem:
            strong = name_elem.find("strong")
            if strong:
                project_name = strong.get_text(strip=True)

        promoter_elem = card_soup.find("p", class_="darkBlue bold")
        promoter = ""
        if promoter_elem:
            promoter = promoter_elem.get_text(strip=True)

        def get_field_value(label_text: str) -> str:
            for label in card_soup.find_all("div", class_="greyColor"):
                if label.get_text(strip=True) == label_text:
                    next_p = label.find_next_sibling("p")
                    if next_p:
                        return next_p.get_text(strip=True)
            return ""

        view_url = ""
        original_url = ""
        for link in card_soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if "public/project/view/" in href:
                if "isOriginal=true" in href:
                    original_url = href
                elif text == "View Details":
                    view_url = href

        if rera_id and project_name:
            return {
                "rera_id": rera_id,
                "project_name": project_name,
                "promoter": promoter,
                "district": get_field_value("District"),
                "state": get_field_value("State"),
                "pincode": get_field_value("Pincode"),
                "last_modified": get_field_value("Last Modified"),
                "view_url": view_url,
                "original_url": original_url,
            }
    except Exception:
        pass
    return None


async def _parse_project_cards(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", class_="row shadow p-3 mb-5 bg-body rounded")
    projects = []
    for card in cards:
        project = _extract_project_from_card(card)
        if project:
            projects.append(project)
    return projects


def _get_total_pages(html: str) -> int:
    match = re.search(r'<span class="pagesCount"[^>]*data-current-data="(\d+)"', html)
    if match:
        return int(match.group(1))
    return 1


async def _fetch_projects(district_name: str, max_pages: int = 2) -> list[dict]:
    district_code = await _resolve_district_code(district_name)

    search_url = (
        f"{SEARCH_URL}?"
        f"project_name=&"
        f"project_location=&"
        f"project_completion_date=&"
        f"project_state={STATE_CODE}&"
        f"project_district={district_code}&"
        f"carpetAreas=&"
        f"completionPercentages=&"
        f"project_division=&"
        f"page=1&"
        f"op="
    )

    html = await _fetch_html(search_url)
    if not html or "Unable to find records" in html:
        return []

    projects = await _parse_project_cards(html)
    total_pages = _get_total_pages(html)
    pages_to_fetch = min(total_pages - 1, max_pages - 1)

    for page_num in range(2, 2 + pages_to_fetch):
        page_url = (
            f"{SEARCH_URL}?"
            f"project_name=&"
            f"project_location=&"
            f"project_completion_date=&"
            f"project_state={STATE_CODE}&"
            f"project_district={district_code}&"
            f"carpetAreas=&"
            f"completionPercentages=&"
            f"project_division=&"
            f"page={page_num}&"
            f"op="
        )
        page_html = await _fetch_html(page_url)
        if page_html and "Unable to find records" not in page_html:
            projects.extend(await _parse_project_cards(page_html))
        if page_num < 2 + pages_to_fetch - 1:
            await asyncio.sleep(0.5)

    seen: set[str] = set()
    unique = []
    for p in projects:
        if p["rera_id"] not in seen:
            seen.add(p["rera_id"])
            unique.append(p)
    return unique


@tool
def search_rera_projects(district_name: str, max_pages: int = 2) -> str:
    """Search MahaRERA registered projects by district name.

    Returns a JSON array of projects with RERA ID, name, promoter, district,
    pincode, and view URL. Each page has ~10 projects. Use max_pages to
    control breadth (default 2 = ~20 projects).

    Args:
        district_name: District name in Maharashtra (e.g. "Pune", "Mumbai City")
        max_pages: Number of result pages to fetch (default 2)
    """
    projects = asyncio.get_event_loop().run_until_complete(
        _fetch_projects(district_name, max_pages)
    )
    return json.dumps(projects, indent=2)


@tool
def get_rera_project_details(view_url: str) -> str:
    """Fetch detailed information from a MahaRERA project detail page.

    Given a view_url from search_rera_projects, scrapes the full project
    detail page for compliance data, promoter info, and project status.
    Note: The project detail portal is a single-page app (SPA). This tool
    uses Playwright to render the page and extract content.

    Args:
        view_url: The project detail URL (e.g. https://maharerait.maharashtra.gov.in/public/project/view/53)
    """
    full_url = view_url if view_url.startswith("http") else f"{BASE_URL}{view_url}"

    async def _fetch():
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            all_responses = []

            async def capture(resp):
                if "/api/" in resp.url and "getProjectById" in resp.url:
                    try:
                        body = await resp.text()
                        all_responses.append((resp.url, resp.status, body))
                    except Exception:
                        pass

            page.on("response", capture)

            await page.goto(full_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(5000)

            await browser.close()

        if all_responses:
            _, status, body = all_responses[0]
            if status == 200:
                return body[:8000]
            return f"API returned status {status}: {body[:500]}"

        html_text = None
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(full_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(5000)

            html_text = await page.inner_text("body")
            await browser.close()

        if html_text and len(html_text.strip()) > 100:
            return html_text[:8000]

        return (
            "Could not extract project details. The MahaRERA detail portal is a "
            "single-page app that requires JavaScript rendering which may not work "
            "in headless mode. Use search_rera_projects to get summary data, or "
            f"visit the URL directly: {full_url}"
        )

    return asyncio.get_event_loop().run_until_complete(_fetch())
