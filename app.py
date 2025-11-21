# -*- coding: utf-8 -*-
import json,os,logging,random,threading,time,requests
from flask import Flask,request,abort
from linebot import LineBotApi,WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *

logging.basicConfig(level=logging.INFO)
app=Flask(__name__)
TOKEN,SECRET=os.getenv("LINE_CHANNEL_ACCESS_TOKEN"),os.getenv("LINE_CHANNEL_SECRET")
if not TOKEN or not SECRET:raise RuntimeError("Set LINE tokens")
line,handler=LineBotApi(TOKEN),WebhookHandler(SECRET)

C={'bg':'#0a0a0c','card':'#13131a','card_inner':'#1a1a22','primary':'#9C6BFF','primary_light':'#C7A3FF','accent':'#A67CFF','border':'#B58CFF','text':'#FFFFFF','text_dim':'#BFBFD9','text_muted':'#8C8CA3','btn_sec':'#1E1E27','btn_sec_txt':'#FFFFFF'}

class CM:
    def __init__(s):s.files={};s.mention=[];s.riddles=[];s.games=[];s.quotes=[];s.situations=[];s.results={};s.used={}
    def ld_l(s,f):
        if not os.path.exists(f):return []
        try:return[l.strip()for l in open(f,'r',encoding='utf-8')if l.strip()]
        except:return[]
    def ld_j(s,f):
        if not os.path.exists(f):return[]if'.json'in f else{}
        try:return json.load(open(f,'r',encoding='utf-8'))
        except:return[]if'.json'in f else{}
    def init(s):
        s.files={"سؤال":s.ld_l("questions.txt"),"تحدي":s.ld_l("challenges.txt"),"اعتراف":s.ld_l("confessions.txt")}
        s.mention=s.ld_l("more_questions.txt");s.situations=s.ld_l("situations.txt");s.riddles=s.ld_j("riddles.json")
        s.quotes=s.ld_j("quotes.json");s.results=s.ld_j("detailed_results.json")
        d=s.ld_j("personality_games.json");s.games=[d[k]for k in sorted(d.keys())]if isinstance(d,dict)else[]
        s.used={k:[]for k in list(s.files.keys())+["منشن","لغز","اقتباس","موقف"]}
    def rnd(s,k,mx):
        if mx==0:return 0
        if len(s.used.get(k,[]))>=mx:s.used[k]=[]
        av=[i for i in range(mx)if i not in s.used.get(k,[])]
        idx=random.choice(av)if av else random.randint(0,mx-1)
        if k not in s.used:s.used[k]=[]
        s.used[k].append(idx);return idx
    def get(s,c):l=s.files.get(c,[]);return l[s.rnd(c,len(l))]if l else None
    def get_m(s):return s.mention[s.rnd("منشن",len(s.mention))]if s.mention else None
    def get_s(s):return s.situations[s.rnd("موقف",len(s.situations))]if s.situations else None
    def get_r(s):return s.riddles[s.rnd("لغز",len(s.riddles))]if s.riddles else None
    def get_q(s):return s.quotes[s.rnd("اقتباس",len(s.quotes))]if s.quotes else None

cm=CM();cm.init()
rdl_st,gm_st={},{}

def menu():
    items=[("سؤال","سؤال"),("منشن","منشن"),("اعتراف","اعتراف"),("تحدي","تحدي"),("موقف","موقف"),("اقتباسات","اقتباسات"),("لغز","لغز"),("تحليل","تحليل")]
    return QuickReply(items=[QuickReplyButton(action=MessageAction(label=l,text=t))for l,t in items])

def hdr(t,i=""):
    return BoxComponent(layout='vertical',backgroundColor=C['card'],cornerRadius='16px',paddingAll='16px',borderWidth='1px',borderColor=C['border'],
        contents=[TextComponent(text=f"{i} {t}"if i else t,weight='bold',size='xl',color=C['text'],align='center')])

