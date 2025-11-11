import json
import os
import logging
import random
from typing import List, Optional, Dict, Union
from threading import Lock
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    QuickReply, QuickReplyButton, MessageAction
)

# === إعداد Logging ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# === إعداد متغيرات البيئة ===
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise RuntimeError("يجب تعيين LINE_CHANNEL_ACCESS_TOKEN و LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# === Locks للتزامن ===
content_lock = Lock()

class ContentManager:
    """مدير المحتوى مع معالجة أفضل للأخطاء"""
    
    def __init__(self):
        self.content_files: Dict[str, List[str]] = {}
        self.more_questions: List[str] = []
        self.proverbs_list: List[dict] = []
        self.riddles_list: List[dict] = []
        self.games_list: List[dict] = []
        self.detailed_results: Dict = {}
        
        # تتبع العناصر المستخدمة لكل قسم
        self.used_indices: Dict[str, List[int]] = {}
        
    def load_file_lines(self, filename: str) -> List[str]:
        """تحميل محتوى ملف نصي مع معالجة أفضل للأخطاء"""
        if not os.path.exists(filename):
            logger.warning(f"الملف غير موجود: {filename}")
            return []
        try:
            with open(filename, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                logger.info(f"تم تحميل {len(lines)} سطر من {filename}")
                return lines
        except UnicodeDecodeError:
            logger.error(f"خطأ في ترميز الملف: {filename}")
            return []
        except IOError as e:
            logger.error(f"خطأ في قراءة الملف {filename}: {e}")
            return []
    
    def load_json_file(self, filename: str) -> Union[dict, list]:
        """تحميل ملف JSON مع معالجة أفضل"""
        if not os.path.exists(filename):
            logger.warning(f"الملف غير موجود: {filename}")
            return [] if filename.endswith("s.json") else {}
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"تم تحميل {filename}")
                return data
        except json.JSONDecodeError as e:
            logger.error(f"خطأ في بنية JSON في {filename}: {e}")
            return [] if filename.endswith("s.json") else {}
        except IOError as e:
            logger.error(f"خطأ في قراءة {filename}: {e}")
            return [] if filename.endswith("s.json") else {}
    
    def initialize(self):
        """تحميل جميع الملفات"""
        # تحميل الملفات النصية
        self.content_files = {
            "سؤال": self.load_file_lines("questions.txt"),
            "تحدي": self.load_file_lines("challenges.txt"),
            "اعتراف": self.load_file_lines("confessions.txt"),
        }
        
        # تهيئة قوائم التتبع
        self.used_indices = {key: [] for key in self.content_files.keys()}
        self.used_indices["أكثر"] = []
        self.used_indices["أمثال"] = []
        self.used_indices["لغز"] = []
        
        # تحميل الملفات الأخرى
        self.more_questions = self.load_file_lines("more_file.txt")
        self.proverbs_list = self.load_json_file("proverbs.json")
        self.riddles_list = self.load_json_file("riddles.json")
        self.detailed_results = self.load_json_file("detailed_results.json")
        
        # تحميل الألعاب
        data = self.load_json_file("personality_games.json")
        if isinstance(data, dict):
            self.games_list = [data[key] for key in sorted(data.keys())]
        else:
            self.games_list = []
        
        logger.info("تم تهيئة جميع الملفات بنجاح")
    
    def get_random_index(self, command: str, max_length: int) -> int:
        """الحصول على index عشوائي غير مكرر"""
        with content_lock:
            # إذا استخدمنا كل العناصر، نعيد البدء
            if len(self.used_indices[command]) >= max_length:
                self.used_indices[command] = []
            
            # إنشاء قائمة بالـ indices المتاحة
            available_indices = [i for i in range(max_length) if i not in self.used_indices[command]]
            
            # اختيار index عشوائي
            if available_indices:
                index = random.choice(available_indices)
                self.used_indices[command].append(index)
                return index
            
            # fallback: اختيار عشوائي بالكامل
            return random.randint(0, max_length - 1)
    
    def get_content(self, command: str) -> Optional[str]:
        """الحصول على محتوى عشوائي مع تجنب التكرار"""
        file_list = self.content_files.get(command, [])
        if not file_list:
            return None
        
        index = self.get_random_index(command, len(file_list))
        return file_list[index]
    
    def get_more_question(self) -> Optional[str]:
        """الحصول على سؤال 'أكثر' عشوائي"""
        if not self.more_questions:
            return None
        
        index = self.get_random_index("أكثر", len(self.more_questions))
        return self.more_questions[index]
    
    def get_proverb(self) -> Optional[dict]:
        """الحصول على مثل عشوائي"""
        if not self.proverbs_list:
            return None
        
        index = self.get_random_index("أمثال", len(self.proverbs_list))
        return self.proverbs_list[index]
    
    def get_riddle(self) -> Optional[dict]:
        """الحصول على لغز عشوائي"""
        if not self.riddles_list:
            return None
        
        index = self.get_random_index("لغز", len(self.riddles_list))
        return self.riddles_list[index]

# تهيئة مدير المحتوى
content_manager = ContentManager()
content_manager.initialize()

# === حالات المستخدمين (يفضل استخدام Redis في الإنتاج) ===
user_game_state: Dict[str, dict] = {}
user_proverb_state: Dict[str, dict] = {}
user_riddle_state: Dict[str, dict] = {}

# === خريطة الأوامر ===
COMMANDS_MAP = {
    "سؤال": ["سؤال", "سوال", "اسأله", "اسئلة", "اسأل"],
    "تحدي": ["تحدي", "تحديات", "تحد"],
    "اعتراف": ["اعتراف", "اعترافات"],
    "أكثر": ["أكثر", "اكثر", "زيادة"],
    "أمثال": ["أمثال", "امثال", "مثل"],
    "لغز": ["لغز", "الغاز", "ألغاز"]
}

def find_command(text: str) -> Optional[str]:
    """البحث عن الأمر المطابق"""
    text_lower = text.lower().strip()
    for key, variants in COMMANDS_MAP.items():
        if text_lower in [v.lower() for v in variants]:
            return key
    return None

def create_main_menu() -> QuickReply:
    """إنشاء القائمة السريعة"""
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="❓ سؤال", text="سؤال")),
        QuickReplyButton(action=MessageAction(label="🎯 تحدي", text="تحدي")),
        QuickReplyButton(action=MessageAction(label="💬 اعتراف", text="اعتراف")),
        QuickReplyButton(action=MessageAction(label="✨ أكثر", text="أكثر")),
        QuickReplyButton(action=MessageAction(label="🎮 لعبة", text="لعبه")),
        QuickReplyButton(action=MessageAction(label="📜 أمثال", text="أمثال")),
        QuickReplyButton(action=MessageAction(label="🧩 لغز", text="لغز")),
    ])

