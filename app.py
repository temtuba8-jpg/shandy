import os
import base64
import io
import re
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, render_template_string, request, redirect, url_for, session, flash, Response, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from bson.objectid import ObjectId
from xml.sax.saxutils import escape

app = Flask(__name__)

# =========================================================
# إعدادات التطبيق
# =========================================================

app.secret_key = os.environ.get("SECRET_KEY", "shendi_secret_news_key_2026")

UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# =========================================================
# مفتاح ImgBB API
# ضعه في Render Environment Variables باسم:
# IMGBB_API_KEY
# =========================================================

IMGBB_API_KEY = '85c7ff6f1e72c472683b7ac998a05e38'

# =========================================================
# رابط MongoDB Atlas
# ضعه في Render Environment Variables باسم:
# MONGO_URI
# =========================================================

MONGO_URI = "mongodb+srv://shendi_admin:Fad%400911923356@khloosa.s4zdyr6.mongodb.net/?appName=khloosa"

# الاتصال بقاعدة البيانات
client = MongoClient(MONGO_URI)
db = client.shendi_news_db


# =========================================================
# دالة مساعدة لرفع الصور إلى ImgBB تلقائياً
# =========================================================

def upload_image_to_imgbb(file_storage):
    try:
        if not file_storage or file_storage.filename == '':
            return ''

        if not IMGBB_API_KEY:
            print("ImgBB API Key is missing.")
            return ''

        file_bytes = file_storage.read()

        url = "https://api.imgbb.com/1/upload"

        payload = {
            "key": IMGBB_API_KEY
        }

        files = {
            "image": file_bytes
        }

        response = requests.post(
            url,
            data=payload,
            files=files,
            timeout=15
        )

        result = response.json()

        if result.get("success"):
            return result["data"]["url"]

    except Exception as e:
        print("ImgBB Upload Error:", e)

    return ''


# =========================================================
# تهيئة الحسابات الافتراضية عند التشغيل
# =========================================================

def init_db():
    try:
        admin_user = db.managers.find_one({
            "username": "admin"
        })

        if not admin_user:
            db.managers.insert_one({
                "username": "admin",
                "password": generate_password_hash('admin123'),
                "role": "super_admin"
            })

    except Exception as e:
        print("MongoDB Init Alert:", e)


try:
    init_db()
except Exception as e:
    print("Init DB error:", e)


# =========================================================
# الحذف التلقائي للأخبار القديمة
# يبقى كما طلبت: حذف الأخبار بعد 30 يوم
# =========================================================

def clean_expired_news():
    try:
        expiry_date = datetime.now() - timedelta(days=30)

        db.news.delete_many({
            "created_at": {
                "$lt": expiry_date
            }
        })

        db.ticker_news.delete_many({
            "created_at": {
                "$lt": expiry_date
            }
        })

    except Exception:
        pass


@app.before_request
def auto_clean():
    clean_expired_news()


# =========================================================
# دالة تحويل عناوين الأخبار إلى Slug
# =========================================================

def make_slug(text):
    if not text:
        return ""

    text = re.sub(
        r'[^\w\s-]',
        '',
        str(text)
    ).strip()

    return re.sub(
        r'[\s_-]+',
        '-',
        text
    )


@app.template_filter('slugify')
def slugify_filter(s):
    return make_slug(s)


# =========================================================
# فلتر الصور
# =========================================================

@app.template_filter('image_src')
def image_src_filter(img_val):

    if not img_val:
        return url_for(
            'static',
            filename='uploads/logo.png'
        )

    if str(img_val).startswith('http://') or str(img_val).startswith('https://'):
        return img_val

    if str(img_val).startswith('data:image'):
        return img_val

    return url_for(
        'static',
        filename='uploads/' + str(img_val)
    )


# =========================================================
# فلتر تنسيق التاريخ والوقت
# =========================================================