def help_flex():
    cmds=["سؤال","منشن","اعتراف","تحدي","موقف","اقتباسات","لغز","تحليل"]
    items=[TextComponent(text=f"• {c}",size='md',color=C['text_dim'],margin='sm')for c in cmds]
    return FlexSendMessage(alt_text="مساعدة",contents=BubbleContainer(direction='rtl',
        styles=BubbleStyle(body=BlockStyle(backgroundColor=C['bg'])),
        body=BoxComponent(layout='vertical',backgroundColor=C['bg'],paddingAll='20px',contents=[
            hdr("بوت عناد المالكي"),
            SeparatorComponent(margin='lg',color=C['border']),
            TextComponent(text="أوامر البوت:",weight='bold',size='lg',color=C['primary'],margin='lg'),
            BoxComponent(layout='vertical',margin='md',spacing='xs',contents=items),
            SeparatorComponent(margin='lg',color=C['border']),
            BoxComponent(layout='vertical',margin='md',paddingAll='12px',backgroundColor=C['card'],cornerRadius='8px',
                contents=[TextComponent(text="💡 ملاحظة: تقدر تستخدم البوت بالخاص والقروبات",size='sm',color=C['text_muted'],wrap=True,align='center')]),
            SeparatorComponent(margin='lg',color=C['border']),
            TextComponent(text="تم إنشاء هذا البوت بواسطة عبير الدوسري ©️ 2025",size='xxs',color=C['text_muted'],align='center',margin='md')])))

def puzzle_flex(p):
    return FlexSendMessage(alt_text="لغز",contents=BubbleContainer(direction='rtl',
        styles=BubbleStyle(body=BlockStyle(backgroundColor=C['bg'])),
        body=BoxComponent(layout='vertical',backgroundColor=C['bg'],paddingAll='24px',contents=[
            hdr("لغز","🧩"),
            BoxComponent(layout='vertical',margin='xl',paddingAll='24px',backgroundColor=C['card_inner'],cornerRadius='16px',borderWidth='1px',borderColor=C['border'],
                contents=[TextComponent(text=p['question'],size='lg',color=C['text'],wrap=True,align='center',weight='bold')]),
            BoxComponent(layout='vertical',margin='xl',spacing='md',contents=[
                ButtonComponent(action=MessageAction(label='💡 تلميح',text='لمح'),style='secondary',color=C['btn_sec'],height='md'),
                ButtonComponent(action=MessageAction(label='✓ التالي',text='جاوب'),style='primary',color=C['primary'],height='md')])])))

def games_flex(g):
    btns=[ButtonComponent(action=MessageAction(label=f"{i}. {x.get('title',f'تحليل {i}')}",text=str(i)),style='secondary',color=C['btn_sec'],height='sm')for i,x in enumerate(g[:10],1)]
    return FlexSendMessage(alt_text="تحليل الشخصية",contents=BubbleContainer(direction='rtl',
        styles=BubbleStyle(body=BlockStyle(backgroundColor=C['bg'])),
        body=BoxComponent(layout='vertical',backgroundColor=C['bg'],paddingAll='24px',contents=[
            hdr("تحليل الشخصية","🔮"),
            BoxComponent(layout='vertical',margin='xl',spacing='sm',contents=btns)])))

def ans_flex(a,t):
    i,cl=("✓ الجواب",C['primary'])if"جاوب"in t else("💡 تلميح",C['accent'])
    return FlexSendMessage(alt_text=t,contents=BubbleContainer(direction='rtl',
        styles=BubbleStyle(body=BlockStyle(backgroundColor=C['bg'])),
        body=BoxComponent(layout='vertical',backgroundColor=C['bg'],paddingAll='24px',contents=[
            BoxComponent(layout='vertical',paddingAll='16px',backgroundColor=C['card'],cornerRadius='16px',borderWidth='1px',borderColor=C['border'],
                contents=[TextComponent(text=i,weight='bold',size='xl',color=cl,align='center')]),
            BoxComponent(layout='vertical',margin='xl',paddingAll='24px',backgroundColor=C['card_inner'],cornerRadius='16px',
                contents=[TextComponent(text=a,size='lg',color=C['text'],wrap=True,align='center',weight='bold')])])))

