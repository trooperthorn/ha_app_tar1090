import gzip
import http.server
import json
from pathlib import Path
import sys
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tar1090/app'))
from collector import Settings, State, Fetcher, validate, collect, encode
from server import handler_for


def sample(now=1000):
    return dict(now=now, messages=10, aircraft=[dict(hex='a12345', seen=0.1, lat=30, lon=-97,
                                                  alt_baro=5000, flight='TEST1', type='adsb_icao')])


class StateTests(unittest.TestCase):
    def setUp(self):
        self.time = 1000
        self.state = State(Settings(), clock=lambda: self.time, wall=lambda: self.time)

    def test_frozen_source_expires_without_history_duplicates(self):
        self.state.accept(sample())
        for _ in range(15):
            self.time += 5
            self.state.accept(sample())
        self.assertEqual(len(self.state.pending), 1)
        self.assertEqual(self.state.status()['state'], 'expired')
        self.assertEqual(self.state.current['now'], 1000)

    def test_rollback_starts_new_epoch(self):
        self.state.accept(sample())
        epoch = self.state.epoch
        self.time += 5
        self.state.accept(sample(990))
        self.assertNotEqual(self.state.epoch, epoch)
        self.assertEqual(len(self.state.pending), 1)

    def test_stale_at_first_fetch(self):
        self.time = 1100
        self.state.accept(sample())
        self.assertEqual(self.state.status()['state'], 'expired')

    def test_published_capabilities_do_not_copy_source_binary_flags(self):
        self.state.metadata_update(dict(lat=30, lon=-97, binCraft=True, zstd=True, reapi=True))
        meta = self.state.receiver()
        self.assertEqual(meta['refresh'], 5000)
        self.assertFalse(meta['binCraft'])
        self.assertNotIn('reapi', meta)

    def test_full_field_and_unknown_altitude_preservation(self):
        data = sample()
        data['aircraft'][0].pop('alt_baro')
        data['aircraft'][0]['mlat'] = ['lat','lon']
        self.state.accept(data)
        self.assertEqual(self.state.current, data)

    def test_retention_and_gzip_contract(self):
        self.state.settings.history_minutes = 1
        for _ in range(36):
            self.time += 5
            self.state.accept(sample(self.time))
        _, body, compressed = self.state.response('/chunks/chunks.json')
        self.assertFalse(compressed)
        chunks = json.loads(body)['chunks']
        for name in chunks:
            code, body, compressed = self.state.response('/chunks/'+name)
            self.assertEqual(code, 200)
            self.assertTrue(compressed)
            self.assertIn('files', json.loads(gzip.decompress(body)))
        self.time += 120
        self.state.prune()
        self.assertEqual(len(self.state.sealed), 0)
        self.assertEqual(len(self.state.pending), 0)

    def test_malformed_never_replaces_last_good(self):
        self.state.accept(sample())
        for invalid in ({}, {'now':1,'aircraft':{}}, {'now':1,'aircraft':[{'hex':'x','lat':200}]},
                        {'now':float('nan'),'aircraft':[]}):
            with self.assertRaises(ValueError): self.state.accept(invalid)
        self.assertEqual(self.state.current['now'],1000)

    def test_outage_does_not_make_health_fail(self):
        self.state.failures = 20
        self.assertEqual(self.state.response('/health')[0],200)

    def test_memory_cap(self):
        self.state.settings.history_mb = 1
        for _ in range(25):
            self.time += 5
            data = sample(self.time)
            data['aircraft'] *= 1000
            self.state.accept(data)
        self.assertLessEqual(self.state.history_bytes + len(encode({'files':self.state.pending})), 1024*1024)

    def test_options(self):
        for opts in ({'source_url':'file:///etc/passwd'}, {'source_url':'http://u:p@pi'},
                     {'poll_seconds':0}, {'stale_seconds':5}, {'map_type':'<script>'}):
            with self.assertRaises(ValueError): Settings(opts)

    def test_future_timestamp_does_not_replace_good_data(self):
        self.state.accept(sample())
        with self.assertRaises(ValueError): self.state.accept(sample(100000))
        self.assertEqual(self.state.current['now'],1000)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.body = encode(sample(time.time()))
        self.encoding = 'identity'
        self.status = 200
        parent = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(parent.status)
                self.send_header('Content-Encoding',parent.encoding)
                self.send_header('Content-Length',str(len(parent.body)))
                self.end_headers()
                self.wfile.write(parent.body)
            def log_message(self,*_): pass
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.fetcher = Fetcher(Settings({'source_url':f'http://127.0.0.1:{self.server.server_port}'}))
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
    def test_plain_and_gzip(self):
        original = self.fetcher.get('/data/aircraft.json')
        self.body = gzip.compress(self.body)
        self.encoding = 'gzip'
        self.assertEqual(self.fetcher.get('/data/aircraft.json'),original)
        self.assertEqual(self.fetcher.encoding,'gzip')
    def test_bad_gzip(self):
        self.body, self.encoding = b'bad gzip', 'gzip'
        with self.assertRaises(Exception): self.fetcher.get('/data/aircraft.json')
    def test_gzip_bomb_bounded(self):
        self.fetcher.settings.max_response_mb = 1
        self.body, self.encoding = gzip.compress(b' ' * (2*1024*1024)), 'gzip'
        with self.assertRaises(ValueError): self.fetcher.get('/data/aircraft.json')
    def test_redirect_rejected(self):
        self.status = 302
        with self.assertRaises(ValueError): self.fetcher.get('/data/aircraft.json')
        self.assertEqual(self.fetcher.requests,1)
    def test_truncated_json(self):
        self.body = b'{"now":'
        with self.assertRaises(ValueError): self.fetcher.get('/data/aircraft.json')
    def test_plain_response_size_bound(self):
        self.fetcher.settings.max_response_mb=1
        self.body=b' '*(2*1024*1024)
        with self.assertRaises(ValueError): self.fetcher.get('/data/aircraft.json')


class SchedulingTests(unittest.TestCase):
    def test_browser_reads_never_fetch_upstream(self):
        state = State(Settings())
        class Source:
            bytes, requests, encoding = 0, 0, 'gzip'
            def get(self,path):
                self.requests += 1
                if 'receiver' in path: return dict(lat=30,lon=-97)
                return sample(time.time())
        source = Source()
        stop = threading.Event()
        worker = threading.Thread(target=collect,args=(state,stop,source))
        worker.start()
        deadline = time.monotonic()+2
        while state.current is None and time.monotonic()<deadline: time.sleep(.01)
        for _ in range(100):
            state.response('/data/aircraft.json')
            state.response('/chunks/chunks.json')
            state.response('/status.json')
        stop.set()
        worker.join(2)
        self.assertEqual(source.requests,2)  # one metadata, one aircraft request
        self.assertFalse(worker.is_alive())


if __name__ == '__main__': unittest.main()
