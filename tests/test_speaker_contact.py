import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/vitech-events-radar/scripts/speaker_contact.py'
SPEC = importlib.util.spec_from_file_location('speaker_handoff', SCRIPT)
speaker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(speaker)
NOW = datetime.fromisoformat('2026-10-15T09:00:00+03:00')


def card():
    return dict(id='qa-1', kind='cfp', name='Синтетическая QA-конференция',
                starts_at='2026-11-20T10:00:00+03:00', checked_at=NOW.isoformat(),
                url='https://example.org/cfp', primary_url='https://example.org/event',
                topics=['API'], audience='QA', format='online', accessible=True,
                primary_verified=True, free_for_attendee=True, free_for_speaker=True, language='ru', russian_community=True,
                cfp_status='open', deadline='2026-10-30T23:59:00+03:00',
                evidence={key:'Synthetic fixture evidence' for key in
                          ('date','status','attendee_price','speaker_price','language','community','deadline','section','speaker_route')})


def payload(state='no_idea', **selection):
    if 'topic' in selection:
        selection.setdefault('topic_fit', 'confirmed')
        selection.setdefault('topic_fit_evidence', 'Synthetic section and rules check')
    return dict(conferences=[card()], selection=dict(conference_id='qa-1', topic_state=state, **selection))


