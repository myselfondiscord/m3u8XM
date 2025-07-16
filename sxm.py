import argparse
import requests
import base64
import urllib.parse
import json
import time, datetime
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
import configparser
config = configparser.ConfigParser()

class SiriusXM:
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'
    REST_FORMAT = 'https://api.edge-gateway.siriusxm.com/{}'
    CDN_URL = "https://imgsrv-sxm-prod-device.streaming.siriusxm.com/{}"

    def __init__(self, username, password):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.USER_AGENT})
        self.username = username
        self.password = password
        self.playlists = {}
        self.channels = None
        self.m3u8dat = None
        self.channel_urls = {}

    @staticmethod
    def log(x):
        print('{} <SiriusXM>: {}'.format(datetime.datetime.now().strftime('%d.%b %Y %H:%M:%S'), x))


    #TODO: Figure out if authentication is a valid method anymore. It might need a new login each time.
    def is_logged_in(self):
        return 'Authorization' in self.session.headers

    def is_session_authenticated(self):
        return 'Authorization' in self.session.headers
    
    def sfetch(self, url):
        res = self.session.get(url)
        if res.status_code != 200:
            self.log("Failed to recieve stream data.")
            return None
        return res.content

    def get(self, method, params={}, authenticate=True):
        if authenticate and not self.is_session_authenticated() and not self.authenticate():
            self.log('Unable to authenticate')
            return None

        res = self.session.get(self.REST_FORMAT.format(method), params=params)
        if res.status_code != 200:
            if res.status_code == 401:
                self.authenticate()
            self.log('Received status code {} for method \'{}\''.format(res.status_code, method))
            return None

        try:
            return res.json()
        except ValueError:
            self.log('Error decoding json for method \'{}\''.format(method))
            return None

    def post(self, method, postdata, authenticate=True, headers={}):
        if authenticate and not self.is_session_authenticated() and not self.authenticate():
            self.log('Unable to authenticate')
            return None

        res = self.session.post(self.REST_FORMAT.format(method), data=json.dumps(postdata),headers=headers)
        if res.status_code != 200 and res.status_code != 201:
            if res.status_code == 401:
                self.authenticate()
            self.log('Received status code {} for method \'{}\''.format(res.status_code, method))
            return None

        resjson = res.json()
        bearer_token = resjson["grant"] if "grant" in resjson else resjson["accessToken"] if "accessToken" in resjson else None
        if bearer_token != None:
            self.session.headers.update({"Authorization": f"Bearer {bearer_token}"})

        try:
            return resjson
        except ValueError:
            self.log('Error decoding json for method \'{}\''.format(method))
            return None

    def login(self):
        # Four layer process
        # Assuming the login can work separate from Auth, this is split into two connections:
        # 1) device acknowledge
        # 2) grant anonymous permission
        # The following is reserved for Authentication:
        # Login
        # Affirm Authentication

        postdata = {
            'devicePlatform': "web-desktop",
            'deviceAttributes': {
                'browser': {
                    'browserVersion': "7.74.0",
                    'userAgent': self.USER_AGENT,
                    'sdk': 'web',
                    'app': 'web',
                    'sdkVersion': "7.74.0",
                    'appVersion': "7.74.0"
                }
            },
            'grantVersion': 'v2'
        }
        sxmheaders = {
            "x-sxm-tenant":"sxm" # required, but not used everywhere
        }
        data = self.post('device/v1/devices', postdata, authenticate=False,headers=sxmheaders)
        if not data:
            self.log("Error creating device session:",data)
            return False
        
        #try:
        #    return data['grant'] == True and self.is_logged_in()
        #except KeyError:
        #    self.log('Error decoding json response for login')
        #    return False
        
        # Once device is registered, grant anonymous permissions 
        data = self.post('session/v1/sessions/anonymous', {}, authenticate=False,headers=sxmheaders)
        if not data:
            self.log("Error validating anonymous session:",data)
            return False
        try:
            return "accessToken" in data and self.is_logged_in()
        except KeyError:
            self.log('Error decoding json response for login')
            return False
        


    def authenticate(self):
        if not self.is_logged_in() and not self.login():
            self.log('Unable to authenticate because login failed')
            return False

        postdata = {
            "handle": self.username,
            "password": self.password
        }
        data = self.post('identity/v1/identities/authenticate/password', postdata, authenticate=False)
        if not data:
            return False

        
        autheddata = self.post('session/v1/sessions/authenticated', {}, authenticate=False)

        try:
            return autheddata['sessionType'] == "authenticated" and self.is_session_authenticated()
        except KeyError:
            self.log('Error parsing json response for authentication')
            return False


    def get_playlist(self):
        # Not 100% sure how this was working previously, but modern times
        # mostly fetch info via json, so we have to make the m3u8 from scratch
        # Create our own M3U8 from scratch, include all we found
        if not self.channels:
            self.get_channels()
        if not self.m3u8dat:
            data = []
            data.append("#EXTM3U")
            m3umetadata = """#EXTINF:-1 tvg-logo="{}" group-title="{}",{}\n{}"""
            for channel in self.channels:
                #TODO: Work on finding the proper M3U8 metadata needed.
                title = channel["title"]
                genre = channel["genre"]
                logo = channel["logo"]
                url = "/listen/{}".format(channel["id"])
                formattedm3udata = m3umetadata.format(logo,genre,title,url)
                data.append(formattedm3udata)
            self.m3u8dat = "\n".join(data)
        
        return self.m3u8dat

    def get_channels(self):
        # download channel list if necessary
        # todo: find out if the container ID or the UUID changes; how to auto fetch if so.
        # channel list is split up. gotta get every channel

        if not self.channels:
            self.channels = []
            # todo: this is how the web traffic processed the channels, might not be needed though
            initData = {
                "containerConfiguration": {
                    "3JoBfOCIwo6FmTpzM1S2H7": {
                        "filter": {
                            "one": {
                                "filterId": "all"
                            }
                        },
                        "sets": {
                            "5mqCLZ21qAwnufKT8puUiM": {
                                "sort": {
                                    "sortId": "CHANNEL_NUMBER_ASC"
                                }
                            }
                        }
                    }
                },
                "pagination": {
                    "offset": {
                        "containerLimit": 3,
                        "setItemsLimit": 50
                    }
                },
                "deviceCapabilities": {
                    "supportsDownloads": False
                }
            }
            data = self.post('browse/v1/pages/curated-grouping/403ab6a5-d3c9-4c2a-a722-a94a6a5fd056/view', initData)
            if not data:
                self.log('Unable to get init channel list')
                return (None, None)
            for channel in data["page"]["containers"][0]["sets"][0]["items"]:
                title = channel["entity"]["texts"]["title"]["default"]
                description = channel["entity"]["texts"]["description"]["default"]
                genre = channel["decorations"]["genre"] if "genre" in channel["decorations"] else ""
                logo = channel["entity"]["images"]["tile"]["aspect_1x1"]["preferred"]["url"]
                logo_width = channel["entity"]["images"]["tile"]["aspect_1x1"]["preferred"]["width"]
                logo_height = channel["entity"]["images"]["tile"]["aspect_1x1"]["preferred"]["height"]
                id = channel["entity"]["id"]
                jsonlogo = json.dumps({
                    "key": logo,
                    "edits":[
                        {"format":{"type":"jpeg"}},
                        {"resize":{"width":logo_width,"height":logo_height}}
                    ]
                },separators=(',', ':'))
                b64logo = base64.b64encode(jsonlogo.encode("ascii")).decode("utf-8")
                self.channels.append({
                    "title": title,
                    "description": description,
                    "genre": genre,
                    "logo":  self.CDN_URL.format(b64logo),
                    "url": "/listen/{}".format(id),
                    "id": id
                })
            channellen = data["page"]["containers"][0]["sets"][0]["pagination"]["offset"]["size"]
            for offset in range(50,channellen,50):
                postdata = {
                    "filter": {
                        "one": {
                        "filterId": "all"
                        }
                    },
                    "sets": {
                        "5mqCLZ21qAwnufKT8puUiM": {
                        "sort": {
                            "sortId": "CHANNEL_NUMBER_ASC"
                        },
                        "pagination": {
                            "offset": {
                            "setItemsOffset": offset,
                            "setItemsLimit": 50
                            }
                        }
                        }
                    },
                    "pagination": {
                        "offset": {
                        "setItemsLimit": 50
                        }
                    }
                }
                data = self.post('browse/v1/pages/curated-grouping/403ab6a5-d3c9-4c2a-a722-a94a6a5fd056/containers/3JoBfOCIwo6FmTpzM1S2H7/view', postdata, initData)
                if not data:
                    self.log('Unable to get fetch channel list chunk')
                    return (None, None)
                for channel in data["container"]["sets"][0]["items"]:
                    title = channel["entity"]["texts"]["title"]["default"]
                    description = channel["entity"]["texts"]["description"]["default"]
                    genre = channel["decorations"]["genre"] if "genre" in channel["decorations"] else ""
                    logo = channel["entity"]["images"]["tile"]["aspect_1x1"]["preferred"]["url"]
                    logo_width = channel["entity"]["images"]["tile"]["aspect_1x1"]["preferred"]["width"]
                    logo_height = channel["entity"]["images"]["tile"]["aspect_1x1"]["preferred"]["height"]
                    id = channel["entity"]["id"]
                    jsonlogo = json.dumps({
                        "key": logo,
                        "edits":[
                            {"format":{"type":"jpeg"}},
                            {"resize":{"width":logo_width,"height":logo_height}}
                        ]
                    },separators=(',', ':'))
                    b64logo = base64.b64encode(jsonlogo.encode("ascii")).decode("utf-8")
                    self.channels.append({
                        "title": title,
                        "description": description,
                        "genre": genre,
                        "logo":  self.CDN_URL.format(b64logo),
                        "url": "/listen/{}".format(id),
                        "id": id
                    })
        return self.channels

    def get_tuner(self,id):
        postdata = {
            "id":id,
            "type":"channel-linear",
            "hlsVersion":"V3",
            "manifestVariant":"WEB",
            "mtcVersion":"V2"
        }
        data = self.post('playback/play/v1/tuneSource',postdata,authenticate=True)
        if not data:
            self.log("Couldn't tune channel.")
            return False
        #TODO: add secondary cause why not
        streaminfo = {}
        primarystreamurl = data["streams"][0]["urls"][0]["url"]
        base_url, m3u8_loc = primarystreamurl.rsplit('/', 1)
        streaminfo["base_url"] = base_url
        streaminfo["sources"] = m3u8_loc
        streaminfo["chid"] = base_url.split('/')[-2]
        streamdata = self.sfetch(primarystreamurl).decode("utf-8")
        if not streamdata:
            print("Failed to fetch m3u8 stream details")
            return False
        # TODO: make this have options for other qualities (url parameter?)
        for line in streamdata.splitlines():
            if line.find("256k") > 0 and line.endswith("m3u8"):
                streaminfo["quality"] = line
                streaminfo["HLS"] = line.split("/")[0]
        self.channel_urls[id] = streaminfo
        return streaminfo

    def get_channel(self, id):
        # Hit a wall in how I wanted to implement this, but this is what I ended up doing:
        # Caching the /tuneSource url provided, and associating it to the /listen UUID
        # this prevents multiple hits to /tuneSource and more to the Streaming CDN
        # potentially speeding this part of the process up, as well as being more subtle
        # in main site web traffic.
        if not id in self.channel_urls:
            self.get_tuner(id)
        streaminfo = self.channel_urls[id]
        aacurl = "{}/{}".format(streaminfo["base_url"],streaminfo["quality"])
        # fetch the list of aac files
        data = self.sfetch(aacurl).decode("utf-8")
        if not data:
            print("failed to fetch AAC stream list")
            return False
        data = data.replace("https://api.edge-gateway.siriusxm.com/playback/key/v1/00000000-0000-0000-0000-000000000000","/key/1",1)
        lineoutput = []
        lines = data.splitlines()
        for x in range(len(lines)):
            if lines[x].rstrip().endswith('.aac'):
                lines[x] = '{}/{}'.format(id, lines[x])
        return '\n'.join(lines).encode('utf-8')

    def get_segment(self,id,seg):
        if not id in self.channel_urls:
            self.get_tuner(id)
        streaminfo = self.channel_urls[id]
        baseurl = streaminfo["base_url"]
        HLStag = streaminfo["HLS"]
        segmenturl = "{}/{}/{}".format(baseurl,HLStag,seg)
        # print("fetching seg from url:",segmenturl)
        data = self.sfetch(segmenturl)
        return data
        
    def getAESkey(self):
        data = self.get("playback/key/v1/00000000-0000-0000-0000-000000000000")
        if not data:
            self.log("AES Key fetch error.")
        return data["key"]