def get_games_list() -> str:
    """قائمة الألعاب المتاحة"""
    if not content_manager.games_list:
        return "⚠️ لا توجد ألعاب متاحة حالياً."
    
    # بناء القائمة ديناميكياً بناءً على عدد الألعاب الموجودة
    titles = ["🎮 الألعاب المتاحة:", ""]
    
    # الرموز للأرقام
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, game in enumerate(content_manager.games_list):
        emoji = number_emojis[i] if i < len(number_emojis) else f"{i+1}️⃣"
        game_title = game.get('title', f'اللعبة {i+1}')
        titles.append(f"{emoji} {game_title}")
    
    titles.append("")
    titles.append(f"📌 أرسل رقم اللعبة (1-{len(content_manager.games_list)})")
    
    return "\n".join(titles)

def calculate_result(answers: List[str], game_index: int) -> str:
    """حساب نتيجة اللعبة"""
    count = {"أ": 0, "ب": 0, "ج": 0}
    for ans in answers:
        if ans in count:
            count[ans] += 1
    
    most_common = max(count, key=count.get)
    game_key = f"لعبة{game_index + 1}"
    result_text = content_manager.detailed_results.get(game_key, {}).get(
        most_common,
        f"✅ إجابتك الأكثر: {most_common}\n\n🎯 نتيجتك تعكس شخصية فريدة!"
    )
    
    stats = f"\n\n📊 إحصائياتك:\n"
    stats += f"أ: {count['أ']} | ب: {count['ب']} | ج: {count['ج']}"
    return result_text + stats

# === Routes ===
@app.route("/", methods=["GET"])
def home():
    return "✅ البوت يعمل بنجاح!", 200

@app.route("/health", methods=["GET"])
def health_check():
    """نقطة فحص صحة التطبيق"""
    return {"status": "healthy", "service": "line-bot"}, 200

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("توقيع غير صالح")
        abort(400)
    except Exception as e:
        logger.error(f"خطأ في معالجة الطلب: {e}")
        abort(500)
    
    return "OK"

# === معالج الرسائل ===
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    text_lower = text.lower()
    
    try:
        # === أمر المساعدة ===
        if text_lower in ["مساعدة", "help", "بداية", "start"]:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="اختر من القائمة أدناه:", quick_reply=create_main_menu())
            )
            return
        
        # === معالجة الأوامر الأساسية ===
        command = find_command(text)
        if command:
            handle_content_command(event, command)
            return
        
        # === معالجة إجابات الأمثال والألغاز ===
        if text_lower in ["جاوب", "الجواب", "الاجابة", "اجابة"]:
            handle_answer_command(event, user_id)
            return
        
        # === معالجة التلميح ===
        if text_lower in ["لمح", "تلميح", "hint"]:
            handle_hint_command(event, user_id)
            return
        
        # === معالجة طلب الألعاب ===
        if text_lower in ["لعبه", "لعبة", "العاب", "ألعاب", "game"]:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=get_games_list())
            )
            return
        
        # === معالجة اختيار اللعبة ===
        if text.isdigit():
            handle_game_selection(event, user_id, int(text))
            return
        
        # === معالجة إجابات اللعبة ===
        if user_id in user_game_state:
            handle_game_answer(event, user_id, text)
            return
        
        # تجاهل أي رسائل أخرى
        return
        
    except Exception as e:
        logger.error(f"خطأ في معالجة الرسالة: {e}", exc_info=True)
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="⚠️ حدث خطأ، يرجى المحاولة مرة أخرى")
            )
        except:
            pass



