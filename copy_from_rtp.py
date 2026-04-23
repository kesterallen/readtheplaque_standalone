# examplar pages:
#     tags:
#          /crater-principal-del-volcan-poas (i=0, no tags) -> [[]]
#          /menehune-ditch (i=32, three tags) -> [['menehune ditch', 'waimea', 'kauai']]
#          /mike-haggerty-plaza (i=330, one tag) -> [['the mike']]

import datetime
import glob
import json
import os
import random
import requests
from requests.exceptions import RequestException
import time
import urllib.request

# base_url = "https://readtheplaque-standalone.fly.dev"
base_url = "http://127.0.0.1:5000"  # N.B. no httpS

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

#for rtp_plaque in [
    #rtp_data["features"][0],
    #rtp_data["features"][32],
    #rtp_data["features"][330],
#]:
NUM_PLAQUES = 30
for rtp_plaque in random.choices(rtp_data["features"], k=NUM_PLAQUES):
    # for i, rtp_plaque in enumerate(reversed(rtp_data["features"])):

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
    print(f"Copying {slug} from {rtp_url} to {base_url}")

    response = requests.get(rtp_url)
    plaque_props = response.json()["features"][0]["properties"]
    description = plaque_props["description"]
    img_url = plaque_props["img_url"]
    updated_at = plaque_props["updated_on"]
    submitted_by = plaque_props["created_by"]
    created_at = plaque_props["created_on"]
    tags = ", ".join(plaque_props["tags"][0])
    img_filename = f"/tmp/{slug}.jpg"
    urllib.request.urlretrieve(img_url, img_filename)

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
    except RequestException as e:
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
