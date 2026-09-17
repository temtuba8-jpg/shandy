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

# رابط قاعدة البيانات الجديدة (MongoDB Atlas)
MONGO_URI = "mongodb+srv://shendi_admin:YOUR_REAL_PASSWORD@khloosa.s4zdyr6.mongodb.net/?appName=khloosa"
client = MongoClient(MONGO_URI)
db = client.shendi_news_db  # اسم قاعدة البيانات

# تهيئة الحسابات والجداول الافتراضية عند التشغيل
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

# الحذف التلقائي للأخبار والشريط الإخباري بعد 30 يوماً لتوفير المساحة وسرعة الأداء
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

# دالة تحويل عنوان الخبر إلى رابط نصي (Slug)
def make_slug(text):
    if not text:
        return ""
    text = re.sub(r'[^\w\s-]', '', str(text)).strip()
    return re.sub(r'[\s_-]+', '-', text)

@app.template_filter('slugify')
def slugify_filter(s):
    return make_slug(s)

# دالة مصدر الصورة
@app.template_filter('image_src')
def image_src_filter(img_val):
    if not img_val:
        return url_for('static', filename='uploads/logo.png')
    if str(img_val).startswith('data:image'):
        return img_val
    return url_for('static', filename='uploads/' + str(img_val))

# عرض صورة الخبر الحقيقية
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

# الصفحة الرئيسية (مع الدعم المرن لقسم الاقتصاد)
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

# صفحة تفاصيل الخبر الكاملة
@app.route('/news/<news_id>')
@app.route('/news/<news_id>-<slug>')
def news_detail(news_id, slug=None):
    try:
        news_item = db.news.find_one({"_id": ObjectId(news_id)})
        if not news_item:
            return "الخبر غير موجود أو انتهت صلاحيته", 404
        
        related_news = list(db.news.find({"category": news_item['category'], "_id": {"$ne": ObjectId(news_id)}}).sort("created_at", -1).limit(3))
        return render_template('news_detail.html', news=news_item, related=related_news)
    except Exception:
        return "الخبر غير موجود", 404

# الصفحات القانونية لـ Google AdSense & SEO
@app.route('/privacy-policy')
def privacy_policy():
    html_content = """
    {% extends 'base.html' %}
    {% block title %}سياسة الخصوصية وملفات تعريف الارتباط | صحيفة شندي{% endblock %}
    {% block content %}
    <div class="container" style="max-width: 900px; margin: 40px auto; background: #fff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); line-height: 2;">
        <h1 style="color: #0f2c59; border-right: 5px solid var(--primary-red); padding-right: 15px; margin-bottom: 25px;">سياسة الخصوصية وملفات تعريف الارتباط</h1>
        <p>أهلاً بكم في <strong>صحيفة شندي الإخبارية</strong>. تمثل خصوصية زوارنا أهمية بالغة لنا. توضح هذه الوثيقة أنواع المعلومات الشخصية التي نجمعها وكيفية استخدامها لحماية بياناتكم والامتثال لسياسات شبكة Google الإعلانية.</p>
        <h3 style="color: var(--primary-red); margin-top: 25px;">1. ملفات السجل (Log Files)</h3>
        <p>مثل معظم المواقع الإخبارية، نستخدم ملفات السجل لتسجيل معلومات تشمل عناوين بروتوكول الإنترنت (IP)، نوع المتصفح، ومزود الخدمة.</p>
        <h3 style="color: var(--primary-red); margin-top: 25px;">2. ملفات تعريف الارتباط وشبكة Google AdSense</h3>
        <p>نحن نستخدم ملفات تعريف الارتباط (Cookies) لتخزين تفضيلات الزوار. تستخدم شركة Google بصفتها مورداً خارجياً ملفات تعريف الارتباط لعرض الإعلانات على موقعنا وفقاً لاهتمامات المستخدمين عبر تقنية ملف تعريف الارتباط DART التابع لـ Google.</p>
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
        <p>مرحباً بكم في <strong>صحيفة شندي الإخبارية</strong>. يحكم استخدامكم لهذا الموقع الشروط والأحكام المعتمدة.</p>
        <h3 style="color: var(--primary-red); margin-top: 25px;">1. حقوق الملكية الفكرية</h3>
        <p>جميع المواد المنشورة من نصوص وتقارير وصور وفيديوهات هي حقوق محفوظة لصحيفة شندي الإخبارية، ويُسمح بالاقتباس الصحفي المعتدل بشرط الإشارة المباشرة والصريحة للمصدر مع وضع الرابط الأصلي للخبر.</p>
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
        <p><strong>صحيفة شندي الإخبارية</strong> هي منصة إعلامية رقمية مستقلة وشاملة، انطلقت لتكون صوتاً حراً والمعبراً عن مدينة شندي وولاية نهر النيل وعموم السودان، تنقل الخبر بمهنية، دقة، وموضوعية غير منحازة.</p>
    </div>
    {% endblock %}
    """
    return render_template_string(html_content)