class SpeakerContactTests(unittest.TestCase):
    def test_no_idea_immediately_produces_message_and_exact_two_contacts(self):
        result = speaker.compose(payload(), now=NOW)
        self.assertTrue(result['message'].startswith('Олег, привет!'))
        self.assertIn('Хочу выступить на конференции «Синтетическая QA-конференция»', result['message'])
        self.assertIn('Пока нет идеи темы.', result['message'])
        self.assertIn('собрать фактуру', result['message'])
        self.assertEqual(result['links'], {
            'loop':'https://msg.vseinstrumenti.ru/vitech/messages/@buselov',
            'telegram':'https://t.me/oleg_busel'})
        self.assertNotIn('mailto:', json.dumps(result))

    def test_idea_does_not_require_topic_title(self):
        message = speaker.compose(payload('has_idea'), now=NOW)['message']
        self.assertIn('У меня уже есть идея темы.', message)
        self.assertNotIn('Тема:', message)
        self.assertNotIn('Как называется', message)

    def test_explicit_public_topic_preserved_without_inventing_experience(self):
        message = speaker.compose(payload('has_idea', topic='Контрактные тесты API'), now=NOW)['message']
        self.assertIn('«Контрактные тесты API»', message)
        for text in ('Метрики:', 'Меня зовут', 'В нашем проекте'):
            self.assertNotIn(text, message)

    def test_single_conference_still_has_two_native_choice_options(self):
        result = speaker.survey([card()], NOW)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(len(result['questions']), 2)
        for question in result['questions']:
            self.assertEqual(question['type'], 'single_select')
            self.assertGreaterEqual(len(question['options']), 2)
            self.assertLessEqual(len(question['options']), 10)
            self.assertTrue(question['free_text_placeholder'])
        self.assertIn('qa-1', result['questions'][0]['options'][0])
        self.assertIn('skip', result['questions'][0]['options'][-1])

    def test_no_eligible_cfp_does_not_create_fictional_choices(self):
        for mutation in [dict(cfp_status='closed'),
                         dict(free_for_speaker=False), dict(language='en'), dict(russian_community=False),
                         dict(checked_at='2026-10-01T09:00:00+03:00')]:
            c = card(); c.update(mutation)
            with self.subTest(mutation=mutation):
                self.assertEqual(speaker.eligible([c], NOW), [])
                with self.assertRaises(ValueError):
                    speaker.compose(dict(conferences=[c], selection=payload()['selection']), now=NOW)
        self.assertEqual(speaker.survey([], NOW)['status'], 'ready')

    def test_listed_event_without_cfp_can_be_selected_honestly(self):
        c=card(); c.update(kind='event',registration='open',cfp_status='unknown',
                           starts_at='2026-10-20T10:00:00+03:00',speaker_route='external_talks',speaker_url='https://example.org/speakers')
        c.pop('deadline')
        survey=speaker.survey([c],NOW)
        self.assertEqual(survey['status'],'ready')
        self.assertIn('возможность выступления нужно уточнить',survey['questions'][0]['options'][0])
        result=speaker.compose(dict(conferences=[c],selection=payload()['selection']),now=NOW)
        self.assertIn('Открытый приём докладов пока не подтверждён',result['message'])
        self.assertIn('выяснить, возможно ли участие',result['message'])
        self.assertNotIn('CFP:',result['message'])
        self.assertEqual(len(result['links']),2)

    def test_closed_cfp_on_verified_event_cannot_be_selected(self):
        c=card(); c.update(kind='event',registration='open',cfp_status='closed',
                           starts_at='2026-10-20T10:00:00+03:00',
                           speaker_route='external_talks',speaker_url='https://example.org/speakers')
        self.assertEqual(speaker.eligible([c], NOW), [])
        with self.assertRaises(ValueError):
            speaker.compose(dict(conferences=[c],selection=payload()['selection']),now=NOW)

    def test_mixed_cards_keep_a_single_numbering_and_distinct_statuses(self):
        event=card(); event.update(id='event-1',kind='event',registration='open',cfp_status='unknown',
                                  starts_at='2026-10-20T10:00:00+03:00',speaker_route='external_talks',speaker_url='https://example.org/speakers')
        event.pop('deadline')
        options=speaker.survey([event,card()],NOW)['questions'][0]['options']
        self.assertTrue(options[0].startswith('1. event-1'))
        self.assertTrue(options[1].startswith('2. qa-1'))
        self.assertIn('нужно уточнить',options[0])
        self.assertIn('CFP открыт',options[1])

    def test_opt_out_has_no_message_and_no_contacts(self):
        result = speaker.compose(dict(conferences=[], selection=dict(conference_id='skip')), now=NOW)
        self.assertEqual(result['status'], 'skipped')
        self.assertIsNone(result['message'])
        self.assertEqual(result['links'], {})

    def test_unknown_id_and_new_url_cannot_replace_verified_card(self):
        for selection in [dict(conference_id='new', topic_state='has_idea'),
                          dict(conference_id='qa-1', topic_state='no_idea', url='https://other.example')]:
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                speaker.compose(dict(conferences=[card()], selection=selection), now=NOW)

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            speaker.survey([card(), card()], NOW)

    def test_copy_fence_survives_backticks_in_public_topic(self):
        result = speaker.compose(payload('has_idea', topic='Тесты ``` API'), now=NOW)
        rendered = speaker.markdown(result)
        self.assertTrue(rendered.startswith('````text\n'))
        self.assertIn(result['message'], rendered)
        self.assertIn('**[Написать Олегу в Loop]', rendered)
        self.assertLess(rendered.index(result['links']['loop']), rendered.index(result['links']['telegram']))

    def test_unexpected_private_fields_are_rejected(self):
        for key in ('private_case','public_case_summary','speaker_name','email'):
            data = payload(); data[key] = 'TEST_ONLY_SECRET'
            with self.subTest(key=key), self.assertRaises(ValueError):
                speaker.compose(data, now=NOW)

    def test_invalid_or_conflicting_selection_fails(self):
        values = [None, [], {}, dict(conferences=[], selection={}), payload('unknown'),
                  payload('no_idea', topic='Conflict'), payload('has_idea', topic=7),
                  payload('has_idea', topic='line\nbreak')]
        for data in values:
            with self.subTest(data=data), self.assertRaises(ValueError):
                speaker.compose(data, now=NOW)

    def test_credentials_in_links_are_rejected(self):
        c = card(); c['url'] = 'https://user:password@example.org/cfp'
        self.assertEqual(speaker.eligible([c], NOW), [])

    def test_survey_caps_options_at_ten(self):
        cards = []
        for i in range(20):
            c = card(); c['id'] = str(i); cards.append(c)
        self.assertEqual(len(speaker.survey(cards, NOW)['questions'][0]['options']), 10)

    def test_contact_changes_only_need_configuration(self):
        contact = speaker.load_contact()
        contact.update(greeting='Олег, добрый день!', loop_label='Открыть Loop')
        result = speaker.compose(payload(), contact=contact, now=NOW)
        self.assertTrue(result['message'].startswith('Олег, добрый день!'))
        self.assertIn('Открыть Loop', speaker.markdown(result))

    def test_cli_message_and_survey(self):
        for action in ('message','survey'):
            run = subprocess.run([sys.executable,str(SCRIPT),'--action',action,'--format','json','--now',NOW.isoformat()],
                                 input=json.dumps(payload()),text=True,capture_output=True,check=True)
            result = json.loads(run.stdout)
            self.assertEqual(result['status'], 'ready')
            self.assertEqual(run.stderr, '')

    def test_cli_invalid_input_does_not_echo_data(self):
        run = subprocess.run([sys.executable,str(SCRIPT)],input='TEST_ONLY_SECRET_INVALID',
                             text=True,capture_output=True)
        self.assertEqual(run.returncode,2)
        self.assertEqual(run.stdout,'')
        self.assertNotIn('TEST_ONLY_SECRET_INVALID',run.stderr)


if __name__ == '__main__':
    unittest.main()
