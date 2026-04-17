
import datetime
import random
import requests
import pathlib

fields = ("slug", "title", "description", "latitude", "longitude")
seed_data = [
    ('alamo-san-antonio', 'The Alamo', 'HERE ON THIS SITE IN 1836 THE DEFENDERS OF THE ALAMO MADE THEIR HEROIC STAND FOR TEXAS INDEPENDENCE', 29.426, -98.4861, 'sample_alamo.jpg', 'admin'),
    ('liberty-bell-philadelphia', 'Liberty Bell', 'PROCLAIM LIBERTY THROUGHOUT ALL THE LAND UNTO ALL THE INHABITANTS THEREOF — Leviticus XXV:X', 39.9496, -75.1503, 'sample_liberty.jpg', 'admin'),
    ('golden-gate-dedication', 'Golden Gate Bridge', 'THIS BRIDGE, A SYMBOL OF HUMAN INGENUITY AND PERSEVERANCE, WAS COMPLETED MAY 27, 1937', 37.8199, -122.4783, 'sample_goldengate.jpg', 'admin'),
    ('ellis-island-memorial', 'Ellis Island', 'THROUGH THESE DOORS PASSED MORE THAN 12 MILLION IMMIGRANTS IN SEARCH OF FREEDOM AND A NEW LIFE', 40.6995, -74.0397, 'sample_ellis.jpg', 'admin'),
    ('lincoln-memorial-dc', 'Lincoln Memorial', 'IN THIS TEMPLE, AS IN THE HEARTS OF THE PEOPLE FOR WHOM HE SAVED THE UNION, THE MEMORY OF ABRAHAM LINCOLN IS ENSHRINED FOREVER', 38.8893, -77.0502, 'sample_lincoln.jpg', 'admin'),
    ('space-needle-seattle', 'Space Needle', "BUILT FOR THE 1962 WORLD'S FAIR, THIS STRUCTURE STANDS AS A SYMBOL OF SEATTLE'S SPIRIT AND INNOVATION", 47.6205, -122.3493, 'sample_needle.jpg', 'admin'),
    ('eiffel-tower-paris', 'Eiffel Tower', "CONSTRUITE DE 1887 À 1889 PAR GUSTAVE EIFFEL POUR L'EXPOSITION UNIVERSELLE", 48.8584, 2.2945, 'sample_eiffel.jpg', 'admin'),
    ('big-ben-london', 'Big Ben', "THE CLOCK TOWER OF THE PALACE OF WESTMINSTER, RENAMED ELIZABETH TOWER IN 2012 TO MARK THE QUEEN'S DIAMOND JUBILEE", 51.5007, -0.1246, 'sample_bigben.jpg', 'admin'),
    ('colosseum-rome', 'Colosseum', 'THE FLAVIAN AMPHITHEATRE, COMPLETED IN 80 AD UNDER EMPEROR TITUS, COULD HOLD UP TO 80,000 SPECTATORS', 41.8902, 12.4922, 'sample_colosseum.jpg', 'admin'),
    ('great-wall-china', 'Great Wall of China', 'BUILT AND REBUILT FROM THE 7TH CENTURY BC TO THE 16TH CENTURY AD TO PROTECT CHINA FROM INVASIONS', 40.4319, 116.5704, 'sample_greatwall.jpg', 'admin'),
    ('sydney-opera-house', 'Sydney Opera House', 'DESIGNED BY JØRN UTZON AND OPENED BY QUEEN ELIZABETH II ON OCTOBER 20, 1973', -33.8568, 151.2153, 'sample_sydney.jpg', 'admin'),
    ('machu-picchu-peru', 'Machu Picchu', 'BUILT IN THE 15TH CENTURY BY THE INCA EMPEROR PACHACUTI, REDISCOVERED BY HIRAM BINGHAM IN 1911', -13.1631, -72.545, 'sample_machu.jpg', 'admin'),
    ('taj-mahal-agra', 'Taj Mahal', 'BUILT BY EMPEROR SHAH JAHAN IN MEMORY OF HIS WIFE MUMTAZ MAHAL, COMPLETED IN 1643', 27.1751, 78.0421, 'sample_taj.jpg', 'admin'),
    ('statue-of-liberty', 'Statue of Liberty', 'GIVE ME YOUR TIRED, YOUR POOR, YOUR HUDDLED MASSES YEARNING TO BREATHE FREE', 40.6892, -74.0445, 'sample_liberty2.jpg', 'admin'),
    ('mount-rushmore', 'Mount Rushmore', 'DEDICATED 1941 — COMMEMORATING THE BIRTH, GROWTH, AND PRESERVATION OF THIS NATION', 43.8791, -103.4591, 'sample_rushmore.jpg', 'admin'),
    ('acropolis-athens', 'Acropolis of Athens', 'SYMBOL OF DEMOCRACY AND THE GOLDEN AGE OF CLASSICAL GREECE, CONSTRUCTION BEGAN UNDER PERICLES IN 447 BC', 37.9715, 23.7257, 'sample_acropolis.jpg', 'admin'),
    ('angkor-wat-cambodia', 'Angkor Wat', 'CONSTRUCTED IN THE EARLY 12TH CENTURY BY SURYAVARMAN II, THE LARGEST RELIGIOUS MONUMENT IN THE WORLD', 13.4125, 103.867, 'sample_angkor.jpg', 'admin'),
    ('christ-redeemer-rio', 'Christ the Redeemer', 'INAUGURATED ON OCTOBER 12, 1931, THIS ART DECO STATUE STANDS 30 METRES TALL ATOP CORCOVADO MOUNTAIN', -22.9519, -43.2105, 'sample_christ.jpg', 'admin'),
    ('petra-jordan', 'Petra', 'THE ROSE-RED CITY HALF AS OLD AS TIME — CARVED INTO ROCK BY THE NABATAEAN KINGDOM FROM THE 4TH CENTURY BC', 30.3285, 35.4444, 'sample_petra.jpg', 'admin'),
    ('chichen-itza-mexico', 'Chichén Itzá', 'EL CASTILLO WAS BUILT BY THE MAYA CIVILIZATION AS A TEMPLE TO KUKULCAN, CIRCA 800–900 AD', 20.6843, -88.5678, 'sample_chichen.jpg', 'admin'),
    ('stonehenge-england', 'Stonehenge', "ERECTED BETWEEN 3000 AND 1500 BC, ITS PURPOSE REMAINS ONE OF HISTORY'S GREAT MYSTERIES", 51.1789, -1.8262, 'sample_stonehenge.jpg', 'admin'),
    ('parthenon-athens', 'The Parthenon', 'DEDICATED TO ATHENA PARTHENOS, GODDESS OF WISDOM, COMPLETED IN 432 BC UNDER THE SUPERVISION OF PHIDIAS', 37.9714, 23.7267, 'sample_parthenon.jpg', 'admin'),
    ('versailles-palace', 'Palace of Versailles', 'TRANSFORMED BY LOUIS XIV INTO THE MOST SPLENDID ROYAL RESIDENCE IN EUROPE, SEAT OF FRENCH GOVERNMENT 1682–1789', 48.8049, 2.1204, 'sample_versailles.jpg', 'admin'),
    ('alhambra-granada', 'The Alhambra', 'BUILT PRIMARILY IN THE 13TH AND 14TH CENTURIES, A MASTERPIECE OF MOORISH ARCHITECTURE AND ISLAMIC ART', 37.176, -3.5881, 'sample_alhambra.jpg', 'admin'),
    ('sagrada-familia-barcelona', 'Sagrada Família', 'DESIGNED BY ANTONI GAUDÍ, CONSTRUCTION BEGAN IN 1882 AND CONTINUES TO THIS DAY — A TESTAMENT TO HUMAN DEVOTION', 41.4036, 2.1744, 'sample_sagrada.jpg', 'admin'),
    ('tower-of-london', 'Tower of London', 'FOUNDED IN 1066 BY WILLIAM THE CONQUEROR, SERVING AS ROYAL PALACE, FORTRESS, PRISON, AND TREASURY', 51.5081, -0.0759, 'sample_tower.jpg', 'admin'),
    ('forbidden-city-beijing', 'The Forbidden City', 'BUILT BETWEEN 1406 AND 1420, SERVED AS THE HOME OF 24 EMPERORS OF THE MING AND QING DYNASTIES', 39.9163, 116.3972, 'sample_forbidden.jpg', 'admin'),
    ('notre-dame-paris', 'Notre-Dame de Paris', 'CONSTRUCTION BEGAN IN 1163 UNDER BISHOP MAURICE DE SULLY. ONE OF THE FINEST EXAMPLES OF FRENCH GOTHIC ARCHITECTURE', 48.853, 2.3499, 'sample_notredame.jpg', 'admin'),
    ('hagia-sophia-istanbul', 'Hagia Sophia', 'COMPLETED IN 537 AD UNDER EMPEROR JUSTINIAN I. CATHEDRAL, MOSQUE, AND NOW MUSEUM — WITNESS TO 1500 YEARS OF HISTORY', 41.0086, 28.9802, 'sample_hagia.jpg', 'admin'),
    ('st-peters-vatican', "St. Peter's Basilica", 'THE LARGEST CHURCH IN THE WORLD, BUILT OVER THE TOMB OF SAINT PETER. MICHELANGELO DESIGNED ITS ICONIC DOME IN 1547', 41.9022, 12.4539, 'sample_stpeters.jpg', 'admin'),
    ('westminster-abbey', 'Westminster Abbey', 'FOUNDED IN 960 AD, SITE OF ROYAL CORONATIONS SINCE 1066 AND RESTING PLACE OF MONARCHS, POETS, AND SCIENTISTS', 51.4994, -0.1273, 'sample_westminster.jpg', 'admin'),
    ('mont-saint-michel', 'Mont Saint-Michel', 'THE ABBEY WAS FOUNDED IN 708 AD BY BISHOP AUBERT OF AVRANCHES FOLLOWING A VISION OF THE ARCHANGEL MICHAEL', 48.6361, -1.5115, 'sample_montmichel.jpg', 'admin'),
    ('kremlin-moscow', 'The Moscow Kremlin', 'THE ORIGINAL WOODEN KREMLIN WAS BUILT IN 1156. THE PRESENT WALLS DATE FROM 1485–1495 UNDER IVAN THE GREAT', 55.752, 37.6175, 'sample_kremlin.jpg', 'admin'),
    ('empire-state-building', 'Empire State Building', "OPENED MAY 1, 1931. BUILT IN JUST 410 DAYS, IT STOOD AS THE WORLD'S TALLEST BUILDING FOR 40 YEARS", 40.7484, -73.9857, 'sample_empire.jpg', 'admin'),
    ('burj-khalifa-dubai', 'Burj Khalifa', 'OPENED JANUARY 4, 2010. AT 828 METRES, THE TALLEST STRUCTURE EVER BUILT BY HUMAN HANDS', 25.1972, 55.2744, 'sample_burj.jpg', 'admin'),
    ('hoover-dam', 'Hoover Dam', 'DEDICATED SEPTEMBER 30, 1935 BY PRESIDENT FRANKLIN D. ROOSEVELT. BUILT BY 21,000 WORKERS IN THE HEART OF THE MOJAVE', 36.016, -114.7377, 'sample_hoover.jpg', 'admin'),
]

now = datetime.datetime.now()
url = "http://127.0.0.1:5000/submit"
approve_url = "http://127.0.0.1:5000/admin/approve/all"

num_dups = 3

image_dir = pathlib.Path("/mnt/c/Users/CIAE/OneDrive - Novonesis/Pictures/Screenshots/")
image_filenames = [f for f in image_dir.iterdir() if f.is_file()]

for i in range(num_dups):
    print(f"{i} / {num_dups}")
    for seed in seed_data:
        image_filename = str(random.choice(image_filenames))
        with open(image_filename, "rb") as file:
            files = {"images": (image_filename, file)}
            response = requests.post(url, data=dict(zip(fields, seed)), files=files)

response = requests.get(approve_url)