@app.route('/contact', methods=['GET', 'POST'])
def contact_us():
    if request.method == 'POST':
        flash('تم استلام رسالتكم بنجاح! سيتواصل معكم فريق التحرير قريباً.')
        return redirect(url_for('contact_us'))

    html_content = """
    {% extends 'base.html' %}
    {% block title %}اتصل بنا | صحيفة شندي الإخبارية{% endblock %}
    {% block content %}
    <div class="container" style="max-width: 800px; margin: 40px auto; background: #fff; padding: 40px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.05);">
        <h1 style="color: #0f2c59; border-right: 5px solid var(--primary-red); padding-right: 15px; margin-bottom: 20px;">اتصل بهيئة التحرير</h1>
        {% with messages = get_flashed_messages() %}
          {% if messages %}
            {% for msg in messages %}
              <div style="background:#dcfce7; color:#15803d; padding:12px; border-radius:8px; margin-bottom:20px; font-weight:bold;">{{ msg }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}
        <form method="POST">
            <div style="margin-bottom: 15px;">
                <label style="display:block; font-weight:bold; margin-bottom:6px;">الاسم الكامل:</label>
                <input type="text" name="name" required style="width:100%; padding:10px; border:1px solid #cbd5e1; border-radius:6px; box-sizing:border-box;">
            </div>
            <div style="margin-bottom: 15px;">
                <label style="display:block; font-weight:bold; margin-bottom:6px;">البريد الإلكتروني:</label>
                <input type="email" name="email" required style="width:100%; padding:10px; border:1px solid #cbd5e1; border-radius:6px; box-sizing:border-box;">
            </div>
            <div style="margin-bottom: 20px;">
                <label style="display:block; font-weight:bold; margin-bottom:6px;">موضوع الرسالة:</label>
                <input type="text" name="subject" required style="width:100%; padding:10px; border:1px solid #cbd5e1; border-radius:6px; box-sizing:border-box;">
            </div>
            <div style="margin-bottom: 20px;">
                <label style="display:block; font-weight:bold; margin-bottom:6px;">نص الرسالة أو البلاغ الإخباري:</label>
                <textarea name="message" rows="5" required style="width:100%; padding:10px; border:1px solid #cbd5e1; border-radius:6px; box-sizing:border-box;"></textarea>
            </div>
            <button type="submit" style="background:var(--primary-red); color:#fff; padding:12px 25px; border:none; border-radius:6px; font-weight:bold; cursor:pointer;">إرسال الرسالة</button>
        </form>
    </div>
    {% endblock %}
    """
    return render_template_string(html_content)

@app.route('/ads.txt')
def ads_txt():
    content = "google.com, pub-0000000000000000, DIRECT, f08c47fec0942fa0"
    return Response(content, mimetype='text/plain')