def gq_flex(t,q,p):
    btns=[ButtonComponent(action=MessageAction(label=f"{k}. {v}",text=k),style='secondary',color=C['btn_sec'],height='sm')for k,v in q['options'].items()]
    return FlexSendMessage(alt_text=t,contents=BubbleContainer(direction='rtl',
        styles=BubbleStyle(body=BlockStyle(backgroundColor=C['bg'])),
        body=BoxComponent(layout='vertical',backgroundColor=C['bg'],paddingAll='20px',contents=[
            BoxComponent(layout='horizontal',contents=[
                TextComponent(text=t,weight='bold',size='lg',color=C['primary'],flex=1),
                TextComponent(text=p,size='xs',color=C['text_muted'],flex=0,align='end')]),
            SeparatorComponent(margin='md',color=C['border']),
            BoxComponent(layout='vertical',margin='lg',paddingAll='16px',backgroundColor=C['card'],cornerRadius='8px',borderWidth='1px',borderColor=C['border'],
                contents=[TextComponent(text=q['question'],size='md',color=C['text'],wrap=True)]),
            BoxComponent(layout='vertical',margin='lg',spacing='sm',contents=btns)])))

def calc_res(ans,gi):
    cnt={"أ":0,"ب":0,"ج":0}
    for a in ans:
        if a in cnt:cnt[a]+=1
    mc=max(cnt,key=cnt.get)
    return cm.results.get(f"لعبة{gi+1}",{}).get(mc,"شخصيتك فريدة ومميزة!")

def gr_flex(r):
    return FlexSendMessage(alt_text="النتيجة",contents=BubbleContainer(direction='rtl',
        styles=BubbleStyle(body=BlockStyle(backgroundColor=C['bg'])),
        body=BoxComponent(layout='vertical',backgroundColor=C['bg'],paddingAll='20px',contents=[
            TextComponent(text='✨ نتيجة التحليل',weight='bold',size='xl',color=C['primary'],align='center'),
            SeparatorComponent(margin='md',color=C['border']),
            BoxComponent(layout='vertical',margin='lg',paddingAll='16px',backgroundColor=C['card'],cornerRadius='8px',borderWidth='1px',borderColor=C['border'],
                contents=[TextComponent(text=r,size='md',color=C['text'],wrap=True,lineSpacing='6px')]),
            BoxComponent(layout='vertical',margin='xl',contents=[
                ButtonComponent(action=MessageAction(label='🔄 تحليل جديد',text='تحليل'),style='primary',color=C['primary'],height='sm')])])))

def content_flex(title,icon,content):
    return FlexSendMessage(alt_text=title,contents=BubbleContainer(direction='rtl',
        styles=BubbleStyle(body=BlockStyle(backgroundColor=C['bg'])),
        body=BoxComponent(layout='vertical',backgroundColor=C['bg'],paddingAll='24px',contents=[
            hdr(title,icon),
            BoxComponent(layout='vertical',margin='xl',paddingAll='20px',backgroundColor=C['card_inner'],cornerRadius='16px',borderWidth='1px',borderColor=C['border'],
                contents=[TextComponent(text=content,size='lg',color=C['text'],wrap=True,align='center')])])))

def quote_flex(q):
    txt=q.get('text','')
    auth=q.get('author','مجهول')
    return FlexSendMessage(alt_text="اقتباس",contents=BubbleContainer(direction='rtl',
        styles=BubbleStyle(body=BlockStyle(backgroundColor=C['bg'])),
        body=BoxComponent(layout='vertical',backgroundColor=C['bg'],paddingAll='24px',contents=[
            hdr("اقتباس","✨"),
            BoxComponent(layout='vertical',margin='xl',paddingAll='20px',backgroundColor=C['card_inner'],cornerRadius='16px',borderWidth='1px',borderColor=C['border'],
                contents=[
                    TextComponent(text=f'"{txt}"',size='lg',color=C['text'],wrap=True,align='center',style='italic'),
                    TextComponent(text=f"— {auth}",size='sm',color=C['text_muted'],align='center',margin='lg')])])))

CMDS={"سؤال":["سؤال","سوال"],"تحدي":["تحدي"],"اعتراف":["اعتراف"],"منشن":["منشن"],"موقف":["موقف"],"لغز":["لغز"],"اقتباسات":["اقتباسات","اقتباس","حكمة"]}
ICONS={"سؤال":"💭","تحدي":"🎯","اعتراف":"🤫","منشن":"👥","موقف":"🎭"}

def find_cmd(t):
    t=t.lower().strip()
    for k,v in CMDS.items():
        if t in[x.lower()for x in v]:return k
    return None

def reply(tk,msg):
    try:line.reply_message(tk,msg)
    except Exception as e:logging.error(f"Err:{e}")

@app.route("/",methods=["GET"])
def home():return"OK",200

@app.route("/health",methods=["GET"])
def health():return{"status":"ok"},200

