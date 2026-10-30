"""Portable owner-only bot transport. All credentials come from environment secrets."""
import html,json,os,re,urllib.error,urllib.parse,urllib.request,uuid
from pathlib import Path
OWNER_ID=int(os.environ.get('TELEGRAM_OWNER_ID','0'))
class DeliveryError(RuntimeError):pass

class Bot:
    def __init__(self, token=None):
        self._token = token or os.environ['TELEGRAM_BOT_TOKEN']

    def call(self, method, fields=None, document=None):
        if method not in {'getMe','getChat','getWebhookInfo','sendMessage','sendDocument','editMessageMedia'}:
            raise DeliveryError('Unsupported bot operation')
        fields = dict(fields or {})
        if method in {'getChat','sendMessage','sendDocument','editMessageMedia'}:
            if fields.get('chat_id') != OWNER_ID:
                raise DeliveryError('Recipient is not the configured owner')
        if document:
            path = Path(document)
            boundary = 'THelp'+uuid.uuid4().hex
            chunks=[]
            for key,value in fields.items():
                chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
            name = path.name.replace('"','').replace('\r','').replace('\n','')
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
            chunks.extend([path.read_bytes(),f'\r\n--{boundary}--\r\n'.encode()])
            body=b''.join(chunks)
            content_type='multipart/form-data; boundary='+boundary
        else:
            body=urllib.parse.urlencode(fields).encode()
            content_type='application/x-www-form-urlencoded'
        req=urllib.request.Request('https://api.telegram.org/bot'+self._token+'/'+method,data=body,headers={'Content-Type':content_type})
        try:
            with urllib.request.urlopen(req,timeout=90) as response:
                payload=json.load(response)
        except urllib.error.HTTPError as exc:
            # Never expose request URLs, response details or credential-bearing exceptions.
            raise DeliveryError('Telegram HTTP '+str(exc.code)) from None
        except Exception:
            raise DeliveryError('Telegram request failed') from None
        if not payload.get('ok'):
            raise DeliveryError('Telegram rejected operation')
        result=payload['result']
        if method in {'sendMessage','sendDocument','editMessageMedia'} and result.get('chat',{}).get('id')!=OWNER_ID:
            raise DeliveryError('Unexpected delivery recipient')
        return result

    def summary(self, data):
        esc=html.escape
        lines=[f'<b>THelp · {esc(data["date"])}</b>',f'<b>{esc(data["title"])}</b>','']
        for n,h in enumerate(data['highlights'][:4],1):
            lines.extend([f'<b>{n}. {esc(h["title"])}</b>',esc(h['summary']),f'<i>Где:</i> {esc(h["where"])}',f'<i>Когда:</i> {esc(h["when"])}',''])
        lines.append('Краткий PDF и подробный HTML — в следующих файлах. В HTML нажми «Подробный отчёт».')
        text='\n'.join(lines)
        if len(text)>3900:
            raise DeliveryError('Summary exceeds safe message length')
        return text

    def send_summary(self,data):
        return self.call('sendMessage',{'chat_id':OWNER_ID,'text':self.summary(data),'parse_mode':'HTML','disable_web_page_preview':'true'})

    def send_file(self,path,caption):
        path=Path(path)
        message=self.call('sendDocument',{'chat_id':OWNER_ID,'caption':caption},document=path)
        document=message.get('document',{})
        if document.get('file_name')!=path.name or document.get('file_size')!=path.stat().st_size:
            raise DeliveryError('Uploaded document metadata mismatch')
        return message

    def replace_file(self,message_id,path,caption):
        if not isinstance(message_id,int) or message_id<=0:raise DeliveryError('Invalid message ID')
        media=json.dumps({'type':'document','media':'attach://document','caption':caption},ensure_ascii=False)
        message=self.call('editMessageMedia',{'chat_id':OWNER_ID,'message_id':message_id,'media':media},document=path)
        if message.get('document',{}).get('file_size')!=Path(path).stat().st_size:
            raise DeliveryError('Replacement document metadata mismatch')
        return message
