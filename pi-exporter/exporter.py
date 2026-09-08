"""Optional local-file exporter: apply filters before crossing the radio link.

Run on the receiver with read-only access to its decoded JSON directory.
No decoder changes, credentials, external services, or broker required.
"""
import argparse
import gzip
import http.server
import json
import math
from pathlib import Path
import urllib.parse

def distance_nm(lat1,lon1,lat2,lon2):
    lat1,lon1,lat2,lon2=map(math.radians,(lat1,lon1,lat2,lon2))
    a=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 3440.065*2*math.asin(min(1,math.sqrt(a)))

def filtered(data,receiver,altitude=None,radius=None):
    result=[]
    for ac in data['aircraft']:
        alt=ac.get('alt_baro',ac.get('altitude'))
        # Unknown altitude/position are retained, rather than silently treated as zero.
        if altitude is not None and isinstance(alt,(int,float)) and alt>altitude: continue
        if radius is not None and all(k in ac for k in ('lat','lon')):
            if distance_nm(receiver['lat'],receiver['lon'],ac['lat'],ac['lon'])>radius: continue
        result.append(ac)
    return data | {'aircraft':result}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir',required=True,type=Path)
    p.add_argument('--bind',default='127.0.0.1')
    p.add_argument('--port',default=8097,type=int)
    p.add_argument('--allow-client',required=True,help='HA-side source IP as seen by this receiver')
    p.add_argument('--max-altitude',type=float)
    p.add_argument('--radius-nm',type=float)
    args=p.parse_args()
    def read(name):
        with (args.source_dir/name).open('rb') as f: body=f.read(8*1024*1024+1)
        if len(body)>8*1024*1024: raise ValueError('source too large')
        return json.loads(body)
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.client_address[0]!=args.allow_client:
                self.send_error(403);return
            path=urllib.parse.urlsplit(self.path).path
            if path not in ('/data/aircraft.json','/data/receiver.json'):
                self.send_error(404);return
            try:
                receiver=read('receiver.json')
                data=receiver if path.endswith('/receiver.json') else filtered(read('aircraft.json'),receiver,args.max_altitude,args.radius_nm)
                body=json.dumps(data,separators=(',',':'),allow_nan=False).encode()
                compressed='gzip' in self.headers.get('Accept-Encoding','')
                if compressed: body=gzip.compress(body,compresslevel=3,mtime=0)
            except (OSError,ValueError,KeyError,TypeError): self.send_error(503);return
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store')
            self.send_header('Vary','Accept-Encoding')
            if compressed:self.send_header('Content-Encoding','gzip')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)
        def log_message(self,*_):pass
    http.server.ThreadingHTTPServer((args.bind,args.port),Handler).serve_forever()

if __name__=='__main__':main()
