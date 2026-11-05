import io,json,tarfile,tempfile,unittest
from pathlib import Path
from offline_llm import OfflineError,unpack,LocalModel

class OfflineTests(unittest.TestCase):
    def test_internal_library_link_is_copied_without_creating_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'engine.tar'
            with tarfile.open(archive,'w') as tar:
                member=tarfile.TarInfo('bin/lib.so.1');member.size=3;tar.addfile(member,io.BytesIO(b'abc'))
                link=tarfile.TarInfo('bin/lib.so');link.type=tarfile.SYMTYPE;link.linkname='lib.so.1';tar.addfile(link)
            unpack(archive,root/'out')
            self.assertEqual((root/'out/bin/lib.so').read_bytes(),b'abc')
            self.assertFalse((root/'out/bin/lib.so').is_symlink())
    def test_traversal_and_external_links_are_rejected(self):
        for name,link in [('../escape',''),('lib.so','../../outside')]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);archive=root/'engine.tar'
                with tarfile.open(archive,'w') as tar:
                    member=tarfile.TarInfo(name)
                    if link:member.type=tarfile.SYMTYPE;member.linkname=link
                    tar.addfile(member)
                with self.assertRaises(OfflineError):unpack(archive,root/'out')
                self.assertFalse((root/'escape').exists())
    def test_context_is_checked_before_generation(self):
        model=LocalModel(Path('.'),context=100)
        model.tokens=lambda text:100
        model.request=lambda *args,**kwargs:self.fail('No generation request allowed')
        with self.assertRaises(OfflineError):model.infer('test',{},max_tokens=30)

    def test_schema_uses_engine_supported_nested_wrapper(self):
        model=LocalModel(Path('.'),context=4096);model.tokens=lambda text:5
        captured=[]
        def request(path,body):
            captured.append(body)
            return {'choices':[{'finish_reason':'stop','message':{'content':'{"answer":"yes"}'}}]}
        model.request=request
        schema={'type':'object','properties':{'answer':{'type':'string'}},'required':['answer']}
        self.assertEqual(model.infer('test',schema,max_tokens=30),{'answer':'yes'})
        self.assertEqual(captured[0]['response_format']['json_schema']['schema'],schema)

    def test_valid_json_with_missing_required_fields_is_not_accepted(self):
        model=LocalModel(Path('.'),context=4096);model.tokens=lambda text:5
        model.request=lambda *args,**kwargs:{'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}
        with self.assertRaises(OfflineError):model.infer('test',{'type':'object','required':['sources']},max_tokens=30)

    def test_partition_preserves_complete_text_including_oversized_message(self):
        from offline_report import batches
        rows=[{'chat_id':1,'message_id':1,'timestamp':'2026-11-04T00:00:00+00:00','text':'начало-'+('длинный текст '*180)+'-конец'},
              {'chat_id':2,'message_id':2,'timestamp':'2026-11-04T01:00:00+00:00','text':''},
              {'chat_id':1,'message_id':3,'timestamp':'2026-11-04T02:00:00+00:00','text':'отмена'}]
        parts=list(batches(rows,max_chars=1000))
        flat=[item for batch in parts for item in batch]
        self.assertGreater(len(parts),1)
        for row in rows:
            self.assertEqual(''.join(r['text'] for r in flat if r['chat_id']==row['chat_id'] and r['message_id']==row['message_id']),row['text'])
        self.assertEqual(sum(r['message_id']==2 for r in flat),1)

    def test_editorial_selection_cannot_invent_evidence(self):
        import datetime
        from offline_report import finalize
        from cloud_run import CloudError
        row={'chat_id':1,'chat_title':'Study','message_id':1,'timestamp':'2026-11-04T00:00:00+00:00','text':'Exam on November 6','outgoing':False,'reply_to_message_id':None}
        part={'sources':[{'key':'s1','chat_id':1,'message_id':1,'quote':'Exam on November 6'}],
              '_chat_summaries':[{'chat_id':1,'summary':'Discussed an exam'}],
              'sections':[],'highlights':[{'title':'Exam','summary':'Exam','urgency':'high','evidence':['s1']}],'actions':[]}
        class Model:
            context=32000
            def tokens(self,text):return 100
            def infer(self,*args,**kwargs):return {'title':'Exam','subtitle':'Review','highlights':[{'evidence':['fake']}],'actions':[],'sections':[]}
        with self.assertRaises(CloudError):finalize(datetime.date(2026,11,4),[row],[part],Model())

    def test_editor_sees_cancellation_even_when_it_is_not_among_last_three_messages(self):
        import datetime
        from offline_report import finalize
        rows=[]
        for n,text in enumerate(['Bring the documents','Canceled, do not bring them','Chat one','Chat two','Chat three'],1):
            rows.append({'chat_id':1,'chat_title':'Task','message_id':n,'timestamp':f'2026-11-04T0{n}:00:00+00:00','text':text,'outgoing':False,'reply_to_message_id':None})
        part={'sources':[{'key':'s1','chat_id':1,'message_id':1,'quote':'Bring the documents'}],
              '_chat_summaries':[{'chat_id':1,'summary':'Documents were discussed'}],
              'sections':[],'highlights':[],'actions':[{'text':'Bring documents','priority':'high','evidence':['s1']}]}
        class Model:
            context=32000
            def __init__(self):self.prompts=[]
            def tokens(self,text):return 100
            def infer(self,prompt,*args,**kwargs):
                self.prompts.append(prompt)
                return {'title':'Canceled task','subtitle':'Review','highlights':[],'actions':[],'sections':[]}
        model=Model();result=finalize(datetime.date(2026,11,4),rows,[part],model)
        self.assertTrue(all('Canceled, do not bring them' in prompt for prompt in model.prompts))
        self.assertEqual(result['actions'],[])

    def test_fake_section_citation_is_rejected(self):
        from report_analysis import verify_content
        for key in ['s999','999','_fake','-fake']:
            result={'sources':[],'chat_summaries':[],'highlights':[],'actions':[],'sections':[{'body':f'Invented evidence [{key}]'}]}
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'Unreferenced section evidence'):verify_content(result,[])

    def test_batch_grammar_requires_every_chat_and_uses_trusted_source_ids(self):
        from offline_report import batch_inference
        from jsonschema import validate,ValidationError
        rows=[{'chat_id':10,'message_id':11,'text':'Actual original'}, {'chat_id':20,'message_id':21,'text':''}]
        class Model:
            def infer(self,prompt,schema,**kwargs):
                self.schema=schema
                return {'title':'t','subtitle':'s','sources':[],'chat_summaries':{'10':'Text','20':'Media'},'highlights':[{'evidence':['s1']}],'actions':[],'sections':[]}
        model=Model();result=batch_inference(model,rows)('prompt')
        self.assertEqual(result['sources'],[{'key':'s1','chat_id':10,'message_id':11,'quote':'Actual original'}])
        self.assertEqual(model.schema['properties']['chat_summaries']['required'],['10','20'])
        with self.assertRaises(ValidationError):validate({'10':'Missing media chat'},model.schema['properties']['chat_summaries'])

    def test_past_deadlines_are_not_sent_as_current_actions(self):
        import datetime
        from offline_report import remove_expired_actions
        from report_analysis import LOCAL
        now=datetime.datetime(2026,11,5,15,30,tzinfo=LOCAL)
        result={'actions':[{'text':'Register','when':'4 ноября в 17:00'}, {'text':'Meeting','when':'5 ноября в 18:00'}, {'text':'Exam','when':'06.11.2026, 11:00'}, {'text':'Past ISO','when':'2026-11-04 17:00'}, {'text':'Ask','when':'Срок не указан'}]}
        self.assertEqual([a['text'] for a in remove_expired_actions(result,now)['actions']],['Meeting','Exam','Ask'])

    def test_timing_points_to_actual_same_chat_message_not_neighbor_proposal(self):
        from offline_report import ground_explicit_times
        sources={'m1':{'chat_id':10,'quote':'Предлагаю фронтенд'},'m2':{'chat_id':10,'quote':'Обсудим 5 ноября в 18:00'},'m3':{'chat_id':20,'quote':'Встреча 5 ноября в 18:00'}}
        result={'highlights':[],'actions':[{'when':'5 ноября в 18:00','evidence':['m1']}]}
        fixed=ground_explicit_times(result,sources,set(sources))
        self.assertEqual(fixed['actions'][0]['evidence'],['m1','m2'])
        self.assertEqual(result['actions'][0]['evidence'],['m1'])
        sources['m2']['quote']='Дату уточним'
        fixed=ground_explicit_times(result,sources,set(sources))
        self.assertNotIn('18:00',fixed['actions'][0]['when'])

    def test_deadline_guard_accounts_for_wait_until_ten_not_only_generation_time(self):
        import datetime
        from offline_report import effective_delivery,remove_expired_actions
        from report_analysis import LOCAL
        generated=datetime.datetime(2026,11,5,9,30,tzinfo=LOCAL)
        effective=effective_delivery(datetime.date(2026,11,4),generated)
        self.assertEqual(effective.hour,10)
        data={'actions':[{'when':'5 ноября в 09:45'},{'when':'5 ноября в 11:00'}]}
        self.assertEqual([a['when'] for a in remove_expired_actions(data,effective)['actions']],['5 ноября в 11:00'])

    def test_expired_imperative_highlight_moves_to_retrospective_section(self):
        import datetime
        from offline_report import remove_expired_actions
        from report_analysis import LOCAL
        result={'highlights':[{'title':'Registration','summary':'Нужно зарегистрироваться в срок','when':'4 ноября в 17:00','where':'Online','evidence':['m4']}],'actions':[],'sections':[]}
        fixed=remove_expired_actions(result,datetime.datetime(2026,11,5,10,tzinfo=LOCAL))
        self.assertEqual(fixed['highlights'],[])
        self.assertIn('уже прошло',fixed['sections'][0]['body'])
        self.assertIn('[m4]',fixed['sections'][0]['body'])

if __name__=='__main__':unittest.main()