@app.template_filter('format_date')
def format_date_filter(val):

    if isinstance(val, datetime):
        return val.strftime('%Y-%m-%d | %H:%M')

    try:
        dt = datetime.fromisoformat(str(val))
        return dt.strftime('%Y-%m-%d | %H:%M')

    except Exception:
        return str(val)


# =========================================================
# Google Search Console Verification
# =========================================================
# Google طلبت الملف:
# google9269c338022e040d.html
#
# عند زيارة:
# /google9269c338022e040d.html
#
# سيظهر النص الذي طلبته Google.
# =========================================================

@app.route('/google9269c338022e040d.html')
def google_verification():
    return Response(
        'google-site-verification: google9269c338022e040d.html',
        mimetype='text/html'
    )


# =========================================================
# دالة عرض صور الأخبار
# =========================================================

@app.route('/news-image/<news_id>')
def serve_news_image(news_id):

    try:

        clean_id = news_id.split('-')[0].lstrip('-')

        news_item = None

        if ObjectId.is_valid(clean_id):

            news_item = db.news.find_one({
                "_id": ObjectId(clean_id)
            })

        if not news_item:

            news_item = db.news.find_one({
                "_id": clean_id
            })

        if news_item and news_item.get('image'):

            img_val = news_item['image']

            # صورة خارجية
            if (
                str(img_val).startswith('http://')
                or
                str(img_val).startswith('https://')
            ):

                return redirect(img_val)

            # صورة Base64
            if str(img_val).startswith('data:image'):

                try:

                    header, encoded = img_val.split(',', 1)

                    mime_type = header.split(';')[0].split(':')[1]

                    data = base64.b64decode(encoded)

                    return send_file(
                        io.BytesIO(data),
                        mimetype=mime_type
                    )

                except Exception:
                    pass

            # صورة محلية
            else:

                file_path = os.path.join(
                    app.config['UPLOAD_FOLDER'],
                    str(img_val)
                )

                if os.path.exists(file_path):

                    return send_file(file_path)

    except Exception:
        pass

    # استخدام اللوجو كصورة احتياطية
    logo_path = os.path.join(
        app.config['UPLOAD_FOLDER'],
        'logo.png'
    )

    if os.path.exists(logo_path):

        return send_file(
            logo_path,
            mimetype='image/png'
        )

    return '', 404


# =========================================================
# الصفحة الرئيسية
# =========================================================

@app.route('/')
def index():

    category = request.args.get('category')

    page = request.args.get(
        'page',
        1,
        type=int
    )

    per_page = 50

    skip = (page - 1) * per_page

    breaking_news = list(
        db.ticker_news
        .find()
        .sort("created_at", -1)
        .limit(15)
    )

    if not breaking_news:

        breaking_news = list(
            db.news
            .find({"is_breaking": 1})
            .sort("created_at", -1)
            .limit(10)
        )

    slider_news = list(
        db.news
        .find({"in_slider": 1})
        .sort("created_at", -1)
        .limit(5)
    )

    query = {}

    if category:

        if category in [
            'اقتصادية',
            'إقتصادية',
            'الشؤون الاقتصادية'
        ]:

            query = {
                "$or": [
                    {
                        "category": {
                            "$regex": "اقتصاد",
                            "$options": "i"
                        }
                    },
                    {
                        "category": {
                            "$regex": "إقتصاد",
                            "$options": "i"
                        }
                    },
                    {
                        "category": "الشؤون الاقتصادية"
                    }
                ]
            }

        else:

            query = {
                "category": category
            }

    total_news = db.news.count_documents(query)

    news_list = list(
        db.news
        .find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(per_page)
    )

    total_pages = (
        total_news + per_page - 1
    ) // per_page

    return render_template(
        'index.html',
        news_list=news_list,
        breaking_news=breaking_news,
        slider_news=slider_news,
        current_category=category,
        page=page,
        total_pages=total_pages
    )


# =========================================================
# صفحة تفاصيل الخبر
# =========================================================

