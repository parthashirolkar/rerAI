"""tools/rera_tools.py -- MahaRERA project search and details for rerAI.

Provides tools to search MahaRERA registered projects by district and fetch
detailed project information including promoter details, building info,
 FSI data, inventory, documents, and complaints.

The MahaRERA portal consists of two separate systems:
- Drupal site (maharera.maharashtra.gov.in): project search, server-rendered HTML
- SPA (maharerait.maharashtra.gov.in): project detail view, REST/JSON API

Search works via Drupal HTML scraping. Detail fetching uses the SPA API with
a shared public-service account credentials (AES-encrypted before POST).
"""

import asyncio
import base64
import hashlib
import json
import re
import time
from typing import Optional

from bs4 import BeautifulSoup
from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_core.tools import tool

from tools.config import (
    MAHARERA_CRYPTOJS_KEY,
    MAHARERA_PUBLIC_PASSWORD,
    MAHARERA_PUBLIC_USERNAME,
)

BASE_URL = "https://maharera.maharashtra.gov.in"
DIVISION_API = f"{BASE_URL}/get-division-data"
DISTRICT_API = f"{BASE_URL}/div-district-data"
SEARCH_URL = f"{BASE_URL}/projects-search-result"
STATE_CODE = "27"
LANG_ID = "1"

MAHARERA_API_BASE = (
    "https://maharerait.maharashtra.gov.in"
    "/api/maha-rera-public-view-project-registration-service"
    "/public/projectregistartion"
)
MAHARERA_LOGIN_API = (
    "https://maharerait.maharashtra.gov.in/api/maha-rera-login-service/login"
)

CRYPTOJS_KEY = MAHARERA_CRYPTOJS_KEY
_PUBLIC_USERNAME = MAHARERA_PUBLIC_USERNAME
_PUBLIC_PASSWORD = MAHARERA_PUBLIC_PASSWORD

_cached_token: Optional[str] = None
_token_issued_at: float = 0.0


def evp_bytes_to_key(
    password: bytes, salt: bytes, key_len: int = 32, iv_len: int = 16
) -> tuple[bytes, bytes]:
    """Derive AES-256 key and IV from a password and salt using OpenSSL's EVP_BytesToKey.

    This implements the key-derivation function that CryptoJS uses when encrypting
    with a passphrase (ciphername: "AES", mode: "CBC", padding: "Pkcs7").
    EVP_BytesToKey is MD5-based and intentionally slow for brute-force resistance.
    The derived key and IV are used to AES-encrypt credentials before sending
    them to the MahaRERA login endpoint.

    Args:
        password: The secret passphrase (bytes).
        salt: Random salt, exactly 8 bytes (bytes).
        key_len: Desired key length in bytes (default 32 = AES-256).
        iv_len: Desired IV length in bytes (default 16 = AES block size).

    Returns:
        A tuple (key_bytes, iv_bytes) of the derived key and IV.
    """
    dtot = b""
    d = b""
    while len(dtot) < key_len + iv_len:
        d = hashlib.md5(d + password + salt).digest()
        dtot += d
    return dtot[:key_len], dtot[key_len : key_len + iv_len]


def cryptojs_encrypt(plaintext: str, passphrase: str) -> str:
    """Encrypt a string using CryptoJS AES-compatible encryption.

    Produces a Base64-encoded string in the format used by CryptoJS
    with OpenSSL-compatible salted key derivation (prefix ``Salted__``).

    The encryption scheme is:
      1. Generate 8 random salt bytes.
      2. Derive key + IV via EVP_BytesToKey (MD5, 1 iteration).
      3. Pad plaintext with PKCS7.
      4. AES-256-CBC encrypt.
      5. Prepend ``Salted__`` + 8-byte salt to ciphertext.
      6. Base64-encode the result.

    Args:
        plaintext: The UTF-8 string to encrypt.
        passphrase: The secret passphrase used for key derivation.

    Returns:
        A Base64-encoded ``Salted__<salt><ciphertext>`` string.
    """
    import os
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    salt = os.urandom(8)
    key, iv = evp_bytes_to_key(passphrase.encode("utf-8"), salt)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    pad_len = 16 - (len(plaintext.encode("utf-8")) % 16)
    padded = plaintext.encode("utf-8") + bytes([pad_len] * pad_len)
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(b"Salted__" + salt + encrypted).decode()


