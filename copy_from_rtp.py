# examplar pages:
#     tags:
#          /crater-principal-del-volcan-poas (i=0, no tags) -> [[]]
#          /menehune-ditch (i=32, three tags) -> [['menehune ditch', 'waimea', 'kauai']]
#          /mike-haggerty-plaza (i=330, one tag) -> [['the mike']]
#     "Submitted by @someone":
#          /trinity-site (i=5204) -> '<a href="https:twitter.com/wellerstein">@wellerstein</a>'
#     "Submitted via @someone":
#          /plaque-the-church-of-all-saints
#     "Submitted by @Geograph_Bob via Temple Meads to Ashton Gate (70)."
#          /from-this-port-john-cabot-and-his-son
#     "Submitted by: someone"
#          /dickerman-steele-house
#     "From the Flickr group ..."
#          /historical-marker-for-george-washington-carver
#     Plaque page not there anymore, so /dict/full returns a malformed 500 page (a message about a 500 error in a 200 response page):
#          /harold-swindells-co-founder-of-bath-postal-museum-he-enjoyed-walking-in-this-park

import bleach
from bs4 import BeautifulSoup
import datetime
import glob
import json
import os
import random
import re
import requests
from requests.exceptions import RequestException, JSONDecodeError
import time
import unicodedata
import urllib.request


DEBUG_RANDOM = "debug_random"
DEBUG_BAD_EXAMPLARS = "bad_exemplars"
FULL_UPLOAD = "full_upload"
MODES = set([DEBUG_RANDOM, DEBUG_BAD_EXAMPLARS, FULL_UPLOAD])

LOCALHOST = "http://127.0.0.1:5000"  # N.B. no httpS
PRODUCTION = "https://readtheplaque-standalone.fly.dev"
TARGETS = set([LOCALHOST, PRODUCTION])

TARGET = PRODUCTION
MODE = FULL_UPLOAD

assert TARGET in TARGETS
assert MODE in MODES


def print_results(results):
    print("")
    print("Results:")
    for status, result in results.items():
        print(f"    {status}: {len(result)}")
        for url, reason in result.items():
            print(f"        {reason} -- {url}")

    print("Summary:")
    for status, result in results.items():
        print(f"    {status}: {len(result)}")

def bad_exemplars(rtp_data):
    match_texts = [
        "/plaque/historical-marker-for-george-washington-carver",
        "/plaque/crater-principal-del-volcan-poas",
        "/plaque/menehune-ditch",
        "/plaque/mike-haggerty-plaza",
        "/plaque/trinity-site",
        "/plaque/plaque-the-church-of-all-saints",
        "/plaque/from-this-port-john-cabot-and-his-son",
        "/plaque/dickerman-steele-house",
        "/plaque/harold-swindells-co-founder-of-bath-postal-museum-he-enjoyed-walking-in-this-park",
    ]
    match_indices = []
    for match_text in match_texts:
        for i, p in enumerate(rtp_data["features"]):
            if p["properties"]["title_page_url"] == match_text:
                match_indices.append(i)

    return match_indices