@app.route('/news/<news_id>')
@app.route('/news/<news_id>-<slug>')
def news_detail(news_id, slug=None):

    try:

        clean_id = news_id.split('-')[0].lstrip('-')

        news_item = None

        if ObjectId.is_valid(clean_id):

            news_item = db.news.find_one({
                "_id": ObjectId(clean_id)
            })

        if not news_item:

            news_item = db.news.find_one({
                "_id": clean_id
            })

        if not news_item:

            return "الخبر غير موجود أو انتهت صلاحيته", 404

        related_news = list(
            db.news.find({
                "category": news_item.get('category'),
                "_id": {
                    "$ne": news_item['_id']
                }
            })
            .sort("created_at", -1)
            .limit(3)
        )

        try:

            return render_template(
                'news_detail.html',
                news=news_item,
                related=related_news
            )

        except Exception:

            fallback_html = """
            {% extends 'base.html' %}

            {% block title %}
            {{ news.title }} | صحيفة شندي الإخبارية
            {% endblock %}

            {% block content %}

            <div class="container"
                 style="max-width: 900px; margin: 30px auto; background: #fff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.05);">

                <div style="margin-bottom: 15px;">

                    <span style="background: var(--primary-red, #dc2626); color: #fff; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: bold;">
                        {{ news.category }}
                    </span>

                    <span style="color: #64748b; font-size: 14px; margin-right: 15px;">
                        <i class="far fa-clock"></i>
                        {{ news.created_at | format_date }}
                    </span>

                </div>

                <h1 style="color: #0f2c59; font-size: 28px; line-height: 1.6; margin-bottom: 20px;">
                    {{ news.title }}
                </h1>

                {% if news.image %}

                <div style="margin-bottom: 25px; text-align: center; background: #08111d; border-radius: 10px; padding: 10px;">

                    <img
                        src="{{ url_for('serve_news_image', news_id=news._id) }}"
                        alt="{{ news.title }}"
                        style="max-width: 100%; max-height: 450px; border-radius: 8px; object-fit: contain;"
                    >

                </div>

                {% endif %}

                <div style="font-size: 18px; line-height: 2.2; color: #334155; white-space: pre-line; margin-bottom: 40px;">
                    {{ news.details }}
                </div>

                <div style="border-top: 1px solid #e2e8f0; padding-top: 20px; display: flex; justify-content: space-between; align-items: center; color: #64748b; font-size: 14px;">

                    <span>
                        الكاتب / المصدر:
                        <strong>
                            {{ news.author | default('فريق التحرير') }}
                        </strong>
                    </span>

                    <a
                        href="{{ url_for('index') }}"
                        style="background: #0f2c59; color: #fff; padding: 8px 16px; border-radius: 6px; text-decoration: none;"
                    >
                        العودة للرئيسية
                    </a>

                </div>

            </div>

            {% endblock %}
            """

            return render_template_string(
                fallback_html,
                news=news_item,
                related=related_news
            )

    except Exception as e:

        print(
            "Error in news_detail:",
            e
        )

        return "الخبر غير موجود", 404


# =========================================================
# الصفحات القانونية والثابتة
# =========================================================

@app.route('/privacy-policy')
def privacy_policy():

    return render_template_string(
        """
        {% extends 'base.html' %}

        {% block content %}

        <div class='container'
             style='padding:40px; background:#fff; border-radius:10px; margin:30px auto; max-width:900px;'>

            <h1>سياسة الخصوصية</h1>

            <p>
                نحن نحترم خصوصية زوارنا ونلتزم بحماية بياناتهم...
            </p>

        </div>

        {% endblock %}
        """
    )


@app.route('/terms')
def terms_of_service():

    return render_template_string(
        """
        {% extends 'base.html' %}

        {% block content %}

        <div class='container'
             style='padding:40px; background:#fff; border-radius:10px; margin:30px auto; max-width:900px;'>

            <h1>شروط الاستخدام</h1>

            <p>
                يحكم استخدامكم لموقع صحيفة شندي هذه الشروط والأحكام...
            </p>

        </div>

        {% endblock %}
        """
    )