def _post_json(url: str, payload: dict, headers: Optional[dict] = None) -> dict:
    """POST a JSON payload to a URL and parse the JSON response.

    Args:
        url: Full URL to POST to.
        payload: Dictionary that will be JSON-serialized and sent as the body.
        headers: Additional HTTP headers (optional). Content-Type is always
            set to ``application/json``.

    Returns:
        The parsed JSON response as a dictionary.

    Raises:
        urllib.error.URLError: On network or HTTP errors.
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    headers = headers or {}
    headers["Content-Type"] = "application/json"
    headers["User-Agent"] = "rerAI/0.1"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_bearer_token() -> str:
    """Obtain a JWT bearer token from the MahaRERA login API.

    The SPA uses a shared public-service account to authenticate all
    anonymous API requests. The credentials are AES-encrypted with a
    hardcoded key before being sent. On success the API returns a
    RS256-signed JWT that must be included as ``Authorization: Bearer <token>``
    on subsequent requests.

    The token is cached in module globals with a 90-minute expiry
    (the API issues tokens valid for 100 minutes).

    Returns:
        A valid JWT bearer token string.

    Raises:
        RuntimeError: If the login API returns an unexpected response.
    """
    global _cached_token, _token_issued_at

    if _cached_token is not None:
        elapsed = time.time() - _token_issued_at
        if elapsed < 5400:
            return _cached_token

    encrypted_user = cryptojs_encrypt(_PUBLIC_USERNAME, CRYPTOJS_KEY)
    encrypted_pass = cryptojs_encrypt(_PUBLIC_PASSWORD, CRYPTOJS_KEY)

    resp = _post_json(
        f"{MAHARERA_LOGIN_API}/authenticatePublic",
        {"userName": encrypted_user, "password": encrypted_pass},
    )

    if resp.get("status") == "1" and "responseObject" in resp:
        _cached_token = resp["responseObject"]["accessToken"]
        _token_issued_at = time.time()
        return _cached_token

    raise RuntimeError(f"MahaRERA auth failed: {resp}")


async def _fetch_html(url: str) -> str:
    """Fetch and return the HTML content of a URL using an async loader.

    Args:
        url: The URL to fetch.

    Returns:
        The page content as a string, or an empty string on failure.
    """
    loader = AsyncHtmlLoader([url])
    docs = await asyncio.to_thread(loader.load)
    if docs and len(docs) > 0:
        return docs[0].page_content
    return ""


async def _get_divisions() -> dict[str, str]:
    """Fetch the division-to-code mapping from the Drupal search portal.

    Divisions are the top-level administrative tier in the MahaRERA
    search filter (e.g., "Pune", "Konkan", "Nashik").

    Returns:
        Dictionary mapping division name (e.g. "Pune") to its numeric code.
    """
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
    """Fetch the district-to-code mapping for a given division.

    The Drupal portal returns districts as AJAX dropdown options filtered
    by the selected division.

    Args:
        division_code: The numeric division code (e.g. "2" for Pune).

    Returns:
        Dictionary mapping district name (e.g. "Pune") to its numeric code.
    """
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
    """Resolve a human-readable district name to its numeric code.

    Searches all divisions to find the district code, using exact match
    first, then fuzzy match (substring) as a fallback.

    Args:
        district_name: District name as it appears in the portal (e.g. "Pune").

    Returns:
        The numeric district code string.

    Raises:
        ValueError: If the district is not found in any division.
    """
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
    """Parse a single project card element from the Drupal HTML search results.

    Each card contains: RERA ID, project name, promoter name, district,
    and a "View Details" link containing the project view URL.

    Args:
        card_soup: A BeautifulSoup element representing one project card div.

    Returns:
        A dictionary with keys ``rera_id``, ``project_name``, ``promoter``,
        ``district``, and ``view_url``, or ``None`` if parsing fails.
    """
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
        for link in card_soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if "public/project/view/" in href and text == "View Details":
                view_url = href

        if rera_id and project_name:
            return {
                "rera_id": rera_id,
                "project_name": project_name,
                "promoter": promoter,
                "district": get_field_value("District"),
                "view_url": view_url,
            }
    except Exception:
        pass
    return None


async def _parse_project_cards(html: str) -> list[dict]:
    """Extract all project cards from a Drupal search results HTML page.

    Args:
        html: The full HTML string of a search results page.

    Returns:
        A list of parsed project dictionaries from that page.
    """
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", class_="row shadow p-3 mb-5 bg-body rounded")
    projects = []
    for card in cards:
        project = _extract_project_from_card(card)
        if project:
            projects.append(project)
    return projects


def _get_total_pages(html: str) -> int:
    """Extract the total page count from a Drupal search results page.

    The Drupal search results include a ``pagesCount`` span element containing
    the total number of result pages.

    Args:
        html: The HTML of a search results page.

    Returns:
        The total number of pages, or 1 if the element is not found.
    """
    match = re.search(r'<span class="pagesCount"[^>]*data-current-data="(\d+)"', html)
    if match:
        return int(match.group(1))
    return 1


async def _fetch_projects(district_name: str, max_pages: int = 1) -> list[dict]:
    """Fetch all (or up to max_pages) project cards for a district.

    The Drupal search endpoint returns one page at a time with ~10 projects.
    This function fetches the first page, reads the total page count,
    then fetches any additional pages up to ``max_pages``.

    Args:
        district_name: District name as accepted by ``_resolve_district_code``.
        max_pages: Maximum number of result pages to fetch (default 1).

    Returns:
        A deduplicated list of project dictionaries.
    """
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
async def search_rera_projects(district_name: str, max_pages: int = 1) -> str:
    """Search MahaRERA registered projects by district name.

    Returns a JSON array of projects with RERA ID, name, promoter, and district.
    Each page has ~10 projects. Use max_pages to control breadth (default 1).

    Args:
        district_name: District name in Maharashtra (e.g. "Pune", "Mumbai City")
        max_pages: Number of result pages to fetch (default 1)
    """
    projects = await _fetch_projects(district_name, max_pages)
    trimmed = projects[:5]
    return json.dumps(
        {"projects": trimmed, "total_available": len(projects)},
        ensure_ascii=False,
    )


def _extract_project_id(view_url: str) -> int:
    """Extract the numeric projectId from a MahaRERA project view URL.

    The view URL path format is ``/public/project/view/<projectId>``.
    Note that this is the internal database ID, NOT the RERA registration
    number (e.g. ``P52100001864``).

    Args:
        view_url: Full URL or path like
            ``https://maharerait.maharashtra.gov.in/public/project/view/53``.

    Returns:
        The integer projectId.

    Raises:
        ValueError: If the URL does not match the expected pattern.
    """
    match = re.search(r"/public/project/view/(\d+)", view_url)
    if not match:
        raise ValueError(f"Could not extract projectId from view_url: {view_url}")
    return int(match.group(1))


async def _call_api(operation: str, payload: dict, token: Optional[str] = None) -> dict:
    """Call a MahaRERA SPA API endpoint.

    Args:
        operation: The API operation name (e.g. ``getProjectGeneralDetailsByProjectId``).
            Appended to ``MAHARERA_API_BASE`` to form the full URL.
        payload: JSON-serializable request body dict.
        token: Optional JWT bearer token. If provided, the
            ``Authorization: Bearer <token>`` header is included.

    Returns:
        The parsed JSON response dictionary from the API.
    """
    url = f"{MAHARERA_API_BASE}/{operation}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return await asyncio.to_thread(_post_json, url, payload, headers)


@tool
async def get_rera_project_details(view_url: str) -> str:
    """Fetch detailed information for a MahaRERA project.

    Given a view_url from search_rera_projects, fetches full project details
    via the MahaRERA public API including registration info, promoter details,
    building list, FSI data, inventory, uploaded documents, and complaints.

    The function calls both public endpoints (no authentication required) and
    authenticated endpoints (requires bearer token obtained via the public-service
    account). Authenticated calls are best-effort — if token acquisition fails,
    only public data is returned.

    Args:
        view_url: The project detail URL
            (e.g. https://maharerait.maharashtra.gov.in/public/project/view/53)

    Returns:
        A JSON string with keys:

        - ``projectId``: The internal project ID.
        - ``view_url``: The URL that was queried.
        - ``public_info``: Response from getProjectGeneralDetailsByProjectId
          (RERA reg number, type, status, dates, fees).
        - ``status``: Response from getProjectCurrentStatus
          (statusId, statusName, isDeregistered, isAbeyance).
        - ``complaints``: Response from getComplaintDetailsByProjectId
          (complaints array, warrant details).
        - ``authenticated_info``: Present only when a bearer token was obtained.
          Contains ``promoter``, ``buildings``, ``general_plan``,
          ``inventory``, and ``documents`` from the respective authenticated
          endpoints.
    """
    project_id = _extract_project_id(view_url)

    public_payload = {"projectId": project_id}
    token = None
    try:
        token = _get_bearer_token()
    except Exception:
        pass

    async def call(op: str, p: Optional[dict] = None) -> dict:
        return await _call_api(op, p or public_payload, token)

    (
        general,
        status,
        complaints,
        promoter,
        buildings,
        plan,
        inventory,
        docs,
    ) = await asyncio.gather(
        call("getProjectGeneralDetailsByProjectId"),
        call("getProjectCurrentStatus"),
        call("getComplaintDetailsByProjectId"),
        call("getProjectAndAssociatedPromoterDetails") if token else asyncio.sleep(0),
        call("getProjectBuildingDetails") if token else asyncio.sleep(0),
        call("getProjectGeneralPlanSummary") if token else asyncio.sleep(0),
        call("getProjectSoldUnsoldInventory") if token else asyncio.sleep(0),
        call("getUploadedDocuments") if token else asyncio.sleep(0),
    )

    result = {
        "projectId": project_id,
        "view_url": view_url,
        "public_info": general if isinstance(general, dict) else None,
        "status": status if isinstance(status, dict) else None,
        "complaints": complaints if isinstance(complaints, dict) else None,
    }

    if token:
        auth_data = {
            "promoter": promoter if isinstance(promoter, dict) else None,
            "buildings": buildings if isinstance(buildings, dict) else None,
            "general_plan": plan if isinstance(plan, dict) else None,
            "inventory": inventory if isinstance(inventory, dict) else None,
            "documents": docs if isinstance(docs, dict) else None,
        }
        result["authenticated_info"] = {
            k: v for k, v in auth_data.items() if v is not None
        }

    return json.dumps(result, ensure_ascii=False, indent=2)
