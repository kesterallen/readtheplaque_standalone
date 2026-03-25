
import json
from pathlib import Path
import random
import requests
import urllib.request

"""
get json with e.g.
     curl -s http://readtheplaque.com/dict/full/peak-district-national-park-footpath-to-open-country
"""

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

with open("rtp_plaques.geojson") as file:
    plaques = json.load(file)

    for plaque in random.choices(plaques["features"], k=10):
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



#curl -X POST http://localhost:5000/submit \
#  -F "title=My Plaque Title" \
#  -F "description=THE TEXT ON THE PLAQUE" \
#  -F "location=Boston, MA" \
#  -F "latitude=42.3601" \
#  -F "longitude=-71.0589" \
#  -F "submitted_by=yourname" \
#  -F "image=@/path/to/photo.jpg;type=image/jpeg"
#
#
#
#
#
#
#
#
#demo_json = """
#{
#  "type": "FeatureCollection",
#  "features": [
#    {
#      "geometry": {
#        "type": "Point",
#        "coordinates": [
#          -1.8008607,
#          53.3701441
#        ]
#      },
#      "type": "Feature",
#      "properties": {
#        "img_url_tiny": "http://lh3.googleusercontent.com/er9TznDC4OFllcke8OASdB_ndMupPxy7UpFrn_SfayZdeGpiFXHYjePcAMpwJCn3SmojqtVaaIQlfO873WE1IOKtLqC5lQ",
#        "title_page_url": "/plaque/peak-district-national-park-footpath-to-open-country",
#        "title": "Peak District National Park Footpath to Open Country",
#        "key": "ag9yZWFkLXRoZS1wbGFxdWVyJQsSBlBsYXF1ZSIGcHVibGljDAsSBlBsYXF1ZRiAgID87aSKCgw",
#        "description": "          \r\n<br/> PEAK DISTRICT NATIONAL PARK\r\n <br/> FOOTPATH\r\n <br/> TO OPEN COUNTRY\r\n <br/> PLEASE KEEP TO THE PATH\r\n <br/> UNTIL SIGN IS REACHED MARKING\r\n <br/> BOUNDARY OF OPEN COUNTRY\r\n <br/> PEAK PARK PLANNING BOARD\r\n <br/> D. G. GILMAN,\r\n <br/> ALDERN HOUSE, BAKEWELL,\r\n <br/> CLERK.\r\n <br/> \r\n <br/>Submitted by <a href=\"https://twitter.com/peak_chair\">@peak_chair</a>\r\n <br/>(The plaque is half a mile east of Edale village, on a public footpath near Woodhouse Farm,  approx grid ref SK133859.)\r\n          \r\n          ",
#        "img_url": "http://lh3.googleusercontent.com/er9TznDC4OFllcke8OASdB_ndMupPxy7UpFrn_SfayZdeGpiFXHYjePcAMpwJCn3SmojqtVaaIQlfO873WE1IOKtLqC5lQ",
#        "tags": [
#          "footpath",
#          "open country",
#          "peak_chair"
#        ]
#      }
#    }
#  ],
#  "updated_on": "2026-03-24 15:39:13.902205"
#}
#"""
#
#demo_sql = """
#          id = 36
#        slug = hoover-dam
#       title = Hoover Dam
# description = DEDICATED SEPTEMBER 30, 1935 BY PRESIDENT FRANKLIN D. ROOSEVELT. BUILT BY 21,000 WORKERS IN THE HEART OF THE MOJAVE
#    location = Nevada/Arizona, USA
#    latitude = 36.016
#   longitude = -114.7377
#  image_file = sample_hoover.jpg
#  thumb_file =
#submitted_by = admin
#    approved = 1
# is_featured = 0
#  created_at = 2026-03-24T15:20:43.692786
#"""
#
#
