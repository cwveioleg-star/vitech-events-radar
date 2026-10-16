import copy, importlib.util, unittest, tempfile, subprocess, json
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'skills/vitech-events-radar/scripts/check_candidates.py'
s=importlib.util.spec_from_file_location('gate',p);g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
NOW=g.dt('2026-10-08T13:00:00+03:00')
def card():
 return dict(kind='event',name='Synthetic fixture',starts_at='2026-10-14T19:00:00+03:00',url='https://example.org/register',primary_url='https://example.org/event',checked_at='2026-10-08T12:00:00+03:00',topics=['Kafka'],audience='backend',format='online',accessible=True,primary_verified=True,free_for_attendee=True,language='ru',russian_community=True,registration='open',evidence=dict(date='fixture date',status='fixture open',attendee_price='fixture zero',language='fixture ru talks',community='fixture Russian tech community'))
class GateTests(unittest.TestCase):
 def test_valid(self): self.assertEqual(g.reasons(card(),NOW),[])
 def test_unknown_price(self):
  c=card();c['free_for_attendee']=None;self.assertIn('attendee price unconfirmed or paid',g.reasons(c,NOW))
 def test_paid(self):
  c=card();c['free_for_attendee']=False;self.assertTrue(g.reasons(c,NOW))
 def test_past(self):
  c=card();c['starts_at']='2025-10-14T19:00:00+03:00';self.assertIn('past or started event',g.reasons(c,NOW))
 def test_closed_registration(self):
  c=card();c['registration']='closed';self.assertIn('registration unavailable',g.reasons(c,NOW))
 def test_stale(self):
  c=card();c['checked_at']='2026-10-01T12:00:00+03:00';self.assertIn('stale/future check',g.reasons(c,NOW))
 def test_no_primary(self):
  c=card();c['primary_verified']=False;self.assertIn('unverified primary source',g.reasons(c,NOW))
 def test_window(self):
  c=card();c['starts_at']='2026-12-14T19:00:00+03:00';self.assertIn('outside window',g.reasons(c,NOW))
 def test_naive_date(self):
  c=card();c['starts_at']='2026-10-14';self.assertTrue(g.reasons(c,NOW))
 def test_closed_cfp(self):
  c=card();c.update(kind='cfp',free_for_speaker=True,cfp_status='closed',deadline='2026-10-07T19:00:00+03:00');c['evidence'].update(deadline='fixture deadline',speaker_price='fixture speaker free',section='fixture section');self.assertIn('CFP closed',g.reasons(c,NOW))
 def test_cfp_next_year(self):
  c=card();c.update(kind='cfp',free_for_speaker=True,starts_at='2027-02-01T10:00:00+03:00',cfp_status='open',deadline='2026-11-01T19:00:00+03:00');c['evidence'].update(deadline='fixture deadline',speaker_price='fixture speaker free',section='fixture section');self.assertEqual(g.reasons(c,NOW),[])
 def test_missing_evidence(self):
  c=card();c['evidence'].pop('attendee_price');self.assertIn('missing evidence',g.reasons(c,NOW))
 def test_geography_access(self):
  c=card();c['accessible']=False;self.assertIn('access unconfirmed',g.reasons(c,NOW))
 def test_timezone_instant(self):
  c=card();c['starts_at']='2026-10-08T09:59:00Z';self.assertIn('past or started event',g.reasons(c,NOW))
 def test_english_is_rejected(self):
  c=card();c['language']='en';self.assertIn('Russian language unconfirmed',g.reasons(c,NOW))
 def test_russian_interface_without_language_evidence_is_rejected(self):
  c=card();c['evidence'].pop('language');self.assertIn('missing evidence',g.reasons(c,NOW))
 def test_unconfirmed_community_is_rejected(self):
  c=card();c['russian_community']=None;self.assertTrue(g.reasons(c,NOW))
 def test_free_submission_does_not_confirm_speaker_price(self):
  c=card();c.update(kind='cfp',free_for_speaker=None,starts_at='2027-02-01T10:00:00+03:00',cfp_status='open',deadline='2026-11-01T19:00:00+03:00');c['evidence']['deadline']='fixture';self.assertIn('speaker price unconfirmed or paid',g.reasons(c,NOW))
 def test_credentials_in_url_are_rejected(self):
  c=card();c['url']='https://user:pass@example.org/';self.assertIn('invalid url',g.reasons(c,NOW))
class CLITests(unittest.TestCase):
 def test_fewer_and_duplicate(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/'c.json';f.write_text(json.dumps([card(),card(),{'kind':'event'}]))
   out=subprocess.run(['python3',str(p),str(f),'--now',NOW.isoformat()],capture_output=True,text=True,check=True)
   result=json.loads(out.stdout)
   self.assertEqual(len(result['accepted']),1);self.assertEqual(len(result['rejected']),2)
if __name__=='__main__': unittest.main()
