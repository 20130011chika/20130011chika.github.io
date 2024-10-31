from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_from_directory,
    session,
    jsonify,
)
from datetime import datetime, date
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import logging
from functools import wraps
import logging
from logging.handlers import RotatingFileHandler


# Flaskアプリケーションのインスタンスを作成
app = Flask(__name__)


# ログインページ表示とログイン処理
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        # データベースからユーザ情報を取得
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()

            # ユーザが存在し、パスワードが一致するか確認
            if user and check_password_hash(user[2], password):
                session["user_id"] = user[0]  # ユーザIDをセッションに保存
                return redirect(url_for("index"))
            else:
                flash("ユーザIDまたはパスワードが正しくありません。", "danger")

    return render_template("login.html")


# ログアウト処理
@app.route("/logout")
def logout():
    session.pop("user_id", None)  # セッションからユーザIDを削除
    flash("ログアウトしました。", "info")
    return redirect(url_for("login"))


# ユーザがログインしているかどうかを確認する関数
def login_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return decorated_view


# 新規ユーザの登録
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        password_hash = generate_password_hash(password, method="pbkdf2:sha256")

        with get_db_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, password_hash),
                )
                conn.commit()
                flash("新規登録が完了しました！", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("このユーザIDは既に使用されています。", "danger")

    return render_template("register.html")


# ロギングの設定
logging.basicConfig(level=logging.DEBUG)  # DEBUGレベルのログを表示する
logger = logging.getLogger(__name__)

# 環境フラグを設定 (サーバーではCGI対応、ローカルではしない)
if "tani-chika.com" in os.getenv("HOSTNAME", ""):
    app.config["USE_CGI"] = True
else:
    app.config["USE_CGI"] = False

# ログ設定
if not app.debug:
    handler = RotatingFileHandler("error.log", maxBytes=10000, backupCount=1)
    handler.setLevel(logging.ERROR)
    app.logger.addHandler(handler)

app.secret_key = "your_secret_key"  # フラッシュメッセージ用の秘密鍵

# 曜日を取得しやすいようにWEEKDAYS配列を定義
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

# アップロード可能な拡張子を定義
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "mp4"}


