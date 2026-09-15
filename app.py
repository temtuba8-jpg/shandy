import os
import base64
import io
from datetime import datetime, timedelta
from flask import Flask, render_template, render_template_string, request, redirect, url_for, session, flash, g, Response, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = 'shendi_secret_news_key_2026'
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# رابط قاعدة البيانات السحابية الدائمة (Neon Tech)
DATABASE_URL = "postgresql://neondb_owner:npg_Ekpb6L5BPJiM@ep-soft-cake-b4wof47n-pooler.c-6.us-east-2.aws.neon.tech/neondb?sslmode=require"

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        try:
            if error:
                db.rollback()
            db.close()
        except Exception:
            pass

def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # جدول المشرفين
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS managers (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'admin'
            );
        ''')
        
        # جدول الأخبار - عمود image يحفظ مسار الصورة أو كود Base64 السحابي الدائم
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS news (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                details TEXT NOT NULL,
                category TEXT NOT NULL,
                image TEXT,
                color TEXT DEFAULT '#1f2937',
                is_breaking INTEGER DEFAULT 0,
                in_slider INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        
        # جدول الشريط الإخباري العاجل
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ticker_news (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # حساب المدير الافتراضي
        cursor.execute("SELECT * FROM managers WHERE username = %s;", ('admin',))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO managers (username, password, role) VALUES (%s, %s, %s);",
                ('admin', generate_password_hash('admin123'), 'super_admin')
            )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print("Database Init Alert:", e)

# تشغيل إنشاء الجداول فوراً عند تحميل التطبيق ليعمل مع Gunicorn على Render
try:
    init_db()
except Exception as e:
    print("Init DB error:", e)

# الحذف التلقائي بعد 30 يوماً مع معالجة التراجع عند الخطأ لمنع تعليق المعاملة
def clean_expired_news():
    try:
        conn = get_db()
        cursor = conn.cursor()
        expiry_date = datetime.now() - timedelta(days=30)
        cursor.execute("DELETE FROM news WHERE created_at < %s;", (expiry_date,))
        cursor.execute("DELETE FROM ticker_news WHERE created_at < %s;", (expiry_date,))
        conn.commit()
        cursor.close()
    except Exception:
        if 'db' in g:
            try:
                g.db.rollback()
            except Exception:
                pass

@app.before_request
def auto_clean():
    clean_expired_news()

# دالة مساعدة لتحديد مصدر الصورة (سواء كانت Base64 أو مسار مجلد)
@app.template_filter('image_src')
def image_src_filter(img_val):
    if not img_val:
        return url_for('static', filename='uploads/logo.png')
    if str(img_val).startswith('data:image'):
        return img_val
    return url_for('static', filename='uploads/' + str(img_val))

# ==============================================================================
# 📸 مسار توليد رابط صورة حقيقي ومباشر لظهور الصورة المصغرة في واتساب وفيسبوك
# ==============================================================================
@app.route('/news-image/<int:news_id>')
def serve_news_image(news_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT image FROM news WHERE id = %s;", (news_id,))
    row = cursor.fetchone()
    cursor.close()

    if row and row['image']:
        img_val = row['image']
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

    # صورة بديلة (الشعار) في حال عدم وجود صورة للخبر
    logo_path = os.path.join(app.config['UPLOAD_FOLDER'], 'logo.png')
    if os.path.exists(logo_path):
        return send_file(logo_path, mimetype='image/png')
    return '', 404

# الصفحة الرئيسية
@app.route('/')
def index():
    category = request.args.get('category')
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, url, created_at FROM ticker_news ORDER BY id DESC LIMIT 15;")
    breaking_news = cursor.fetchall()
    
    if not breaking_news:
        cursor.execute("SELECT id, title, NULL as url, created_at FROM news WHERE is_breaking = 1 ORDER BY id DESC LIMIT 10;")
        breaking_news = cursor.fetchall()

    cursor.execute("SELECT * FROM news WHERE in_slider = 1 ORDER BY id DESC LIMIT 5;")
    slider_news = cursor.fetchall()

    if category:
        cursor.execute("SELECT COUNT(*) as count FROM news WHERE category = %s;", (category,))
        total_news = cursor.fetchone()['count']
        cursor.execute("SELECT * FROM news WHERE category = %s ORDER BY id DESC LIMIT %s OFFSET %s;", (category, per_page, offset))
    else:
        cursor.execute("SELECT COUNT(*) as count FROM news;")
        total_news = cursor.fetchone()['count']
        cursor.execute("SELECT * FROM news ORDER BY id DESC LIMIT %s OFFSET %s;", (per_page, offset))
    
    news_list = cursor.fetchall()
    total_pages = (total_news + per_page - 1) // per_page
    cursor.close()

    return render_template('index.html', news_list=news_list, breaking_news=breaking_news,
                           slider_news=slider_news, current_category=category,
                           page=page, total_pages=total_pages)

# صفحة تفاصيل الخبر الكاملة
@app.route('/news/<int:news_id>')
def news_detail(news_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM news WHERE id = %s;", (news_id,))
    news_item = cursor.fetchone()
    if not news_item:
        cursor.close()
        return "الخبر غير موجود أو انتهت صلاحيته", 404
        
    cursor.execute("SELECT * FROM news WHERE category = %s AND id != %s ORDER BY id DESC LIMIT 3;", (news_item['category'], news_id))
    related_news = cursor.fetchall()
    cursor.close()
    return render_template('news_detail.html', news=news_item, related=related_news)

# ==============================================================================
# الصفحات القانونية لـ Google AdSense & SEO
# ==============================================================================

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
        <p>يمكن للمستخدمين إلغاء استخدام ملف تعريف الارتباط DART عبر زيارة سياسة الخصوصية الخاصة بإعلانات Google وشبكة المحتوى على الرابط الرسمي لشركة Google.</p>
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
        <p><strong>صحيفة شندي الإخبارية</strong> هي منصة إعلامية رقمية مستقلة وشاملة، انطلقت لتكون صوتاً حراً ومعبراً عن مدينة شندي وولاية نهر النيل وعموم السودان، تنقل الخبر بمهنية، دقة، وموضوعية غير منحازة.</p>
        <h3 style="color: var(--primary-red); margin-top: 25px;">رؤيتنا الإعلامية</h3>
        <p>أن نكون المصدر الإخباري الأول والموثوق الذي يربط أبناء شندي وولاية نهر النيل في الداخل والمهاجر بأرض الوطن، وتقديم محتوى صحفي يرتقي بثقافة وقضايا المجتمع.</p>
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
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, created_at FROM news ORDER BY id DESC LIMIT 500;")
    news_items = cursor.fetchall()
    cursor.close()

    base_url = request.url_root.rstrip('/')
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    xml.append(f'<url><loc>{base_url}/</loc><priority>1.0</priority><changefreq>always</changefreq></url>')
    xml.append(f'<url><loc>{base_url}/about-us</loc><priority>0.5</priority><changefreq>monthly</changefreq></url>')
    xml.append(f'<url><loc>{base_url}/privacy-policy</loc><priority>0.5</priority><changefreq>monthly</changefreq></url>')
    xml.append(f'<url><loc>{base_url}/terms</loc><priority>0.5</priority><changefreq>monthly</changefreq></url>')
    xml.append(f'<url><loc>{base_url}/contact</loc><priority>0.5</priority><changefreq>monthly</changefreq></url>')

    for cat in ['سياسية', 'اجتماعية', 'ثقافية', 'ترفيه']:
        xml.append(f'<url><loc>{base_url}/?category={cat}</loc><priority>0.8</priority><changefreq>daily</changefreq></url>')

    for item in news_items:
        xml.append(f'<url><loc>{base_url}/news/{item["id"]}</loc><priority>0.8</priority><changefreq>weekly</changefreq></url>')

    xml.append('</urlset>')
    return Response('\n'.join(xml), mimetype='application/xml')

# ==============================================================================
# لوحة التحكم والإدارة
# ==============================================================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM managers WHERE username = %s;", (user,))
        manager = cursor.fetchone()
        cursor.close()
        
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
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM ticker_news ORDER BY id DESC;")
    ticker_items = cursor.fetchall()

    if search:
        cursor.execute("SELECT COUNT(*) as count FROM news WHERE title ILIKE %s;", (f'%{search}%',))
        total = cursor.fetchone()['count']
        cursor.execute("SELECT * FROM news WHERE title ILIKE %s ORDER BY id DESC LIMIT %s OFFSET %s;", (f'%{search}%', per_page, offset))
    else:
        cursor.execute("SELECT COUNT(*) as count FROM news;")
        total = cursor.fetchone()['count']
        cursor.execute("SELECT * FROM news ORDER BY id DESC LIMIT %s OFFSET %s;", (per_page, offset))

    news_list = cursor.fetchall()
    total_pages = (total + per_page - 1) // per_page
    cursor.close()

    return render_template('admin_dashboard.html', news_list=news_list, ticker_items=ticker_items, page=page, total_pages=total_pages, search=search)

@app.route('/admin/add-ticker', methods=['POST'])
def add_ticker():
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))

    text = request.form.get('ticker_text', '').strip()
    url = request.form.get('ticker_url', '').strip()

    if text:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO ticker_news (title, url) VALUES (%s, %s);", (text, url))
        conn.commit()
        cursor.close()
        flash('تمت إضافة الخبر إلى الشريط الإخباري بنجاح!')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete-ticker/<int:ticker_id>')
def delete_ticker(ticker_id):
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ticker_news WHERE id = %s;", (ticker_id,))
    conn.commit()
    cursor.close()
    flash('تم حذف الخبر من الشريط الإخباري بنجاح')
    return redirect(url_for('admin_dashboard'))

# إضافة خبر مع الحفظ السحابي الدائم للصورة
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

    image_data = ''
    if 'image' in request.files:
        file = request.files['image']
        if file.filename != '':
            filename = secure_filename(file.filename)
            local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(local_path)
            
            with open(local_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                mime_type = file.content_type if file.content_type else 'image/jpeg'
                image_data = f"data:{mime_type};base64,{encoded_string}"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO news (title, details, category, image, color, is_breaking, in_slider)
        VALUES (%s, %s, %s, %s, %s, %s, %s);
    ''', (title, details, category, image_data, color, is_breaking, in_slider))
    conn.commit()
    cursor.close()
    flash('تم نشر الخبر وحفظ الصورة سحابياً بنجاح!')
    return redirect(url_for('admin_dashboard'))

