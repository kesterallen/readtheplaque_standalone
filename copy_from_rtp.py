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


#base_url = "https://readtheplaque-standalone.fly.dev"
base_url = "http://127.0.0.1:5000"  # N.B. no httpS

rtp_geojson_filename = "./plaques.geojson"
with open(rtp_geojson_filename) as geojson_file:
    rtp_data = json.load(geojson_file)

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


now = datetime.datetime.now(datetime.UTC),
url = f"{base_url}/submit"
approve_url = f"{base_url}/admin/approve/all"

results = {
    "uploaded": dict(),  # slug -> response
    "problem": dict(),
}

#for i, rtp_plaque in enumerate([rtp_data["features"][i] for i in match_indices]):
NUM_PLAQUES = 20
for i, rtp_plaque in enumerate(random.choices(rtp_data["features"], k=NUM_PLAQUES)):
#for i, rtp_plaque in enumerate(reversed(rtp_data["features"][:10])):
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
            response = requests.post(url, data=data, files=files)
        os.remove(img_filename)

        result_key = "uploaded" if response.status_code == 200 else "problem"
        result_value = response
    except (RequestException, JSONDecodeError) as e:
        result_key = "problem"
        result_value = e

    results[result_key][slug] = result_value

response = requests.get(approve_url)


print("")
print("Results:")
for status, result in results.items():
    print(f"    {status}: {len(result)}")
    for url, reason in result.items():
        print(f"        {reason} -- {url}")

print("Summary:")
for status, result in results.items():
    print(f"    {status}: {len(result)}")
