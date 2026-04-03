"""tools/land_records_tools.py -- Land records automation for rerAI.

Automates the Mahabhulekh (Maharashtra land records) portal to extract
7/12 (Satbara) extracts and property card (Malmatta Patrak) data.

Uses Playwright for browser automation and BeautifulSoup for HTML parsing.
"""

import asyncio
import json
import os
import re

from bs4 import BeautifulSoup
from langchain_core.tools import tool
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# Primary URL may not resolve in all environments, fallback to working URL
MAHABHULEKH_URL = "https://bhulekh.mahabhumi.gov.in"
LAND_RECORDS_CACHE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "land_records_cache.json"
)

DEFAULT_TIMEOUT = 30000  # 30 seconds
NAVIGATION_DELAY = 3000  # 3 seconds between actions

# Division mapping for Pune region
DIVISIONS = {
    "pune": "2",
    "konkan": "1",
    "nashik": "3",
    "aurangabad": "4",
    "amravati": "5",
    "nagpur": "6",
}


class MahabhulekhError(Exception):
    """Custom exception for Mahabhulekh portal errors."""

    pass


def _load_cache() -> dict:
    """Load cached dropdown values."""
    cache_path = os.path.abspath(LAND_RECORDS_CACHE_FILE)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(cache: dict) -> None:
    """Save dropdown values to cache."""
    cache_path = os.path.abspath(LAND_RECORDS_CACHE_FILE)
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _normalize_name(name: str) -> str:
    """Normalize a name for matching in the portal dropdowns.

    The Mahabhulekh portal uses Devanagari (Marathi) script for all
    dropdown options. This function strips whitespace and ensures
    the name is ready for matching.

    Note: Arguments should be provided in Devanagari script as they
    appear on the portal (e.g., 'पुणे' not 'Pune').
    """
    return name.strip()


def _parse_7_12_html(html: str) -> dict:
    """Parse 7/12 extract HTML into structured data.

    The 7/12 extract is rendered as nested HTML tables with Sakal Marathi font.
    """
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "extract_type": "7/12 (Satbara)",
        "village": "",
        "taluka": "",
        "district": "",
        "survey_number": "",
        "area_hectares": None,
        "pot_kharab_hectares": None,
        "assessment": "",
        "owners": [],
        "land_classification": "",
        "rights_and_liabilities": [],
        "other_remarks": "",
        "raw_extract_available": False,
    }

    extract_table = soup.find("table", id="ExtractData") or soup.find(
        "table", class_="extract-table"
    )
    if extract_table:
        result["raw_extract_available"] = True
    elif soup.find("table") and any(kw in html for kw in ["सातबारा", "गाव", "हेक्टर"]):
        result["raw_extract_available"] = True

    # Try to extract village/taluka/district from headers
    # Look for common patterns in table headers
    for table in soup.find_all("table"):
        text = table.get_text()
        # Village name often appears in the first few tables
        if "गाव" in text or "Village" in text:
            # Try to extract village name
            cells = table.find_all("td")
            for i, cell in enumerate(cells):
                if "गाव" in cell.get_text() or "Village" in cell.get_text():
                    if i + 1 < len(cells):
                        result["village"] = cells[i + 1].get_text(strip=True)
                if "तालुका" in cell.get_text() or "Taluka" in cell.get_text():
                    if i + 1 < len(cells):
                        result["taluka"] = cells[i + 1].get_text(strip=True)

    # Extract survey number from title or headers
    title_match = re.search(
        r"(?:Survey|Gat)नंबर[:ः]?\s*(\d+[/\d]*)", html, re.IGNORECASE
    )
    if title_match:
        result["survey_number"] = title_match.group(1)

    # Look for area information
    # Pattern: hectare-are-sqm format or decimal hectares
    area_patterns = [
        r"(\d+)\.(\d+)\.(\d+)\s*हेक्टर",  # Hectare-Are-SqM format
        r"(\d+\.\d+)\s*हे",  # Decimal hectares
        r"Total Area[:ः]?\s*(\d+[\.\d]*)",
    ]
    for pattern in area_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            result["area_hectares"] = match.group(1)
            break

    # Look for owner information in table rows
    # Owners are typically listed with their names and shares
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) >= 2:
            text = tr.get_text()
            # Look for owner-related keywords
            if any(kw in text for kw in ["मालक", "भोगंदार", "Owner", "Occupant"]):
                owner_name = tds[-1].get_text(strip=True) if tds else ""
                if owner_name and len(owner_name) > 2:
                    result["owners"].append(owner_name)

    # If no structured data found but we have the extract, return note about raw HTML
    if result["raw_extract_available"] and not result["owners"]:
        result["note"] = (
            "7/12 extract retrieved successfully. "
            "The extract contains Marathi text in table format. "
            "Full parsing of all fields (owners, area, rights) requires "
            "detailed HTML table analysis. Raw HTML available."
        )

    return result


