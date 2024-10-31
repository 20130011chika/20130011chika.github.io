from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_from_directory,
)
from datetime import datetime
from datetime import datetime, timedelta
import os
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
import google.auth.transport.requests
from werkzeug.utils import secure_filename
import sqlite3
import logging
import requests

# Flaskアプリケーションのインスタンスを作成
app = Flask(__name__)
os.environ["IS_PRODUCTION"] = "1"  # 環境変数を設定
app.config["IS_PRODUCTION"] = os.getenv("IS_PRODUCTION") == "1"

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY", "default_secret_key"
)  # フラッシュメッセージ用の秘密鍵（環境変数が見つからない場合はデフォルト値を使用）

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
    minutes=30
)  # セッションの有効期限を30分に設定


@app.before_request
def make_session_permanent():
    session.permanent = True  # リクエストごとにセッションを永続化


# 環境フラグを設定 (サーバーではCGI対応、ローカルではしない)
app.config["USE_CGI"] = app.config["IS_PRODUCTION"]

import logging
from logging.handlers import RotatingFileHandler

# ロギングの設定
logging.basicConfig(
    filename="/home/tani-chika/log/app_debug.log",  # ログファイルのパスを指定
    level=logging.DEBUG,  # DEBUGレベルのログを記録
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.debug(f"IS_PRODUCTION (環境変数): {os.getenv('IS_PRODUCTION')}")
logging.debug(f"IS_PRODUCTION (app.config): {app.config['IS_PRODUCTION']}")
logging.debug("Application has started")
logger = logging.getLogger(__name__)

# Google OAuthのクライアント設定ファイルを指定
client_secrets_file = os.path.join(os.path.dirname(__file__), "client_secret.json")


@app.route("/cgi-bin/login")
def login():
    if not app.config["IS_PRODUCTION"]:
        return "Googleログインは本番環境でのみ有効です。", 403

    flow = Flow.from_client_secrets_file(
        client_secrets_file=client_secrets_file,
        scopes=[
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/userinfo.email",
        ],
        redirect_uri="https://tani-chika.com/cgi-bin/callback",
    )
    authorization_url, state = flow.authorization_url()
    session["state"] = state

    # セッション情報をログに出力
    logging.debug(f"Generated authorization URL: {authorization_url}")
    logging.debug(f"Session state set to: {session.get('state')}")  # ここで確認

    return redirect(authorization_url)


# ログ設定
if not app.debug:
    handler = RotatingFileHandler("error.log", maxBytes=10000, backupCount=1)
    handler.setLevel(logging.ERROR)
    app.logger.addHandler(handler)

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
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS diary
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                          date TEXT UNIQUE, 
                          content TEXT, 
                          filename TEXT)"""
        )
        conn.commit()


# 許可されているファイル拡張子をチェック
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


from functools import wraps


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if (
            "email" not in session
        ):  # セッションにメールアドレスがない場合はログインページにリダイレクト
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


# ホーム画面：各日付のサムネイルを表示
@app.route("/")
@login_required
def index():
    # デバッグメッセージ
    print("アクセス：indexページに到達しました")

    # サーバー環境で、ユーザーが未ログインの場合、ログインページにリダイレクト
    if app.config["IS_PRODUCTION"]:
        print("サーバーモードで実行されています")
        if "user_id" not in session:
            print(
                "ユーザーがログインしていないため、ログインページにリダイレクトします"
            )
            return redirect(url_for("login"))
        else:
            print(f"ログイン済みユーザー: {session['user_id']}")
    else:
        print("ローカルモードで実行されています")

    # 日記データの取得
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, date, content, filename FROM diary ORDER BY date DESC"
        )
        entries = cursor.fetchall()

        # 最新の日記の年号を取得
        if entries:
            latest_year = entries[0][1][:4]  # 日付から最初の4文字（年）を取得
        else:
            latest_year = None

    return render_template(
        "index.html",
        entries=entries,
        latest_year=latest_year,
        use_cgi=app.config["USE_CGI"],
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

        # 日付のフォーマットを行う
        if entry and entry[1]:  # entry[1] が日付フィールド
            formatted_date = datetime.strptime(entry[1], "%Y-%m-%d").strftime(
                "%Y年%m月%d日"
            )
        else:
            formatted_date = None
    return render_template(
        "detail.html",
        entry=entry,
        formatted_date=formatted_date,
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

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 同じ日付がすでに存在するか確認
            cursor.execute("SELECT * FROM diary WHERE date=?", (date,))
            existing_entry = cursor.fetchone()
            if existing_entry:
                flash("この日付の日記は既に存在します。")
                return redirect(url_for("add"))

            # ファイル保存処理を共通関数にまとめる
            filename = save_file(file)

            # 新規日記をデータベースに追加
            cursor.execute(
                "INSERT INTO diary (date, content, filename) VALUES (?, ?, ?)",
                (date, content, filename if filename else None),
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


@app.route("/cgi-bin/callback")
def callback():
    logging.debug("callbackルートに到達しました")
    if not app.config["IS_PRODUCTION"]:
        return "Googleログインは本番環境でのみ有効です。", 403

    flow = Flow.from_client_secrets_file(
        client_secrets_file=client_secrets_file,
        scopes=[
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/userinfo.email",
        ],
        redirect_uri="https://tani-chika.com/cgi-bin/callback",
    )

    logging.debug(f"リクエストのstate: {request.args.get('state')}", flush=True)
    logging.debug(f"セッションのstate: {session.get('state')}", flush=True)

    flow.fetch_token(authorization_response=request.url)
    if session.get("state") != request.args.get("state"):
        return "リクエストの状態が一致しません。", 403

    credentials = flow.credentials
    request_session = requests.session()
    token_request = google.auth.transport.requests.Request(session=request_session)

    try:
        id_info = id_token.verify_oauth2_token(credentials._id_token, token_request)
        session["email"] = id_info.get("email")  # メールアドレスをセッションに保存
    except ValueError as e:
        print(f"トークンの検証に失敗しました: {e}")
        return "トークンの検証に失敗しました。", 403

    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# 404エラーハンドリングのコード
@app.errorhandler(404)
def page_not_found(error):
    logging.error(f"404エラー: リクエストされたURLは {request.url}")
    return render_template("404.html", error=error), 404


# 500エラーハンドリングのコード
@app.errorhandler(500)
def internal_server_error(error):
    return render_template("500.html", error=error), 500


# アプリケーションの開始前にデータベースを初期化
# if __name__ == "__main__":
# init_db()
# app.run(debug=True, use_reloader=False)  # 本番環境では削除またはコメントアウト