@app.route('/about-us')
def about_us():

    return render_template_string(
        """
        {% extends 'base.html' %}

        {% block content %}

        <div class='container'
             style='padding:40px; background:#fff; border-radius:10px; margin:30px auto; max-width:900px;'>

            <h1>من نحن</h1>

            <p>
                صحيفة شندي الإخبارية منصة إعلامية رقمية مستقلة...
            </p>

        </div>

        {% endblock %}
        """
    )


@app.route('/contact', methods=['GET', 'POST'])
def contact_us():

    if request.method == 'POST':

        flash(
            'تم استلام رسالتكم بنجاح! سيتواصل معكم فريق التحرير قريباً.'
        )

        return redirect(
            url_for('contact_us')
        )

    return render_template_string(
        """
        {% extends 'base.html' %}

        {% block content %}

        <div class='container'
             style='padding:40px; background:#fff; border-radius:10px; margin:30px auto; max-width:900px;'>

            <h1>اتصل بنا</h1>

            <form method='POST'>

                <button
                    type='submit'
                    style='background:var(--primary-red); color:#fff; padding:10px 20px; border:none; border-radius:6px;'
                >
                    إرسال الرسالة
                </button>

            </form>

        </div>

        {% endblock %}
        """
    )


# =========================================================
# ads.txt
# =========================================================

@app.route('/ads.txt')
def ads_txt():

    return Response(
        "google.com, pub-0000000000000000, DIRECT, f08c47fec0942fa0",
        mimetype='text/plain'
    )


# =========================================================
# robots.txt
# =========================================================

@app.route('/robots.txt')
def robots_txt():

    base_url = request.url_root.rstrip('/')

    robots_content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /admin/\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )

    return Response(
        robots_content,
        mimetype='text/plain'
    )


# =========================================================
# Sitemap XML
# =========================================================
#
# يشمل:
# - الصفحة الرئيسية
# - الصفحات الثابتة
# - الأخبار الموجودة حاليًا
#
# الأخبار المحذوفة بعد 30 يومًا تختفي تلقائيًا من Sitemap.
# =========================================================

