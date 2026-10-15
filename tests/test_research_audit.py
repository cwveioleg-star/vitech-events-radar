import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/'skills/vitech-events-radar/scripts/research_audit.py'
SPEC=importlib.util.spec_from_file_location('research_audit',SCRIPT)
research=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(research)
NOW=datetime.fromisoformat('2026-10-15T09:00:00+03:00')


def ledger(count=100):
    # Synthetic documents, never presented as actual research.
    return [dict(url=f'https://example.org/event/{i}', checked_at=NOW.isoformat(),
                 brand='AvitoTech' if i==0 else 'Alfa Digital' if i==1 else 'Synthetic brand',
                 kind='event',status='read',relevant=True,tool_ref=f'synthetic-read-{i}',
                 evidence='Synthetic fixture, no actual source was read') for i in range(count)]


class ResearchAuditTests(unittest.TestCase):
    def test_hundred_unique_reads_and_required_brands(self):
        result=research.audit(ledger(),NOW)
        self.assertTrue(result['complete'])
        self.assertEqual(result['read_unique'],100)
        self.assertEqual(result['domains'],1)

    def test_99_is_not_complete(self):
        result=research.audit(ledger(99),NOW)
        self.assertFalse(result['complete'])
        self.assertEqual(result['read_unique'],99)

    def test_tracking_fragment_and_pagination_cannot_pad(self):
        records=ledger(99)
        for suffix in ['?utm_source=test','#fragment','?page=2','?offset=100&sort=date','/']:
            duplicate=copy.deepcopy(records[0]); duplicate['url']+=suffix; records.append(duplicate)
        result=research.audit(records,NOW)
        self.assertFalse(result['complete'])
        self.assertEqual(result['read_unique'],99)

    def test_mirrors_and_redirects_deduplicate(self):
        records=ledger(99)
        records[0]['source_id']='same-document'
        a=copy.deepcopy(records[0]);a['url']='https://mirror.example/announcement';records.append(a)
        b=copy.deepcopy(records[1]);b['url']='https://redirect.example/link';b['canonical_url']=records[1]['url'];records.append(b)
        self.assertEqual(research.audit(records,NOW)['read_unique'],99)

    def test_blocked_error_irrelevant_or_untraced_not_counted(self):
        for change in [dict(status='blocked'),dict(status='error'),dict(relevant=False),
                       dict(tool_ref=''),dict(evidence=''),dict(kind='snippet')]:
            records=ledger(); records[-1].update(change)
            with self.subTest(change=change):
                self.assertEqual(research.audit(records,NOW)['read_unique'],99)

    def test_stale_future_and_naive_checks_not_counted(self):
        for checked in ['2026-10-10T09:00:00+03:00','2026-10-16T09:00:00+03:00','2026-10-15T09:00:00']:
            records=ledger();records[-1]['checked_at']=checked
            with self.subTest(checked=checked):
                self.assertFalse(research.audit(records,NOW)['complete'])

    def test_missing_required_brand_is_not_complete(self):
        records=ledger();records[1]['brand']='Other brand'
        result=research.audit(records,NOW)
        self.assertFalse(result['complete'])
        self.assertIn('alfa digital',result['missing_brands'])

    def test_alias_chain_does_not_pad(self):
        records=ledger(99);records[0]['source_id']='original'
        a=copy.deepcopy(records[0]);a['url']='https://alias.example/a';records.append(a)
        b=copy.deepcopy(a);b.pop('source_id');records.append(b)
        self.assertEqual(research.audit(records,NOW)['read_unique'],99)

    def test_meaningful_query_identifier_preserved(self):
        self.assertNotEqual(research.canonical('https://example.org/event?id=1'),
                            research.canonical('https://example.org/event?id=2'))

    def test_invalid_urls_and_credentials_not_counted(self):
        for url in ['http://example.org/event','https://user:pass@example.org/event','javascript:bad','/event']:
            records=ledger();records[-1]['url']=url
            with self.subTest(url=url):
                self.assertEqual(research.audit(records,NOW)['read_unique'],99)

    def test_minimum_cannot_be_lowered(self):
        with self.assertRaises(ValueError): research.audit(ledger(),NOW,minimum=99)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'synthetic.json';file.write_text(json.dumps(ledger()))
            run=subprocess.run([sys.executable,str(SCRIPT),str(file),'--now',NOW.isoformat()],
                               capture_output=True,text=True,check=True)
            self.assertTrue(json.loads(run.stdout)['complete'])


if __name__=='__main__':
    unittest.main()
