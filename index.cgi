#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

import os
import cgitb
import logging
from app import app, init_db  # init_dbをインポート

cgitb.enable()  # デバッグ出力の有効化

# 必須のContent-Typeヘッダーを追加
print("Content-Type: text/html\n")

# ロギングの設定
logging.basicConfig(filename="/home/tani-chika/logs/app_debug.log", level=logging.DEBUG)

# 環境変数の設定を手動で追加
os.environ["IS_PRODUCTION"] = "1"
os.environ["FLASK_SECRET_KEY"] = "somerandomlygeneratedstringthatisverylongandsecure"

# 環境変数の確認をログに出力
logging.debug(f"INDXCGI IS_PRODUCTION={os.getenv('IS_PRODUCTION')}")

if __name__ == "__main__":
    init_db()
    from wsgiref.handlers import CGIHandler
    CGIHandler().run(app)
