
import datetime
import glob
import json
import os
import random
import requests
import time
import urllib.request

#base_url = "https://readtheplaque-standalone.fly.dev"
base_url = "http://127.0.0.1:5000" # N.B. no httpS

rtp_geojson = "./plaques.geojson"
with open(rtp_geojson) as file:
    rtp_data = json.load(file)

now = datetime.datetime.now()
url = f"{base_url}/submit"
approve_url = f"{base_url}/admin/approve/all"
fields = ("slug", "title", "description", "latitude", "longitude", "updated_by", "updated_on", "created_by", "created_on")

for rtp_plaque in random.choices(rtp_data["features"], k=5):
# for i, rtp_plaque in enumerate(reversed(rtp_data["features"])):
    # Load from geojson
    props = rtp_plaque["properties"]
    slug = props["title_page_url"].split("/")[2]
    title = props["title"]
    latitude = rtp_plaque["geometry"]["coordinates"][1]
    longitude = rtp_plaque["geometry"]["coordinates"][0]

    # Load from readtheplaque.com
    response = requests.get(f"https://readtheplaque.com/dict/full/{slug}")
    plaque_props = response.json()["features"][0]["properties"]
    description = plaque_props["description"]
    img_url = plaque_props["img_url"]
    img_rot = plaque_props["img_rot"]
    updated_by = plaque_props["updated_by"]
    updated_at = plaque_props["updated_on"]
    created_by = plaque_props["created_by"]
    created_at = plaque_props["created_on"]
    # TODO TAGS SHOULD BE COMMA-SEP STRING HERE tags = response.json()["features"][0]["properties"]["tags"]
    img_filename = f"/tmp/{slug}.jpg"
    urllib.request.urlretrieve(img_url, img_filename)

    # TODO: update /submit endpoint to allow created_at and updated_at to be submitted?

    with open(img_filename, "rb") as file:
        seed = (slug, title, description, latitude, longitude, updated_by, updated_on, created_by, created_on)
        files = {"images": (img_filename, file)}
        response = requests.post(url, data=dict(zip(fields, seed)), files=files)
        print(slug, response)
        time.sleep(30)

    os.remove(img_filename)

response = requests.get(approve_url)
