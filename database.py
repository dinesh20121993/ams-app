import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'ams.db')

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            mobile      TEXT    NOT NULL UNIQUE,
            email       TEXT,
            gender      TEXT,
            course_name TEXT,
            batch_name  TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_name TEXT,
            date         DATE,
            start_time   TIMESTAMP,
            end_time     TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            student_mobile TEXT      NOT NULL,
            session_id     INTEGER   NOT NULL,
            timestamp      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_mobile, session_id),
            FOREIGN KEY (student_mobile) REFERENCES students(mobile),
            FOREIGN KEY (session_id)     REFERENCES sessions(id)
        )
    ''')

    conn.commit()
    conn.close()