@app.route('/sitemap.xml')
def sitemap_xml():

    base_url = request.url_root.rstrip('/')

    urls = []

    # =====================================================
    # تحويل تاريخ الخبر إلى صيغة صحيحة لـ Google Sitemap
    # =====================================================
    def sitemap_lastmod(value):

        if not value:
            return None

        try:

            # إذا كان التاريخ من MongoDB كـ datetime
            if isinstance(value, datetime):

                return value.strftime(
                    "%Y-%m-%d"
                )

            value_text = str(value).strip()

            if not value_text:
                return None

            # =================================================
            # محاولة قراءة ISO 8601
            # =================================================
            try:

                normalized_value = value_text.replace(
                    "Z",
                    "+00:00"
                )

                parsed_date = datetime.fromisoformat(
                    normalized_value
                )

                return parsed_date.strftime(
                    "%Y-%m-%d"
                )

            except Exception:
                pass

            # =================================================
            # محاولة قراءة صيغ التواريخ الشائعة
            # =================================================

            possible_formats = [
                "%Y-%m-%d",
                "%Y/%m/%d",
                "%d-%m-%Y",
                "%d/%m/%Y",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
                "%d-%m-%Y %H:%M:%S",
                "%d/%m/%Y %H:%M:%S"
            ]

            for date_format in possible_formats:

                try:

                    parsed_date = datetime.strptime(
                        value_text,
                        date_format
                    )

                    return parsed_date.strftime(
                        "%Y-%m-%d"
                    )

                except Exception:
                    continue

        except Exception as e:

            print(
                "Sitemap lastmod conversion error:",
                e
            )

        return None

    # الصفحة الرئيسية
    urls.append({
        "loc": f"{base_url}/",
        "priority": "1.0",
        "changefreq": "hourly"
    })

    # الصفحات الثابتة
    static_pages = [
        ("about-us", "0.5", "monthly"),
        ("contact", "0.5", "monthly"),
        ("privacy-policy", "0.3", "yearly"),
        ("terms", "0.3", "yearly")
    ]

    for page_name, priority, changefreq in static_pages:

        urls.append({
            "loc": f"{base_url}/{page_name}",
            "priority": priority,
            "changefreq": changefreq
        })

    # الأخبار الحالية
    news_items = list(
        db.news
        .find()
        .sort("created_at", -1)
        .limit(500)
    )

    for item in news_items:

        title = item.get(
            'title',
            ''
        )

        slug = make_slug(title)

        news_id = str(
            item['_id']
        )

        if slug:

            news_url = (
                f"{base_url}/news/"
                f"{news_id}-{slug}"
            )

        else:

            news_url = (
                f"{base_url}/news/"
                f"{news_id}"
            )

        news_data = {
            "loc": news_url,
            "priority": "0.8",
            "changefreq": "daily"
        }

        # =================================================
        # إضافة lastmod فقط بعد التأكد من صحة التاريخ
        # =================================================

        lastmod_text = sitemap_lastmod(
            item.get("created_at")
        )

        if lastmod_text:

            news_data["lastmod"] = lastmod_text

        urls.append(
            news_data
        )

    # بناء XML
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>'
    ]

    xml.append(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    )

    for item in urls:

        loc = escape(
            str(item["loc"])
        )

        priority = escape(
            str(item["priority"])
        )

        changefreq = escape(
            str(item["changefreq"])
        )

        xml.append("<url>")

        xml.append(
            f"<loc>{loc}</loc>"
        )

        # =================================================
        # lastmod أصبح دائمًا بصيغة:
        # YYYY-MM-DD
        # =================================================

        if item.get("lastmod"):

            lastmod_text = escape(
                str(item["lastmod"])
            )

            xml.append(
                f"<lastmod>{lastmod_text}</lastmod>"
            )

        xml.append(
            f"<changefreq>{changefreq}</changefreq>"
        )

        xml.append(
            f"<priority>{priority}</priority>"
        )

        xml.append("</url>")

    xml.append("</urlset>")

    return Response(
        '\n'.join(xml),
        mimetype='application/xml'
    )


# =========================================================
# لوحة التحكم والإدارة Admin
# =========================================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():

    if request.method == 'POST':

        user = request.form['username']

        pwd = request.form['password']

        manager = db.managers.find_one({
            "username": user
        })

        if manager and check_password_hash(
            manager['password'],
            pwd
        ):

            session['logged_in'] = True

            session['username'] = manager['username']

            session['role'] = manager.get(
                'role',
                'admin'
            )

            return redirect(
                url_for('admin_dashboard')
            )

        flash(
            'اسم المستخدم أو كلمة المرور غير صحيحة'
        )

    return render_template(
        'login.html'
    )


@app.route('/admin/logout')
def admin_logout():

    session.clear()

    return redirect(
        url_for('admin_login')
    )


@app.route('/admin')
def admin_dashboard():

    if not session.get('logged_in'):

        return redirect(
            url_for('admin_login')
        )

    search = request.args.get(
        'search',
        ''
    )

    author_filter = request.args.get(
        'author',
        ''
    )

    page = request.args.get(
        'page',
        1,
        type=int
    )

    per_page = 10

    skip = (
        page - 1
    ) * per_page

    ticker_items = list(
        db.ticker_news
        .find()
        .sort("_id", -1)
    )

    query = {}

    if search:

        query["title"] = {
            "$regex": search,
            "$options": "i"
        }

    if author_filter:

        query["author"] = author_filter

    total = db.news.count_documents(
        query
    )

    news_list = list(
        db.news
        .find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(per_page)
    )

    total_pages = (
        total + per_page - 1
    ) // per_page

    return render_template(
        'admin_dashboard.html',
        news_list=news_list,
        ticker_items=ticker_items,
        page=page,
        total_pages=total_pages,
        search=search,
        author_filter=author_filter
    )


