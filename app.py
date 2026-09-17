import os
import base64
import io
import re
from datetime import datetime, timedelta
from flask import Flask, render_template, render_template_string, request, redirect, url_for, session, flash, Response, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from bson.objectid import ObjectId

app = Flask(__name__)
app.secret_key = 'shendi_secret_news_key_2026'
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# رابط قاعدة البيانات (MongoDB Atlas)
MONGO_URI = "mongodb+srv://shendi_admin:Fad%400911923356@khloosa.s4zdyr6.mongodb.net/?appName=khloosa"
client = MongoClient(MONGO_URI)
db = client.shendi_news_db  

def init_db():
    try:
        admin_user = db.managers.find_one({"username": "admin"})
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

def clean_expired_news():
    try:
        expiry_date = datetime.now() - timedelta(days=30)
        db.news.delete_many({"created_at": {"$lt": expiry_date}})
        db.ticker_news.delete_many({"created_at": {"$lt": expiry_date}})
    except Exception:
        pass

@app.before_request
def auto_clean():
    clean_expired_news()

def make_slug(text):
    if not text:
        return ""
    text = re.sub(r'[^\w\s-]', '', str(text)).strip()
    return re.sub(r'[\s_-]+', '-', text)

@app.template_filter('slugify')
def slugify_filter(s):
    return make_slug(s)

@app.template_filter('image_src')
def image_src_filter(img_val):
    if not img_val:
        return url_for('static', filename='uploads/logo.png')
    if str(img_val).startswith('data:image'):
        return img_val
    return url_for('static', filename='uploads/' + str(img_val))

# فلتر تنسيق التاريخ والوقت بشكل جميل للقارئ بدلاً من الأرقام الخام
@app.template_filter('format_date')
def format_date_filter(val):
    if isinstance(val, datetime):
        return val.strftime('%Y-%m-%d | %H:%M')
    try:
        dt = datetime.fromisoformat(str(val))
        return dt.strftime('%Y-%m-%d | %H:%M')
    except Exception:
        return str(val)

@app.route('/news-image/<news_id>')
def serve_news_image(news_id):
    try:
        news_item = db.news.find_one({"_id": ObjectId(news_id)})
        if news_item and news_item.get('image'):
            img_val = news_item['image']
            if str(img_val).startswith('data:image'):
                try:
                    header, encoded = img_val.split(',', 1)
                    mime_type = header.split(';')[0].split(':')[1]
                    data = base64.b64decode(encoded)
                    return send_file(io.BytesIO(data), mimetype=mime_type)
                except Exception:
                    pass
            else:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], str(img_val))
                if os.path.exists(file_path):
                    return send_file(file_path)
    except Exception:
        pass

    logo_path = os.path.join(app.config['UPLOAD_FOLDER'], 'logo.png')
    if os.path.exists(logo_path):
        return send_file(logo_path, mimetype='image/png')
    return '', 404

@app.route('/')
def index():
    category = request.args.get('category')
    page = request.args.get('page', 1, type=int)
    per_page = 50
    skip = (page - 1) * per_page

    breaking_news = list(db.ticker_news.find().sort("created_at", -1).limit(15))
    if not breaking_news:
        breaking_news = list(db.news.find({"is_breaking": 1}).sort("created_at", -1).limit(10))

    slider_news = list(db.news.find({"in_slider": 1}).sort("created_at", -1).limit(5))

    query = {}
    if category:
        if category in ['اقتصادية', 'إقتصادية', 'الشؤون الاقتصادية']:
            query = {"$or": [
                {"category": {"$regex": "اقتصاد", "$options": "i"}},
                {"category": {"$regex": "إقتصاد", "$options": "i"}},
                {"category": "الشؤون الاقتصادية"}
            ]}
        else:
            query = {"category": category}

    total_news = db.news.count_documents(query)
    news_list = list(db.news.find(query).sort("created_at", -1).skip(skip).limit(per_page))
    total_pages = (total_news + per_page - 1) // per_page

    return render_template('index.html', news_list=news_list, breaking_news=breaking_news,
                           slider_news=slider_news, current_category=category,
                           page=page, total_pages=total_pages)