@app.route("/callback",methods=["POST"])
def callback():
    sig=request.headers.get("X-Line-Signature","")
    body=request.get_data(as_text=True)
    try:handler.handle(body,sig)
    except InvalidSignatureError:abort(400)
    except:abort(500)
    return"OK"

@handler.add(MessageEvent,message=TextMessage)
def handle_msg(ev):
    uid,txt=ev.source.user_id,ev.message.text.strip()
    tl=txt.lower()
    try:
        if tl=="مساعدة":
            reply(ev.reply_token,[help_flex(),TextSendMessage(text="اختر من الأزرار:",quick_reply=menu())])
            return
        cmd=find_cmd(txt)
        if cmd:
            if cmd=="لغز":
                r=cm.get_r()
                if r:rdl_st[uid]=r;reply(ev.reply_token,puzzle_flex(r))
                else:reply(ev.reply_token,TextSendMessage(text="لا توجد ألغاز متاحة"))
            elif cmd=="اقتباسات":
                q=cm.get_q()
                if q:reply(ev.reply_token,quote_flex(q))
                else:reply(ev.reply_token,TextSendMessage(text="لا توجد اقتباسات"))
            elif cmd=="منشن":
                q=cm.get_m()
                if q:reply(ev.reply_token,content_flex("منشن","👥",q))
                else:reply(ev.reply_token,TextSendMessage(text="لا توجد أسئلة"))
            elif cmd=="موقف":
                s=cm.get_s()
                if s:reply(ev.reply_token,content_flex("موقف","🎭",s))
                else:reply(ev.reply_token,TextSendMessage(text="لا توجد مواقف"))
            else:
                c=cm.get(cmd)
                ic=ICONS.get(cmd,"")
                if c:reply(ev.reply_token,content_flex(cmd,ic,c))
                else:reply(ev.reply_token,TextSendMessage(text="لا توجد بيانات"))
            return
        if tl=="لمح":
            if uid in rdl_st:reply(ev.reply_token,ans_flex(rdl_st[uid].get('hint','لا يوجد'),"لمح"))
            return
        if tl=="جاوب":
            if uid in rdl_st:r=rdl_st.pop(uid);reply(ev.reply_token,ans_flex(r['answer'],"جاوب"))
            return
        if tl in["تحليل","تحليل شخصية","شخصية"]:
            if cm.games:reply(ev.reply_token,games_flex(cm.games))
            else:reply(ev.reply_token,TextSendMessage(text="لا توجد تحليلات متاحة"))
            return
        if txt.isdigit()and uid not in gm_st and 1<=int(txt)<=len(cm.games):
            gi=int(txt)-1;gm_st[uid]={"gi":gi,"qi":0,"ans":[]}
            g=cm.games[gi];reply(ev.reply_token,gq_flex(g.get('title',f'تحليل {int(txt)}'),g["questions"][0],f"1/{len(g['questions'])}"))
            return
        if uid in gm_st:
            st=gm_st[uid]
            amap={"1":"أ","2":"ب","3":"ج","a":"أ","b":"ب","c":"ج","أ":"أ","ب":"ب","ج":"ج"}
            ans=amap.get(tl,None)
            if ans:
                st["ans"].append(ans);g=cm.games[st["gi"]];st["qi"]+=1
                if st["qi"]<len(g["questions"]):reply(ev.reply_token,gq_flex(g.get('title','تحليل'),g["questions"][st["qi"]],f"{st['qi']+1}/{len(g['questions'])}"))
                else:reply(ev.reply_token,gr_flex(calc_res(st["ans"],st["gi"])));del gm_st[uid]
                return
    except Exception as e:logging.error(f"Err:{e}");reply(ev.reply_token,TextSendMessage(text="حدث خطأ، حاول مرة أخرى"))

def keep_alive():
    url=os.getenv("RENDER_EXTERNAL_URL")or os.getenv("REPL_SLUG")
    if url and not url.startswith("http"):url=f"https://{url}.onrender.com"
    while True:
        try:
            if url:requests.get(f"{url}/health",timeout=5)
            time.sleep(840)
        except:pass

if __name__=="__main__":
    if os.getenv("RENDER_EXTERNAL_URL")or os.getenv("REPL_SLUG"):
        threading.Thread(target=keep_alive,daemon=True).start()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",5000)))
