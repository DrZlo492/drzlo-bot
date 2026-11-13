#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DRZLO SINGULARITY v9 - CODE REVIEW BUILD

КРИТИЧНО: /login в присланной версии
не проверял пароль вообще (любой
становился OWNER). Восстановлено.

Остальные правки см. в комментариях
"# FIX:" по тексту. Только stdlib
(+опционально cryptography).
Ширина строки: до 45 символов.
"""

import os
import json
import time
import math
import glob
import shutil
import signal
import random
import hashlib
import hmac
import logging
from logging.handlers import (
    RotatingFileHandler,
)
import sqlite3
import threading
import urllib.request as ureq
import urllib.parse as uparse


class ConsoleUI:
    C_RESET = "\033[0m"
    C_CYAN = "\033[96m"
    C_GREEN = "\033[92m"
    C_RED = "\033[91m"
    C_YEL = "\033[93m"

    def banner(self):
        print(self.C_CYAN)
        print("+--------------------+")
        print("| DRZLO SINGULARITY  |")
        print("|  REVIEWED BUILD v9 |")
        print("+--------------------+")
        print(self.C_RESET)

    def cyan(self, text):
        print(
            self.C_CYAN + text
            + self.C_RESET
        )

    def green(self, text):
        print(
            self.C_GREEN + text
            + self.C_RESET
        )

    def red(self, text):
        print(
            self.C_RED + text
            + self.C_RESET
        )

    def yellow(self, text):
        print(
            self.C_YEL + text
            + self.C_RESET
        )


class AppLogger:
    def __init__(
        self,
        path="drzlo_core.log",
        max_bytes=2_000_000,
        backups=5,
    ):
        path = os.path.join(
            os.getcwd(), path
        )
        self._log = (
            logging.getLogger(
                "drzlo"
            )
        )
        self._log.setLevel(
            logging.INFO
        )
        if not self._log.handlers:
            fh = RotatingFileHandler(
                path,
                maxBytes=max_bytes,
                backupCount=backups,
                encoding="utf-8",
            )
            fmt = logging.Formatter(
                "%(asctime)s "
                "%(levelname)s "
                "%(message)s"
            )
            fh.setFormatter(fmt)
            self._log.addHandler(
                fh
            )

    def info(self, msg):
        self._log.info(msg)

    def warning(self, msg):
        self._log.warning(msg)

    def error(self, msg):
        self._log.error(msg)


class CryptoHelper:
    def __init__(self):
        try:
            import cryptography.fernet as cf
            self._fernet = cf.Fernet
            self.secure = True
        except ImportError:
            self._fernet = None
            self.secure = False

    def make_key(self):
        if not self.secure:
            return None
        return (
            self._fernet.generate_key()
        )

    def encrypt(self, key, text):
        if not self.secure:
            return text
        box = self._fernet(key)
        out = box.encrypt(
            text.encode("utf-8")
        )
        return out.decode("utf-8")

    def decrypt(self, key, token):
        if not self.secure:
            return token
        box = self._fernet(key)
        raw = box.decrypt(
            token.encode("utf-8")
        )
        return raw.decode("utf-8")


class SecurityCore:
    ITERATIONS = 600000

    def hash_password(
        self, password, salt=None
    ):
        if salt is None:
            salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(
                "utf-8"
            ),
            salt,
            self.ITERATIONS,
        )
        return salt, digest

    def verify_password(
        self, password, salt,
        expected,
    ):
        _, digest = (
            self.hash_password(
                password, salt
            )
        )
        return hmac.compare_digest(
            digest, expected
        )


class Database:
    """FIX: путь явно через
    os.getcwd(), как и просили
    (функционально было тем же,
    но теперь явно)."""

    def __init__(
        self, path="drzlo.db"
    ):
        self.path = os.path.join(
            os.getcwd(), path
        )
        self._lock = (
            threading.RLock()
        )
        self._conn = sqlite3.connect(
            self.path,
            check_same_thread=False,
        )
        self._conn.execute(
            "PRAGMA "
            "journal_mode=WAL"
        )
        self._conn.execute(
            "PRAGMA "
            "busy_timeout=5000"
        )
        self._create_tables()

    def _create_tables(self):
        with self._lock:
            cur = self._conn
            cur.execute(
                "CREATE TABLE IF "
                "NOT EXISTS users "
                "(telegram_id "
                "INTEGER PRIMARY "
                "KEY, role TEXT, "
                "created_at TEXT, "
                "last_seen TEXT)"
            )
            cur.execute(
                "CREATE TABLE IF "
                "NOT EXISTS "
                "messages (id "
                "INTEGER PRIMARY "
                "KEY AUTOINCREMENT"
                ", telegram_id "
                "INTEGER, "
                "direction TEXT, "
                "text TEXT, "
                "ts TEXT)"
            )
            cur.execute(
                "CREATE TABLE IF "
                "NOT EXISTS signals"
                " (id INTEGER "
                "PRIMARY KEY "
                "AUTOINCREMENT, "
                "symbol TEXT, "
                "price REAL, "
                "rsi REAL, "
                "adx REAL, "
                "change_pct REAL, "
                "ts TEXT)"
            )
            cur.execute(
                "CREATE TABLE IF "
                "NOT EXISTS "
                "signal_history (id"
                " INTEGER PRIMARY"
                " KEY "
                "AUTOINCREMENT, "
                "symbol TEXT, "
                "signal_type TEXT,"
                " entry_price "
                "REAL, exit_price"
                " REAL, result "
                "TEXT, timestamp "
                "TEXT)"
            )
            self._conn.commit()

    def set_role(
        self, telegram_id, role
    ):
        now = self._now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO users"
                " (telegram_id, "
                "role, created_at"
                ", last_seen) "
                "VALUES (?,?,?,?)"
                " ON CONFLICT"
                "(telegram_id) DO"
                " UPDATE SET "
                "role=excluded."
                "role, last_seen="
                "excluded."
                "last_seen",
                (
                    telegram_id,
                    role, now, now,
                ),
            )
            self._conn.commit()

    def log_message(
        self, telegram_id,
        direction, text,
    ):
        with self._lock:
            self._conn.execute(
                "INSERT INTO "
                "messages "
                "(telegram_id, "
                "direction, text,"
                " ts) VALUES "
                "(?,?,?,?)",
                (
                    telegram_id,
                    direction, text,
                    self._now(),
                ),
            )
            self._conn.commit()

    def log_signal(self, sig):
        with self._lock:
            self._conn.execute(
                "INSERT INTO "
                "signals (symbol,"
                " price, rsi, "
                "adx, change_pct,"
                " ts) VALUES "
                "(?,?,?,?,?,?)",
                (
                    sig["symbol"],
                    sig["price"],
                    sig.get("rsi", 0),
                    sig.get("adx", 0),
                    sig.get(
                        "change_pct", 0
                    ),
                    self._now(),
                ),
            )
            self._conn.commit()

    def last_signals(self, limit=10):
        with self._lock:
            cur = self._conn.execute(
                "SELECT symbol, "
                "price, rsi, adx,"
                " change_pct, ts "
                "FROM signals "
                "ORDER BY id DESC"
                " LIMIT ?",
                (limit,),
            )
            return cur.fetchall()

    def open_signal(
        self, symbol, signal_type,
        entry_price,
    ):
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO "
                "signal_history "
                "(symbol, "
                "signal_type, "
                "entry_price, "
                "result, "
                "timestamp) "
                "VALUES "
                "(?,?,?,?,?)",
                (
                    symbol,
                    signal_type,
                    entry_price,
                    "PENDING",
                    self._now(),
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    def pending_signals(
        self, limit=50
    ):
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, "
                "symbol, "
                "signal_type, "
                "entry_price FROM"
                " signal_history "
                "WHERE "
                "result='PENDING'"
                " ORDER BY id ASC"
                " LIMIT ?",
                (limit,),
            )
            return cur.fetchall()

    def close_signal(
        self, row_id, exit_price,
        result,
    ):
        with self._lock:
            self._conn.execute(
                "UPDATE "
                "signal_history "
                "SET exit_price=?"
                ", result=? WHERE"
                " id=?",
                (
                    exit_price,
                    result, row_id,
                ),
            )
            self._conn.commit()

    def recent_results(
        self, limit=10
    ):
        with self._lock:
            cur = self._conn.execute(
                "SELECT result "
                "FROM "
                "signal_history "
                "WHERE result != "
                "'PENDING' ORDER"
                " BY id DESC "
                "LIMIT ?",
                (limit,),
            )
            return [
                r[0] for r in
                cur.fetchall()
            ]

    def last_signal_for_symbol(
        self, symbol
    ):
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, "
                "result, "
                "timestamp FROM "
                "signal_history "
                "WHERE symbol=? "
                "ORDER BY id DESC"
                " LIMIT 1",
                (symbol,),
            )
            return cur.fetchone()

    def signal_stats(self):
        with self._lock:
            cur = self._conn.execute(
                "SELECT result, "
                "COUNT(*) FROM "
                "signal_history "
                "GROUP BY result"
            )
            counts = dict(
                cur.fetchall()
            )
        wins = counts.get("WIN", 0)
        losses = counts.get(
            "LOSS", 0
        )
        pending = counts.get(
            "PENDING", 0
        )
        return {
            "total": (
                wins + losses
                + pending
            ),
            "wins": wins,
            "losses": losses,
            "pending": pending,
        }

    def close(self):
        with self._lock:
            self._conn.close()

    @staticmethod
    def _now():
        return time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )


class ConfigManager:
    SECRET_FIELDS = (
        "bot_token", "ai_api_key",
    )

    ENV_MAP = {
        "bot_token": (
            "DRZLO_BOT_TOKEN"
        ),
        "ai_api_key": (
            "DRZLO_AI_API_KEY"
        ),
        "ai_model": (
            "DRZLO_AI_MODEL"
        ),
        "owner_id": (
            "DRZLO_OWNER_ID"
        ),
    }

    TEMPLATE = {
        "bot_token": (
            "PUT_TELEGRAM_TOKEN"
        ),
        "owner_id": 0,
        "password_hash": "",
        "password_salt": "",
        "rsi_overbought": 70,
        "adx_threshold": 25,
        "price_change_pct": 2.0,
        "scan_interval_sec": 300,
        "ai_api_key": (
            "PUT_AI_API_KEY"
        ),
        "ai_model": (
            "llama-3.1-8b-instant"
        ),
        "win_rate": 0.0,
        "telegram_proxy": "",
    }

    def __init__(
        self,
        path="config.json",
        key_path="secret.key",
    ):
        self._path = os.path.join(
            os.getcwd(), path
        )
        self._lock = (
            threading.RLock()
        )
        self._crypto = CryptoHelper()
        self._key = self._load_key(
            os.path.join(
                os.getcwd(), key_path
            )
        )
        if not os.path.exists(
            self._path
        ):
            self._write_plain(
                dict(self.TEMPLATE)
            )
        self._data = self._read()
        self._data = (
            self._apply_env(
                self._data
            )
        )

    def _load_key(self, key_path):
        if not self._crypto.secure:
            return None
        if os.path.exists(key_path):
            with open(
                key_path, "rb"
            ) as fh:
                return fh.read()
        key = self._crypto.make_key()
        with open(
            key_path, "wb"
        ) as fh:
            fh.write(key)
        return key

    def _write_plain(self, data):
        tmp = self._path + ".tmp"
        with open(
            tmp, "w",
            encoding="utf-8",
        ) as fh:
            json.dump(
                data, fh,
                ensure_ascii=False,
                indent=2,
            )
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self._path)

    def _read(self):
        try:
            with open(
                self._path, "r",
                encoding="utf-8",
            ) as fh:
                raw = json.load(fh)
        except (
            json.JSONDecodeError,
            OSError,
        ):
            bad = (
                self._path
                + ".corrupt"
            )
            try:
                os.replace(
                    self._path, bad
                )
            except OSError:
                pass
            raw = dict(self.TEMPLATE)
            self._write_plain(raw)
        cr = self._crypto
        for field in (
            self.SECRET_FIELDS
        ):
            val = raw.get(field, "")
            if val and not (
                val.startswith(
                    "PUT_"
                )
            ):
                try:
                    raw[field] = (
                        cr.decrypt(
                            self._key,
                            val,
                        )
                    )
                except Exception:
                    pass
        return raw

    def _apply_env(self, data):
        for key, env_name in (
            self.ENV_MAP.items()
        ):
            val = os.environ.get(
                env_name
            )
            if val is None:
                continue
            if key == "owner_id":
                try:
                    val = int(val)
                except ValueError:
                    continue
            data[key] = val
        return data

    def _write(self, data):
        enc = dict(data)
        cr = self._crypto
        for field in (
            self.SECRET_FIELDS
        ):
            val = enc.get(field, "")
            if val and not (
                val.startswith(
                    "PUT_"
                )
            ):
                enc[field] = (
                    cr.encrypt(
                        self._key,
                        val,
                    )
                )
        self._write_plain(enc)

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(
                key, default
            )

    def set(self, key, value):
        with self._lock:
            self._data[key] = value
            self._write(self._data)


class TechnicalIndicators:
    @staticmethod
    def safe_float(
        value, default=0.0
    ):
        try:
            out = float(value)
        except (
            TypeError, ValueError,
        ):
            return default
        if math.isnan(out) or (
            math.isinf(out)
        ):
            return default
        return out

    @staticmethod
    def rsi(closes, period=14):
        if len(closes) <= period:
            return 50.0
        gains, losses = [], []
        for i in range(
            1, period + 1
        ):
            delta = (
                closes[i]
                - closes[i - 1]
            )
            gains.append(
                max(delta, 0.0)
            )
            losses.append(
                max(-delta, 0.0)
            )
        avg_gain = (
            sum(gains) / period
        )
        avg_loss = (
            sum(losses) / period
        )
        for i in range(
            period + 1, len(closes)
        ):
            delta = (
                closes[i]
                - closes[i - 1]
            )
            gain = max(delta, 0.0)
            loss = max(-delta, 0.0)
            avg_gain = (
                avg_gain
                * (period - 1)
                + gain
            ) / period
            avg_loss = (
                avg_loss
                * (period - 1)
                + loss
            ) / period
        if avg_gain == 0 and (
            avg_loss == 0
        ):
            return 50.0
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (
            100.0 / (1.0 + rs)
        )

    @staticmethod
    def adx(
        highs, lows, closes,
        period=14,
    ):
        n = len(closes)
        if n <= period + 1:
            return 0.0
        plus_dm = [0.0]
        minus_dm = [0.0]
        tr_list = [0.0]
        for i in range(1, n):
            up = (
                highs[i]
                - highs[i - 1]
            )
            down = (
                lows[i - 1]
                - lows[i]
            )
            pdm = (
                up if (
                    up > down
                    and up > 0
                ) else 0.0
            )
            mdm = (
                down if (
                    down > up
                    and down > 0
                ) else 0.0
            )
            plus_dm.append(pdm)
            minus_dm.append(mdm)
            tr = max(
                highs[i] - lows[i],
                abs(
                    highs[i]
                    - closes[i - 1]
                ),
                abs(
                    lows[i]
                    - closes[i - 1]
                ),
            )
            tr_list.append(tr)
        sm_tr = sum(
            tr_list[1:period + 1]
        )
        sm_pdm = sum(
            plus_dm[1:period + 1]
        )
        sm_mdm = sum(
            minus_dm[1:period + 1]
        )

        def _dx(s_tr, s_pdm, s_mdm):
            if s_tr == 0:
                return 0.0
            pdi = (
                100.0 * s_pdm / s_tr
            )
            mdi = (
                100.0 * s_mdm / s_tr
            )
            denom = pdi + mdi
            if denom == 0:
                return 0.0
            return (
                100.0
                * abs(pdi - mdi)
                / denom
            )

        dx_values = [
            _dx(sm_tr, sm_pdm, sm_mdm)
        ]
        for i in range(
            period + 1, n
        ):
            sm_tr = (
                sm_tr - sm_tr / period
                + tr_list[i]
            )
            sm_pdm = (
                sm_pdm
                - sm_pdm / period
                + plus_dm[i]
            )
            sm_mdm = (
                sm_mdm
                - sm_mdm / period
                + minus_dm[i]
            )
            dx_values.append(
                _dx(
                    sm_tr, sm_pdm,
                    sm_mdm,
                )
            )
        if len(dx_values) < period:
            return (
                sum(dx_values)
                / len(dx_values)
            )
        adx_val = (
            sum(dx_values[:period])
            / period
        )
        for i in range(
            period, len(dx_values)
        ):
            adx_val = (
                adx_val
                * (period - 1)
                + dx_values[i]
            ) / period
        return adx_val


class BinanceFuturesClient:
    """FIX: добавлен volumes() -
    раньше CryptoRadar лез в
    приватный _get() напрямую,
    снаружи класса."""

    BASE = "https://fapi.binance.com"
    DELAY = 0.25

    def _get(self, path, params=None):
        qs = ""
        if params:
            qs = "?" + (
                uparse.urlencode(
                    params
                )
            )
        url = self.BASE + path + qs
        req = ureq.Request(
            url,
            headers={
                "User-Agent": (
                    "drzlo/9.0"
                )
            },
        )
        with ureq.urlopen(
            req, timeout=10
        ) as resp:
            raw = resp.read()
        time.sleep(self.DELAY)
        return json.loads(raw)

    def ticker_24h(self):
        """Один общий запрос по
        всем символам сразу - из
        него же берутся объёмы и
        24ч изменение, без
        повторных запросов по
        одному символу."""
        return self._get(
            "/fapi/v1/ticker/24hr"
        )

    def top_symbols(
        self, tickers, n=20
    ):
        ti = TechnicalIndicators
        usdt = [
            d for d in tickers
            if str(
                d.get("symbol", "")
            ).endswith("USDT")
        ]

        def vol(d):
            return ti.safe_float(
                d.get("quoteVolume")
            )

        usdt.sort(
            key=vol, reverse=True
        )
        return usdt[:n]

    def klines(
        self, symbol,
        interval="15m", limit=100,
    ):
        data = self._get(
            "/fapi/v1/klines",
            {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            },
        )
        ti = TechnicalIndicators
        highs = [
            ti.safe_float(row[2])
            for row in data
        ]
        lows = [
            ti.safe_float(row[3])
            for row in data
        ]
        closes = [
            ti.safe_float(row[4])
            for row in data
        ]
        return highs, lows, closes

    def volumes(
        self, symbol,
        interval="5m", limit=12,
    ):
        data = self._get(
            "/fapi/v1/klines",
            {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            },
        )
        ti = TechnicalIndicators
        return [
            ti.safe_float(row[5])
            for row in data
        ]

    def last_price(self, symbol):
        data = self._get(
            "/fapi/v1/ticker/price",
            {"symbol": symbol},
        )
        ti = TechnicalIndicators
        return ti.safe_float(
            data.get("price")
        )


class AutoCleaner:
    """ВОССТАНОВЛЕНО: этого класса
    не было в присланном коде,
    хотя его явно просили не
    удалять. Поведение то же, что
    было раньше."""

    JUNK_FILES = (
        "config.json.txt",
        "config.json..txt",
        "test.py.txt",
        "drzlo_v8.py.txt",
    )

    def __init__(self, ui):
        self._ui = ui

    def clean(self):
        removed = 0
        removed += self._named()
        removed += self._glob(
            "*.tmp"
        )
        removed += self._glob(
            "*.bak"
        )
        removed += self._dirs()
        removed += self._glob(
            "drzlo_core.log.*"
        )
        removed += self._backups()
        self._report(removed)
        return removed

    def _named(self):
        n = 0
        for name in self.JUNK_FILES:
            if os.path.exists(name):
                try:
                    os.remove(name)
                    n += 1
                except OSError:
                    pass
        return n

    def _glob(self, pattern):
        n = 0
        for fp in glob.glob(pattern):
            try:
                os.remove(fp)
                n += 1
            except OSError:
                pass
        return n

    def _dirs(self):
        n = 0
        for name in (
            "__pycache__",
            ".ipynb_checkpoints",
        ):
            if os.path.isdir(name):
                try:
                    shutil.rmtree(
                        name
                    )
                    n += 1
                except OSError:
                    pass
        return n

    def _backups(self):
        n = 0
        for pattern in (
            "drzlo_core.db.*",
            "backup_*.db",
            "drzlo_backup_*.db",
        ):
            matches = glob.glob(
                pattern
            )
            matches.sort(
                key=os.path.getmtime,
                reverse=True,
            )
            for fp in matches[3:]:
                try:
                    os.remove(fp)
                    n += 1
                except OSError:
                    pass
        return n

    def _report(self, removed):
        if removed:
            self._ui.cyan(
                "\U0001F9F9 Очистка"
                " мусора: удалено "
                + str(removed)
                + " файлов/папок"
            )
        else:
            self._ui.cyan(
                "\U0001F9F9 Очистка"
                ": мусора не "
                "найдено"
            )


class SignalTracker(
    threading.Thread
):
    """FIX: добавлен
    is_on_cooldown() - метод в БД
    (last_signal_for_symbol) уже
    был, но раньше нигде не
    вызывался, т.е. кулдаун не
    работал вообще."""

    CHECK_SEC = 900
    TARGET_PCT = 1.5
    WINDOW = 10
    MIN_WIN_RATE = 0.4
    MAX_THRESHOLD = 60
    COOLDOWN_SEC = 3600

    def __init__(
        self, config, db, logger,
        client, stop_event,
    ):
        super().__init__(daemon=True)
        self._cfg = config
        self._db = db
        self._log = logger
        self._client = client
        self._stop_event = stop_event

    def is_on_cooldown(self, symbol):
        row = (
            self._db.
            last_signal_for_symbol(
                symbol
            )
        )
        if not row:
            return False
        _, _, ts = row
        try:
            last_t = time.mktime(
                time.strptime(
                    ts,
                    "%Y-%m-%d %H:%M:%S",
                )
            )
        except ValueError:
            return False
        return (
            time.time() - last_t
            < self.COOLDOWN_SEC
        )

    def run(self):
        while not (
            self._stop_event.is_set()
        ):
            try:
                self._check_pending()
                self._adapt_threshold()
            except Exception as exc:
                self._log.error(
                    "signal tracker: "
                    + str(exc)
                )
            self._stop_event.wait(
                self.CHECK_SEC
            )

    def _check_pending(self):
        rows = (
            self._db.
            pending_signals()
        )
        for row in rows:
            try:
                self._evaluate_one(
                    row
                )
            except Exception as exc:
                self._log.warning(
                    "tracker eval: "
                    + str(exc)
                )

    def _evaluate_one(self, row):
        row_id = row[0]
        symbol = row[1]
        sig_type = row[2]
        entry_price = row[3]
        if not entry_price:
            return
        price = (
            self._client.
            last_price(symbol)
        )
        change = (
            (price - entry_price)
            / entry_price * 100.0
        )
        if sig_type == "SHORT":
            change = -change
        if change >= self.TARGET_PCT:
            self._db.close_signal(
                row_id, price, "WIN"
            )
        elif change <= (
            -self.TARGET_PCT
        ):
            self._db.close_signal(
                row_id, price, "LOSS"
            )

    def _adapt_threshold(self):
        recent = (
            self._db.recent_results(
                self.WINDOW
            )
        )
        if len(recent) < self.WINDOW:
            return
        wins = recent.count("WIN")
        rate = wins / len(recent)
        self._cfg.set(
            "win_rate", rate
        )
        if rate < self.MIN_WIN_RATE:
            cur = self._cfg.get(
                "adx_threshold", 25
            )
            new_val = min(
                cur + 5,
                self.MAX_THRESHOLD,
            )
            if new_val != cur:
                self._cfg.set(
                    "adx_threshold",
                    new_val,
                )
                self._log.info(
                    "win_rate "
                    + "{:.0%}".format(
                        rate
                    )
                    + " < 40%, "
                    "adx_threshold"
                    " -> "
                    + str(new_val)
                )


class CryptoRadar:
    """FIX: раньше был отдельный
    global_alert_loop(), который
    параллельно (из второго
    потока) дёргал тот же
    HTTP-клиент и пере-запрашивал
    /ticker/24hr ПО ОДНОЙ монете
    (20 лишних запросов каждые
    5 мин), хотя эти же данные уже
    есть в общем запросе
    top_symbols(). Слито в один
    scan_once(), один поток, один
    клиент, без лишних запросов.
    + кулдаун через tracker."""

    ALERT_PCT = 5.0
    ALERT_COOLDOWN_SEC = 7200

    def __init__(
        self, config, db, logger,
        client=None, tracker=None,
        on_signal=None,
    ):
        self._cfg = config
        self._db = db
        self._log = logger
        self._client = (
            client
            or BinanceFuturesClient()
        )
        self._tracker = tracker
        self._on_signal = on_signal
        self._last_alert = {}

    def scan_once(self):
        triggered = []
        try:
            tickers = (
                self._client.
                ticker_24h()
            )
        except Exception as exc:
            self._log.warning(
                "radar ticker_24h: "
                + str(exc)
            )
            return triggered
        top = (
            self._client.top_symbols(
                tickers, 20
            )
        )
        for entry in top:
            symbol = entry.get(
                "symbol"
            )
            if not symbol:
                continue
            try:
                self._check_24h_alert(
                    symbol, entry
                )
            except Exception as exc:
                self._log.warning(
                    "radar alert "
                    + symbol + ": "
                    + str(exc)
                )
            try:
                sig = (
                    self._check_symbol(
                        symbol
                    )
                )
            except Exception as exc:
                self._log.warning(
                    "radar symbol "
                    + symbol + ": "
                    + str(exc)
                )
                continue
            if sig is not None:
                triggered.append(sig)
                self._db.log_signal(
                    sig
                )
                self._db.open_signal(
                    sig["symbol"],
                    sig[
                        "signal_type"
                    ],
                    sig["price"],
                )
                if self._on_signal:
                    self._on_signal(
                        sig
                    )
        return triggered

    def _check_24h_alert(
        self, symbol, entry
    ):
        ti = TechnicalIndicators
        chg = ti.safe_float(
            entry.get(
                "priceChangePercent"
            )
        )
        if abs(chg) < self.ALERT_PCT:
            return
        now = time.time()
        last = self._last_alert.get(
            symbol, 0
        )
        if now - last < (
            self.ALERT_COOLDOWN_SEC
        ):
            return
        self._last_alert[symbol] = (
            now
        )
        if self._on_signal:
            self._on_signal({
                "symbol": symbol,
                "signal_type": (
                    "24H_ALERT"
                ),
                "change_pct": chg,
                "price": (
                    ti.safe_float(
                        entry.get(
                            "lastPrice"
                        )
                    )
                ),
            })

    def _check_symbol(self, symbol):
        if (
            self._tracker is not None
            and self._tracker.
            is_on_cooldown(symbol)
        ):
            return None
        highs, lows, closes = (
            self._client.klines(
                symbol
            )
        )
        if len(closes) < 30:
            return None
        rsi_th = self._cfg.get(
            "rsi_overbought", 70
        )
        adx_th = self._cfg.get(
            "adx_threshold", 25
        )
        chg_th = self._cfg.get(
            "price_change_pct", 2.0
        )
        ti = TechnicalIndicators
        rsi_val = ti.rsi(closes)
        adx_val = ti.adx(
            highs, lows, closes
        )
        change = (
            (closes[-1] - closes[0])
            / closes[0] * 100.0
            if closes[0] else 0.0
        )
        is_long = (
            change > chg_th
            and rsi_val > rsi_th
            and adx_val > adx_th
        )
        is_short = (
            change < -chg_th
            and rsi_val
            < (100 - rsi_th)
            and adx_val > adx_th
        )
        if not (is_long or is_short):
            return None
        sig_type = (
            "LONG" if is_long
            else "SHORT"
        )
        if not self._mtf_confirms(
            symbol, sig_type
        ):
            return None
        if not self._volume_confirms(
            symbol
        ):
            return None
        return {
            "symbol": symbol,
            "price": closes[-1],
            "rsi": rsi_val,
            "adx": adx_val,
            "change_pct": change,
            "signal_type": sig_type,
        }

    def _mtf_confirms(
        self, symbol, sig_type
    ):
        try:
            _, _, closes_1h = (
                self._client.klines(
                    symbol, "1h", 50
                )
            )
        except Exception as exc:
            self._log.warning(
                "radar mtf "
                + symbol + ": "
                + str(exc)
            )
            return True
        if len(closes_1h) < 15:
            return True
        rsi_1h = (
            TechnicalIndicators.
            rsi(closes_1h)
        )
        if (
            sig_type == "LONG"
            and rsi_1h < 50
        ):
            return False
        if (
            sig_type == "SHORT"
            and rsi_1h > 50
        ):
            return False
        return True

    def _volume_confirms(
        self, symbol
    ):
        """FIX: гарантирован от
        ZeroDivisionError при <2
        свечей (раньше тихо
        ловилось широким except,
        теперь явная проверка)."""
        try:
            vols = (
                self._client.
                volumes(
                    symbol, "5m", 12
                )
            )
        except Exception as exc:
            self._log.warning(
                "radar volume "
                + symbol + ": "
                + str(exc)
            )
            return True
        if len(vols) < 2:
            return True
        history = vols[:-1]
        current = vols[-1]
        avg_hist = (
            sum(history)
            / len(history)
        )
        if avg_hist <= 0:
            return True
        return (
            current >= avg_hist * 1.5
        )

    def loop_forever(
        self, stop_event
    ):
        while not (
            stop_event.is_set()
        ):
            interval = self._cfg.get(
                "scan_interval_sec",
                300,
            )
            try:
                self.scan_once()
            except Exception as exc:
                self._log.error(
                    "radar loop: "
                    + str(exc)
                )
            stop_event.wait(interval)


class AICore:
    GROQ_URL = (
        "https://api.groq.com"
        "/openai/v1/chat/"
        "completions"
    )
    DEEPSEEK_URL = (
        "https://api.deepseek.com"
        "/chat/completions"
    )
    SYSTEM = (
        "Ты лаконичный ассистент "
        "внутри личного бота "
        "владельца, тон техно/"
        "киберпанк. Отвечай "
        "кратко и по делу."
    )
    MAX_IN = 1000
    MAX_OUT = 500

    def __init__(self, config, logger):
        self._cfg = config
        self._log = logger

    def _endpoint(self):
        model = self._cfg.get(
            "ai_model", ""
        ).lower()
        if "deepseek" in model:
            return self.DEEPSEEK_URL
        return self.GROQ_URL

    def ask(self, text):
        key = self._cfg.get(
            "ai_api_key", ""
        )
        if not key or (
            key.startswith("PUT_")
        ):
            return (
                "AI-ядро не "
                "настроено."
            )
        model = self._cfg.get(
            "ai_model",
            "llama-3.1-8b-instant",
        )
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        self.SYSTEM
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        text[
                            :self.MAX_IN
                        ]
                    ),
                },
            ],
            "max_tokens": 300,
            "temperature": 0.6,
        }
        body = json.dumps(
            payload
        ).encode("utf-8")
        req = ureq.Request(
            self._endpoint(),
            data=body,
            method="POST",
            headers={
                "Authorization": (
                    "Bearer " + key
                ),
                "Content-Type": (
                    "application/"
                    "json"
                ),
            },
        )
        try:
            with ureq.urlopen(
                req, timeout=20
            ) as resp:
                raw = resp.read()
            data = json.loads(raw)
            choices = data.get(
                "choices", []
            )
            if not choices:
                return (
                    "AI-ядро: "
                    "пустой ответ."
                )
            out = (
                choices[0]
                .get("message", {})
                .get("content", "")
            )
            return out[:self.MAX_OUT]
        except Exception as exc:
            self._log.warning(
                "AICore: " + str(exc)
            )
            return (
                "AI-ядро недоступно"
                " сейчас."
            )


class TelegramAdapter(
    threading.Thread
):
    """FIX (КРИТИЧНО): /login в
    присланном коде не проверял
    пароль вообще - любой
    написавший боту становился
    OWNER. Проверка восстановлена
    (PBKDF2 через SecurityCore),
    identity - user_id, как и
    просили.
    FIX: offset сдвигался ДО
    обработки апдейта - краш на
    обработке = апдейт терялся
    навсегда после рестарта.
    Теперь сдвигается в finally,
    после попытки обработки (один
    "ядовитый" апдейт не зависает
    навечно, но нормальный краш
    не теряет сообщения).
    FIX: жёсткий sleep(3) при
    ошибке опроса -> экспоненциальный
    бэкофф 3с..60с.
    Восстановлено: лок на перебор
    пароля, редакция токена из
    логов, fallback-лог при сбое
    отправки (всё это было в
    более ранней версии и исчезло
    в присланном коде)."""

    MAX_LOGIN_FAILS = 5
    LOGIN_LOCKOUT_SEC = 300
    MAX_OUT = 4000
    MAX_BACKOFF = 60

    def __init__(
        self, config, db, sec,
        logger, radar, stop_event,
        ai_core=None,
    ):
        super().__init__(daemon=True)
        self._cfg = config
        self._db = db
        self._sec = sec
        self._log = logger
        self._radar = radar
        self._stop_event = stop_event
        self._ai = ai_core
        self._offset = 0
        self._login_fails = {}
        self._started_at = time.time()

    def _get_opener(self):
        proxy = self._cfg.get(
            "telegram_proxy", ""
        )
        if not proxy:
            return ureq.build_opener()
        scheme = proxy.split(
            "://", 1
        )[0].lower()
        if scheme.startswith("socks"):
            self._log.warning(
                "telegram_proxy="
                + scheme + ":// - "
                "голый urllib не "
                "умеет SOCKS "
                "нативно (нужен "
                "сторонний PySocks"
                " или HTTP-мост "
                "перед Tor). Прокси"
                " НЕ применён."
            )
            return ureq.build_opener()
        handler = ureq.ProxyHandler(
            {
                "http": proxy,
                "https": proxy,
            }
        )
        return ureq.build_opener(
            handler
        )

    def _redact(self, text):
        token = self._cfg.get(
            "bot_token", ""
        )
        if token and token in text:
            return text.replace(
                token, "***"
            )
        return text

    def run(self):
        self._log.info(
            "telegram поток "
            "запущен"
        )
        token = self._cfg.get(
            "bot_token", ""
        ).strip()
        if not token or (
            "PUT_" in token
        ):
            self._log.warning(
                "telegram: токен "
                "не задан"
            )
            return
        base = (
            "https://api.telegram"
            ".org/bot" + token
        )
        opener = self._get_opener()
        backoff = 3
        while not (
            self._stop_event.
            is_set()
        ):
            try:
                updates = self._poll(
                    base, opener
                )
                backoff = 3
            except Exception as exc:
                self._log.error(
                    self._redact(
                        "telegram "
                        "poll: "
                        + str(exc)
                    )
                )
                self._stop_event.wait(
                    backoff
                )
                backoff = min(
                    backoff * 2,
                    self.MAX_BACKOFF,
                )
                continue
            for upd in updates:
                try:
                    self.\
                        _process_update(
                            base, upd,
                            opener,
                        )
                finally:
                    self._offset = (
                        upd[
                            "update_id"
                        ] + 1
                    )

    def _poll(self, base, opener):
        url = (
            base + "/getUpdates?"
            + uparse.urlencode(
                {
                    "timeout": 20,
                    "offset": (
                        self._offset
                    ),
                }
            )
        )
        with opener.open(
            url, timeout=25
        ) as resp:
            data = json.loads(
                resp.read()
            )
        return data.get("result", [])

    def _process_update(
        self, base, upd, opener
    ):
        msg = upd.get("message")
        if not msg:
            return
        chat_id = msg.get(
            "chat", {}
        ).get("id")
        user_id = msg.get(
            "from", {}
        ).get("id")
        chat_type = msg.get(
            "chat", {}
        ).get("type")
        text = msg.get("text", "")
        if not chat_id or not (
            user_id
        ):
            return
        is_login = (
            text.strip().lower()
            .startswith("/login")
        )
        log_text = (
            "/login [REDACTED]"
            if is_login else text
        )
        self._db.log_message(
            chat_id, "in", log_text
        )
        reply = self._dispatch(
            chat_id, user_id,
            chat_type, text,
        )
        if reply:
            try:
                opener.open(
                    base
                    + "/sendChatAction",
                    uparse.urlencode(
                        {
                            "chat_id": (
                                chat_id
                            ),
                            "action": (
                                "typing"
                            ),
                        }
                    ).encode("utf-8"),
                    timeout=10,
                )
            except Exception:
                pass
            time.sleep(
                random.uniform(
                    1.0, 2.5
                )
            )
            self._send(
                base, chat_id, reply,
                opener,
            )

    def _login_locked(self, user_id):
        hist = self._login_fails.get(
            user_id, []
        )
        now = time.time()
        hist = [
            t for t in hist
            if now - t
            < self.LOGIN_LOCKOUT_SEC
        ]
        self._login_fails[user_id] = (
            hist
        )
        return (
            len(hist)
            >= self.MAX_LOGIN_FAILS
        )

    def _do_login(self, user_id, text):
        if self._cfg.get(
            "owner_id"
        ) == user_id:
            return "Ты уже OWNER."
        if self._login_locked(
            user_id
        ):
            return (
                "Слишком много "
                "попыток. Жди "
                "5 минут."
            )
        parts = text.strip().split(
            " ", 1
        )
        if len(parts) < 2:
            return "Нужен пароль."
        salt_hex = self._cfg.get(
            "password_salt", ""
        )
        hash_hex = self._cfg.get(
            "password_hash", ""
        )
        if not salt_hex or (
            not hash_hex
        ):
            return (
                "Пароль ещё не "
                "настроен."
            )
        try:
            salt = bytes.fromhex(
                salt_hex
            )
            expected = (
                bytes.fromhex(
                    hash_hex
                )
            )
        except ValueError:
            return (
                "Конфиг пароля "
                "повреждён."
            )
        ok = (
            self._sec.
            verify_password(
                parts[1], salt,
                expected,
            )
        )
        if ok:
            self._cfg.set(
                "owner_id", user_id
            )
            self._login_fails.pop(
                user_id, None
            )
            return "Доступ разрешен."
        self._login_fails.setdefault(
            user_id, []
        ).append(time.time())
        return "Неверный пароль."

    def _dispatch(
        self, chat_id, user_id,
        chat_type, text,
    ):
        text = text[:2000]
        cmd = (
            text.strip()
            .split(" ")[0].lower()
        )
        owner_id = self._cfg.get(
            "owner_id", 0
        )
        if cmd == "/start":
            return "DRZLO v9 ONLINE"
        if cmd == "/login":
            if chat_type != (
                "private"
            ):
                return (
                    "/login только "
                    "в личном чате."
                )
            return self._do_login(
                user_id, text
            )
        if user_id != owner_id:
            return "Доступ запрещен."
        if cmd == "/status":
            rate = self._cfg.get(
                "win_rate", 0.0
            )
            adx_th = self._cfg.get(
                "adx_threshold", 25
            )
            return (
                "Система активна."
                "\nwin_rate: "
                + "{:.0%}".format(
                    rate
                )
                + "\nadx_threshold"
                ": " + str(adx_th)
            )
        if cmd == "/stats":
            return self._do_stats()
        if cmd == "/scan":
            res = (
                self._radar.
                scan_once()
            )
            if not res:
                return "Сигналов нет."
            lines = [
                s["symbol"] + " "
                + s["signal_type"]
                + " "
                + "{:.2f}".format(
                    s.get(
                        "change_pct",
                        0,
                    )
                ) + "%"
                for s in res
            ]
            return "\n".join(lines)
        known = (
            "/start", "/login",
            "/status", "/stats",
            "/scan",
        )
        if (
            cmd not in known
            and self._ai is not None
        ):
            return self._ai.ask(text)
        return (
            "Команды: /status, "
            "/stats, /scan"
        )

    def _do_stats(self):
        """Все 6 полей из ТЗ в
        одной команде (раньше было
        разбросано по /status и
        /stats, и нигде не было
        полного набора)."""
        stats = (
            self._db.signal_stats()
        )
        uptime_sec = int(
            time.time()
            - self._started_at
        )
        hrs = uptime_sec // 3600
        mins = (
            uptime_sec % 3600
        ) // 60
        rate = self._cfg.get(
            "win_rate", 0.0
        )
        adx_th = self._cfg.get(
            "adx_threshold", 25
        )
        return (
            "Uptime: " + str(hrs)
            + "h " + str(mins)
            + "m\n"
            "Total: "
            + str(stats["total"])
            + "\nWins: "
            + str(stats["wins"])
            + "\nLosses: "
            + str(stats["losses"])
            + "\nWin rate: "
            + "{:.0%}".format(rate)
            + "\nADX threshold: "
            + str(adx_th)
        )

    def _write_fallback(
        self, chat_id, text
    ):
        path = os.path.join(
            os.getcwd(),
            "signals_fallback.log",
        )
        try:
            with open(
                path, "a",
                encoding="utf-8",
            ) as fh:
                fh.write(
                    time.strftime(
                        "%Y-%m-%d "
                        "%H:%M:%S"
                    )
                    + " ["
                    + str(chat_id)
                    + "] "
                    + text.replace(
                        "\n", " "
                    )
                    + "\n"
                )
        except OSError:
            pass

    def _send(
        self, base, chat_id, text,
        opener,
    ):
        text = text[:self.MAX_OUT]
        try:
            body = (
                uparse.urlencode(
                    {
                        "chat_id": (
                            chat_id
                        ),
                        "text": text,
                    }
                ).encode("utf-8")
            )
            req = ureq.Request(
                base + "/sendMessage",
                data=body,
            )
            with opener.open(
                req, timeout=10
            ) as resp:
                resp.read()
        except Exception as exc:
            self._log.warning(
                self._redact(
                    "telegram send: "
                    + str(exc)
                )
            )
            self._write_fallback(
                chat_id, text
            )


class DrzloApp:
    """FIX: в присланном коде не
    было _ensure_password() нигде
    - без неё password_hash
    никогда не создаётся, и
    восстановленная проверка
    пароля всегда отвечала бы
    'не настроен'. Восстановлено
    (без input(), без хардкода -
    из DRZLO_OWNER_PASSWORD или
    генерируется и показывается
    один раз в консоль).
    Восстановлено: AutoCleaner,
    фоновый бэкап БД раз в 24ч
    (shutil.copy2, 3 последних)."""

    BACKUP_INTERVAL_SEC = 86400

    def __init__(self):
        self.ui = ConsoleUI()
        self.cleaner = AutoCleaner(
            self.ui
        )
        self.cleaner.clean()
        self.logger = AppLogger()
        self.config = ConfigManager()
        self.db = Database()
        self.security = SecurityCore()
        self.stop_event = (
            threading.Event()
        )
        self.binance = (
            BinanceFuturesClient()
        )
        # SignalTracker до CryptoRadar -
        # радару нужна ссылка на
        # трекер для кулдауна
        self.tracker = SignalTracker(
            self.config, self.db,
            self.logger, self.binance,
            self.stop_event,
        )
        self.radar = CryptoRadar(
            self.config, self.db,
            self.logger,
            client=self.binance,
            tracker=self.tracker,
            on_signal=(
                self._on_signal
            ),
        )
        self.ai = AICore(
            self.config, self.logger
        )
        self.telegram = (
            TelegramAdapter(
                self.config,
                self.db,
                self.security,
                self.logger,
                self.radar,
                self.stop_event,
                ai_core=self.ai,
            )
        )
        self.radar_thread = None
        self.backup_thread = None
        self._register_signals()

    def _register_signals(self):
        for name in (
            "SIGINT", "SIGTERM",
        ):
            num = getattr(
                signal, name, None
            )
            if num is None:
                continue
            try:
                signal.signal(
                    num, self._on_sig
                )
            except (
                ValueError, OSError,
                RuntimeError,
            ) as exc:
                self.logger.warning(
                    name
                    + " не "
                    "зарегистрирован:"
                    " " + str(exc)
                )

    def _on_sig(self, signum, frame):
        self.logger.info(
            "signal " + str(signum)
            + " -> остановка"
        )
        self.stop_event.set()

    def _ensure_password(self):
        if self.config.get(
            "password_hash", ""
        ):
            return
        env_pwd = os.environ.get(
            "DRZLO_OWNER_PASSWORD"
        )
        if env_pwd:
            pwd = env_pwd
            source = "env"
        else:
            pwd = (
                hashlib.sha256(
                    os.urandom(32)
                ).hexdigest()[:20]
            )
            source = "generated"
        sec = self.security
        salt, digest = (
            sec.hash_password(pwd)
        )
        self.config.set(
            "password_salt",
            salt.hex(),
        )
        self.config.set(
            "password_hash",
            digest.hex(),
        )
        self.logger.info(
            "owner password set "
            "(" + source + ")"
        )
        if source == "generated":
            self.ui.yellow(
                "Пароль владельца "
                "сгенерирован "
                "(сохрани, "
                "показывается один"
                " раз):"
            )
            self.ui.green(pwd)

    def _on_signal(self, sig):
        kind = sig.get(
            "signal_type", "?"
        )
        text = (
            kind + " "
            + sig["symbol"] + " "
            + "{:.2f}".format(
                sig.get(
                    "change_pct", 0
                )
            ) + "%"
        )
        self.logger.info(text)
        threading.Thread(
            target=(
                self._send_signal_tg
            ),
            args=(text,),
            daemon=True,
        ).start()

    def _send_signal_tg(self, text):
        """FIX: раньше слал через
        голый ureq.urlopen в обход
        настроенного прокси -
        теперь через тот же
        opener, что и остальной
        telegram-трафик."""
        token = self.config.get(
            "bot_token", ""
        )
        owner = self.config.get(
            "owner_id", 0
        )
        if not token or not owner:
            return
        try:
            base = (
                "https://api."
                "telegram.org/bot"
                + token
            )
            opener = (
                self.telegram.
                _get_opener()
            )
            body = (
                uparse.urlencode(
                    {
                        "chat_id": (
                            owner
                        ),
                        "text": text,
                    }
                ).encode("utf-8")
            )
            req = ureq.Request(
                base + "/sendMessage",
                data=body,
            )
            with opener.open(
                req, timeout=10
            ) as resp:
                resp.read()
        except Exception as exc:
            self.logger.warning(
                "signal tg send: "
                + str(exc)
            )
            self.telegram.\
                _write_fallback(
                    owner, text
                )

    def _backup_loop(self):
        while not (
            self.stop_event.is_set()
        ):
            try:
                self._do_backup()
            except Exception as exc:
                self.logger.error(
                    "backup: "
                    + str(exc)
                )
            self.stop_event.wait(
                self.BACKUP_INTERVAL_SEC
            )

    def _do_backup(self):
        src = self.db.path
        if not os.path.exists(src):
            return
        ts = time.strftime(
            "%Y%m%d_%H%M%S"
        )
        dest = os.path.join(
            os.getcwd(),
            "drzlo_backup_" + ts
            + ".db",
        )
        shutil.copy2(src, dest)
        self.logger.info(
            "backup created: "
            + dest
        )
        backups = sorted(
            glob.glob(
                os.path.join(
                    os.getcwd(),
                    "drzlo_backup_"
                    "*.db",
                )
            ),
            key=os.path.getmtime,
            reverse=True,
        )
        for old in backups[3:]:
            try:
                os.remove(old)
            except OSError:
                pass

    def run(self):
        self.ui.banner()
        self._ensure_password()
        self.telegram.start()
        self.tracker.start()
        radar_t = threading.Thread(
            target=(
                self.radar.
                loop_forever
            ),
            args=(self.stop_event,),
            daemon=True,
        )
        radar_t.start()
        self.radar_thread = radar_t
        backup_t = threading.Thread(
            target=self._backup_loop,
            daemon=True,
        )
        backup_t.start()
        self.backup_thread = backup_t
        self.ui.green(
            "Система запущена "
            "(24/7)."
        )
        try:
            while not (
                self.stop_event.
                is_set()
            ):
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop_event.set()
        self.ui.yellow(
            "Остановка..."
        )
        self.telegram.join(
            timeout=5
        )
        self.tracker.join(
            timeout=5
        )
        radar_t.join(timeout=5)
        backup_t.join(timeout=5)
        self.db.close()
        self.ui.red("Завершено.")


if __name__ == "__main__":
    app = DrzloApp()
    app.run()
