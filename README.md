# ناشر المنصات الاجتماعية (مجاني بالكامل)

ينشر منشورات مجدولة (نص عربي + صورة مصمّمة) على: فيسبوك، إنستغرام، ثريدز، تيليجرام — عبر GitHub Actions فقط، بلا خادم وبلا تكلفة.

## كيف يعمل
1. تُكتب المنشورات في `content/queue.yaml` (يكتبها Claude Code بقولك: «جهّز منشورات الأسبوع»).
2. `python src/preview.py` يولّد خلفية لكل منشور (Cloudflare ثم Pollinations) ويعرض الصور النهائية في `out/`.
3. بعد موافقتك تضع `approved: true` وتدفع التعديل.
4. كل 30 دقيقة يشغّل `publish.yml` السكربت `src/main.py`: ينشر المستحق فقط، ولا يكرّر منشوراً نُشر.

## 1) التهيئة الأولية
- أنشئ مستودعاً **عاماً** على GitHub وادفع هذا المجلد إليه (الفرع `main`).
- فعّل GitHub Pages: Settings ← Pages ← Source: `gh-pages` / root (يُنشأ الفرع تلقائياً عند أول نشر؛ أنشئه بتشغيل أول منشور ثم فعّل Pages).
- ضع خط **Cairo** (`Cairo-Regular.ttf` و`Cairo-Bold.ttf` أو الخط المتغيّر `Cairo[...].ttf`) في `brand/fonts/` (ترخيص OFL مجاني)، وشعارك في `brand/logo.png`، وعدّل `brand/brand.yaml`.
- Settings ← Actions ← General ← Workflow permissions: **Read and write**.

## 2) تيليجرام (الأسهل — ابدأ به)
1. كلّم `@BotFather` ← `/newbot` ← احفظ التوكن → `TELEGRAM_BOT_TOKEN`.
2. أضف البوت **مشرفاً** في قناتك. المعرّف `@اسم_القناة` أو رقم القناة → `TELEGRAM_CHANNEL_ID`.
3. أرسل أي رسالة للبوت في محادثة خاصة، ثم افتح `https://api.telegram.org/bot<TOKEN>/getUpdates` وخذ `chat.id` → `TELEGRAM_OWNER_CHAT_ID` (لاستقبال الملخصات والأخطاء).

## 3) فيسبوك + إنستغرام (تطبيق Meta)
1. حوّل حساب إنستغرام إلى **Business/Creator** واربطه بصفحة فيسبوك.
2. developers.facebook.com ← Create App (نوع Business) ← أضف منتج **Facebook Login for Business** أو استعمل Graph API Explorer.
3. الصلاحيات: `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`, `instagram_basic`, `instagram_content_publish`, `business_management`.
4. من Graph API Explorer: ولّد User Token ثم حوّله إلى طويل الأمد:
   `GET /oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=SHORT_TOKEN`
5. ثم `GET /me/accounts?access_token=LONG_USER_TOKEN` ← خذ `id` الصفحة → `FB_PAGE_ID` و`access_token` الصفحة (لا ينتهي) → `FB_PAGE_TOKEN`.
6. `GET /PAGE_ID?fields=instagram_business_account&access_token=...` ← `IG_USER_ID`.
> وضع التطوير يكفي لحسابك أنت (ضع نفسك مطوّراً/مختبراً في التطبيق) ولا يحتاج مراجعة Meta.

## 4) ثريدز
1. في نفس حساب المطوّر أنشئ تطبيقاً بحالة استخدام **Threads API**، وأضف حسابك مختبراً (Threads Tester) ووافق على الدعوة من تطبيق ثريدز.
2. الصلاحيتان: `threads_basic`, `threads_content_publish`.
3. ولّد توكن قصير ثم طويل الأمد (60 يوماً): `GET https://graph.threads.net/access_token?grant_type=th_exchange_token&client_secret=SECRET&access_token=SHORT` → `THREADS_TOKEN`.
4. `GET https://graph.threads.net/v1.0/me?fields=id&access_token=...` ← `THREADS_USER_ID`.
5. `refresh-tokens.yml` يجدّد التوكن كل أسبوع تلقائياً ويحدّث السرّ (يلزمه `GH_PAT`).

## 5) Cloudflare (خلفيات الذكاء الاصطناعي، مجاني بلا بطاقة)
dash.cloudflare.com ← Workers AI ← انسخ Account ID → `CF_ACCOUNT_ID`، وأنشئ API Token بصلاحية **Workers AI** فقط → `CF_API_TOKEN`. بدونهما يُستعمل Pollinations ثم خلفية متدرجة (لا يتوقف النشر).

## ما تفعله من اللوحة
المواضيع (إضافة/حذف) · توليد مسودات بالذكاء الاصطناعي · إضافة منشور يدوياً · **تعديل** منشور (العنوان والنص والموعد والمنصات، وتتجدد الصورة إن غيّرتَ كلمات البحث) · موافقة/إلغاء موافقة/حذف · **🚀 انشر الآن** · **🔁 إعادة المحاولة** للفاشل · **🔁 إعادة نشر** أي منشور (نسخة جديدة بنفس المحتوى والصورة: فوراً أو بموعد أو كمسودة) · **تقويم أسبوعي** مع توزيع تلقائي للمسودات · **لوحة صحة النظام** (فحص يومي لمفاتيح فيسبوك وإنستغرام وثريدز). مفتاح GitHub المطلوب: Contents وActions بصلاحية Read and write.