# صفحة تفاصيل الخبر الكاملة مع تصميم احترافي متجاوب
@app.route('/news/<news_id>')
@app.route('/news/<news_id>-<slug>')
def news_detail(news_id, slug=None):
    try:
        clean_id = news_id.lstrip('-')
        news_item = db.news.find_one({"_id": ObjectId(clean_id)})
        if not news_item:
            return "الخبر غير موجود أو انتهت صلاحيته", 404
        
        related_news = list(db.news.find({"category": news_item.get('category'), "_id": {"$ne": ObjectId(clean_id)}}).sort("created_at", -1).limit(3))
        
        # قالب داخلي لصفحة التفاصيل يمنع أي خطأ في حال نسيان ملف الـ HTML الخاص بها
        detail_html = """
        {% extends 'base.html' %}
        {% block title %}{{ news.title }} | صحيفة شندي الإخبارية{% endblock %}
        {% block content %}
        <div class="container" style="max-width: 900px; margin: 30px auto; background: #fff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.05);">
            <div style="margin-bottom: 15px;">
                <span style="background: var(--primary-red, #dc2626); color: #fff; padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: bold;">{{ news.category }}</span>
                <span style="color: #64748b; font-size: 14px; margin-right: 15px;"><i class="far fa-clock"></i> {{ news.created_at | format_date }}</span>
            </div>
            <h1 style="color: #0f2c59; font-size: 28px; line-height: 1.6; margin-bottom: 20px;">{{ news.title }}</h1>
            
            {% if news.image %}
            <div style="margin-bottom: 25px; text-align: center;">
                <img src="{{ url_for('serve_news_image', news_id=news._id) }}" alt="{{ news.title }}" style="max-width: 100%; max-height: 450px; border-radius: 10px; object-fit: cover; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
            </div>
            {% endif %}
            
            <div style="font-size: 18px; line-height: 2.2; color: #334155; white-space: pre-line; margin-bottom: 40px;">
                {{ news.details }}
            </div>

            <div style="border-top: 1px solid #e2e8f0; padding-top: 20px; display: flex; justify-content: space-between; align-items: center; color: #64748b; font-size: 14px;">
                <span>الكاتب / المصدر: <strong>{{ news.author | default('فريق التحرير') }}</strong></span>
                <a href="{{ url_for('index') }}" style="background: #0f2c59; color: #fff; padding: 8px 16px; border-radius: 6px; text-decoration: none;">العودة للرئيسية</a>
            </div>
        </div>
        {% endblock %}
        """
        return render_template_string(detail_html, news=news_item, related=related_news)
    except Exception as e:
        print("Error in news_detail:", e)
        return "الخبر غير موجود", 404

@app.route('/privacy-policy')
def privacy_policy():
    html_content = """
    {% extends 'base.html' %}
    {% block title %}سياسة الخصوصية وملفات تعريف الارتباط | صحيفة شندي{% endblock %}
    {% block content %}
    <div class="container" style="max-width: 900px; margin: 40px auto; background: #fff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); line-height: 2;">
        <h1 style="color: #0f2c59; border-right: 5px solid var(--primary-red); padding-right: 15px; margin-bottom: 25px;">سياسة الخصوصية وملفات تعريف الارتباط</h1>
        <p>أهلاً بكم في <strong>صحيفة شندي الإخبارية</strong>. تمثل خصوصية زوارنا أهمية بالغة لنا...</p>
    </div>
    {% endblock %}
    """
    return render_template_string(html_content)

@app.route('/terms')
def terms_of_service():
    html_content = """
    {% extends 'base.html' %}
    {% block title %}اتفاقية وشروط الاستخدام | صحيفة شندي{% endblock %}
    {% block content %}
    <div class="container" style="max-width: 900px; margin: 40px auto; background: #fff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); line-height: 2;">
        <h1 style="color: #0f2c59; border-right: 5px solid var(--primary-red); padding-right: 15px; margin-bottom: 25px;">شروط الاستخدام واتفاقية النشر</h1>
        <p>مرحباً بكم في <strong>صحيفة شندي الإخبارية</strong>...</p>
    </div>
    {% endblock %}
    """
    return render_template_string(html_content)

@app.route('/about-us')
def about_us():
    html_content = """
    {% extends 'base.html' %}
    {% block title %}من نحن | صحيفة شندي الإخبارية{% endblock %}
    {% block content %}
    <div class="container" style="max-width: 900px; margin: 40px auto; background: #fff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); line-height: 2;">
        <h1 style="color: #0f2c59; border-right: 5px solid var(--primary-red); padding-right: 15px; margin-bottom: 25px;">من نحن - صحيفة شندي الإخبارية</h1>
        <p><strong>صحيفة شندي الإخبارية</strong> منصة إعلامية رقمية مستقلة...</p>
    </div>
    {% endblock %}
    """
    return render_template_string(html_content)

@app.route('/contact', methods=['GET', 'POST'])
def contact_us():
    if request.method == 'POST':
        flash('تم استلام رسالتكم بنجاح! سيتواصل معكم فريق التحرير قريباً.')
        return redirect(url_for('contact_us'))
    return "اتصل بنا"

@app.route('/ads.txt')
def ads_txt():
    return Response("google.com, pub-0000000000000000, DIRECT, f08c47fec0942fa0", mimetype='text/plain')

@app.route('/robots.txt')
def robots_txt():
    content = "User-agent: *\nAllow: /\nDisallow: /admin\n"
    return Response(content, mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap_xml():
    news_items = list(db.news.find().sort("created_at", -1).limit(500))
    base_url = request.url_root.rstrip('/')
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for item in news_items:
        slug = make_slug(item['title'])
        news_id = str(item['_id'])
        news_url = f"{base_url}/news/{news_id}-{slug}" if slug else f"{base_url}/news/{news_id}"
        xml.append(f'<url><loc>{news_url}</loc><priority>0.8</priority><changefreq>weekly</changefreq></url>')
    xml.append('</urlset>')
    return Response('\n'.join(xml), mimetype='application/xml')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']
        manager = db.managers.find_one({"username": user})
        if manager and check_password_hash(manager['password'], pwd):
            session['logged_in'] = True
            session['username'] = manager['username']
            session['role'] = manager['role']
            return redirect(url_for('admin_dashboard'))
        flash('اسم المستخدم أو كلمة المرور غير صحيحة')
    return "Login Page"

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))
    return "Admin Dashboard"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
