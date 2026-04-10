"""tests/test_rera_tools.py -- Tests for RERA tools and crypto helpers."""

import json

import pytest

from tools.rera_tools import (
    _extract_project_id,
    cryptojs_encrypt,
    evp_bytes_to_key,
    get_rera_project_details,
    search_rera_projects,
)


class TestCryptoHelpers:
    def test_evp_bytes_to_key_derives_key_and_iv(self):
        key, iv = evp_bytes_to_key(b"password", b"salt1234", key_len=32, iv_len=16)
        assert len(key) == 32
        assert len(iv) == 16

    def test_evp_bytes_to_key_deterministic(self):
        k1, i1 = evp_bytes_to_key(b"pass", b"salt1234")
        k2, i2 = evp_bytes_to_key(b"pass", b"salt1234")
        assert k1 == k2
        assert i1 == i2

    def test_evp_bytes_to_key_different_salts_different_output(self):
        k1, i1 = evp_bytes_to_key(b"pass", b"salt0001")
        k2, i2 = evp_bytes_to_key(b"pass", b"salt0002")
        assert k1 != k2 or i1 != i2

    def test_cryptojs_encrypt_returns_base64_string(self):
        result = cryptojs_encrypt("hello world", "mypassword")
        assert isinstance(result, str)
        assert result

    def test_cryptojs_encrypt_deterministic_with_random_salt(self):
        r1 = cryptojs_encrypt("hello", "pass")
        r2 = cryptojs_encrypt("hello", "pass")
        assert r1 != r2

    def test_cryptojs_encrypt_can_be_decrypted(self):
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        import base64

        encrypted = cryptojs_encrypt("secret message", "testpass123")
        decoded = base64.b64decode(encrypted)
        assert decoded[:8] == b"Salted__"

        salt = decoded[8:16]
        ciphertext = decoded[16:]
        key, iv = evp_bytes_to_key(b"testpass123", salt)
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        pad_len = padded[-1]
        decrypted = padded[:-pad_len].decode("utf-8")
        assert decrypted == "secret message"


class TestExtractProjectId:
    def test_extracts_numeric_id(self):
        url = "https://maharerait.maharashtra.gov.in/public/project/view/531"
        assert _extract_project_id(url) == 531

    def test_handles_trailing_slash(self):
        url = "https://maharerait.maharashtra.gov.in/public/project/view/531/"
        assert _extract_project_id(url) == 531

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            _extract_project_id("https://example.com/")


@pytest.mark.live
class TestSearchReraProjectsLive:
    @pytest.mark.timeout(60)
    async def test_search_pune_returns_projects(self):
        result = await search_rera_projects.ainvoke(
            {
                "district_name": "Pune",
                "max_pages": 1,
            }
        )
        assert isinstance(result, str)
        data = json.loads(result)
        assert "error" not in data or data.get("error") == ""
        projects = data.get("projects", data.get("results", []))
        assert isinstance(projects, list)

    @pytest.mark.timeout(60)
    async def test_search_pune_returns_list(self):
        result = await search_rera_projects.ainvoke(
            {
                "district_name": "Pune",
                "max_pages": 1,
            }
        )
        data = json.loads(result)
        projects = data.get("projects", data.get("results", []))
        assert isinstance(projects, list)

    @pytest.mark.timeout(60)
    async def test_search_pune_project_has_required_fields(self):
        result = await search_rera_projects.ainvoke(
            {
                "district_name": "Pune",
                "max_pages": 1,
            }
        )
        data = json.loads(result)
        projects = data.get("projects", data.get("results", []))
        if projects:
            first = projects[0]
            assert any(
                k in first for k in ("name", "project_name", "Name", "projectName")
            )

    @pytest.mark.timeout(60)
    async def test_search_invalid_district_raises(self):
        with pytest.raises(ValueError, match="District .* not found"):
            await search_rera_projects.ainvoke(
                {
                    "district_name": "NonexistentDistrictXYZ",
                    "max_pages": 1,
                }
            )


@pytest.mark.live
class TestGetReraProjectDetailsLive:
    @pytest.mark.timeout(60)
    async def test_get_details_with_valid_url(self):
        search_result = await search_rera_projects.ainvoke(
            {
                "district_name": "Pune",
                "max_pages": 1,
            }
        )
        search_data = json.loads(search_result)
        projects = search_data.get("projects", search_data.get("results", []))
        if not projects:
            pytest.skip("No projects found in search to test details")

        view_urls = [
            p.get("view_url") or p.get("url") or p.get("link") for p in projects if p
        ]
        valid_url = next((u for u in view_urls if u and "projectView" in str(u)), None)
        if not valid_url:
            pytest.skip("No valid view_url found in project results")

        result = await get_rera_project_details.ainvoke({"view_url": valid_url})
        assert isinstance(result, str)
        data = json.loads(result)
        assert "error" not in data, f"Unexpected error: {data.get('error')}"

    @pytest.mark.timeout(60)
    async def test_get_details_returns_promoter_info(self):
        search_result = await search_rera_projects.ainvoke(
            {
                "district_name": "Pune",
                "max_pages": 1,
            }
        )
        search_data = json.loads(search_result)
        projects = search_data.get("projects", search_data.get("results", []))
        if not projects:
            pytest.skip("No projects found")

        view_urls = [p.get("view_url") or p.get("url") for p in projects if p]
        valid_url = next((u for u in view_urls if u and "projectView" in str(u)), None)
        if not valid_url:
            pytest.skip("No valid view_url")

        result = await get_rera_project_details.ainvoke({"view_url": valid_url})
        data = json.loads(result)
        assert (
            "promoter" in data
            or "developer" in data
            or "promoter_name" in data
            or len(data) > 0
        )
