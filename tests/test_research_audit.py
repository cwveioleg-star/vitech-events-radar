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
        self.assertFalse(result['scoped_no_cfp_claim_allowed'])
        self.assertEqual(result['read_unique'],100)
        self.assertEqual(result['domains'],1)

    def test_reads_without_discovery_and_cfp_plan_are_not_complete(self):
        result=research.audit(ledger(99),NOW)
        self.assertFalse(result['complete'])
        self.assertEqual(result['read_unique'],99)
        self.assertTrue(result['reads_complete'])
        self.assertIsNone(result['minimum'])

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

    def test_read_target_is_optional_and_explicit_target_is_respected(self):
        self.assertTrue(research.audit(ledger(3),NOW)['reads_complete'])
        self.assertTrue(research.audit(ledger(3),NOW,minimum=3)['reads_complete'])
        self.assertFalse(research.audit(ledger(99),NOW,minimum=100)['reads_complete'])
        for bad in (0,-1,True,'100'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                research.audit(ledger(),NOW,minimum=bad)

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
    return dict(mode='full', reads=records,brand_checks=checks,
        discovery_searches=[dict(kind=k,checked_at=NOW.isoformat(),tool_ref='synthetic-'+k,evidence='Synthetic discovery')
                            for k in ('aggregator','web')],cfp_search=dict(
        **{'from':'2026-10-15'},through='2027-04-15',verified_suitable_count=0,unresolved=[],
        community_searches=[dict(tool_ref='synthetic-community-query',evidence='Synthetic topic and period search')]))


class BreadthAndHorizonTests(unittest.TestCase):
    def test_all_brands_and_six_months_allow_limited_negative_claim(self):
        result=research.audit(bundle(),NOW)
        self.assertTrue(result['complete'])
        self.assertTrue(result['scoped_no_cfp_claim_allowed'])
        self.assertEqual(result['brands_checked'],len(bundle()['brand_checks']))
        self.assertFalse(result['no_cfp_claim_allowed'])
        self.assertEqual(result['cfp_through'],'2027-04-15')

    def test_hundred_pages_from_one_brand_do_not_cover_other_brands(self):
        data=bundle();data['brand_checks']=data['brand_checks'][:1]
        result=research.audit(data,NOW)
        self.assertTrue(result['reads_complete'])
        self.assertFalse(result['complete'])
        self.assertFalse(result['scoped_no_cfp_claim_allowed'])

    def test_incomplete_horizon_does_not_allow_negative_even_with_many_reads(self):
        for end in ('2026-11-15','2027-03-15','2027-04-14'):
            data=bundle();data['cfp_search']['through']=end
            for check in data['brand_checks']:check['cfp_through']=end
            with self.subTest(end=end):
                self.assertFalse(research.audit(data,NOW)['scoped_no_cfp_claim_allowed'])

    def test_explicit_shorter_horizon_is_respected(self):
        data=bundle();data['cfp_search'].update(months=4,through='2027-02-15')
        for check in data['brand_checks']:check['cfp_through']='2027-02-15'
        self.assertTrue(research.audit(data,NOW)['scoped_no_cfp_claim_allowed'])
        data['cfp_search'].update(months=3,through='2027-01-15')
        for check in data['brand_checks']:check['cfp_through']='2027-01-15'
        self.assertTrue(research.audit(data,NOW)['scoped_no_cfp_claim_allowed'])

    def test_month_end_and_year_rollover(self):
        self.assertEqual(research.add_months(datetime(2026,8,31).date(),6).isoformat(),'2027-02-28')

    def test_blocked_or_snippet_route_is_gap(self):
        for status in ('blocked','snippet_only'):
            data=bundle();data['brand_checks'][50]['routes'][0]['status']=status
            with self.subTest(status=status):
                result=research.audit(data,NOW)
                self.assertEqual(result['brands_checked'],len(data['brand_checks'])-1)
                self.assertFalse(result['scoped_no_cfp_claim_allowed'])

    def test_route_cannot_reuse_unrelated_or_rejected_read(self):
        for change in ('unrelated','blocked'):
            data=bundle()
            if change=='unrelated':data['reads'][0]['brand_ids']=['habr-002']
            else:data['reads'][0]['status']='blocked'
            with self.subTest(change=change):
                self.assertFalse(research.audit(data,NOW)['scoped_no_cfp_claim_allowed'])

    def test_missing_community_searches_or_gaps_block_negative(self):
        for mutation in (dict(community_searches=[]),dict(unresolved=['unread official calendar']),
                         dict(verified_suitable_count=1)):
            data=bundle();data['cfp_search'].update(mutation)
            with self.subTest(mutation=mutation):
                self.assertFalse(research.audit(data,NOW)['scoped_no_cfp_claim_allowed'])

    def test_each_brand_needs_full_period_and_fresh_trace(self):
        for change in (dict(cfp_through='2026-11-15'),dict(checked_at='2026-10-01T09:00:00+03:00')):
            data=bundle();data['brand_checks'][-1].update(change)
            with self.subTest(change=change):
                self.assertFalse(research.audit(data,NOW)['scoped_no_cfp_claim_allowed'])

    def test_extra_organizers_expand_required_coverage(self):
        data=bundle();data['extra_brands']=[dict(id='new-community',name='Synthetic community')]
        result=research.audit(data,NOW)
        self.assertEqual(result['brands_total'],len(data['brand_checks'])+1)
        self.assertIn('new-community',result['missing_brands'])
        self.assertFalse(result['scoped_no_cfp_claim_allowed'])


class TargetedSearchTests(unittest.TestCase):
    def targeted(self):
        data=bundle()
        data['mode']='targeted'
        data['brand_checks']=data['brand_checks'][:3]
        data['selected_brand_ids']=[b['brand_id'] for b in data['brand_checks']]
        data['reads']=data['reads'][:12]
        return data

    def test_small_verified_plan_does_not_require_hundred_or_all_brands(self):
        result=research.audit(self.targeted(),NOW)
        self.assertTrue(result['complete'])
        self.assertEqual(result['read_unique'],12)
        self.assertEqual(result['brands_selected'],3)
        self.assertEqual(result['brands_checked'],3)
        self.assertTrue(result['scoped_no_cfp_claim_allowed'])
        self.assertFalse(result['no_cfp_claim_allowed'])

    def test_explicit_minimum_does_not_disappear_in_targeted_mode(self):
        data=self.targeted();data['minimum_reads']=100
        result=research.audit(data,NOW)
        self.assertEqual(result['minimum'],100)
        self.assertFalse(result['reads_complete'])
        self.assertFalse(result['complete'])

    def test_two_discovery_channels_required_even_with_many_reads(self):
        data=bundle();data['discovery_searches']=data['discovery_searches'][:1]
        self.assertFalse(research.audit(data,NOW)['complete'])
        data['discovery_searches']*=2
        self.assertFalse(research.audit(data,NOW)['complete'])

    def test_optional_telegram_block_does_not_invalidate_official_evidence(self):
        data=self.targeted()
        data['brand_checks'][0]['routes'].append(dict(kind='telegram',status='blocked',tool_ref='synthetic-block',evidence='Blocked'))
        result=research.audit(data,NOW)
        self.assertTrue(result['complete'])
        self.assertEqual(result['optional_route_gaps'],[data['selected_brand_ids'][0]+':telegram'])

    def test_core_form_gap_is_not_hidden_as_optional_platform_gap(self):
        data=self.targeted()
        data['brand_checks'][0]['routes'][0]['status']='blocked'
        self.assertFalse(research.audit(data,NOW)['complete'])

    def test_current_registry_can_have_a_different_number_of_entries(self):
        data=bundle();data['reads']=data['reads'][:2];data['brand_checks']=data['brand_checks'][:2]
        brands=json.loads(research.REGISTRY.read_text())['brands'][:2]
        data['registry']=dict(source_url='https://habr.com/ru/specials/000001/',checked_at=NOW.isoformat(),
                              tool_ref='synthetic-current-registry',evidence='Synthetic changed registry',brands=brands)
        result=research.audit(data,NOW)
        self.assertTrue(result['complete'])
        self.assertTrue(result['registry_fresh'])
        self.assertEqual(result['brands_total'],2)
        self.assertEqual(result['brands_checked'],2)

    def test_stale_malformed_or_duplicate_current_registry_is_rejected(self):
        base=self.targeted()
        registry=dict(source_url='https://example.org/list',checked_at=NOW.isoformat(),tool_ref='synthetic-list',
                      evidence='Synthetic list',brands=[dict(id='one',name='One')])
        for patch in (dict(checked_at='2026-09-01T09:00:00+03:00'),dict(checked_at=1),
                      dict(tool_ref=''),dict(brands=[]),dict(brands=[dict(id='a',name='A'),dict(id='a',name='B')])):
            data=copy.deepcopy(base);data['registry']=dict(registry,**patch)
            with self.subTest(patch=patch),self.assertRaises(ValueError):research.audit(data,NOW)

    def test_snapshot_fallback_is_labelled(self):
        result=research.audit(self.targeted(),NOW)
        self.assertFalse(result['registry_fresh'])
        self.assertEqual(result['registry_snapshot_on'],json.loads(research.REGISTRY.read_text())['refreshed_on'])

    def test_no_reads_cannot_complete_a_metadata_only_plan(self):
        data=self.targeted();data['reads']=[];data['brand_checks']=[];data['selected_brand_ids']=[]
        self.assertFalse(research.audit(data,NOW)['complete'])

    def test_selected_scope_must_be_explicitly_known(self):
        data=self.targeted();data['selected_brand_ids']=['unknown-brand']
        with self.assertRaises(ValueError):research.audit(data,NOW)


if __name__=='__main__':
    unittest.main()
