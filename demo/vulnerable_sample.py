# Sample vulnerable code for ALPHA CodeGuard AI demonstration
# This code contains intentional security and bug issues for demo purposes

import sqlite3
import os
import subprocess

def get_user_data(username):
    """Fetch user data from database - VULNERABLE to SQL injection"""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    # SQL Injection vulnerability
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    result = cursor.fetchall()
    conn.close()
    return result

def run_command(user_input):
    """Execute system command - VULNERABLE to command injection"""
    # Command injection vulnerability
    os.system("ping -c 1 " + user_input)

def read_file(filename):
    """Read file - VULNERABLE to path traversal"""
    # Path traversal vulnerability
    with open("/var/www/files/" + filename, 'r') as f:
        return f.read()

def divide_numbers(a, b):
    """Divide two numbers - BUG: No division by zero check"""
    # Division by zero bug
    return a / b

def process_data(items):
    """Process data inefficiently - PERFORMANCE issue"""
    result = []
    for i in range(len(items)):  # Inefficient
        for j in range(len(items)):  # O(n^2) when not needed
            if items[i] == items[j]:
                result.append(items[i])
    return result

# Hardcoded credentials - SECURITY issue
API_KEY = "sk_live_1234567890abcdef"
PASSWORD = "admin123"