> تنبيه: GitHub يشغّل الجداول الدورية «بأفضل جهد» وقد يتأخر النشر المجدول ساعات؛ للنشر الفوري استعمل «انشر الآن».

## أشكال الصور
- **كاروسيل** (`carousel`): منشور من 3 إلى 10 شرائح بأسلوب «دراسة حالة» (غلاف كريمي، شرائح داكنة وفاتحة بالتناوب، عدّاد 01/08، وشريحة ختام بسؤال تفاعلي). يُنشر ألبوماً على إنستغرام وفيسبوك وثريدز وتيليجرام. تُكتب الشرائح في `image.slides` (كل شريحة: `kicker` و`title` و`body` و`points`)، أو من اللوحة بصيغة: `# عنوان` و`@ سطر صغير` و`- نقطة` وبين الشرائح `---`.
- **إنفوجرافك** (`infographic`): عنوان ونقاط مرقّمة (2 إلى 6) في `image.points`؛ مرتبط بالموضوع دائماً ولا يحتاج صورة خارجية.
- **صورة حقيقية** (`split`): صورة فوتوغرافية في الأعلى ولوحة نص أسفلها. تُجلب من Openverse (ملكية عامة CC0، بلا مفتاح ولا إسناد)، وإن أضفتَ مفتاح Pixabay أو Pexels صارا أولاً. دقة صور Openverse نحو 1024 بكسل فلذلك قالب `split` أنسب من `photo` الكامل.

## صور حقيقية مجاناً (Pexels)
للحصول على صور فوتوغرافية حقيقية بدل صور الذكاء الاصطناعي: سجّل مجاناً في pexels.com/api (فوري وبلا بطاقة)، وانسخ المفتاح، ثم:
`gh secret set PEXELS_API_KEY -R engshadi-79/social-publisher`
ويستعمله النظام تلقائياً للمنشورات التي فيها `image.photo_query`. القالبان الجديدان `photo` و`split` يُظهران الصورة بوضوح.

**بديل إن أوقف Pexels المفاتيح:** Pixabay (مجاني بلا إسناد): سجّل في pixabay.com ثم خذ المفتاح من pixabay.com/api/docs/ و`gh secret set PIXABAY_API_KEY -R engshadi-79/social-publisher`.

## توليد المنشورات من اللوحة
في تبويب «إضافة منشور» زر **✨ ولّد المسودات**: تختار موضوعاً وعدداً وموعداً، فيكتب Gemini (نص مجاني) المسودات ويقترح هاشتاجات من ترند Google الحالي، وتظهر بصورها في «بانتظار موافقتك». سير العمل `generate`. يحتاج سرّ `GEMINI_API_KEY`.

## المواضيع
حدّد المواضيع المسموحة في `content/topics.yaml`. أي منشور خارجها يُرفض.

## Gemini (خلفيات أعلى جودة، مدفوع)
إن وُجد سرّ `GEMINI_API_KEY` صار Gemini المزوّد الأول للخلفيات (نموذج `gemini-nano-banana-2.1`، نحو 0.03 دولار للصورة ولا حصة مجانية لتوليد الصور)، ويبقى Cloudflare ثم Pollinations احتياطاً. لإعادة توليد الخلفيات بعد تفعيله: شغّل workflow باسم `preview` واكتب `all` في خانة regen.

## 6) أسرار GitHub
Settings ← Secrets and variables ← Actions ← New repository secret، لكل مما يلي:

`FB_PAGE_ID`, `FB_PAGE_TOKEN`, `IG_USER_ID`, `THREADS_USER_ID`, `THREADS_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `TELEGRAM_OWNER_CHAT_ID`, `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `GH_PAT` (توكن دقيق الصلاحيات للمستودع نفسه: Secrets = Read and write)، واختيارياً `GEMINI_API_KEY`.

لا تضع أي سرّ في الملفات. المنصة التي لا سرّ لها تفشل بوضوح وتصلك رسالة بالخطأ؛ احذف مفتاحها من `platforms` لتجاهلها.

## لوحة التحكم
تُنشر تلقائياً على `https://<حسابك>.github.io/social-publisher/` وتتجدّد بعد كل نشر أو تعديل على `queue.yaml` (workflow اسمه `dashboard`). تعرض القادمة والمنشورة والمسودات والفاشلة بصورها وحالة كل منصة. للعرض فقط؛ الموافقة تتم بتعديل `approved` في الطابور.

## الاستعمال اليومي
```bash
pip install -r requirements.txt && playwright install chromium
python src/preview.py                 # معاينة + توليد الخلفيات إلى out/ و content/media/
python src/preview.py --regen ID --seed 7   # خلفية جديدة لمنشور
python src/main.py --dry-run          # تحقق + عرض بلا نشر
```
- القوالب: `quote` (1080×1080، نص في الوسط) · `announcement` (1080×1350، النص في الأعلى) · `tip` (1080×1350، البطاقة في الأسفل) · `story` (1080×1920، النص في الأعلى). اكتب في `visual_prompt` «empty space at top/center/bottom» بما يناسب القالب.
- قالب `story` يُنشر على إنستغرام كـ Story (بلا نص)، وعلى بقية المنصات كصورة عادية.
- الصورة تُرفع إلى `gh-pages` بصيغة JPEG (إنستغرام يشترطها) ويُرسل PNG مباشرة إلى تيليجرام.
- حالات `state.json`: `published` · `retry` (ستُعاد) · `failed` (3 محاولات فُشلت — أصلح السبب واحذف مدخل المنصة من الحالة لإعادة المحاولة).
- خطأ في `queue.yaml` يوقف كل النشر ويرسل لك السبب.
