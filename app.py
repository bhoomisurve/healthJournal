from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from datetime import datetime, timedelta
import json
import re

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

# Database setup
DATABASE = 'health_journal.db'

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Symptoms table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS symptoms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                symptoms TEXT NOT NULL,
                severity INTEGER CHECK(severity >= 1 AND severity <= 10),
                notes TEXT,
                date_logged TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Health notes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS health_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()

# AI Symptom Checker Logic
class SymptomChecker:
    def __init__(self):
        self.symptom_rules = {
            'fever': {
                'causes': ['Common cold', 'Flu', 'Viral infection', 'Bacterial infection'],
                'severity': 'moderate',
                'advice': 'Monitor temperature, stay hydrated, rest. Consult doctor if fever persists >3 days or >101.5°F'
            },
            'headache': {
                'causes': ['Tension headache', 'Migraine', 'Dehydration', 'Stress', 'Sinus congestion'],
                'severity': 'mild-moderate',
                'advice': 'Rest in dark room, stay hydrated, consider over-the-counter pain relief. Seek medical attention for severe or persistent headaches'
            },
            'cough': {
                'causes': ['Common cold', 'Flu', 'Allergies', 'Bronchitis', 'Pneumonia'],
                'severity': 'mild-moderate',
                'advice': 'Stay hydrated, use humidifier, avoid irritants. Consult doctor if cough persists >2 weeks or produces blood'
            },
            'chest pain': {
                'causes': ['Muscle strain', 'Heartburn', 'Anxiety', 'Heart conditions', 'Lung issues'],
                'severity': 'high',
                'advice': 'SEEK IMMEDIATE MEDICAL ATTENTION if severe, crushing, or accompanied by shortness of breath, nausea, or sweating'
            },
            'shortness of breath': {
                'causes': ['Asthma', 'Anxiety', 'Heart conditions', 'Lung conditions', 'Anemia'],
                'severity': 'high',
                'advice': 'SEEK IMMEDIATE MEDICAL ATTENTION if severe or sudden onset. Monitor oxygen levels if possible'
            },
            'nausea': {
                'causes': ['Food poisoning', 'Stomach flu', 'Pregnancy', 'Medication side effects', 'Anxiety'],
                'severity': 'mild-moderate',
                'advice': 'Stay hydrated with small sips, eat bland foods, rest. Consult doctor if persistent vomiting or signs of dehydration'
            },
            'fatigue': {
                'causes': ['Lack of sleep', 'Stress', 'Anemia', 'Thyroid issues', 'Depression'],
                'severity': 'mild-moderate',
                'advice': 'Ensure adequate sleep, manage stress, maintain regular exercise. Consult doctor if persistent despite lifestyle changes'
            },
            'dizziness': {
                'causes': ['Dehydration', 'Low blood pressure', 'Inner ear problems', 'Medication side effects'],
                'severity': 'moderate',
                'advice': 'Sit or lie down immediately, stay hydrated. Seek medical attention if persistent or accompanied by other symptoms'
            }
        }
    
    def analyze_symptoms(self, symptoms_text, severity):
        symptoms_text = symptoms_text.lower()
        matches = []
        
        for symptom, data in self.symptom_rules.items():
            if symptom in symptoms_text or any(word in symptoms_text for word in symptom.split()):
                matches.append({
                    'symptom': symptom,
                    'data': data
                })
        
        if not matches:
            return {
                'message': 'No specific matches found for your symptoms.',
                'general_advice': 'Consider consulting with a healthcare provider for proper evaluation.',
                'severity_assessment': 'Unknown'
            }
        
        # Determine overall severity
        high_severity = any(match['data']['severity'] == 'high' for match in matches)
        
        result = {
            'matches': matches,
            'severity_assessment': 'High Priority' if high_severity else 'Moderate Priority',
            'general_advice': 'This is an AI-powered suggestion only. Always consult healthcare professionals for proper diagnosis and treatment.',
            'emergency_warning': high_severity
        }
        
        return result

