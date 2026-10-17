"""Regression scenarios from issue #1; all events/evidence are synthetic."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_speaker_contact import speaker, card, payload, NOW

GATE = sys.modules['check_candidates']


def inquiry():
    c=card()
    c.update(kind='speaker',cfp_status='unknown',free_for_attendee=False,
             starts_at='2027-02-01T10:00:00+03:00',
             speaker_route='external_talks',speaker_url='https://example.org/speakers')
    return c


class RoleSpecificPriceTests(unittest.TestCase):
    def test_paid_attendance_with_free_speaker_is_a_valid_cfp(self):
        c=card(); c['free_for_attendee']=False
        self.assertEqual(GATE.reasons(c,NOW),[])
        self.assertEqual(speaker.survey([c],NOW)['status'],'ready')

    def test_free_listener_does_not_establish_free_speaker(self):
        c=card(); c.pop('free_for_speaker'); c['free']=True
        self.assertIn('speaker price unconfirmed or paid',GATE.reasons(c,NOW))

    def test_free_submission_without_free_speaker_terms_is_rejected(self):
        c=card(); c.pop('free_for_speaker'); c['submission_free']=True
        self.assertTrue(GATE.reasons(c,NOW))

    def test_speaker_fee_is_rejected_even_with_free_listener(self):
        c=card(); c['free_for_speaker']=False
        self.assertTrue(GATE.reasons(c,NOW))

    def test_unknown_listener_price_does_not_block_confirmed_free_speaker(self):
        c=card(); c['free_for_attendee']=None; c['evidence'].pop('attendee_price')
        self.assertEqual(GATE.reasons(c,NOW),[])

    def test_price_evidence_for_one_role_does_not_prove_the_other(self):
        for key in ('speaker_price','attendee_price'):
            c=card(); c['evidence'].pop(key)
            with self.subTest(key=key): self.assertIn('missing evidence',GATE.reasons(c,NOW))

    def test_unknown_price_is_not_free_attendance(self):
        c=card(); c.update(kind='event',registration='open',free_for_attendee=None,
                           starts_at='2026-10-20T10:00:00+03:00')
        self.assertTrue(GATE.reasons(c,NOW))


class SpeakingOptionTests(unittest.TestCase):
    def test_attendance_only_party_has_no_speaking_survey(self):
        c=card(); c.update(kind='event',registration='open',cfp_status='unknown',
                           starts_at='2026-10-20T10:00:00+03:00')
        self.assertEqual(GATE.reasons(c,NOW),[])
        self.assertEqual(speaker.eligible([c], NOW),[])

    def test_verified_inquiry_is_available_beyond_thirty_days(self):
        c=inquiry()
        self.assertEqual(GATE.reasons(c,NOW),[])
        self.assertIn('нужно уточнить',speaker.survey([c], NOW)['questions'][0]['options'][0])
        message=speaker.compose(dict(conferences=[c],selection=payload()['selection']),now=NOW)['message']
        self.assertIn('Спикерам: https://example.org/speakers',message)
        self.assertNotIn('подготовиться к подаче',message)

    def test_closed_finalized_or_unsupported_formats_have_no_speaking_option(self):
        for patch in (dict(cfp_status='closed'),dict(program_final=True),dict(speaker_route='discussion'),
                      dict(speaker_route=None),dict(speaker_url='https://user:pass@example.org')):
            c=inquiry(); c.update(patch)
            with self.subTest(patch=patch): self.assertEqual(speaker.eligible([c], NOW),[])

    def test_route_requires_readable_evidence_and_section_fit(self):
        for key in ('speaker_route','section'):
            c=inquiry(); c['evidence'].pop(key)
            with self.subTest(key=key): self.assertEqual(speaker.eligible([c], NOW),[])

    def test_speaker_page_is_a_valid_inquiry_route(self):
        c=inquiry(); c['speaker_route']='speaker_page'
        self.assertEqual(GATE.reasons(c,NOW),[])

    def test_survey_keeps_digest_numbers_after_filtering(self):
        attendance=card(); attendance.update(id='party',kind='event',registration='open',cfp_status='unknown',
                                            starts_at='2026-10-20T10:00:00+03:00')
        options=speaker.survey([attendance,card()],NOW)['questions'][0]['options']
        self.assertTrue(options[0].startswith('2. qa-1'))
        self.assertEqual(len(options),2)

    def test_cfp_and_inquiry_share_the_six_month_horizon(self):
        for candidate in (card(),inquiry()):
            candidate['starts_at']='2027-05-01T10:00:00+03:00'
            with self.subTest(kind=candidate['kind']):
                self.assertIn('outside speaker window',GATE.reasons(candidate,NOW))
                self.assertEqual(GATE.reasons(candidate,NOW,months=8),[])

    def test_calendar_month_end_rollover(self):
        start=GATE.dt('2026-08-31T09:00:00+03:00')
        self.assertEqual(GATE.add_months(start,6).isoformat(),'2027-02-28T09:00:00+03:00')

    def test_explicit_longer_window_applies_to_survey_and_message(self):
        c=card(); c['starts_at']='2027-05-01T10:00:00+03:00'
        data=dict(conferences=[c],selection=payload()['selection'])
        self.assertEqual(speaker.eligible([c], NOW),[])
        self.assertEqual(speaker.survey([c],NOW,months=8)['status'],'ready')
        self.assertEqual(speaker.compose(data,now=NOW,months=8)['status'],'ready')

    def test_expired_deadline_blocks_even_a_good_free_speaker(self):
        c=card(); c['deadline']=NOW.isoformat()
        self.assertEqual(speaker.eligible([c], NOW),[])

    def test_cli_accepts_paid_listener_free_speaker_and_rejects_attendance_only(self):
        c=card(); c['free_for_attendee']=False
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'cards.json'; source.write_text(json.dumps([c]))
            result=subprocess.run([sys.executable,str(Path(GATE.__file__)),str(source),'--now',NOW.isoformat()],
                                  text=True,capture_output=True,check=True)
            self.assertEqual(len(json.loads(result.stdout)['accepted']),1)


class TopicTests(unittest.TestCase):
    def test_topic_prefix_is_normalized_without_inventing_content(self):
        for raw in ('доклад про Kafka','Доклад о Kafka','выступление на тему Kafka','тема: Kafka'):
            result=speaker.compose(payload('has_idea',topic=raw),now=NOW)
            with self.subTest(raw=raw): self.assertIn('Идея темы: «Kafka».',result['message'])

    def test_named_topic_requires_confirmed_section_and_rules_check(self):
        for state in (None,'unknown','mismatch'):
            data=payload('has_idea',topic='Kafka',topic_fit=state)
            with self.subTest(state=state),self.assertRaises(ValueError): speaker.compose(data,now=NOW)

    def test_topic_check_without_evidence_is_rejected(self):
        data=payload('has_idea',topic='Kafka'); data['selection'].pop('topic_fit_evidence')
        with self.assertRaises(ValueError): speaker.compose(data,now=NOW)


if __name__=='__main__': unittest.main()
