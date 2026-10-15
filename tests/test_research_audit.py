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
                 kind='event',status='read',relevant=True,tool_ref=f'synthetic-read-{i}',
                 evidence='Synthetic fixture, no actual source was read') for i in range(count)]


class ResearchAuditTests(unittest.TestCase):
    def test_hundred_unique_reads_do_not_prove_brand_or_horizon_coverage(self):
        result=research.audit(ledger(),NOW)
        self.assertTrue(result['reads_complete'])
        self.assertFalse(result['complete'])
        self.assertFalse(result['no_cfp_claim_allowed'])
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

    def test_no_named_pair_is_required_for_read_count(self):
        records=ledger()
        result=research.audit(records,NOW)
        self.assertTrue(result['reads_complete'])
        self.assertEqual(result['brands_checked'],0)

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
            self.assertTrue(json.loads(run.stdout)['reads_complete'])


def bundle():
    brands=json.loads(research.REGISTRY.read_text())['brands']
    records=ledger(len(brands))
    checks=[]
    for i,brand in enumerate(brands):
        records[i]['brand_ids']=[brand['id']]
        routes=[]
        for kind in sorted(research.ROUTES):
            route=dict(kind=kind,status='read' if kind in {'calendar','cfp'} else 'not_found',
                       tool_ref=f'synthetic-route-{i}-{kind}',evidence='Synthetic full-period route check')
            if route['status']=='read': route['read_indices']=[i]
            routes.append(route)
        checks.append(dict(brand_id=brand['id'],checked_at=NOW.isoformat(),routes=routes,
                           cfp_from='2026-10-15',cfp_through='2027-04-15'))
    return dict(reads=records,brand_checks=checks,cfp_search=dict(
        **{'from':'2026-10-15'},through='2027-04-15',verified_suitable_count=0,unresolved=[],
        community_searches=[dict(tool_ref='synthetic-community-query',evidence='Synthetic topic and period search')]))


class BreadthAndHorizonTests(unittest.TestCase):
    def test_all_brands_and_six_months_allow_limited_negative_claim(self):
        result=research.audit(bundle(),NOW)
        self.assertTrue(result['complete'])
        self.assertTrue(result['no_cfp_claim_allowed'])
        self.assertEqual(result['brands_checked'],126)
        self.assertEqual(result['cfp_through'],'2027-04-15')

    def test_hundred_pages_from_one_brand_do_not_cover_other_brands(self):
        data=bundle();data['brand_checks']=data['brand_checks'][:1]
        result=research.audit(data,NOW)
        self.assertTrue(result['reads_complete'])
        self.assertFalse(result['complete'])
        self.assertFalse(result['no_cfp_claim_allowed'])

    def test_incomplete_horizon_does_not_allow_negative_even_with_many_reads(self):
        for end in ('2026-11-15','2027-03-15','2027-04-14'):
            data=bundle();data['cfp_search']['through']=end
            for check in data['brand_checks']:check['cfp_through']=end
            with self.subTest(end=end):
                self.assertFalse(research.audit(data,NOW)['no_cfp_claim_allowed'])

    def test_explicit_four_month_request_allowed_but_not_three(self):
        data=bundle();data['cfp_search'].update(months=4,through='2027-02-15')
        for check in data['brand_checks']:check['cfp_through']='2027-02-15'
        self.assertTrue(research.audit(data,NOW)['no_cfp_claim_allowed'])
        data['cfp_search']['months']=3
        self.assertFalse(research.audit(data,NOW)['no_cfp_claim_allowed'])

    def test_month_end_and_year_rollover(self):
        self.assertEqual(research.add_months(datetime(2026,8,31).date(),6).isoformat(),'2027-02-28')

    def test_blocked_or_snippet_route_is_gap(self):
        for status in ('blocked','snippet_only'):
            data=bundle();data['brand_checks'][50]['routes'][0]['status']=status
            with self.subTest(status=status):
                result=research.audit(data,NOW)
                self.assertEqual(result['brands_checked'],125)
                self.assertFalse(result['no_cfp_claim_allowed'])

    def test_route_cannot_reuse_unrelated_or_rejected_read(self):
        for change in ('unrelated','blocked'):
            data=bundle()
            if change=='unrelated':data['reads'][0]['brand_ids']=['habr-002']
            else:data['reads'][0]['status']='blocked'
            with self.subTest(change=change):
                self.assertFalse(research.audit(data,NOW)['no_cfp_claim_allowed'])

    def test_missing_community_searches_or_gaps_block_negative(self):
        for mutation in (dict(community_searches=[]),dict(unresolved=['unread official calendar']),
                         dict(verified_suitable_count=1)):
            data=bundle();data['cfp_search'].update(mutation)
            with self.subTest(mutation=mutation):
                self.assertFalse(research.audit(data,NOW)['no_cfp_claim_allowed'])

    def test_each_brand_needs_full_period_and_fresh_trace(self):
        for change in (dict(cfp_through='2026-11-15'),dict(checked_at='2026-10-01T09:00:00+03:00')):
            data=bundle();data['brand_checks'][-1].update(change)
            with self.subTest(change=change):
                self.assertFalse(research.audit(data,NOW)['no_cfp_claim_allowed'])

    def test_extra_organizers_expand_required_coverage(self):
        data=bundle();data['extra_brands']=[dict(id='new-community',name='Synthetic community')]
        result=research.audit(data,NOW)
        self.assertEqual(result['brands_total'],127)
        self.assertIn('new-community',result['missing_brands'])
        self.assertFalse(result['no_cfp_claim_allowed'])


if __name__=='__main__':
    unittest.main()
