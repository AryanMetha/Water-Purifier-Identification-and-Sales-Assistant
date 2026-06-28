import os
import requests
#from serpapi import GoogleSearch
import serpapi
# ========= CONFIG =========
# 1) Put your keys here or as env vars SERPAPI_API_KEY and IMGBB_API_KEY
SERPAPI_API_KEY = ""
IMGBB_API_KEY = ""

# 2) Path to the local image you want to test
LOCAL_IMAGE_PATH = "C:\Misc_progs\RO\Image\Screenshot 2026-02-28 185633.png"
# ==========================

#3


def upload_to_imgbb(image_path: str, api_key: str) -> str:
    with open(image_path, "rb") as f:
        payload = {"key": api_key}
        files = {"image": f}
        resp = requests.post("https://api.imgbb.com/1/upload", data=payload, files=files)
        resp.raise_for_status()
        data = resp.json()
        return data["data"]["url"]


def reverse_image_search(image_url: str, api_key: str) -> dict:
    """
    Use SerpApi's REST API directly for google_reverse_image.
    Docs: https://serpapi.com/google-reverse-image
    """
    params = {
        "engine": "google_reverse_image",
        "image_url": image_url,
        "api_key": api_key,
    }
    resp = requests.get("https://serpapi.com/search", params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def main():
    if SERPAPI_API_KEY == "YOUR_SERPAPI_API_KEY":
        raise RuntimeError("Set SERPAPI_API_KEY env var or edit the script.")
    if IMGBB_API_KEY == "YOUR_IMGBB_API_KEY":
        raise RuntimeError("Set IMGBB_API_KEY env var or edit the script.")
    if not os.path.exists(LOCAL_IMAGE_PATH):
        raise FileNotFoundError(f"Image not found: {LOCAL_IMAGE_PATH}")

    print(f"Uploading {LOCAL_IMAGE_PATH} to imgbb...")
    image_url = upload_to_imgbb(LOCAL_IMAGE_PATH, IMGBB_API_KEY)
    print("Public image URL:", image_url)

    print("Calling SerpApi google_reverse_image...")
    results = reverse_image_search(image_url, SERPAPI_API_KEY)

    search_url = results.get("search_metadata", {}).get("google_reverse_image_url")
    print("\nGoogle reverse image search URL:", search_url)

    image_results = results.get("image_results", [])
    print(f"\nFound {len(image_results)} image_results")

    for i, ir in enumerate(image_results[:10], start=1):
        title = ir.get("title")
        link = ir.get("link")
        source = ir.get("source")
        print(f"\nResult #{i}")
        print("Title :", title)
        print("Source:", source)
        print("Link  :", link)


if __name__ == "__main__":
    main()
