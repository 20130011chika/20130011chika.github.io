import sqlite3

# Connect to your SQLite database
conn = sqlite3.connect('diary.db')

# Create a cursor object
cursor = conn.cursor()

# Execute a query to get the schema of the 'diary' table
cursor.execute("PRAGMA table_info(diary)")

# Fetch and display the schema information
schema = cursor.fetchall()
for column in schema:
    print(column)

# Close the database connection
conn.close()