def make_sirius_handler(sxm):
    class SiriusHandler(BaseHTTPRequestHandler):
        HLS_AES_KEY = base64.b64decode(sxm.getAESkey())

        def do_GET(self):
            if self.path.endswith('.m3u8'):
                data = sxm.get_playlist()
                if data:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/x-mpegURL')
                    self.end_headers()
                    self.wfile.write(bytes(data, 'utf-8'))
                    return
                else:
                    self.send_response(500)
                    self.end_headers()
            elif self.path.endswith('.aac'):
                split = self.path.split("/")
                id = split[-2]
                seg = split[-1]
                data = sxm.get_segment(id,seg)
                if data:
                    self.send_response(200)
                    self.send_header('Content-Type', 'audio/x-aac')
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_response(500)
                    self.end_headers()
            elif self.path.endswith('/key/1'):
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(self.HLS_AES_KEY)
            # TODO: Add a path which works in the format of /listen/{UUID}
            # Make the M3U8 show it but only fetch the stream when clicked.
            elif self.path.startswith("/listen/"):
                data = sxm.get_channel(self.path.split('/')[-1])
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-mpegURL')
                self.end_headers()
                self.wfile.write(data)

            else:
                self.send_response(500)
                self.end_headers()
    return SiriusHandler

if __name__ == '__main__':
    config.read('config.ini')
    email = config.get("account","email")
    password = config.get("account","password")

    ip = config.get("settings","ip")
    port = int(config.get("settings","port"))
    print(ip, port)
    sxm = SiriusXM(email, password)
    httpd = HTTPServer((ip, port), make_sirius_handler(sxm))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
