import base64
import json
import os
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

os.environ.setdefault('TELEGRAM_OWNER_ID','123456')
import cloud_run


class CloudTests(unittest.TestCase):
    def test_free_request_blocks_paid_and_training_routes(self):
        response={'usage':{'cost':0},'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]}
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-key'}),patch('cloud_run.http_json',return_value=response) as http:
            self.assertEqual(cloud_run.free_inference('synthetic'),{'ok':True})
            body=http.call_args.kwargs['body']
            self.assertTrue(body['model'].endswith(':free'))
            self.assertEqual(body['provider']['max_price'],{'prompt':0,'completion':0})
            self.assertEqual(body['provider']['data_collection'],'deny')
            self.assertTrue(body['provider']['zdr'])
            self.assertFalse(body['provider']['allow_fallbacks'])
            self.assertNotIn('tools',body)

    def test_nonzero_or_missing_cost_rejected(self):
        for cost in [0.01,None]:
            with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-key'}),patch('cloud_run.http_json',return_value={'usage':{'cost':cost}}):
                with self.assertRaises(cloud_run.CloudError):cloud_run.free_inference('synthetic')

    def test_paid_model_rejected_before_network(self):
        with patch('cloud_run.MODEL','paid/model'),patch('cloud_run.http_json') as http:
            with self.assertRaises(cloud_run.CloudError):cloud_run.free_inference('synthetic')
            http.assert_not_called()

    def test_cutoff_output_rejected(self):
        response={'usage':{'cost':0},'choices':[{'finish_reason':'length','message':{'content':'{}'}}]}
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-key'}),patch('cloud_run.http_json',return_value=response):
            with self.assertRaises(cloud_run.CloudError):cloud_run.free_inference('synthetic')

    def test_reviewer_can_correct_rejected_draft_before_final_verification(self):
        import datetime,copy
        rows=[{'chat_id':1,'chat_title':'Example','message_id':8,'timestamp':'2026-10-29T10:00:00+00:00','outgoing':False,'reply_to_message_id':None,'text':'Meeting tomorrow at 10:00'}]
        good={'title':'A meeting','subtitle':'Daily review','sources':[{'key':'s1','chat_id':1,'message_id':8,'quote':'Meeting tomorrow'}],'chat_summaries':[{'chat_id':1,'summary':'Discussed meeting'}],'highlights':[{'evidence':['s1']}],'actions':[],'sections':[]}
        bad=copy.deepcopy(good);bad['sources'][0]['message_id']=999
        with patch.dict(os.environ,{'TELEGRAM_BOT_TOKEN':'999:synthetic'}),patch('cloud_run.free_inference',side_effect=[bad,good]) as inference:
            data=cloud_run.analyze(datetime.date(2026,10,29),rows)
            self.assertEqual(inference.call_count,2)
            self.assertEqual(data['sources'][0]['quote'],'Meeting tomorrow at 10:00')
            self.assertIn('Draft rejected',inference.call_args.args[0])
        with patch.dict(os.environ,{'TELEGRAM_BOT_TOKEN':'999:synthetic'}),patch('cloud_run.free_inference',side_effect=[bad,bad]):
            with self.assertRaises(ValueError):cloud_run.analyze(datetime.date(2026,10,29),rows)

    def test_model_quotation_is_replaced_with_actual_message_not_laundered(self):
        rows=[{'chat_id':1,'message_id':8,'text':'The actual original text.'}]
        draft={'sources':[{'key':'s1','chat_id':1,'message_id':8,'quote':'Fabricated text.'}]}
        result=cloud_run.original_source_text(draft,rows)
        self.assertEqual(result['sources'][0]['quote'],'The actual original text.')
        self.assertEqual(draft['sources'][0]['quote'],'Fabricated text.')
        draft['sources'][0]['message_id']=999
        result=cloud_run.original_source_text(draft,rows)
        self.assertEqual(result['sources'][0]['message_id'],999)

    def test_state_encrypted_at_rest_and_bound_to_repository(self):
        key=os.urandom(32);nonce=os.urandom(12);repo='example/reports'
        clear={'days':{'2026-10-29':{'parts':{'summary':{'status':'sent','message_id':9}}}}}
        cipher=AESGCM(key).encrypt(nonce,json.dumps(clear).encode(),repo.encode())
        envelope=json.dumps({'version':1,'nonce':base64.b64encode(nonce).decode(),'ciphertext':base64.b64encode(cipher).decode()}).encode()
        response={'sha':'test-sha','content':base64.b64encode(envelope).decode()}
        env={'GITHUB_REPOSITORY':repo,'GITHUB_TOKEN':'test-token','STATE_ENCRYPTION_KEY':base64.b64encode(key).decode()}
        with patch.dict(os.environ,env),patch('cloud_run.http_json',return_value=response):
            state=cloud_run.State();self.assertEqual(state.data,clear)
        self.assertNotIn(b'message_id',envelope)
        with patch.dict(os.environ,env|{'GITHUB_REPOSITORY':'other/repository'}),patch('cloud_run.http_json',return_value=response):
            with self.assertRaises(InvalidTag):cloud_run.State()

    def test_failed_state_read_not_treated_as_first_run(self):
        env={'GITHUB_REPOSITORY':'example/reports','GITHUB_TOKEN':'test','STATE_ENCRYPTION_KEY':base64.b64encode(os.urandom(32)).decode()}
        with patch.dict(os.environ,env),patch('cloud_run.http_json',side_effect=cloud_run.CloudError('HTTP 401')):
            with self.assertRaises(cloud_run.CloudError):cloud_run.State()

    def test_sent_parts_are_idempotent_without_bot_calls(self):
        class MemoryState:
            data={'days':{'2026-10-29':{'parts':{k:{'status':'sent','message_id':i} for i,k in enumerate(['summary','pdf','html'])}}}}
            def save(self):raise AssertionError('No write should be needed')
        import datetime
        with patch('cloud_run.Bot') as bot:
            cloud_run.deliver(MemoryState(),datetime.date(2026,10,29),{},None,None)
            bot.return_value.send_summary.assert_not_called();bot.return_value.send_file.assert_not_called()

    def test_uncertain_delivery_does_not_repeat(self):
        class MemoryState:
            data={'days':{'2026-10-29':{'parts':{'summary':{'status':'sending'}}}}}
            def save(self):raise AssertionError('Do not overwrite uncertainty')
        import datetime
        with patch('cloud_run.Bot') as bot:
            with self.assertRaises(cloud_run.CloudError):cloud_run.deliver(MemoryState(),datetime.date(2026,10,29),{},None,None)
            bot.return_value.send_summary.assert_not_called()


if __name__=='__main__':unittest.main()