# =========================================================
# إضافة خبر للشريط
# =========================================================

@app.route('/admin/add-ticker', methods=['POST'])
def add_ticker():

    if not session.get('logged_in'):

        return redirect(
            url_for('admin_login')
        )

    text = request.form.get(
        'ticker_text',
        ''
    ).strip()

    url = request.form.get(
        'ticker_url',
        ''
    ).strip()

    if text:

        db.ticker_news.insert_one({
            "title": text,
            "url": url,
            "created_at": datetime.now()
        })

        flash(
            'تمت إضافة الخبر إلى الشريط الإخباري بنجاح!'
        )

    return redirect(
        url_for('admin_dashboard')
    )


# =========================================================
# حذف خبر من الشريط
# =========================================================

@app.route('/admin/delete-ticker/<ticker_id>')
def delete_ticker(ticker_id):

    if not session.get('logged_in'):

        return redirect(
            url_for('admin_login')
        )

    try:

        db.ticker_news.delete_one({
            "_id": ObjectId(ticker_id)
        })

        flash(
            'تم حذف الخبر من الشريط الإخباري بنجاح'
        )

    except Exception:
        pass

    return redirect(
        url_for('admin_dashboard')
    )


# =========================================================
# إضافة خبر
# =========================================================

@app.route('/admin/add-news', methods=['POST'])
def add_news():

    if not session.get('logged_in'):

        return redirect(
            url_for('admin_login')
        )

    title = request.form['title']

    details = request.form['details']

    category = request.form['category']

    color = request.form.get(
        'color',
        '#1f2937'
    )

    is_breaking = (
        1
        if 'is_breaking' in request.form
        else 0
    )

    in_slider = (
        1
        if 'in_slider' in request.form
        else 0
    )

    author = session.get(
        'username',
        'admin'
    )

    image_url = ''

    if 'image' in request.files:

        file = request.files['image']

        if file.filename != '':

            image_url = upload_image_to_imgbb(
                file
            )

    db.news.insert_one({
        "title": title,
        "details": details,
        "category": category,
        "image": image_url,
        "color": color,
        "is_breaking": is_breaking,
        "in_slider": in_slider,
        "author": author,
        "created_at": datetime.now()
    })

    flash(
        'تم نشر الخبر بنجاح!'
    )

    return redirect(
        url_for('admin_dashboard')
    )


# =========================================================
# تعديل خبر
# =========================================================

@app.route('/admin/edit/<news_id>', methods=['POST'])
def edit_news(news_id):

    if not session.get('logged_in'):

        return redirect(
            url_for('admin_login')
        )

    title = request.form['title']

    details = request.form['details']

    category = request.form['category']

    color = request.form.get(
        'color',
        '#1f2937'
    )

    is_breaking = (
        1
        if 'is_breaking' in request.form
        else 0
    )

    in_slider = (
        1
        if 'in_slider' in request.form
        else 0
    )

    update_data = {
        "title": title,
        "details": details,
        "category": category,
        "color": color,
        "is_breaking": is_breaking,
        "in_slider": in_slider
    }

    if (
        'image' in request.files
        and request.files['image'].filename != ''
    ):

        file = request.files['image']

        image_url = upload_image_to_imgbb(
            file
        )

        if image_url:

            update_data["image"] = image_url

    try:

        db.news.update_one(
            {
                "_id": ObjectId(news_id)
            },
            {
                "$set": update_data
            }
        )

        flash(
            'تم تعديل الخبر بنجاح'
        )

    except Exception:

        flash(
            'حدث خطأ أثناء التعديل'
        )

    return redirect(
        url_for('admin_dashboard')
    )


# =========================================================
# حذف خبر
# =========================================================

