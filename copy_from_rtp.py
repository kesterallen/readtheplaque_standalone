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
import time
import urllib.request

# base_url = "https://readtheplaque-standalone.fly.dev"
base_url = "http://127.0.0.1:5000"  # N.B. no httpS

rtp_geojson_filename = "./plaques.geojson"
with open(rtp_geojson_filename) as geojson_file:
    rtp_data = json.load(geojson_file)

# for i, feature in enumerate(rtp_data["features"]):
# props = feature["properties"]
# if props["title_page_url"] == "/plaque/mike-haggerty-plaza":
# print(f"{i}, {props}")

now = datetime.datetime.now()
url = f"{base_url}/submit"
approve_url = f"{base_url}/admin/approve/all"

results = {
    "uploaded_plaques": dict(),  # slug -> response
    "skipped_plaques": dict(),
}

for rtp_plaque in [
    rtp_data["features"][0],
    rtp_data["features"][32],
    rtp_data["features"][330],
]:
    # for rtp_plaque in random.choices(rtp_data["features"], k=5):
    # for i, rtp_plaque in enumerate(reversed(rtp_data["features"])):
    # Load from geojson
    props = rtp_plaque["properties"]

    slug = props["title_page_url"].split("/")[2]
    if slug in results["uploaded_plaques"]:
        results["skipped_plaques"][slug] = "skipped"
        continue

    print(slug)
    title = props["title"]
    latitude = rtp_plaque["geometry"]["coordinates"][1]
    longitude = rtp_plaque["geometry"]["coordinates"][0]

    # Load from readtheplaque.com
    response = requests.get(f"https://readtheplaque.com/dict/full/{slug}")
    plaque_props = response.json()["features"][0]["properties"]
    description = plaque_props["description"]
    img_url = plaque_props["img_url"]
    # img_rot = plaque_props["img_rot"]
    updated_at = plaque_props["updated_on"]
    submitted_by = plaque_props["created_by"]
    created_at = plaque_props["created_on"]
    tags = ", ".join(plaque_props["tags"][0])
    img_filename = f"/tmp/{slug}.jpg"
    urllib.request.urlretrieve(img_url, img_filename)

    # TODO: update / submit endpoint to allow created_at and updated_at to be submitted?

    with open(img_filename, "rb") as img_file:
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
        files = {"images": (img_filename, img_file)}
        response = requests.post(url, data=data, files=files)
        print(slug, response)
        results["uploaded_plaques"][slug] = response

    os.remove(img_filename)

response = requests.get(approve_url)
print(results)
print("")
for status, result in results.items():
    print(f"{status}: {len(result)}")
