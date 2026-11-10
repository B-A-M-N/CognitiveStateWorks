"""Stand-alone tests; run from archive root, no checkout mutation."""
from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / 'testworks'
sys.path.insert(0, str(BUNDLE / 'qualification'))
from policy import before_execution, after_execution, removal_permitted


class TestQualification(unittest.TestCase):
    def test_reference_decision_scenarios(self):
        scenarios = yaml.safe_load((BUNDLE / 'qualification/scenarios.yaml').read_text())['scenarios']
        self.assertGreaterEqual(len(scenarios), 12)
        for entry in scenarios:
            with self.subTest(entry['id']):
                f = {'before': before_execution, 'after': after_execution,
                     'removal': removal_permitted}[entry['phase']]
                self.assertEqual(f(entry['context']), entry['expect'])

    def test_manifest_shape_and_bundle_paths(self):
        manifest = yaml.safe_load((BUNDLE / 'manifest.yaml').read_text())
        self.assertEqual(manifest['id'], 'testworks')
        self.assertEqual(manifest['domain'], 'test_assurance')
        self.assertEqual(manifest['bundle_schema_version'], 2)
        for p in [manifest['engine']['contract'], manifest['contracts']['packets'],
                  manifest['contracts']['evidence'], *manifest['contracts']['schemas']]:
            self.assertTrue((BUNDLE / p).is_file(), p)
        self.assertEqual(len(list((BUNDLE / 'flows').glob('*/FLOW.md'))), 10)
        self.assertEqual(len(list((BUNDLE / 'flows').glob('*/flow.yaml'))), 10)

    def test_graph_is_connected_and_evidence_types_exist(self):
        tr = yaml.safe_load((BUNDLE / 'transitions.yaml').read_text())
        kinds = yaml.safe_load((BUNDLE / 'contracts/evidence-kinds.yaml').read_text())['kinds']
        ids = [t['id'] for t in tr['transitions']]
        self.assertEqual(len(ids), len(set(ids)))
        s = set(tr['states'])
        self.assertTrue(set([tr['initial_state'], *tr['completion_states'], *tr['normal_path']]).issubset(s))
        for t in tr['transitions']:
            self.assertIn(t['from'], s)
            self.assertIn(t['to'], s)
            self.assertTrue(t['required_evidence'])
            for kind in t['required_evidence']:
                self.assertIn(kind, kinds, (t['id'], kind))
        reached = {tr['initial_state']}
        while True:
            nxt = reached | {t['to'] for t in tr['transitions'] if t['from'] in reached}
            if nxt == reached: break
            reached = nxt
        self.assertEqual(reached, s)
        self.assertIn('NO_ADDITIONAL_TESTING_NEEDED', tr['completion_states'])
        self.assertIn('VERIFIED', tr['completion_states'])

    def test_schema_and_example_packet(self):
        schema = json.loads((ROOT/'schemas/testing-evidence-packet.schema.json').read_text())
        envelope = yaml.safe_load((BUNDLE/'templates/testing-evidence-packet.example.yaml').read_text())
        handoff = json.loads((BUNDLE/'tests/fixtures/handoff-packet.schema.json').read_text())
        registry = Registry().with_resources([
            ('https://cognitivestatework.dev/schemas/handoff-packet.schema.json', Resource.from_contents(handoff)),
            ('https://cognitivestatework.dev/schemas/testing-evidence-packet.schema.json', Resource.from_contents(schema))
        ])
        v = Draft202012Validator(schema, registry=registry, format_checker=Draft202012Validator.FORMAT_CHECKER)
        self.assertEqual(list(v.iter_errors(envelope)), [])
        changed = json.loads(json.dumps(envelope))
        changed['payload']['subject'].pop('fingerprint')
        self.assertTrue(list(v.iter_errors(changed)))
        changed = json.loads(json.dumps(envelope))
        changed['packet_type'] = 'repository_truth_packet'
        self.assertTrue(list(v.iter_errors(changed)))

    def test_packet_registry_subject_freshness(self):
        packet = yaml.safe_load((BUNDLE/'contracts/packets.yaml').read_text())['packets']['testing_evidence_packet']
        self.assertEqual(packet['freshness']['strategy'],'exact_context')
        self.assertEqual(packet['freshness']['packet_path'],'payload.subject.fingerprint')
        self.assertEqual(packet['freshness']['context_path'],'testing_fingerprint')


if __name__ == '__main__': unittest.main()
