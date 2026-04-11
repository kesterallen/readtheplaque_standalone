
import datetime
import requests
import random
import json

rtp_geojson = "./plaques.geojson"
with open(rtp_geojson) as file:
    rtp_data = json.load(file)

now = datetime.datetime.now()
url = "http://127.0.0.1:5000/submit"
approve_url = "http://127.0.0.1:5000/admin/approve/all"
fields = ("slug", "title", "description", "latitude", "longitude")

for rtp_plaque in random.choices(rtp_data["features"], k=50):
    props = rtp_plaque["properties"]

    slug = props["title_page_url"].split("/")[2]
    title = props["title"]
    description = props.get("description", "")
    print(slug, description)
    latitude = rtp_plaque["geometry"]["coordinates"][1]
    longitude = rtp_plaque["geometry"]["coordinates"][0]

    image_filename = "/mnt/c/Users/CIAE/OneDrive - Novonesis/Pictures/Screenshots/Screenshot 2025-05-08 142354.png"
    with open(image_filename, "rb") as file:
        seed = (slug, title, description, latitude, longitude)
        files = {"images": (image_filename, file)}
        response = requests.post(url, data=dict(zip(fields, seed)), files=files)

response = requests.get(approve_url)