@app.route('/admin/delete/<news_id>')
def delete_news(news_id):

    if not session.get('logged_in'):

        return redirect(
            url_for('admin_login')
        )

    try:

        db.news.delete_one({
            "_id": ObjectId(news_id)
        })

        flash(
            'تم حذف الخبر بنجاح'
        )

    except Exception:
        pass

    return redirect(
        url_for('admin_dashboard')
    )


# =========================================================
# إدارة المشرفين
# =========================================================

@app.route('/admin/managers', methods=['GET', 'POST'])
def manage_managers():

    if (
        not session.get('logged_in')
        or
        session.get('role') != 'super_admin'
    ):

        flash(
            'عذراً، الوصول لصفحة إدارة المشرفين متاح للمدير العام فقط!'
        )

        return redirect(
            url_for('admin_dashboard')
        )

    if request.method == 'POST':

        new_username = request.form.get(
            'username',
            ''
        ).strip()

        new_password = request.form.get(
            'password',
            ''
        ).strip()

        new_role = request.form.get(
            'role',
            'editor'
        ).strip()

        if new_username and new_password:

            if db.managers.find_one({
                "username": new_username
            }):

                flash(
                    'اسم المستخدم موجود مسبقاً'
                )

            else:

                db.managers.insert_one({
                    "username": new_username,
                    "password": generate_password_hash(
                        new_password
                    ),
                    "role": new_role
                })

                flash(
                    'تمت إضافة المشرف بنجاح'
                )

        else:

            flash(
                'يرجى تعبئة كافة الحقول بشكل صحيح'
            )

    managers_cursor = (
        db.managers
        .find()
        .sort("_id", 1)
    )

    managers = []

    for m in managers_cursor:

        count = db.news.count_documents({
            "author": m['username']
        })

        managers.append({
            "id": str(m['_id']),
            "username": m['username'],
            "role": m.get(
                'role',
                'editor'
            ),
            "news_count": count
        })

    return render_template(
        'admin_managers.html',
        managers=managers
    )


# =========================================================
# إعادة تعيين كلمة مرور المشرف
# =========================================================

@app.route(
    '/admin/managers/reset-password/<manager_id>',
    methods=['POST']
)
def reset_manager_password(manager_id):

    if (
        not session.get('logged_in')
        or
        session.get('role') != 'super_admin'
    ):

        return redirect(
            url_for('admin_dashboard')
        )

    new_pwd = request.form.get(
        'new_password',
        ''
    ).strip()

    if new_pwd:

        try:

            db.managers.update_one(
                {
                    "_id": ObjectId(manager_id)
                },
                {
                    "$set": {
                        "password": generate_password_hash(
                            new_pwd
                        )
                    }
                }
            )

            flash(
                'تم تحديث كلمة المرور للمشرف بنجاح!'
            )

        except Exception:
            pass

    return redirect(
        url_for('manage_managers')
    )


# =========================================================
# حذف المشرف
# =========================================================

@app.route('/admin/managers/delete/<manager_id>')
def delete_manager(manager_id):

    if (
        not session.get('logged_in')
        or
        session.get('role') != 'super_admin'
    ):

        return redirect(
            url_for('admin_dashboard')
        )

    try:

        manager = db.managers.find_one({
            "_id": ObjectId(manager_id)
        })

        if manager and manager['username'] != 'admin':

            db.managers.delete_one({
                "_id": ObjectId(manager_id)
            })

            flash(
                f'تم حذف المشرف {manager["username"]} بنجاح'
            )

    except Exception:
        pass

    return redirect(
        url_for('manage_managers')
    )
# =========================================================
# روت ads.txt
# =========================================================
@app.route('/ads.txt')
def ads_txt():
    response = "google.com, pub-1632368230954022, DIRECT, f08c47fec0942fa0\n"
    return response, 200, {
        'Content-Type': 'text/plain; charset=utf-8'
    }


# =========================================================
# تشغيل التطبيق
# =========================================================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
