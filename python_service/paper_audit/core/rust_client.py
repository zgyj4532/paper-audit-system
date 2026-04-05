from __future__ import annotations

import httpx

from ..config import settings


def _base_url() -> str:
    return f"http://127.0.0.1:{settings.RUST_HTTP_PORT}"


async def health() -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{_base_url()}/health", timeout=10.0)
        response.raise_for_status()
        return response.json()


async def parse(file_path: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_base_url()}/parse",
            json={
                "input_path": file_path,
                "options": {
                    "extract_styles": True,
                    "compute_coordinates": True,
                    "extract_images": False,
                },
            },
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()


async def annotate(
    original_path: str, issues: list, output_filename: str | None = None
) -> dict:
    async with httpx.AsyncClient() as client:
        payload = {
            "original_path": original_path,
            "issues": issues,
        }
        if output_filename:
            payload["output_filename"] = output_filename
        response = await client.post(
            f"{_base_url()}/annotate",
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()