# تعديل خبر
@app.route('/admin/edit/<int:news_id>', methods=['POST'])
def edit_news(news_id):
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))

    title = request.form['title']
    details = request.form['details']
    category = request.form['category']
    color = request.form.get('color', '#1f2937')
    is_breaking = 1 if 'is_breaking' in request.form else 0
    in_slider = 1 if 'in_slider' in request.form else 0

    conn = get_db()
    cursor = conn.cursor()

    if 'image' in request.files and request.files['image'].filename != '':
        file = request.files['image']
        filename = secure_filename(file.filename)
        local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(local_path)

        with open(local_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            mime_type = file.content_type if file.content_type else 'image/jpeg'
            image_data = f"data:{mime_type};base64,{encoded_string}"

        cursor.execute('''
            UPDATE news SET title=%s, details=%s, category=%s, image=%s, color=%s, is_breaking=%s, in_slider=%s WHERE id=%s;
        ''', (title, details, category, image_data, color, is_breaking, in_slider, news_id))
    else:
        cursor.execute('''
            UPDATE news SET title=%s, details=%s, category=%s, color=%s, is_breaking=%s, in_slider=%s WHERE id=%s;
        ''', (title, details, category, color, is_breaking, in_slider, news_id))

    conn.commit()
    cursor.close()
    flash('تم تعديل الخبر بنجاح')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:news_id>')
def delete_news(news_id):
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM news WHERE id = %s;", (news_id,))
    conn.commit()
    cursor.close()
    flash('تم حذف الخبر بنجاح')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/managers', methods=['GET', 'POST'])
def manage_managers():
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))
    
    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        new_username = request.form['username']
        new_password = generate_password_hash(request.form['password'])
        try:
            cursor.execute("INSERT INTO managers (username, password) VALUES (%s, %s);", (new_username, new_password))
            conn.commit()
            flash('تمت إضافة المشرف بنجاح')
        except psycopg2.IntegrityError:
            conn.rollback()
            flash('اسم المستخدم موجود مسبقاً')

    cursor.execute("SELECT id, username, role FROM managers;")
    managers = cursor.fetchall()
    cursor.close()
    return render_template('admin_managers.html', managers=managers)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
