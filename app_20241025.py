from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_from_directory,
)
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import sqlite3

# Flaskアプリケーションのインスタンスを作成
app = Flask(__name__)

import logging
from logging.handlers import RotatingFileHandler

# ログ設定
if not app.debug:
    handler = RotatingFileHandler("error.log", maxBytes=10000, backupCount=1)
    handler.setLevel(logging.ERROR)
    app.logger.addHandler(handler)

app.secret_key = "your_secret_key"  # フラッシュメッセージ用の秘密鍵

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


# SQLiteデータベースへの接続とテーブル作成
def init_db():
    with sqlite3.connect("diary.db") as conn:
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


# ホーム画面：各日付のサムネイルを表示
@app.route("/")
def index():
    with sqlite3.connect("diary.db") as conn:
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

    return render_template("index.html", entries=entries, latest_year=latest_year)


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory("static/uploads", filename)


# 詳細画面：選択した日記の内容と画像・動画を表示
@app.route("/detail/<int:entry_id>")
def detail(entry_id):
    with sqlite3.connect("diary.db") as conn:
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
    return render_template("detail.html", entry=entry, formatted_date=formatted_date)


# 編集画面：既存の日記を編集
@app.route("/edit/<int:entry_id>", methods=["GET", "POST"])
def edit(entry_id):
    if request.method == "POST":
        # フォームからのデータを取得
        date = request.form["date"]
        content = request.form["content"]
        file = request.files.get("file")  # 画像または動画ファイル

        with sqlite3.connect("diary.db") as conn:
            cursor = conn.cursor()

            # 既存のエントリのファイル名を取得
            cursor.execute("SELECT filename FROM diary WHERE id=?", (entry_id,))
            existing_filename = cursor.fetchone()[0]

            # ファイル保存処理を共通関数にまとめる
            filename = save_file(file, default_filename=existing_filename)

            # データベースの更新処理
            cursor.execute(
                "UPDATE diary SET date=?, content=?, filename=? WHERE id=?",
                (date, content, filename, entry_id),
            )
            conn.commit()

        return redirect(url_for("detail", entry_id=entry_id))

    else:
        with sqlite3.connect("diary.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM diary WHERE id=?", (entry_id,))
            entry = cursor.fetchone()

        # エントリが見つからない場合
        if entry is None:
            return "日記が見つかりません", 404
        return render_template("add_or_edit.html", entry=entry)


# 日記の新規作成画面
@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        date = request.form["date"]
        content = request.form["content"]
        file = request.files.get("file")  # 画像または動画ファイル

        with sqlite3.connect("diary.db") as conn:
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
    return render_template("add_or_edit.html", entry=None)


# 日記データ削除処理
@app.route("/delete/<int:entry_id>", methods=["POST"])
def delete(entry_id):
    # データベース接続
    with sqlite3.connect("diary.db") as conn:
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
    app.run(debug=True, use_reloader=False)  # 本番環境では削除またはコメントアウト