# Initialize database
init_db()
symptom_checker = SymptomChecker()

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if not username or not email or not password:
            flash('All fields are required')
            return render_template('register.html')
        
        password_hash = generate_password_hash(password)
        
        try:
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                    (username, email, password_hash)
                )
                conn.commit()
                flash('Registration successful! Please login.')
                return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists')
            return render_template('register.html')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
            
            if user and check_password_hash(user[1], password):
                session['user_id'] = user[0]
                session['username'] = username
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        
        # Get recent symptoms
        cursor.execute('''
            SELECT symptoms, severity, notes, date_logged 
            FROM symptoms 
            WHERE user_id = ? 
            ORDER BY date_logged DESC 
            LIMIT 5
        ''', (user_id,))
        recent_symptoms = cursor.fetchall()
        
        # Get recent health notes
        cursor.execute('''
            SELECT title, content, date_created 
            FROM health_notes 
            WHERE user_id = ? 
            ORDER BY date_created DESC 
            LIMIT 5
        ''', (user_id,))
        recent_notes = cursor.fetchall()
    
    return render_template('dashboard.html', 
                         recent_symptoms=recent_symptoms, 
                         recent_notes=recent_notes)

@app.route('/log_symptoms', methods=['GET', 'POST'])
def log_symptoms():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        symptoms = request.form['symptoms']
        severity = int(request.form['severity'])
        notes = request.form.get('notes', '')
        
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO symptoms (user_id, symptoms, severity, notes) 
                VALUES (?, ?, ?, ?)
            ''', (session['user_id'], symptoms, severity, notes))
            conn.commit()
        
        flash('Symptoms logged successfully!')
        return redirect(url_for('dashboard'))
    
    return render_template('log_symptoms.html')

@app.route('/symptom_checker', methods=['GET', 'POST'])
def symptom_checker_route():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        symptoms = request.form['symptoms']
        severity = int(request.form['severity'])
        
        analysis = symptom_checker.analyze_symptoms(symptoms, severity)
        
        return render_template('symptom_checker.html', 
                             analysis=analysis, 
                             symptoms=symptoms, 
                             severity=severity)
    
    return render_template('symptom_checker.html')

@app.route('/health_journal')
def health_journal():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        
        # Get all symptoms with dates
        cursor.execute('''
            SELECT symptoms, severity, notes, date_logged 
            FROM symptoms 
            WHERE user_id = ? 
            ORDER BY date_logged DESC
        ''', (user_id,))
        symptoms = cursor.fetchall()
        
        # Get all health notes
        cursor.execute('''
            SELECT title, content, date_created 
            FROM health_notes 
            WHERE user_id = ? 
            ORDER BY date_created DESC
        ''', (user_id,))
        notes = cursor.fetchall()
    
    return render_template('health_journal.html', symptoms=symptoms, notes=notes)

@app.route('/add_note', methods=['GET', 'POST'])
def add_note():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO health_notes (user_id, title, content) 
                VALUES (?, ?, ?)
            ''', (session['user_id'], title, content))
            conn.commit()
        
        flash('Health note added successfully!')
        return redirect(url_for('health_journal'))
    
    return render_template('add_note.html')

@app.route('/export_journal')
def export_journal():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        
        # Get user info
        cursor.execute('SELECT username, email FROM users WHERE id = ?', (user_id,))
        user_info = cursor.fetchone()
        
        # Get all symptoms
        cursor.execute('''
            SELECT symptoms, severity, notes, date_logged 
            FROM symptoms 
            WHERE user_id = ? 
            ORDER BY date_logged DESC
        ''', (user_id,))
        symptoms = cursor.fetchall()
        
        # Get all health notes
        cursor.execute('''
            SELECT title, content, date_created 
            FROM health_notes 
            WHERE user_id = ? 
            ORDER BY date_created DESC
        ''', (user_id,))
        notes = cursor.fetchall()
    
    export_data = {
        'user_info': {
            'username': user_info[0],
            'email': user_info[1],
            'export_date': datetime.now().isoformat()
        },
        'symptoms': [
            {
                'symptoms': s[0],
                'severity': s[1],
                'notes': s[2],
                'date': s[3]
            } for s in symptoms
        ],
        'health_notes': [
            {
                'title': n[0],
                'content': n[1],
                'date': n[2]
            } for n in notes
        ]
    }
    
    return jsonify(export_data)

if __name__ == '__main__':
    app.run(debug=True)