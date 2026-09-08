"""Read-only bounded payload comparison; does not change receiver settings."""
import argparse
import http.client
import json
import statistics
import time
import urllib.parse

def measure(base, path, encoding, timeout):
    p=urllib.parse.urlsplit(base.rstrip('/')+path)
    cls=http.client.HTTPSConnection if p.scheme=='https' else http.client.HTTPConnection
    conn=cls(p.hostname,p.port,timeout=timeout)
    started=time.monotonic()
    try:
        conn.request('GET',p.path,headers={'Accept-Encoding':encoding})
        r=conn.getresponse()
        body=r.read(32*1024*1024+1)
        if len(body)>32*1024*1024: raise ValueError('response too large')
        return dict(path=path,requested_encoding=encoding,status=r.status,body_bytes=len(body),
                    content_encoding=r.getheader('Content-Encoding','identity'),seconds=round(time.monotonic()-started,3))
    finally: conn.close()

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('source');p.add_argument('--samples',type=int,default=3)
    args=p.parse_args()
    if not 1<=args.samples<=20: p.error('samples must be 1..20')
    results=[]
    for _ in range(args.samples):
        for path,encoding in [('/data/aircraft.json','identity'),('/data/aircraft.json','gzip'),('/data/aircraft.binCraft.zst','identity')]:
            try: results.append(measure(args.source,path,encoding,10))
            except (OSError,ValueError,http.client.HTTPException) as e: results.append(dict(path=path,error=type(e).__name__))
            time.sleep(1)
    print(json.dumps({'samples':results,'note':'Body bytes only; excludes headers, transport overhead and retransmissions. Sequential samples have different aircraft states.'},indent=2))