def main(mode, target):
    base_url = target

    rtp_geojson_filename = "./plaques.geojson"
    with open(rtp_geojson_filename) as geojson_file:
        rtp_data = json.load(geojson_file)

    now = datetime.datetime.now(datetime.UTC),
    url = f"{base_url}/submit"
    approve_url = f"{base_url}/admin/approve/all"

    results = {
        "uploaded": dict(),  # slug -> response
        "problem": dict(),
    }

    if mode == DEBUG_RANDOM:
        NUM_PLAQUES = 20
        plaques = random.choices(rtp_data["features"], k=NUM_PLAQUES)
    elif mode == DEBUG_BAD_EXAMPLARS:
        plaques = [rtp_data["features"][i] for i in bad_exemplars(rtp_data)]
    elif mode == FULL_UPLOAD:
        plaques = reversed(rtp_data["features"])
    else:
        raise ValueError(f"mode cannot be {MODE}, allowed values are {MODES}")

    for i, rtp_plaque in enumerate(plaques):
        # Skip the plaques already done before crash on 2026-sept-16
        # slug should be plaque-campbell-house (20580/25531) on restart
        i_reverse_countdown_last_good_before_crash  = 20581
        i_reverse_countdown = len(rtp_data['features']) - i
        if i_reverse_countdown > i_reverse_countdown_last_good_before_crash:
            print(f"skipping {i_reverse_countdown} / {i_reverse_countdown_last_good_before_crash}")
            continue

        # Load from geojson
        #
        props = rtp_plaque["properties"]

        slug = props["title_page_url"].split("/")[2]
        if slug in results["uploaded"]:
            results["problem"][slug] = "duplicate slug"
            continue

        title = props["title"]
        latitude = rtp_plaque["geometry"]["coordinates"][1]
        longitude = rtp_plaque["geometry"]["coordinates"][0]

        # Load from readtheplaque.com
        #
        rtp_url = f"https://readtheplaque.com/dict/full/{slug}"
        print(f"Copying {slug} ({len(rtp_data['features']) - i}/{len(rtp_data['features'])})")

        response = requests.get(rtp_url)
        try:
            if "features" not in response.json():
                results["problem"][slug] = f"no features in response.json(): '{response.json()}'"
                continue
        except JSONDecodeError as e:
                results["problem"][slug] = f"Bad JSON from response.json()"
                time.sleep(60)
                continue

        plaque_props = response.json()["features"][0]["properties"]
        description = plaque_props["description"]
        img_url = plaque_props["img_url"]
        updated_at = plaque_props["updated_on"]
        submitted_by = plaque_props["created_by"]
        created_at = plaque_props["created_on"]
        tags = ", ".join(plaque_props["tags"][0])
        img_filename = f"/tmp/{slug}.jpg"
        urllib.request.urlretrieve(img_url, img_filename)

        # If Submitted by/via in the text of the description:
        if submitted_by == "None":
            regex = r"(Submitted (by|via)|From the Flickr group):?(.+)"
            pattern = re.compile(regex, re.IGNORECASE | re.MULTILINE)
            soup = BeautifulSoup(description, "html.parser")
            text = soup.get_text(" ", strip=True)
            if match := re.search(pattern, text):
                submitted_by = bleach.clean(match.group(3), strip=True).strip()
                # Turn accented characters into plain ASCII equivalents
                submitted_by = unicodedata.normalize("NFKD", submitted_by).encode("ascii", "ignore").decode("ascii")
                # Remove punctuation
                submitted_by = re.sub(r"[^A-Za-z0-9\s]+", " ", submitted_by)
                # Collapse repeated whitespace
                submitted_by = re.sub(r"\s+", " ", submitted_by).strip()
                if "photo by" in submitted_by:
                    submitted_by = submitted_by.split(" photo by ")[0]
                print(f"Submitted by '{submitted_by}'")
            else:
                submitted_by = None

        data = {
            "slug": slug,
            "title": title,
            "description": description,
            "latitude": latitude,
            "longitude": longitude,
            "updated_at": updated_at,
            "submitted_by": submitted_by,
            "created_at": created_at,
            "tags": tags,
        }
        try:
            with open(img_filename, "rb") as img_file:
                files = {"images": (img_filename, img_file)}
                print("posting to ", url)
                response = requests.post(url, data=data, files=files)
            os.remove(img_filename)

            result_key = "uploaded" if response.status_code == 200 else "problem"
            result_value = response
        except (RequestException, JSONDecodeError) as e:
            result_key = "problem"
            result_value = e

        results[result_key][slug] = result_value

        if i % 5 == 0:
            print_results(results)

        time.sleep(60)

    print_results(results)
    response = requests.get(approve_url)

if __name__ == "__main__":
    main(MODE, TARGET)
