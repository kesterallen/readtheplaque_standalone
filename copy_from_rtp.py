
import datetime
import glob
import json
import random
import requests
import time

my_path = "/home/kester/Pictures"
pictures = glob.glob(f"{my_path}/**/*.jpg", recursive=True)

rtp_geojson = "./plaques.geojson"
with open(rtp_geojson) as file:
    rtp_data = json.load(file)

now = datetime.datetime.now()
base_url = "https://readtheplaque-standalone.fly.dev"
url = f"{base_url}/submit"
approve_url = f"{base_url}/admin/approve/all"
fields = ("slug", "title", "description", "latitude", "longitude")

for rtp_plaque in random.choices(rtp_data["features"], k=50):
    props = rtp_plaque["properties"]

    slug = props["title_page_url"].split("/")[2]
    title = props["title"]
    description = props.get("description", "")
    latitude = rtp_plaque["geometry"]["coordinates"][1]
    longitude = rtp_plaque["geometry"]["coordinates"][0]

    image_filename = random.choice(pictures)
    print(slug, image_filename)
    with open(image_filename, "rb") as file:
        seed = (slug, title, description, latitude, longitude)
        files = {"images": (image_filename, file)}
        response = requests.post(url, data=dict(zip(fields, seed)), files=files)
        print(response)
        time.sleep(30)

response = requests.get(approve_url)
