"""Full activation regressions using synthetic public evidence; no live actions."""
import copy
import json
import subprocess
import sys
import unittest

from test_speaker_contact import speaker, card, payload, NOW, SCRIPT
from test_monthly_digest import monthly

gate = sys.modules['check_candidates']


def preliminary():
    c=card()
    c.update(kind='speaker_inquiry', cfp_status='unknown', free_for_speaker=None,
             organizer_contact_url='https://example.org/program-contacts')
    c.pop('deadline')
    c['evidence'].pop('speaker_price')
    c['evidence']['speaker_contact']='Official program contact on the current conference page'
    return c


class CompleteFlowTests(unittest.TestCase):
    def test_unknown_speaker_terms_still_offer_selection_and_honest_handoff(self):
        c=preliminary()
        self.assertEqual(gate.reasons(c,NOW),[])
        result=speaker.survey([c],NOW)
        self.assertEqual(len(result['questions']),2)
        self.assertIn('нужно уточнить возможность и условия',result['questions'][0]['options'][0])
        for state in ('has_idea','no_idea'):
            result=speaker.compose(dict(conferences=[c],selection=payload(state)['selection']),now=NOW)
            self.assertIn('Бесплатность участия спикера пока не подтверждена.',result['message'])
            self.assertIn('без обязательного взноса',result['message'])
            self.assertIn('Организаторам: https://example.org/program-contacts',result['message'])
            self.assertNotIn('CFP:',result['message'])
            self.assertNotIn('подготовиться к подаче',result['message'])
            self.assertEqual(len(result['links']),2)

    def test_preliminary_cannot_hide_known_exclusion_or_missing_evidence(self):
        patches=[dict(cfp_status='closed'),dict(program_final=True),dict(external_talks=False),
                 dict(free_for_speaker=False),dict(free_for_speaker='free'),
                 dict(starts_at='2026-01-01T10:00:00+03:00'),dict(starts_at='2027-08-01T10:00:00+03:00'),
                 dict(deadline=NOW.isoformat()),dict(cfp_status='open'),
                 dict(language='en'),dict(russian_community=False),dict(primary_verified=False),
                 dict(checked_at='2026-09-01T10:00:00+03:00'),
                 dict(organizer_contact_url='https://user:pass@example.org/contact'),
                 dict(organizer_contact_url=None)]
        for patch in patches:
            c=preliminary();c.update(patch)
            with self.subTest(patch=patch):
                self.assertTrue(gate.reasons(c,NOW))
                self.assertEqual(speaker.eligible([c],NOW),[])
                self.assertIn('help_find',speaker.survey([c],NOW)['questions'][0]['options'][0])
                with self.assertRaises(ValueError):
                    speaker.compose(dict(conferences=[c],selection=payload()['selection']),now=NOW)
        for field in ('section','speaker_contact','date','language','community'):
            c=preliminary();c['evidence'].pop(field)
            with self.subTest(field=field): self.assertTrue(gate.reasons(c,NOW))

    def test_unknown_price_is_never_promoted_to_confirmed_free_speaker(self):
        c=preliminary();c.update(kind='cfp',cfp_status='open',deadline='2026-10-30T23:59:00+03:00')
        self.assertIn('speaker price unconfirmed or paid',gate.reasons(c,NOW))
        c.update(kind='event',registration='open',starts_at='2026-10-20T10:00:00+03:00',free_for_attendee=None)
        self.assertIn('attendee price unconfirmed or paid',gate.reasons(c,NOW))

    def test_confirmed_speaker_cards_also_honor_final_program_and_no_external_talks(self):
        for patch in (dict(program_final=True),dict(external_talks=False)):
            c=card();c.update(patch)
            with self.subTest(patch=patch):self.assertTrue(gate.reasons(c,NOW))

    def test_known_free_inquiry_does_not_claim_unknown_price(self):
        c=preliminary();c['free_for_speaker']=True;c['evidence']['speaker_price']='No speaker fee'
        result=speaker.compose(dict(conferences=[c],selection=payload()['selection']),now=NOW)
        self.assertNotIn('Бесплатность участия спикера пока не подтверждена',result['message'])

    def test_live_cfp_unknown_price_remains_preliminary_and_checks_deadline(self):
        c=preliminary();c.update(cfp_status='open',deadline='2026-10-30T23:59:00+03:00')
        self.assertEqual(gate.reasons(c,NOW),[])
        self.assertIn('условия',speaker.survey([c],NOW)['questions'][0]['options'][0])
        c['deadline']='2026-12-30T23:59:00+03:00'
        self.assertTrue(gate.reasons(c,NOW))

    def test_preliminary_named_idea_is_a_proposal_until_rules_are_known(self):
        c=preliminary();choice=payload('has_idea',topic='доклад про Kafka',topic_fit='unknown')['selection']
        result=speaker.compose(dict(conferences=[c],selection=choice),now=NOW)
        self.assertIn('Идея темы: «Kafka».',result['message'])
        self.assertIn('Соответствие идеи программе тоже нужно уточнить.',result['message'])
        choice['topic_fit']='mismatch'
        with self.assertRaises(ValueError): speaker.compose(dict(conferences=[c],selection=choice),now=NOW)

    def test_two_lists_keep_original_numbers_for_mixed_speaking_statuses(self):
        attendance=card();attendance.update(id='attendance',kind='event',registration='open',
            starts_at='2026-10-20T10:00:00+03:00',cfp_status='unknown')
        inquiry=preliminary();inquiry['id']='inquiry'
        options=speaker.survey([attendance,card(),inquiry],NOW)['questions'][0]['options']
        self.assertTrue(options[0].startswith('2. qa-1'))
        self.assertTrue(options[1].startswith('3. inquiry'))
        self.assertEqual(len(options),3)

    def test_zero_options_preserves_survey_and_message_without_fictional_event(self):
        result=speaker.survey([],NOW)
        self.assertEqual(len(result['questions']),2)
        self.assertIn('поиском площадки',result['questions'][0]['question'])
        for state in ('has_idea','no_idea'):
            result=speaker.compose(dict(conferences=[],selection=dict(conference_id='help_find',topic_state=state)),now=NOW)
            self.assertIn('подобрать подходящую площадку',result['message'])
            self.assertNotIn('Конференция:',result['message'])
            self.assertEqual(len(result['links']),2)
        self.assertEqual(speaker.compose(dict(conferences=[],selection=dict(conference_id='skip')),now=NOW)['links'],{})

    def test_fallback_named_idea_needs_no_invented_section_check(self):
        result=speaker.compose(dict(conferences=[],selection=dict(conference_id='help_find',
            topic_state='has_idea',topic='DevRel и сообщества')),now=NOW)
        self.assertIn('DevRel и сообщества',result['message'])

    def test_reserved_id_cannot_be_a_fake_conference(self):
        for identity in ('help_find','skip'):
            c=preliminary();c['id']=identity
            with self.assertRaises(ValueError):speaker.survey([c],NOW)
        with self.assertRaises(ValueError):speaker.compose(dict(conferences=[card()],
            selection=dict(conference_id='help_find',topic_state='no_idea')),now=NOW)

    def test_cli_zero_options_returns_survey_and_copy_block(self):
        data=dict(conferences=[],selection=dict(conference_id='help_find',topic_state='no_idea'))
        for action in ('survey','message'):
            run=subprocess.run([sys.executable,str(SCRIPT),'--action',action,'--format','json',
                '--now',NOW.isoformat()],input=json.dumps(data),text=True,capture_output=True,check=True)
            self.assertEqual(json.loads(run.stdout)['status'],'ready')

    def test_monthly_prompt_keeps_both_lists_and_zero_options_help(self):
        profile=monthly.public_profile(dict(role='QA',topics=['API']))
        prompt=monthly.task_prompt(profile,'Europe/Moscow')
        for text in ('personal:v6','Куда сходить бесплатно','Где выступить или уточнить условия',
                     'Нужна помощь Олега с поиском площадки','официальным контактом','без обязательного взноса'):
            self.assertIn(text,prompt)
        self.assertNotIn('пропусти опрос',prompt)
        profile['offer_speaker_help']=False
        self.assertIn('Сотрудник отказался',monthly.task_prompt(profile,'Europe/Moscow'))


if __name__=='__main__':unittest.main()
