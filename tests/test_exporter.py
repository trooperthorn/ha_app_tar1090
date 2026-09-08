import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('exporter',Path(__file__).resolve().parents[1]/'pi-exporter/exporter.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ExporterTests(unittest.TestCase):
    def test_filters_before_transfer_preserve_unknowns_and_fields(self):
        data={'now':123,'aircraft':[{'hex':'a','alt_baro':12000},{'hex':'b','alt_baro':9000,'mlat':['lat']},{'hex':'c'}]}
        filtered=module.filtered(data,{},altitude=10000)
        self.assertEqual([a['hex'] for a in filtered['aircraft']],['b','c'])
        self.assertEqual(filtered['now'],123)
        self.assertEqual(filtered['aircraft'][0]['mlat'],['lat'])
        self.assertEqual(len(data['aircraft']),3)
    def test_distance(self):
        self.assertAlmostEqual(module.distance_nm(0,0,0,1),60.04,places=1)
    def test_radius_keeps_missing_position(self):
        data={'now':123,'aircraft':[{'hex':'a','lat':0,'lon':1},{'hex':'b'}]}
        self.assertEqual(module.filtered(data,{'lat':0,'lon':0},radius=20)['aircraft'],[{'hex':'b'}])
