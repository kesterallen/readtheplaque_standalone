
import json
from pathlib import Path
import random
import requests
import urllib.request

NUM_IMPORT = 10

def download_tmp_file_unless_present(url, slug):
    filename = f"{slug}.jpg"
    if not Path(filename).is_file():
        urllib.request.urlretrieve(url, filename)
    return filename

def get_rtp_info(slug):
    url = f"http://readtheplaque.com/dict/full/{slug}"
    response = requests.get(url)
    rtp_plaque = response.json()["features"][0]["properties"]

    description = rtp_plaque["description"]
    img_url = rtp_plaque["img_url"]
    #updated_on = rtp_plaque["updated_on"]
    updated_on = ""
    tags = rtp_plaque["tags"]
    return description, img_url, updated_on, tags

with open("../../Dropbox/gcloud/projects/read-the-plaque/static/plaques.geojson") as geojson:
    plaques = json.load(geojson)

    for plaque in random.choices(plaques["features"], k=NUM_IMPORT):
        props = plaque["properties"]

        slug = props["title_page_url"].split("/")[-1]
        description, img_url, updated_on, tags = get_rtp_info(slug)

        data = dict(
            slug=slug,
            title=props["title"],
            description=description,
            location="", # skip. Remove?
            latitude=plaque["geometry"]["coordinates"][1],
            longitude=plaque["geometry"]["coordinates"][0],
            updated_on=updated_on,
            tags=tags,
        )

        image_filename = download_tmp_file_unless_present(img_url, slug)
        files = {"image": (image_filename, open(image_filename, "rb"))}
        url = "http://127.0.0.1:5000/submit"
        response = requests.post(url, data=data, files=files)

        try:
            Path(image_filename).unlink()
        except FileNotFoundError:
            print(f"File '{image_filename}' not found.")
