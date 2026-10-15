"""Regressions reproduced from Matt's October manual sessions."""

import os
import sys
import types
import unittest
from unittest.mock import patch

try:
    import openai
except ImportError:
    sys.modules['openai'] = types.SimpleNamespace(OpenAI=object)

from api.chat import run_chat_turn, run_followup_turn, _is_off_topic_request
from api.scenario_planner import _find_matching_skus_for_flow_a as find
from api.universal_engine import _apply_hard_feature_rules, _distribution_role_hints


class OctoberManualFindings(unittest.TestCase):
    def test_three_sources_ten_displays_keeps_sixteen_input_matrix(self):
        query = '3x10 matrix for a sports bar, 4K, 215 feet'
        skus = find(['matrix switcher'], {'How many inputs?': '3', 'How many displays?': '10'}, query)
        self.assertIn('BG-4K-1616MA', skus)
        self.assertIn('BG-4K-VP1616PRO', skus)
        role, hints = _distribution_role_hints(query, {})
        self.assertEqual(role, 'matrix switcher')
        self.assertIn('BG-4K-VP1616PRO', hints)

    def test_full_system_cannot_omit_the_routing_device(self):
        from api import universal_engine
        response = types.SimpleNamespace(usage=None, choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content='Use BG-EXH-70C4 to extend the signal.'))])
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test'}), patch.object(universal_engine, 'OpenAI') as client, \
                patch.object(universal_engine, '_pass1_select_skus', return_value=['BG-EXH-70C4']), \
                patch.object(universal_engine, 'get_relevant_context', return_value=''):
            client.return_value.chat.completions.create.return_value = response
            result = universal_engine.get_universal_recommendation('3x10 matrix for sports bar, 4K, 215 feet', {})
        self.assertIn('BG-4K-1616MA', result['answer'])
        self.assertIn('BG-4K-1616MA', result['selected_skus'])

    def test_lower_cost_wall_processors_are_not_lost(self):
        query = 'budget 1x3 HDMI video wall for a 4K menu across three TVs'
        skus = find(['video wall processor'], {}, query)
        self.assertIn('BG-UHD-VW2X2A', skus)
        self.assertIn('BG-UHD-VWP-1X4', skus)
        self.assertNotIn('BG-IPGEAR-ULTRA', skus)
        perfect, partial = _apply_hard_feature_rules(['BG-UHD-VWP-1X4'], [], {}, {}, requirement=query)
        self.assertEqual(perfect, [])
        self.assertEqual(partial, ['BG-UHD-VWP-1X4'])
        self.assertNotIn('BG-UHD-VWP-1X4', find(['video wall processor'], {}, '1x3 video wall with native 4K outputs'))

    def test_cheaper_options_reopen_the_full_catalog(self):
        with patch('api.chat.OpenAI') as client:
            result = run_followup_turn([], 'Are there any cheaper options?', {'topic': '1x3 video wall'})
        self.assertTrue(result['refine_search'])
        client.assert_not_called()

    def test_off_topic_requests_do_not_start_search_or_change_state(self):
        for question in ("What's 27x6,400,325", 'Can you write a poem about HDMI?',
                         'Can you write some social media posts?', "What's the most popular song on the radio currently?"):
            with self.subTest(question=question), patch('api.chat.OpenAI') as client:
                result = run_chat_turn([], question, {'num_outputs': 10})
                followup = run_followup_turn([], question, {'topic': 'matrix', 'skus': ['BG-4K-1616MA']})
                self.assertFalse(result['ready_to_search'])
                self.assertEqual(result['state_update'], {})
                self.assertFalse(followup['refine_search'])
                client.assert_not_called()
        self.assertFalse(_is_off_topic_request('For 3x10 HDMI routing, how many extenders do I need?'))
        self.assertFalse(_is_off_topic_request('3x10'))

    def test_1080p_closeups_include_jr_thirty_x(self):
        skus = find(['ptz camera'], {}, 'Two 1080p NDI PTZ cameras with 25x zoom for church streaming')
        self.assertIn('BG-ADAMO-JRND30X-B', skus)
        self.assertLess(skus.index('BG-ADAMO-JRND30X-B'), skus.index('BG-ADAMO-4KND25X-B'))

    def test_static_usb_podcast_shots_include_box_camera(self):
        skus = find(['camera'], {'Signal type?': 'USB'}, 'Cameras for fixed shots, USB, 12x zoom, recording a podcast')
        self.assertEqual(skus[0], 'BG-PACKSHOT-C10X')
        self.assertNotIn('BG-CYCLOPS-PRO', skus)

    def test_cyclops_and_adamo_family_comparison_starts_directly(self):
        with patch('api.chat.OpenAI') as client:
            result = run_chat_turn([], 'What’s the difference between your Adamo and Cyclops cameras?', {})
        self.assertTrue(result['ready_to_search'])
        self.assertEqual(set(result['_scenario_plan']['requested_categories']), {'camera', 'videobar'})
        client.assert_not_called()

    def test_keyboard_and_mouse_sharing_prefers_two_host_usb_switch(self):
        result = run_chat_turn([], 'I want one keyboard and mouse for two computers', {})
        plan = result['_scenario_plan']
        skus = find(plan['requested_categories'], result['_scenario_answers'], result['search_query'])
        self.assertEqual(skus[0], 'BG-USW-24')

    def test_pcie_is_not_promised_as_available_capture(self):
        with patch('api.chat.OpenAI') as client:
            result = run_chat_turn([], 'Do you have a PCIe capture card?', {})
        self.assertFalse(result['ready_to_search'])
        self.assertIn('no PCIe capture card is listed', result['message'])
        client.assert_not_called()

    def test_soundbar_earc_finds_the_correct_adapter(self):
        skus = find(['HDMI audio extractor'], {'Resolution?': '4K'},
                    '4K external HDMI source to TV with audio to HDMI ARC/eARC soundbar')
        self.assertIn('BG-8K-SA', skus)
        self.assertIn('BG-8K-AE', skus)
        self.assertNotIn('BG-8K-AA', skus)


if __name__ == '__main__':
    unittest.main()