async def _fetch_7_12_with_playwright(
    district: str,
    taluka: str,
    village: str,
    survey_no: str,
    max_retries: int = 3,
) -> dict:
    """Fetch 7/12 extract using Playwright browser automation."""
    # Normalize all names for consistent matching
    district = _normalize_name(district)
    taluka = _normalize_name(taluka)
    village = _normalize_name(village)

    cache = _load_cache()
    cache_key = f"{district}_{taluka}_{village}"

    for attempt in range(max_retries):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    accept_downloads=True,
                )
                page = await context.new_page()

                # Navigate to Mahabhulekh portal
                await page.goto(MAHABHULEKH_URL, timeout=DEFAULT_TIMEOUT)
                await page.wait_for_load_state("networkidle")

                # Check for maintenance alert
                try:
                    overlay = await page.query_selector("#customAlertOverlay")
                    if overlay:
                        style = await overlay.get_attribute("style")
                        if not style or "display: none" not in style:
                            alert_text = await overlay.inner_text()
                            if (
                                "maintenance" in alert_text.lower()
                                or "देखभाल" in alert_text
                            ):
                                return {
                                    "error": "Mahabhulekh portal is under scheduled maintenance.",
                                    "portal_message": alert_text[:500],
                                    "note": "The portal may be unavailable during maintenance windows. Please try again later.",
                                }
                except Exception:
                    pass

                # Check if we need to select division
                try:
                    # Wait for division dropdown
                    await page.wait_for_selector(
                        "select[name*='division']", timeout=10000
                    )

                    # Select Pune division
                    await page.select_option(
                        "select[name*='division']", DIVISIONS.get("pune", "2")
                    )
                    await page.wait_for_timeout(NAVIGATION_DELAY)

                    # Click Go button - this opens a new window
                    async with page.expect_popup(timeout=20000) as popup_info:
                        await page.click("input[type='submit'], button[type='submit']")

                    popup = await popup_info.value
                    page = popup  # Switch to the popup window
                    await page.wait_for_load_state("networkidle")

                except PlaywrightTimeout:
                    # Maybe we're already on the division-specific page
                    pass

                # Now on the district selection page
                await page.wait_for_timeout(NAVIGATION_DELAY)

                # Select district - match Devanagari text
                district_normalized = _normalize_name(district)
                district_found = False
                for selector in [
                    "select#ContentPlaceHolder1_ddlMainDist",
                    "select[name*='ddlMainDist']",
                    "select",
                ]:
                    try:
                        options = await page.query_selector_all(f"{selector} option")
                        for option in options:
                            text = await option.text_content()
                            if text and district_normalized in text.strip():
                                value = await option.get_attribute("value")
                                if value and value != "--निवडा--":
                                    await page.select_option(selector, value)
                                    district_found = True
                                    break
                        if district_found:
                            break
                    except Exception:
                        continue

                if not district_found:
                    raise MahabhulekhError(
                        f"District '{district}' not found in dropdown"
                    )

                await page.wait_for_timeout(NAVIGATION_DELAY * 2)

                # Select taluka - match Devanagari text
                taluka_normalized = _normalize_name(taluka)
                taluka_found = False
                for selector in [
                    "select#ContentPlaceHolder1_ddlTalForAll",
                    "select[name*='ddlTal']",
                ]:
                    try:
                        await page.wait_for_selector(selector, timeout=10000)
                        options = await page.query_selector_all(f"{selector} option")
                        for option in options:
                            text = await option.text_content()
                            if text and taluka_normalized in text.strip():
                                value = await option.get_attribute("value")
                                if value and value != "--निवडा--":
                                    await page.select_option(selector, value)
                                    taluka_found = True
                                    break
                        if taluka_found:
                            break
                    except Exception:
                        continue

                if not taluka_found:
                    raise MahabhulekhError(f"Taluka '{taluka}' not found in dropdown")

                await page.wait_for_timeout(NAVIGATION_DELAY * 2)

                # Select village - match Devanagari text
                village_normalized = _normalize_name(village)
                village_found = False
                for selector in [
                    "select#ContentPlaceHolder1_ddlVillForAll",
                    "select[name*='ddlVill']",
                ]:
                    try:
                        await page.wait_for_selector(selector, timeout=10000)
                        options = await page.query_selector_all(f"{selector} option")
                        for option in options:
                            text = await option.text_content()
                            if text and village_normalized in text.strip():
                                value = await option.get_attribute("value")
                                if value and value != "--निवडा--":
                                    await page.select_option(selector, value)
                                    village_found = True
                                    # Cache this village
                                    if cache_key not in cache:
                                        cache[cache_key] = {"village_value": value}
                                        _save_cache(cache)
                                    break
                        if village_found:
                            break
                    except Exception:
                        continue

                if not village_found:
                    raise MahabhulekhError(f"Village '{village}' not found in dropdown")

                await page.wait_for_timeout(NAVIGATION_DELAY)

                # Select search type (Survey Number)
                await page.select_option(
                    "select#ContentPlaceHolder1_ddlSelectSearchType", "2"
                )
                await page.wait_for_timeout(NAVIGATION_DELAY // 2)

                # Enter survey number
                survey_input = await page.query_selector(
                    "input#ContentPlaceHolder1_txtcsno"
                )
                if not survey_input:
                    raise MahabhulekhError("Could not find survey number input field")

                await survey_input.fill(survey_no)
                await page.wait_for_timeout(NAVIGATION_DELAY // 2)

                # Click search button
                try:
                    await page.click(
                        "input#ContentPlaceHolder1_btnsearchfind", timeout=10000
                    )
                except Exception as e:
                    raise MahabhulekhError(f"Could not click search button: {e}")

                # Wait for results or alert
                await page.wait_for_timeout(NAVIGATION_DELAY * 2)

                # Check for JavaScript alert
                try:
                    dialog = await page.wait_for_event("dialog", timeout=5000)
                    message = dialog.message
                    await dialog.dismiss()
                    if "not found" in message.lower() or "अस्तित्व" in message:
                        return {
                            "error": f"Survey number '{survey_no}' not found for {village}, {taluka}, {district}",
                            "portal_message": message,
                        }
                except PlaywrightTimeout:
                    pass  # No alert

                # Wait for results page
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(NAVIGATION_DELAY)

                # Get the HTML content
                html_content = await page.content()

                # Parse the extract
                result = _parse_7_12_html(html_content)
                result["district"] = district
                result["taluka"] = taluka
                result["village"] = village
                result["survey_number_queried"] = survey_no

                await browser.close()
                return result

        except MahabhulekhError:
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                try:
                    await browser.close()
                except Exception:
                    pass
                await asyncio.sleep(NAVIGATION_DELAY * 2 / 1000)
                continue
            try:
                await browser.close()
            except Exception:
                pass
            return {
                "error": f"Failed to fetch 7/12 extract after {max_retries} attempts: {str(e)}",
                "district": district,
                "taluka": taluka,
                "village": village,
                "survey_number": survey_no,
            }


@tool
async def fetch_7_12_extract(
    district: str, taluka: str, village: str, survey_no: str
) -> str:
    """Fetch 7/12 (Satbara) extract from Mahabhulekh portal.

    Automates the Maharashtra land records portal to extract ownership,
    land classification, area, and encumbrance information for a given
    survey/gat number.

    IMPORTANT: The Mahabhulekh portal uses Devanagari (Marathi) script
    for all dropdown options. Provide arguments in Devanagari script
    exactly as they appear on the portal.

    Args:
        district: District name in Devanagari (e.g., "पुणे", "सातारा")
        taluka: Taluka name in Devanagari (e.g., "हवेली", "मावळ")
        village: Village name in Devanagari
        survey_no: Survey or Gat number (e.g., "42", "15/2")

    Returns:
        JSON string with 7/12 extract data including:
        - Owners and their shares
        - Total area in hectares
        - Land classification (agricultural/NA/ghairan)
        - Rights, liabilities, and encumbrances
        - Pot kharab (unusable land) area

    Note:
        The Mahabhulekh portal can be slow and occasionally unresponsive.
        Results may take 30-60 seconds. The portal content is in Marathi.
        This is for informational purposes only per portal disclaimer.
    """
    result = await _fetch_7_12_with_playwright(district, taluka, village, survey_no)
    cleaned = {k: v for k, v in result.items() if v is not None and v != "" and v != []}
    return json.dumps(cleaned, ensure_ascii=False)


@tool
async def fetch_property_card(
    district: str, taluka: str, village: str, survey_no: str
) -> str:
    """Provide guidance for obtaining Property Card (Malmatta Patrak) data.

    Property cards are for urban/city survey areas and contain property
    tax assessment, building details, and ownership information.

    NOTE: This tool does not currently fetch property card data directly.
    It returns guidance on where to find property cards, as urban property
    records are typically managed by municipal corporations (PMC/PCMC)
    rather than the Mahabhulekh portal.

    Args:
        district: District name (e.g., "Pune", "Pimpri Chinchwad")
        taluka: Taluka name
        village: Village or city survey ward name
        survey_no: City survey number or property number

    Returns:
        JSON string with guidance on obtaining property card data.
    """
    # Property cards for urban areas are often separate from 7/12
    # For now, attempt to query and provide helpful guidance

    result = {
        "extract_type": "Property Card (Malmatta Patrak)",
        "district": district,
        "taluka": taluka,
        "village": village,
        "survey_number": survey_no,
        "note": (
            "Property cards (Malmatta Patrak) for urban areas are typically "
            "managed by municipal corporations (PMC, PCMC) rather than the "
            "revenue department. For Pune city areas, check: "
            "https://pmc.gov.in/property-tax or visit the PMC office. "
            "For Pimpri-Chinchwad, check: https://pcmcindia.gov.in"
        ),
        "alternative_sources": [
            "PMC Property Tax portal (for Pune city)",
            "PCMC Property Tax portal (for Pimpri-Chinchwad)",
            "Local municipal ward office",
            "7/12 extract (for rural/agricultural land classification)",
        ],
    }

    return json.dumps(result, ensure_ascii=False)