def handle_content_command(event, command: str):
    """معالجة أوامر المحتوى"""
    if command == "أمثال":
        proverb = content_manager.get_proverb()
        if not proverb:
            content = "⚠️ لا توجد أمثال متاحة حالياً."
        else:
            user_proverb_state[event.source.user_id] = proverb
            content = f"📜 المثل:\n{proverb['question']}\n\n💡 اكتب 'جاوب' لمعرفة المعنى"
    
    elif command == "لغز":
        riddle = content_manager.get_riddle()
        if not riddle:
            content = "⚠️ لا توجد ألغاز متاحة حالياً."
        else:
            user_riddle_state[event.source.user_id] = riddle
            content = f"🧩 اللغز:\n{riddle['question']}\n\n💡 اكتب 'لمح' للتلميح أو 'جاوب' للإجابة"
    
    elif command == "أكثر":
        question = content_manager.get_more_question()
        if not question:
            content = "⚠️ لا توجد أسئلة متاحة في قسم 'أكثر'."
        else:
            content = question
    
    else:
        content = content_manager.get_content(command)
        if not content:
            content = f"⚠️ لا توجد بيانات متاحة في قسم '{command}' حالياً."
    
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=content, quick_reply=create_main_menu())
    )

def handle_answer_command(event, user_id: str):
    """معالجة طلب الإجابة"""
    if user_id in user_proverb_state:
        proverb = user_proverb_state.pop(user_id)
        msg = f"✅ معنى المثل:\n{proverb['answer']}"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=msg, quick_reply=create_main_menu())
        )
    elif user_id in user_riddle_state:
        riddle = user_riddle_state.pop(user_id)
        msg = f"✅ الإجابة:\n{riddle['answer']}"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=msg, quick_reply=create_main_menu())
        )

def handle_hint_command(event, user_id: str):
    """معالجة طلب التلميح"""
    if user_id in user_riddle_state:
        riddle = user_riddle_state[user_id]
        hint = riddle.get('hint', 'لا يوجد تلميح')
        msg = f"💡 التلميح:\n{hint}"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=msg)
        )

def handle_game_selection(event, user_id: str, num: int):
    """معالجة اختيار اللعبة"""
    if 1 <= num <= len(content_manager.games_list):
        game_index = num - 1
        user_game_state[user_id] = {
            "game_index": game_index,
            "question_index": 0,
            "answers": []
        }
        
        game = content_manager.games_list[game_index]
        first_q = game["questions"][0]
        options = "\n".join([f"{k}. {v}" for k, v in first_q["options"].items()])
        
        msg = f"🎮 {game.get('title', f'اللعبة {num}')}\n\n"
        msg += f"❓ {first_q['question']}\n\n{options}\n\n📝 أرسل: أ، ب، ج"
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=msg)
        )

def handle_game_answer(event, user_id: str, text: str):
    """معالجة إجابة اللعبة"""
    state = user_game_state[user_id]
    answer_map = {"1": "أ", "2": "ب", "3": "ج", "a": "أ", "b": "ب", "c": "ج"}
    answer = answer_map.get(text.lower(), text)
    
    if answer in ["أ", "ب", "ج"]:
        state["answers"].append(answer)
        game = content_manager.games_list[state["game_index"]]
        state["question_index"] += 1
        
        if state["question_index"] < len(game["questions"]):
            q = game["questions"][state["question_index"]]
            options = "\n".join([f"{k}. {v}" for k, v in q["options"].items()])
            progress = f"[{state['question_index'] + 1}/{len(game['questions'])}]"
            msg = f"{progress} ❓ {q['question']}\n\n{options}\n\n📝 أرسل: أ، ب، ج"
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=msg)
            )
        else:
            result = calculate_result(state["answers"], state["game_index"])
            final_msg = f" انتهت اللعبة!\n\n{result}\n\n💬 أرسل 'لعبه' لتجربة لعبة أخرى!"
            
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=final_msg, quick_reply=create_main_menu())
            )
            del user_game_state[user_id]



# === تشغيل التطبيق ===
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"البوت يعمل على المنفذ {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