# アップロード可能なファイルかどうかをチェックする関数
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# アップロードフォルダの設定
UPLOAD_FOLDER = os.path.join(os.getcwd(), "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ファイル保存用の共通関数
def save_file(file, default_filename="default.jpg"):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        try:
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        except Exception as e:
            flash("ファイルの保存に失敗しました。")
            return redirect(url_for("add"))
        return filename
    return default_filename


# データベースの絶対パスを設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "diary.db")


# データベース接続用の関数
def get_db_connection():
    return sqlite3.connect(DATABASE_PATH)


# SQLiteデータベースへの接続とテーブル作成
def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # diaryテーブルの作成
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS diary
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                          date TEXT UNIQUE, 
                          content TEXT, 
                          filename TEXT)"""
        )

        # usersテーブルの作成
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS users (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT NOT NULL UNIQUE,
                   password_hash TEXT NOT NULL,
                   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        conn.commit()


# 許可されているファイル拡張子をチェック
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ホーム画面：各日付のサムネイルを表示
@app.route("/")
@login_required
def index():
    user_id = session["user_id"]
    today = date.today().isoformat()

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # ユーザ情報を取得
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        username = cursor.fetchone()[0]

        # 本日の日記があるか確認
        cursor.execute(
            "SELECT 1 FROM diary WHERE date = ? AND user_id = ?", (today, user_id)
        )
        entry_exists = cursor.fetchone() is not None

        # メッセージを設定
        if entry_exists:
            message = f"今日も登録ありがとう 😊"
        else:
            message = f"今日もお疲れさまです 😊"

        # 日記一覧の取得と曜日の追加
        cursor.execute(
            "SELECT id, date, content, filename FROM diary WHERE user_id=? ORDER BY date DESC",
            (user_id,),
        )
        entries = cursor.fetchall()

        # 日記がない場合のフラグを設定
        no_entries = len(entries) == 0

        # 曜日を追加したタプル形式のリストを作成
        formatted_entries = []
        for entry in entries:
            entry_date = datetime.strptime(entry[1], "%Y-%m-%d")
            weekday = WEEKDAYS[entry_date.weekday()]
            formatted_entry = entry + (weekday,)  # タプルに weekday を追加
            formatted_entries.append(formatted_entry)

    return render_template(
        "index.html",
        entries=formatted_entries,  # formatted_entriesを渡す
        use_cgi=app.config["USE_CGI"],
        message=message,
        no_entries=no_entries,
    )


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory("static/uploads", filename)


# 詳細画面：選択した日記の内容と画像・動画を表示
@app.route("/detail/<int:entry_id>")
def detail(entry_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM diary WHERE id=?", (entry_id,))
        entry = cursor.fetchone()

        if entry is None:
            return "日記が見つかりません", 404

        # 日付から曜日を取得してタプル形式で weekday を追加
        entry_date = datetime.strptime(entry[1], "%Y-%m-%d")
        weekday = WEEKDAYS[entry_date.weekday()]

        # タプルに weekday を追加
        entry = entry + (weekday,)

    return render_template(
        "detail.html",
        entry=entry,
        use_cgi=app.config["USE_CGI"],
    )


# 編集画面：既存の日記を編集
@app.route("/edit/<int:entry_id>", methods=["GET", "POST"])
def edit(entry_id):
    if request.method == "POST":
        # POSTデータ全体のログ出力
        print(f"受信したPOSTデータ: {request.form}")

        # フォームからのデータを取得
        date = request.form["date"]
        content = request.form["content"]
        file = request.files.get("file")  # 画像または動画ファイル
        file_cleared = request.form.get("file_cleared")  # ファイルクリアフラグを取得

        # ログ出力
        logger.debug("==== DEBUG START ====")
        logger.debug(f"POSTリクエスト受信: entry_id={entry_id}")
        logger.debug(f"file_clearedの値: {file_cleared}")
        logger.debug(f"fileの内容: {file}")  # ファイルの有無を確認
        logger.debug("==== DEBUG END ====")

        # デバッグ用ログ
        print(f"file_clearedの値: {file_cleared}")

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 既存のエントリのファイル名を取得
            cursor.execute("SELECT filename FROM diary WHERE id=?", (entry_id,))
            existing_filename = cursor.fetchone()[0]

            # ファイル選択が解除された場合は、filenameをNoneにする
            if file_cleared == "true":
                logger.debug(
                    "ファイル選択が解除されました。データベースのfilenameをクリアします。"
                )
                filename = "default.jpg"
            else:
                # ファイル保存処理を実行
                filename = save_file(file, default_filename=existing_filename)

            # データベースの更新処理
            cursor.execute(
                "UPDATE diary SET date=?, content=?, filename=? WHERE id=?",
                (date, content, filename, entry_id),
            )
            conn.commit()

        return redirect(url_for("detail", entry_id=entry_id))

    else:
        # 編集画面の初期表示時にエントリを取得
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM diary WHERE id=?", (entry_id,))
            entry = cursor.fetchone()

        # エントリが見つからない場合
        if entry is None:
            return "日記が見つかりません", 404
        return render_template(
            "add_or_edit.html", entry=entry, use_cgi=app.config["USE_CGI"]
        )


# 日記の新規作成画面
@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        date = request.form["date"]
        content = request.form["content"]
        file = request.files.get("file")  # 画像または動画ファイル
        user_id = session["user_id"]

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 同じ日付がすでに存在するか確認
            cursor.execute(
                "SELECT * FROM diary WHERE date=? AND user_id=?", (date, user_id)
            )
            existing_entry = cursor.fetchone()
            if existing_entry:
                flash("この日付の日記は既に存在します。")
                return redirect(url_for("add"))

            # ファイル保存処理を共通関数にまとめる
            filename = save_file(file)

            # 新規日記をデータベースに追加
            cursor.execute(
                "INSERT INTO diary (date, content, filename, user_id) VALUES (?, ?, ?, ?)",
                (date, content, filename, user_id if filename else None),
            )  # ファイルが選択されていない場合はNoneを設定

            conn.commit()
            # 保存後に詳細画面に遷移
            new_entry_id = cursor.lastrowid
            return redirect(url_for("detail", entry_id=new_entry_id))

    # GETリクエスト時には、新規追加画面を表示
    return render_template(
        "add_or_edit.html", entry=None, use_cgi=app.config["USE_CGI"]
    )


# 日記データ削除処理
@app.route("/delete/<int:entry_id>", methods=["POST"])
def delete(entry_id):
    # データベース接続
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 日記データを削除するSQLクエリを実行
        cursor.execute("DELETE FROM diary WHERE id = ?", (entry_id,))
        conn.commit()  # データベースに変更を保存

    # 削除後はホーム画面にリダイレクト
    return redirect(url_for("index"))


# 404エラーハンドリングのコード
@app.errorhandler(404)
def page_not_found(error):
    return render_template("404.html", error=error), 404


# 500エラーハンドリングのコード
@app.errorhandler(500)
def internal_server_error(error):
    return render_template("500.html", error=error), 500


# アプリケーションの開始前にデータベースを初期化
if __name__ == "__main__":
    init_db()
    # app.run(debug=True, use_reloader=False)  # 本番環境では削除またはコメントアウト