@app.route('/robots.txt')
def robots_txt():
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /admin/*\n"
        f"Sitemap: {request.url_root}sitemap.xml\n"
    )
    return Response(content, mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap_xml():
    news_items = list(db.news.find().sort("created_at", -1).limit(500))
    base_url = request.url_root.rstrip('/')
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    xml.append(f'<url><loc>{base_url}/</loc><priority>1.0</priority><changefreq>always</changefreq></url>')
    xml.append(f'<url><loc>{base_url}/about-us</loc><priority>0.5</priority><changefreq>monthly</changefreq></url>')
    xml.append(f'<url><loc>{base_url}/privacy-policy</loc><priority>0.5</priority><changefreq>monthly</changefreq></url>')
    xml.append(f'<url><loc>{base_url}/terms</loc><priority>0.5</priority><changefreq>monthly</changefreq></url>')
    xml.append(f'<url><loc>{base_url}/contact</loc><priority>0.5</priority><changefreq>monthly</changefreq></url>')

    for cat in ['سياسية', 'اجتماعية', 'إقتصادية', 'رياضية']:
        xml.append(f'<url><loc>{base_url}/?category={cat}</loc><priority>0.8</priority><changefreq>daily</changefreq></url>')

    for item in news_items:
        slug = make_slug(item['title'])
        news_id = str(item['_id'])
        news_url = f"{base_url}/news/{news_id}-{slug}" if slug else f"{base_url}/news/{news_id}"
        xml.append(f'<url><loc>{news_url}</loc><priority>0.8</priority><changefreq>weekly</changefreq></url>')

    xml.append('</urlset>')
    return Response('\n'.join(xml), mimetype='application/xml')

# لوحة التحكم والإدارة
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
    return render_template('login.html')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))

    search = request.args.get('search', '')
    author_filter = request.args.get('author', '')
    page = request.args.get('page', 1, type=int)
    per_page = 10
    skip = (page - 1) * per_page

    ticker_items = list(db.ticker_news.find().sort("_id", -1))

    query = {}
    if search:
        query["title"] = {"$regex": search, "$options": "i"}
    if author_filter:
        query["author"] = author_filter

    total = db.news.count_documents(query)
    news_list = list(db.news.find(query).sort("created_at", -1).skip(skip).limit(per_page))
    total_pages = (total + per_page - 1) // per_page

    return render_template('admin_dashboard.html', news_list=news_list, ticker_items=ticker_items,
                           page=page, total_pages=total_pages, search=search, author_filter=author_filter)

@app.route('/admin/add-ticker', methods=['POST'])
def add_ticker():
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))

    text = request.form.get('ticker_text', '').strip()
    url = request.form.get('ticker_url', '').strip()

    if text:
        db.ticker_news.insert_one({
            "title": text,
            "url": url,
            "created_at": datetime.now()
        })
        flash('تمت إضافة الخبر إلى الشريط الإخباري بنجاح!')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-ticker/<ticker_id>')
def delete_ticker(ticker_id):
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))

    try:
        db.ticker_news.delete_one({"_id": ObjectId(ticker_id)})
        flash('تم حذف الخبر من الشريط الإخباري بنجاح')
    except Exception:
        pass
    return redirect(url_for('admin_dashboard'))

# إضافة خبر
@app.route('/admin/add-news', methods=['POST'])
def add_news():
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))

    title = request.form['title']
    details = request.form['details']
    category = request.form['category']
    color = request.form.get('color', '#1f2937')
    is_breaking = 1 if 'is_breaking' in request.form else 0
    in_slider = 1 if 'in_slider' in request.form else 0
    author = session.get('username', 'admin')

    image_filename = ''
    if 'image' in request.files:
        file = request.files['image']
        if file.filename != '':
            filename = secure_filename(file.filename)
            image_filename = f"{int(datetime.now().timestamp())}_{filename}"
            local_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            file.save(local_path)

    db.news.insert_one({
        "title": title,
        "details": details,
        "category": category,
        "image": image_filename,
        "color": color,
        "is_breaking": is_breaking,
        "in_slider": in_slider,
        "author": author,
        "created_at": datetime.now()
    })
    flash('تم نشر الخبر بنجاح!')
    return redirect(url_for('admin_dashboard'))

# تعديل خبر
@app.route('/admin/edit/<news_id>', methods=['POST'])
def edit_news(news_id):
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))

    title = request.form['title']
    details = request.form['details']
    category = request.form['category']
    color = request.form.get('color', '#1f2937')
    is_breaking = 1 if 'is_breaking' in request.form else 0
    in_slider = 1 if 'in_slider' in request.form else 0

    update_data = {
        "title": title,
        "details": details,
        "category": category,
        "color": color,
        "is_breaking": is_breaking,
        "in_slider": in_slider
    }

    if 'image' in request.files and request.files['image'].filename != '':
        file = request.files['image']
        filename = secure_filename(file.filename)
        image_filename = f"{int(datetime.now().timestamp())}_{filename}"
        local_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        file.save(local_path)
        update_data["image"] = image_filename

    try:
        db.news.update_one({"_id": ObjectId(news_id)}, {"$set": update_data})
        flash('تم تعديل الخبر بنجاح')
    except Exception:
        flash('حدث خطأ أثناء التعديل')

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<news_id>')
def delete_news(news_id):
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))
        
    try:
        db.news.delete_one({"_id": ObjectId(news_id)})
        flash('تم حذف الخبر بنجاح')
    except Exception:
        pass
    return redirect(url_for('admin_dashboard'))

# إدارة المشرفين ومتابعة مساهماتهم (خاص بالمدير العام super_admin)
@app.route('/admin/managers', methods=['GET', 'POST'])
def manage_managers():
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))
    
    if session.get('role') != 'super_admin':
        flash('عذراً، الوصول لصفحة إدارة المشرفين متاح للمدير العام فقط!')
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        new_password = request.form.get('password', '').strip()
        if new_username and new_password:
            if db.managers.find_one({"username": new_username}):
                flash('اسم المستخدم موجود مسبقاً')
            else:
                db.managers.insert_one({
                    "username": new_username,
                    "password": generate_password_hash(new_password),
                    "role": "admin"
                })
                flash('تمت إضافة المشرف بنجاح')
        else:
            flash('يرجى تعبئة كافة الحقول بشكل صحيح')

    managers_cursor = db.managers.find().sort("_id", 1)
    managers = []
    for m in managers_cursor:
        count = db.news.count_documents({"author": m['username']})
        managers.append({
            "id": str(m['_id']),
            "username": m['username'],
            "role": m.get('role', 'admin'),
            "news_count": count
        })

    return render_template('admin_managers.html', managers=managers)

@app.route('/admin/managers/reset-password/<manager_id>', methods=['POST'])
def reset_manager_password(manager_id):
    if not session.get('logged_in') or session.get('role') != 'super_admin':
        flash('غير مصرح لك بتغيير كلمات سر المشرفين!')
        return redirect(url_for('admin_dashboard'))

    new_pwd = request.form.get('new_password', '').strip()
    if not new_pwd:
        flash('يرجى كتابة كلمة المرور الجديدة')
        return redirect(url_for('manage_managers'))

    try:
        db.managers.update_one(
            {"_id": ObjectId(manager_id)},
            {"$set": {"password": generate_password_hash(new_pwd)}}
        )
        flash('تم تحديث كلمة المرور للمشرف بنجاح!')
    except Exception:
        pass
    return redirect(url_for('manage_managers'))

@app.route('/admin/managers/delete/<manager_id>')
def delete_manager(manager_id):
    if not session.get('logged_in') or session.get('role') != 'super_admin':
        flash('غير مصرح لك بحذف المشرفين!')
        return redirect(url_for('admin_dashboard'))

    try:
        manager = db.managers.find_one({"_id": ObjectId(manager_id)})
        if manager:
            if manager['username'] == 'admin' or manager.get('role') == 'super_admin':
                flash('لا يمكن حذف حساب الإدارة الرئيسي (admin)!')
                return redirect(url_for('manage_managers'))
            
            db.managers.delete_one({"_id": ObjectId(manager_id)})
            flash(f'تم حذف المشرف {manager["username"]} بنجاح')
    except Exception:
        pass
    return redirect(url_for('manage_managers'))

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
